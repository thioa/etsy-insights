import json
import ssl
import subprocess
from datetime import date

import pytest

from etsy_insights.advisor_ai import (
    MODEL, AdvisorAI, ClaudeBadAnswer, ClaudeBusy, ClaudeCertificateProblem, ClaudeCutOff, ClaudeRefused,
    ClaudeRequestFailed, ClaudeUnreachable, KeyRejected, NoModelAccess, TrendResult, cost_cents)
from etsy_insights.advisor_brief import AnalysisInput, TrendInput
from etsy_insights.advisor_store import Source, Usage
from tests.anthropic_fake import (
    DROP, FakeAnthropic, Json, Sse, Truncated, error_body, error_event, fallback_block, message_events, search_blocks,
    stream, text_block)

KEY = "sk-ant-test-key-123456"
TREND_INPUT = TrendInput(date(2026, 11, 11), ("Mugs", "Tumblers"), ("custom mug", "dog mom sweatshirt"))
ANALYSIS_INPUT = AnalysisInput({"context": {"today": "2026-11-11"}, "keywords": [{"keyword": "custom mug"}]},
                               ("mug", "tumbler"), 1, 2)
ANSWER = {"summary": "Mugs look strong.", "recommendations": [], "keyword_ideas": []}
MESSAGES = "/v1/messages"


@pytest.fixture
def fake():
    with FakeAnthropic() as server:
        yield server


def _ai(fake, **kwargs):
    return AdvisorAI(KEY, base_url=fake.url, trust_env=False, max_retries=0, **kwargs)


def test_test_key(fake):
    ai = _ai(fake)
    ai.test_key()
    path = f"/v1/models/{MODEL}"
    for response, error in ((Json(401, error_body("authentication_error", "invalid x-api-key")), KeyRejected),
                            (Json(403, error_body("permission_error", "no")), NoModelAccess),
                            (Json(404, error_body("not_found_error", "no")), NoModelAccess),
                            (DROP, ClaudeUnreachable)):
        fake.queue("GET", path, response)
        with pytest.raises(error):
            ai.test_key()


def test_check_trends_request_and_sources(fake):
    blocks = search_blocks("etsy gift trends", [("https://a.example/1", "A"), ("https://b.example/2", "B")])
    blocks.append(text_block("- Valentine's Day: list mugs by Jan 15.", citations=[
        ("https://a.example/1", "A"), ("https://a.example/1", "A again"), ("javascript:alert(1)", "bad"),
        ("https://b.example/2", "B")]))
    fake.queue("POST", MESSAGES, stream(blocks, web_searches=1))
    result = _ai(fake).check_trends(TREND_INPUT)
    assert "Valentine's Day" in result.note
    assert result.sources == (Source("S1", "https://a.example/1", "A"), Source("S2", "https://b.example/2", "B"))
    assert result.usage.web_searches == 1 and result.usage.input_tokens == 1000 and result.usage.output_tokens == 500
    request = fake.messages()[0]
    body = request["body"]
    assert body["model"] == "claude-opus-5-5" and body["max_tokens"] == 32000
    assert body["thinking"] == {"type": "adaptive"} and body["output_config"] == {"effort": "medium"}
    assert body["tools"] == [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5,
                              "user_location": {"type": "approximate", "country": "US"}}]
    assert body["fallbacks"] == "default" and body["stream"] is True
    beta = {k.lower(): v for k, v in request["headers"].items()}["anthropic-beta"]
    assert "server-side-fallback-2026-07-01" in beta
    user = json.dumps(body["messages"])
    assert "Mugs" in user and "Tumblers" in user and "2026-11-11" in user and "custom mug" in user
    assert KEY not in json.dumps(body)


def test_sources_from_search_results(fake):
    results = [(f"https://site{i}.example/", f"Site {i}") for i in range(12)] + [("ftp://x.example/", "ftp")]
    fake.queue("POST", MESSAGES, stream(search_blocks("q", results) + [text_block("- A trend.")]))
    sources = _ai(fake).check_trends(TREND_INPUT).sources
    assert len(sources) == 10 and sources[0] == Source("S1", "https://site0.example/", "Site 0")
    assert all(s.url.startswith("https://") for s in sources)


def test_pause_turn_continues(fake):
    fake.queue("POST", MESSAGES, stream(search_blocks("q", [("https://a.example/", "A")]), stop_reason="pause_turn"),
               stream([text_block("- Done.")]))
    result = _ai(fake).check_trends(TREND_INPUT)
    assert result.note == "- Done." and result.usage.input_tokens == 2000
    requests = fake.messages()
    assert len(requests) == 2
    second = requests[1]["body"]["messages"]
    assert len(second) == 2 and second[1]["role"] == "assistant"
    assert [b["type"] for b in second[1]["content"]] == ["server_tool_use", "web_search_tool_result"]


def test_pause_turn_gives_up_after_three_continues(fake):
    for _ in range(4):
        fake.queue("POST", MESSAGES, stream([text_block("part ")], stop_reason="pause_turn"))
    with pytest.raises(ClaudeCutOff) as caught:
        _ai(fake).check_trends(TREND_INPUT)
    assert len(fake.messages()) == 4 and caught.value.usage.input_tokens == 4000


