import pytest

from etsy_insights.product_words import (CATEGORY_NAMES, DICTIONARY, ENTRIES, category_for, category_from_slug,
                                         category_slug)

TITLES = {
    "Unisex Heavy Blend™ Crewneck Sweatshirt": "sweatshirt",
    "Unisex Heavy Blend™ Hooded Sweatshirt": "hoodie",
    "Unisex Jersey Short Sleeve Tee": "t shirt",
    "Unisex Jersey Long Sleeve Tee": "long sleeve shirt",
    "Unisex Pique Polo Shirt": "polo",
    "Women's Flowy Racerback Tank": "tank top",
    "Unisex Fleece Joggers": "sweatpants",
    "Women's Cut & Sew Casual Leggings (AOP)": "leggings",
    "Accent Coffee Mug, 11oz": "mug",
    "Ceramic Mug 15oz (Black)": "mug",
    "Stainless Steel Travel Mug": "tumbler",
    "Tumbler 20oz": "tumbler",
    "Stainless Steel Water Bottle, Standard Lid": "water bottle",
    "Wine Glass, 12oz": "wine glass",
    "Can Cooler Sleeve": "can cooler",
    "Cotton Canvas Tote Bag": "tote bag",
    "Backpack": "backpack",
    "Laptop Sleeve": "laptop sleeve",
    "Tough Phone Cases": "phone case",
    "Classic Leather Wallet": "wallet",
    "Matte Vertical Posters": "poster",
    "Canvas Gallery Wraps": "canvas",
    "Velveteen Plush Blanket": "blanket",
    "Spun Polyester Square Pillow": "pillow",
    "Wall Clock": "wall clock",
    "Area Rugs": "rug",
    "Beach Towel": "towel",
    "Shower Curtains": "shower curtain",
    "Doormat": "doormat",
    "Indoor Wall Tapestries": "tapestry",
    "Garden & House Banner": "other",
    "Garden Flag": "flag",
    "Bamboo Cutting Board": "cutting board",
    "Scented Soy Candle, 9oz": "candle",
    "Cork Back Coaster": "coaster",
    "Kiss-Cut Stickers": "sticker",
    "Ceramic Ornament, 4 Shapes": "ornament",
    "Heart Necklace": "necklace",
    "Engraved Bar Bracelet": "bracelet",
    "Stud Earrings": "earrings",
    "Acrylic Keychain": "keychain",
    "Greeting Cards (1, 10, 30, and 50pcs)": "greeting card",
    "Postcard Bundles (envelopes not included)": "postcard",
    "Wall Calendars (2027)": "calendar",
    "Spiral Notebook - Ruled Line": "notebook",
    "Jigsaw puzzle with Tin": "puzzle",
    "Mouse Pad (Rectangle)": "mouse pad",
    "Pet Bandana Collar": "pet bandana",
    "Pet Bowl": "pet bowl",
    "Pet Bed": "pet bed",
    "Baby Bib": "bib",
    "Infant Fine Jersey Bodysuit": "other",
    "Something Unusual": "other",
}


@pytest.mark.parametrize("title,expected", TITLES.items())
def test_categories_for_catalog_titles(title, expected):
    assert category_for(title) == expected


def test_dictionary_and_names():
    assert len(DICTIONARY) == 52 and DICTIONARY[0][0] == "sweatshirt" and DICTIONARY[-1][0] == "can cooler"
    assert set(CATEGORY_NAMES) == set(ENTRIES) | {"other"}
    assert (CATEGORY_NAMES["t shirt"], CATEGORY_NAMES["wall clock"], CATEGORY_NAMES["other"]) == (
        "T-shirts", "Wall clocks", "Other")
    assert ENTRIES["necklace"] == ("necklace", "pendant", "name necklace")


def test_slugs_round_trip():
    for main in CATEGORY_NAMES:
        assert category_from_slug(category_slug(main)) == main
    assert category_slug("wall clock") == "wall-clock" and category_from_slug("nope") is None


def test_text_in_brackets_does_not_decide_the_category():
    from etsy_insights.product_words import words_for_title
    assert category_for("Velveteen Minky Blanket (Two-sided print)") == "blanket"
    assert "print" not in words_for_title("Velveteen Minky Blanket (Two-sided print)")
    assert category_for("Ceramic Mug 15oz (Black)") == "mug"
    assert category_for("Unclosed (bracket Mug") == "mug"
