from etsy_insights.printify_store import OwnProduct, ProductType
from etsy_insights.printify_suggestions import suggest


def pt(type_id, words, available=True):
    return ProductType(type_id, type_id, 1, f"T{type_id}", "Prov", "own", 100, 100, 100, 3, tuple(words), False,
                       available, None)


def test_suggestions_order_and_dedupe():
    types = [pt(1, ["sweatshirt", "crewneck"]), pt(2, ["mug", "cup"]), pt(3, ["poster"], available=False), pt(4, [])]
    products = [OwnProduct("a", 1, "A", ("Mom Gift", "custom sweatshirt"), 100),
                OwnProduct("b", 2, "B", ("mom gift", "coffee lover"), 100)]
    result = suggest(types, products, {"custom sweatshirt", "mug"})
    assert [(s.keyword, s.origin) for s in result] == [
        ("mom gift", "tag on 2 products"), ("coffee lover", "tag on 1 product"), ("custom mug", "product word"),
        ("personalized mug", "product word"), ("personalized sweatshirt", "product word"),
        ("sweatshirt", "product word")]
    assert [s.keyword for s in suggest(types, products, {"custom sweatshirt", "mug"}, limit=2)] == [
        "mom gift", "coffee lover"]
