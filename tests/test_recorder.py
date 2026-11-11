import base64
import json

from etsy_insights.recorder import MAX_BODY_CHARS, REDACTED, Recording, redact, redact_html
from tests.helpers import T0


def test_redact_nested():
    out = redact({"user": {"email": "a@b.com", "name": "Toko"}, "csrf_nonce": "abc",
                  "items": [{"auth_token": "t", "q": "boho"}], "Session_ID": 5, "_nnc": "n"})
    assert out == {"user": {"email": REDACTED, "name": "Toko"}, "csrf_nonce": REDACTED,
                   "items": [{"auth_token": REDACTED, "q": "boho"}], "Session_ID": REDACTED, "_nnc": REDACTED}


def test_redact_html():
    html = ('<meta name="csrf_nonce" content="abc123"><input type="hidden" name="_nnc" value="v9">'
            '<p>hubungi saya@toko.com</p><script>{"api_token":"zzz","keyword":"boho"}</script>'
            '<input name="search_query" value="boho">')
    out = redact_html(html)
    for secret in ("abc123", "v9", "saya@toko.com", "zzz"):
        assert secret not in out
    assert '"keyword":"boho"' in out and 'name="search_query" value="boho"' in out


def test_add_response_filters():
    r = Recording(T0)
    assert r.add_response("https://www.etsy.com/api/v3/ajax/x", 200, "application/json", '{"q":"boho","csrf":"1"}', T0)
    assert r.add_response("https://api.etsy.com/v3/y", 200, "application/json; charset=utf-8", "[1]", T0)
    assert not r.add_response("https://notetsy.com/a", 200, "application/json", "{}", T0)
    assert not r.add_response("https://www.etsy.com/page", 200, "text/html", "<html>", T0)
    assert not r.add_response("https://www.google-analytics.com/c", 200, "application/json", "{}", T0)
    assert r.responses[0]["body"] == {"q": "boho", "csrf": REDACTED} and len(r.responses) == 2


def test_large_body_truncated():
    r = Recording(T0)
    r.add_response("https://www.etsy.com/x", 200, "application/json", "[" + "1," * MAX_BODY_CHARS + "1]", T0)
    body = r.responses[0]["body"]
    assert isinstance(body, str) and body.endswith("...[TERPOTONG]") and len(body) <= MAX_BODY_CHARS + 20


def test_save_roundtrip(tmp_path):
    r = Recording(T0)
    r.add_snapshot("https://www.etsy.com/your/shops/me/marketplace-insights", "<p>a@b.co</p>", b"\x89PNG", T0)
    path = r.save(tmp_path)
    assert path.name == "kenali-20261111-1000.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "etsy-insights-kenali/1" and "a@b.co" not in data["snapshots"][0]["html"]
    assert base64.b64decode(data["snapshots"][0]["screenshot_png_base64"]) == b"\x89PNG"


def test_url_query_secrets_redacted():
    r = Recording(T0)
    r.add_response("https://www.etsy.com/api/x?keyword=boho&_nnc=abc123", 200, "application/json", "{}", T0)
    url = r.responses[0]["url"]
    assert "keyword=boho" in url and "abc123" not in url


def test_redact_scans_string_values():
    out = redact({"html": '<input type=hidden name="_nnc" value="NNC_SECRET">', "owner": "seller@toko.com",
                  "payload": '{"csrf_token":"TOK"}', "fields": [{"name": "csrf_nonce", "value": "X"}], "q": "boho"})
    dumped = json.dumps(out)
    for secret in ("NNC_SECRET", "seller@toko.com", "TOK", '"X"'):
        assert secret not in dumped
    assert out["q"] == "boho"


def test_redact_html_more_patterns():
    html = ('<a href="/logout.php?ref=x&amp;_nnc=Q1">x</a><img src="https://i.etsy.com/a.png?auth_token=Q2">'
            '<div data-csrf-nonce="Q3" data-listing="ok"></div>'
            '<div data-state="{&quot;api_token&quot;:&quot;Q4&quot;,&quot;q&quot;:&quot;boho&quot;}"></div>')
    out = redact_html(html)
    for secret in ("Q1", "Q2", "Q3", "Q4"):
        assert secret not in out
    assert 'data-listing="ok"' in out and "&quot;q&quot;:&quot;boho&quot;" in out and "ref=x" in out


def test_url_fragment_secrets_redacted():
    r = Recording(T0)
    r.add_response("https://www.etsy.com/cb#access_token=Z9&state=ok", 200, "application/json", "{}", T0)
    assert "Z9" not in r.responses[0]["url"] and "state=ok" in r.responses[0]["url"]


def test_redact_html_is_fast_on_long_tokens():
    import time
    start = time.perf_counter()
    redact_html("a" * 60_000)
    assert time.perf_counter() - start < 1.0


def test_redact_html_object_under_sensitive_key():
    out = redact_html('<script>window.s = {"auth":{"bearer":"Q5"},"q":"boho"};</script>')
    assert "Q5" not in out and '"q":"boho"' in out


FAKE_JWT = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImFAYi5jbyIsIm5hbWUiOiJYIn0.c2lnbmF0dXJlX2hlcmVfMTIz"


def test_jwt_under_unlisted_key_is_redacted():
    html = '<script>window.c = "{\\"zd_messaging_JWT_key\\":\\"' + FAKE_JWT + '\\",\\"q\\":\\"boho\\"}";</script>'
    out = redact_html(html)
    assert FAKE_JWT not in out and "eyJ" not in out and '\\"q\\":\\"boho\\"' in out
    assert redact({"widget": {"credential": FAKE_JWT}})["widget"]["credential"] == REDACTED
