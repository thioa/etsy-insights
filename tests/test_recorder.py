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
