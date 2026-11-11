"""Bantuan tes AI Advisor: AI palsu (tanpa jaringan) dan home berisi data riset, katalog, dan API key."""
from __future__ import annotations

from pathlib import Path

from etsy_insights.advisor_ai import AnalysisResult, TrendResult
from etsy_insights.advisor_key import save_key
from etsy_insights.advisor_store import Source, Usage
from tests.web_helpers import seed_printify, seed_ready_keyword, seeded_home

KEY = "sk-ant-api03-" + "k" * 16 + "3456"
TREND = TrendResult("- Valentine's Day: list by Jan 15.", (Source("S1", "https://news.example/v", "Valentine"),),
                    Usage(5000, 800, 3, 39))
ANSWER = {
    "summary": "Mugs and personalized gifts look strong.",
    "recommendations": [
        {"title": "Custom mugs for Valentine's", "category": "mug", "theme": "couples", "why": "High demand.",
         "evidence_keywords": ["custom mug"], "sources": ["S1"], "action": "List by Jan 15."},
        {"title": "Pet bowls for new puppies", "category": "pet bowl", "theme": "new pet", "why": "New niche.",
         "evidence_keywords": [], "sources": [], "action": "Research first."},
    ],
    "keyword_ideas": [
        {"keyword": "cat dad mug", "category": "mug", "kind": "new_niche", "reason": "Pet owners buy mugs."},
        {"keyword": "teacher necklace", "category": "necklace", "kind": "season", "reason": "Teacher gifts."},
        {"keyword": "custom mug", "category": "mug", "kind": "from_data", "reason": "Already researched."},
    ],
}
ANALYSIS = AnalysisResult(ANSWER, Usage(20000, 3000, 0, 140), "claude-opus-5-5")


class FakeAI:
    """Pengganti AdvisorAI. Nilai berupa Exception dimunculkan; selain itu dikembalikan."""

    def __init__(self, trends=TREND, analysis=ANALYSIS, key_check=None) -> None:
        self.trends, self.analysis, self.key_check = trends, analysis, key_check
        self.calls: list[tuple] = []

    def _answer(self, value):
        if isinstance(value, BaseException):
            raise value
        return value

    def test_key(self) -> None:
        self.calls.append(("test_key",))
        self._answer(self.key_check)

    def check_trends(self, inp):
        self.calls.append(("check_trends", inp))
        return self._answer(self.trends)

    def analyze(self, inp, trend):
        self.calls.append(("analyze", inp, trend))
        return self._answer(self.analysis)


def advisor_home(tmp_path: Path, *, key: bool = True, catalog: bool = True) -> Path:
    home = seeded_home(Path(tmp_path) / "home")
    if catalog:
        seed_printify(home, mug_cost=100, mug_shipping=0)
    seed_ready_keyword(home)
    if key:
        save_key(home, KEY)
    return home
