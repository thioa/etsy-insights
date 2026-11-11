from etsy_insights.advisor_result import clean_idea, idea_status, validate

CATEGORIES = {"mug", "tumbler", "t shirt"}
WITH_DATA = {"custom mug", "dog mom sweatshirt"}
TAKEN = {"custom mug", "teacher mug"}
SOURCES = {"S1", "S2"}


def _rec(**changes):
    rec = {"title": "Dog mom mugs", "category": "mug", "theme": "dog moms", "why": "Strong demand.",
           "evidence_keywords": ["Custom Mug", "unknown"], "sources": ["S1", "S9"], "action": "List by Jan 20."}
    rec.update(changes)
    return rec


def _idea(keyword, category="mug", kind="from_data", reason="Fits your data."):
    return {"keyword": keyword, "category": category, "kind": kind, "reason": reason}


def _validate(recommendations=(), ideas=(), summary="Mugs look strong."):
    return validate({"summary": summary, "recommendations": list(recommendations), "keyword_ideas": list(ideas)},
                    categories=CATEGORIES, with_data=WITH_DATA, taken=TAKEN, source_ids=SOURCES)


def test_recommendations_validated():
    result = _validate([_rec(), _rec(evidence_keywords=["nothing here"], sources=[]), _rec(category="poster")])
    backed, idea = result.result["recommendations"]
    assert backed["evidence"] == ["custom mug"] and backed["backed"] is True and backed["sources"] == ["S1"]
    assert idea["evidence"] == [] and idea["backed"] is False
    assert backed["title"] == "Dog mom mugs" and backed["category"] == "mug" and backed["action"] == "List by Jan 20."
    assert result.dropped["recommendations"] == 1 and result.dropped["evidence"] == 2
    assert result.dropped["sources"] == 1
    many = _validate([_rec(title="x" * 500)] * 10).result["recommendations"]
    assert len(many) == 8 and len(many[0]["title"]) == 120


def test_keyword_ideas_filtered():
    ideas = [
        _idea("Dog Mom Tumblers!", "tumbler"),
        _idea("teacher mug"),
        _idea("dog mom tumblers", "tumbler"),
        _idea("funny cat lover gift for her mug"),
        _idea("retro sunset", "t shirt"),
        _idea("cat dad shirt", "t shirt", reason="r" * 400),
        _idea("dog mom mug", "poster"),
        _idea("dog mom sweatshirt mug"),
        _idea(""),
    ]
    result = _validate(ideas=ideas)
    kept = result.result["keyword_ideas"]
    assert [i["keyword"] for i in kept] == ["dog mom tumblers", "cat dad shirt", "dog mom sweatshirt mug"]
    assert len(kept[1]["reason"]) == 300 and kept[0]["kind"] == "from_data" and kept[0]["category"] == "tumbler"
    assert result.dropped["ideas"] == 6
    many = _validate(ideas=[_idea(f"cat {i} mug") for i in range(25)]).result["keyword_ideas"]
    assert len(many) == 20


def test_summary_truncated():
    assert len(_validate(summary="s" * 2000).result["summary"]) == 1200


def test_clean_idea():
    assert clean_idea("  Mother's Day Mug!! ") == "mother's day mug"
    assert clean_idea("mug/cup set") == "mug cup set"
    assert clean_idea("t-shirt") == "t-shirt"
    assert clean_idea("Black & White  Mug") == "black & white mug"


def test_idea_status():
    statuses = {"a": "pending", "b": "in_progress", "c": "done", "d": "no_data", "e": "harvested"}
    assert [idea_status(k, statuses) for k in "abcdef"] == ["in_queue", "in_queue", "researched", "researched",
                                                             "new", "new"]
