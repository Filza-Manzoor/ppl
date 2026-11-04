import json

from halalcheck import feedback, off, pipeline, rules
from halalcheck.vision import DishReading, LabelReading


def product(**kw):
    base = dict(code="1", name="Gummies", brands="Acme", countries=["united-states"], ingredients_text="sugar, gelatin")
    base.update(kw)
    return off.Product(**base)


def test_product_with_gelatin_is_doubtful():
    r = pipeline.check_product(product(), "united-states")
    assert r.analysis.verdict == rules.DOUBTFUL
    assert r.title == "Gummies - Acme"


def test_country_mismatch_warning_comes_first():
    r = pipeline.check_product(product(), "pakistan")
    assert "not your selected country" in r.warnings[0]


def test_no_warning_when_country_matches_or_unset():
    for tag in ("united-states", None):
        r = pipeline.check_product(product(), tag)
        assert not any("selected country" in w for w in r.warnings)


def test_name_search_adds_scan_warning():
    r = pipeline.check_product(product(), None, "name")
    assert any("name search" in w for w in r.warnings)


def test_missing_ingredients_is_unknown():
    r = pipeline.check_product(product(ingredients_text=""), None)
    assert r.analysis.verdict == rules.UNKNOWN
    assert any("no ingredient list" in w for w in r.warnings)


def test_tags_used_when_no_text():
    r = pipeline.check_product(product(ingredients_text="", ingredients_tags=["en:pork-fat"]), None)
    assert r.analysis.verdict == rules.NOT_HALAL


def test_halal_label_tag_lowers_doubtful():
    r = pipeline.check_product(product(labels_tags=["en:halal"]), None)
    assert r.analysis.verdict == rules.LOOKS_HALAL


def test_unreadable_label_is_unknown():
    assert pipeline.check_label(LabelReading()).analysis.verdict == rules.UNKNOWN


def test_label_pork():
    r = pipeline.check_label(LabelReading(readable=True, ingredients_text="flour, lard"))
    assert r.analysis.verdict == rules.NOT_HALAL


def test_dish_never_looks_halal():
    r = pipeline.check_dish(DishReading(is_food=True, dish_name="Salad", ingredients=["lettuce", "tomato"]))
    assert r.analysis.verdict == rules.DOUBTFUL


def test_non_food_dish_is_unknown():
    assert pipeline.check_dish(DishReading()).analysis.verdict == rules.UNKNOWN


def test_feedback_keeps_only_allowed_fields(tmp_path):
    path = tmp_path / "fb.jsonl"
    ok = feedback.log_feedback(
        {"verdict": "doubtful", "comment": "x" * 900, "email": "me@example.com", "rule_ids": ["a", "b"]},
        path=path,
        webhook="",
    )
    assert ok
    record = json.loads(path.read_text().splitlines()[0])
    assert "email" not in record
    assert len(record["comment"]) == 500
    assert record["rule_ids"] == ["a", "b"]
    assert "time" in record


def test_feedback_webhook_failure_is_swallowed(tmp_path, monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError()

    monkeypatch.setattr(requests, "post", boom)
    assert feedback.log_feedback({"verdict": "x"}, path=tmp_path / "f.jsonl", webhook="https://example.invalid")
