from etsy_insights.product_words import DICTIONARY, matches, matches_tokens, normalize_words, words_for_title


def test_normalize():
    assert normalize_words("Custom T-Shirts & Mugs!") == ("custom", "t", "shirt", "mug")
    assert normalize_words("glasses boxes dress babies baby tees toys") == (
        "glass", "box", "dress", "babie", "babie", "tee", "toy")
    assert normalize_words("hoodies hoodie hoody beanies onesies") == (
        "hoodie", "hoodie", "hoodie", "beanie", "onesie")
    assert normalize_words("Café_Mugs / gifts™") == ("café", "mug", "gift")


def test_whole_words_only():
    shirt = ["t shirt", "tee", "tshirt", "shirt"]
    assert matches("funny shirt for dad", shirt) and matches("custom t-shirts", shirt)
    assert not matches("crewneck sweatshirt", shirt)
    assert matches("personalized coffee mugs", ["mug", "coffee mug", "cup"])
    assert not matches("mugshot poster", ["mug"])
    assert matches("cute beanies for kids", ["hat", "cap", "beanie"])
    assert not matches("anything", [])
    assert matches_tokens(normalize_words("custom t-shirts"), shirt)


def test_words_for_title():
    assert words_for_title("Unisex Heavy Blend™ Crewneck Sweatshirt") == ["sweatshirt", "crewneck", "crew neck", "jumper"]
    assert words_for_title("Accent Coffee Mug, 11oz") == ["mug", "coffee mug", "cup"]
    assert words_for_title("Unisex Jersey Short Sleeve Tee")[0] == "t shirt"
    assert words_for_title("Kiss-Cut Vinyl Decals") == ["sticker", "decal"]
    assert words_for_title("Something Unusual") == []
    assert DICTIONARY[0] == ("sweatshirt", ("crewneck", "crew neck", "jumper"))


def test_plural_cases_and_canvas():
    assert normalize_words("cases case canvases canvas vases purses phrases glasses") == (
        "case", "case", "canvas", "canvas", "vase", "purse", "phrase", "glass")
    assert words_for_title("Tough Phone Cases")[0] == "phone case"
    assert matches("iphone cases for women", words_for_title("Tough Phone Cases"))
    assert matches("canvases wall decor", ["canvas"])


def test_head_noun_wins():
    hoodie = words_for_title("Unisex Heavy Blend™ Hooded Sweatshirt")
    assert hoodie[0] == "hoodie" and "sweatshirt" not in hoodie
    assert words_for_title("Cotton Canvas Tote Bag") == ["tote bag", "tote"]
    assert words_for_title("Travel Mug")[0] == "tumbler"
    assert words_for_title("Canvas Gallery Wraps") == ["canvas", "canvas print"]
