import dataclasses
import json
from pathlib import Path

import pytest

from etsy_insights.models import CapturedResponse, EtsyQuota, ParseError, RawResult, RelatedKeyword
from etsy_insights.parser import parse_search, related_rows_for

FIX = Path(__file__).parent / "fixtures"


def load_raw(name, keyword=None):
    d = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    return RawResult(keyword or d["keyword"], d["page_url"],
                     tuple(CapturedResponse(r["url"], r["status"], r["body"]) for r in d["responses"]), "")


def test_parse_sweatshirt_main_metrics():
    p = parse_search(load_raw("sweatshirt"))
    m = p.main
    assert (m.has_data, m.search_volume, m.competition_value, m.competition_kind, m.conversion_level) == \
        (True, 46395, 1863632, "count", 0)
    assert m.conversion_rate == pytest.approx(0.00014224041690609525) and m.wow_pct == 22.7
    assert len(m.trend) == 30 and (m.trend[0], m.trend[-1]) == (1194, 1949)
    assert p.quota == EtsyQuota(15, 15, 5, False, True) and not p.quota.exhausted


def test_parse_sweatshirt_ignores_stale_poll():
    p = parse_search(load_raw("sweatshirt"))
    assert len(p.related) == 180 and p.related[1].keyword == "gift for him"  # dari enqueue, bukan poll 'swearshirt'


def test_parse_personalized_uses_cached_enqueue():
    p = parse_search(load_raw("personalized"))
    assert p.main.search_volume == 67930 and len(p.related) == 130
    assert p.related[0] == RelatedKeyword("personalized gifts", 113851, 1816694, 1)


def test_parse_custom_uses_matching_poll():
    p = parse_search(load_raw("custom"))
    assert len(p.related) == 180 and p.related[0] == RelatedKeyword("personalized gift", 257361, 712366, 0)
    assert p.main.related[0] == "personalized gift"


def test_parse_typo_has_no_data_but_related():
    p = parse_search(load_raw("swearshirt"))
    assert (p.main.has_data, p.main.search_volume, p.main.conversion_level) == (False, 0, None)
    assert [r.keyword for r in p.related[:2]] == ["gift for her", "craft supplies"]


def test_quota_exhausted_variants():
    raw = load_raw("sweatshirt")

    def with_body(change):
        responses = []
        for r in raw.responses:
            body = r.body
            if isinstance(body, dict) and "stats" in body:
                body = json.loads(json.dumps(body))
                change(body)
            responses.append(CapturedResponse(r.url, r.status, body))
        return dataclasses.replace(raw, responses=tuple(responses))
    assert parse_search(with_body(lambda b: b["quotaData"].update(remainingQuota=5))).quota.exhausted
    assert parse_search(with_body(lambda b: b.update(isSearchAllowed=False))).quota.exhausted


def test_missing_or_other_keyword_raises_parse_error():
    with pytest.raises(ParseError):
        parse_search(load_raw("sweatshirt", keyword="hoodie"))
    raw = load_raw("custom")
    with pytest.raises(ParseError):
        parse_search(dataclasses.replace(raw, responses=tuple(r for r in raw.responses if "results-data" not in r.url)))


def test_related_rows_none_without_lists():
    assert related_rows_for((), "x") is None


def test_quota_flags_without_stats_raise_quota_reached():
    from etsy_insights.models import EtsyQuotaReached
    from etsy_insights.parser import blocked_quota
    url = ("https://www.etsy.com/api/v3/ajax/bespoke/shop/12345678/marketplace-insights/results-data"
           "?query=mug&search_term_hash=&search_trigger=results_search_bar")
    body = {"isQuotaReached": True, "isSearchAllowed": False,
            "quotaData": {"totalQuota": 15, "remainingQuota": 0, "lowRemainingQuotaThreshold": 5}}
    raw = RawResult("mug", "https://www.etsy.com/x", (CapturedResponse(url, 200, body),), "")
    assert blocked_quota(raw.responses, "mug").reached and blocked_quota(raw.responses, "cup") is None
    with pytest.raises(EtsyQuotaReached):
        parse_search(raw)
