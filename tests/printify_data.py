"""Data Printify palsu, berbentuk seperti contoh di dokumentasi resmi (developers.printify.com)."""

SHOPS = [{"id": 111, "title": "My Etsy Shop", "sales_channel": "etsy"},
         {"id": 222, "title": "API store", "sales_channel": "custom_integration"}]

BLUEPRINTS = [
    {"id": 6, "title": "Unisex Heavy Blend™ Crewneck Sweatshirt", "description": "", "brand": "Gildan",
     "model": "18000", "images": []},
    {"id": 68, "title": "Accent Coffee Mug, 11oz", "description": "", "brand": "Generic brand", "model": "",
     "images": []},
    {"id": 384, "title": "Unisex Jersey Short Sleeve Tee", "description": "", "brand": "Bella+Canvas",
     "model": "3001", "images": []},
]


def variant(vid, cost, enabled=True):
    return {"id": vid, "sku": f"SKU{vid}", "cost": cost, "price": cost * 2, "title": f"V{vid}", "grams": 100,
            "is_enabled": enabled, "is_default": False, "is_available": True, "options": [1]}


def product(pid, blueprint_id, provider_id, title, tags, variants):
    return {"id": pid, "title": title, "description": "", "tags": tags, "options": [], "variants": variants,
            "images": [], "created_at": "2026-01-01 10:00:00+00:00", "visible": True, "is_locked": False,
            "blueprint_id": blueprint_id, "user_id": 1, "shop_id": 111, "print_provider_id": provider_id,
            "print_areas": [], "sales_channel_properties": []}


PRODUCTS_PAGE_1 = {"current_page": 1, "last_page": 2, "per_page": 50, "total": 3, "data": [
    product("p-sweat", 6, 99, "Mom Sweatshirt", ["Mom Gift", "custom sweatshirt"],
            [variant(1, 1350), variant(2, 1600), variant(3, 900, enabled=False)]),
]}
PRODUCTS_PAGE_2 = {"current_page": 2, "last_page": 2, "per_page": 50, "total": 3, "data": [
    product("p-mug", 68, 1, "Coffee Lover Mug", ["mom gift", "coffee lover"], [variant(10, 512)]),
    product("p-off", 384, 29, "Old Tee", ["old"], [variant(20, 900, enabled=False)]),
]}

PROVIDERS = {6: [{"id": 99, "title": "Monster Digital"}],
             68: [{"id": 1, "title": "SPOKE Custom Products"}],
             384: [{"id": 29, "title": "Monster Digital"}]}


def profile(variant_ids, cost, countries, currency="USD"):
    return {"variant_ids": variant_ids, "first_item": {"cost": cost, "currency": currency},
            "additional_items": {"cost": 0, "currency": currency}, "countries": countries}


SHIPPING = {
    (6, 99): {"handling_time": {"value": 3, "unit": "day"},
              "profiles": [profile([1, 2, 3], 475, ["US"]), profile([1, 2, 3], 1100, ["REST_OF_THE_WORLD"])]},
    (68, 1): {"handling_time": {"value": 2, "unit": "day"},
              "profiles": [profile([10], 699, ["REST_OF_THE_WORLD"])]},
    (384, 29): {"handling_time": {"value": 4, "unit": "day"}, "profiles": [profile([20], 899, ["CA"])]},
}