def test_analyze_request_and_parse(fake):
    fake.queue("POST", MESSAGES, stream([text_block(json.dumps(ANSWER))], input_tokens=20_000, output_tokens=3_000))
    trend = TrendResult("- Valentine's Day soon.", (Source("S1", "https://a.example/1", "A"),), Usage())
    result = _ai(fake).analyze(ANALYSIS_INPUT, trend)
    assert result.data == ANSWER and result.model == "claude-opus-5-5"
    assert result.usage == Usage(20_000, 3_000, 0, cost_cents(MODEL, 20_000, 3_000, 0))
    body = fake.messages()[0]["body"]
    assert body["max_tokens"] == 64000 and body["output_config"]["effort"] == "high"
    schema = body["output_config"]["format"]["schema"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert schema["properties"]["recommendations"]["items"]["properties"]["category"]["enum"] == ["mug", "tumbler"]
    assert schema["properties"]["keyword_ideas"]["items"]["properties"]["kind"]["enum"] == [
        "from_data", "season", "trend", "new_niche"]
    assert "tools" not in body and body["fallbacks"] == "default"
    user = body["messages"][0]["content"]
    assert "<shop_data>" in user and "custom mug" in user and "S1: A — https://a.example/1" in user


def test_analyze_without_trend_notes(fake):
    fake.queue("POST", MESSAGES, stream([text_block(json.dumps(ANSWER))]))
    _ai(fake).analyze(ANALYSIS_INPUT, None)
    assert "No trend notes" in fake.messages()[0]["body"]["messages"][0]["content"]


def test_analyze_bad_answers(fake):
    fake.queue("POST", MESSAGES, stream([text_block("Sorry, here are some thoughts.")]),
               stream([text_block(json.dumps({"summary": "x", "recommendations": []}))]))
    ai = _ai(fake)
    for _ in range(2):
        with pytest.raises(ClaudeBadAnswer):
            ai.analyze(ANALYSIS_INPUT, None)


def test_stop_reasons_keep_usage(fake):
    fake.queue("POST", MESSAGES, stream([text_block("")], stop_reason="refusal"),
               stream([text_block("{\"summary\": ")], stop_reason="max_tokens"))
    ai = _ai(fake)
    with pytest.raises(ClaudeRefused) as refused:
        ai.analyze(ANALYSIS_INPUT, None)
    assert refused.value.usage.output_tokens == 500 and refused.value.usage.cost_cents > 0
    with pytest.raises(ClaudeCutOff):
        ai.analyze(ANALYSIS_INPUT, None)


def test_error_mapping(fake):
    ai = _ai(fake)
    cases = [
        (Json(400, error_body("invalid_request_error", "Your credit balance is too low to access the Anthropic API.")),
         ClaudeRequestFailed, "credit balance"),
        (Json(429, error_body("rate_limit_error", "Number of requests has exceeded your rate limit")), ClaudeBusy,
         "exceeded your rate limit"),
        (Json(500, error_body("api_error", "Internal server error")), ClaudeBusy, "Claude is busy"),
        (Json(529, error_body("overloaded_error", "Overloaded")), ClaudeBusy, "Claude is busy"),
        (Sse(message_events([])[:1] + [error_event("overloaded_error", "Overloaded")]), ClaudeBusy, "Claude is busy"),
        (Json(401, error_body("authentication_error", "invalid x-api-key")), KeyRejected, "rejected this API key"),
        (Json(400, error_body("invalid_request_error", f"bad key {KEY} here")), ClaudeRequestFailed, "bad key"),
        (DROP, ClaudeUnreachable, "Could not reach Anthropic"),
    ]
    for response, error, text in cases:
        fake.queue("POST", MESSAGES, response)
        with pytest.raises(error) as caught:
            ai.check_trends(TREND_INPUT)
        assert text in caught.value.message
        assert KEY not in caught.value.message and "sk-ant-" not in caught.value.message


def test_certificate_problem(tmp_path):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "2", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, capture_output=True)
    with FakeAnthropic(tls=(cert, key)) as fake:
        with pytest.raises(ClaudeCertificateProblem) as caught:
            _ai(fake).test_key()
        assert "certificate" in caught.value.message
        _ai(fake, ssl_context=ssl.create_default_context(cafile=str(cert))).test_key()


def test_cost_cents():
    assert cost_cents("claude-opus-5-5", 1_000_000, 100_000, 2) == 602
    assert cost_cents("claude-x", 1_000_000, 100_000, 2) == 752
    assert cost_cents(MODEL, 1, 0, 0) == 1
    assert cost_cents(MODEL, 0, 0, 0) == 0


def test_stream_cut_mid_way(fake):
    fake.queue("POST", MESSAGES, Truncated(message_events([text_block("- partial note")])[:4]))
    with pytest.raises(ClaudeUnreachable):
        _ai(fake).check_trends(TREND_INPUT)


def test_stream_without_stop_is_cut_off(fake):
    fake.queue("POST", MESSAGES, Sse(message_events([text_block("- partial note")])[:-2]))
    with pytest.raises(ClaudeCutOff):
        _ai(fake).check_trends(TREND_INPUT)


def test_fallback_answer_uses_text_after_fallback(fake):
    fake.queue("POST", MESSAGES,
               stream([text_block('{"summary": "I was'), fallback_block(), text_block(json.dumps(ANSWER))],
                      model="claude-opus-4-8"),
               stream([text_block("- Declined model's words."), fallback_block(),
                       text_block("- Valentine's Day soon.")], model="claude-opus-4-8"))
    ai = _ai(fake)
    result = ai.analyze(ANALYSIS_INPUT, None)
    assert result.data == ANSWER and result.model == "claude-opus-4-8"
    assert result.usage.cost_cents == cost_cents("claude-opus-4-8", 1000, 500, 0)
    assert ai.check_trends(TREND_INPUT).note == "- Valentine's Day soon."
