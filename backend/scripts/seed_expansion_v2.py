#!/usr/bin/env python3
"""
Seed expansion v2: SE Asia (MY/TH/ID), India long-tail, NZ.
Writes new files into data/chains/. Existing seeds are preserved
(skipped if file already exists).

Run:  cd backend && python scripts/seed_expansion_v2.py
Then: python scripts/merge_chain_seeds_to_registry.py
"""
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"


def _item(name, cal, pro, carb, fat, cat="entree", conf=0.82, veg=False, vgn=False):
    return {
        "item_name": name,
        "category": cat,
        "estimated_calories": cal,
        "estimated_protein_g": pro,
        "estimated_carbs_g": carb,
        "estimated_fat_g": fat,
        "confidence": conf,
        "vegetarian_possible": veg,
        "vegan_possible": vgn,
    }


SEEDS = [
    # ═══════════════ MALAYSIA ═══════════════
    ("mcdonalds", "MY", "McDonald's", "https://www.mcdonalds.com.my/menu", [
        "mcdonalds", "mcdonald's", "mcd"
    ], [
        _item("Grilled Chicken Deluxe", 360, 28, 32, 12),
        _item("McChicken", 400, 16, 40, 18),
        _item("Side Salad", 25, 1, 4, 0, cat="side", veg=True, vgn=True),
        _item("Nasi Lemak McD (grilled)", 520, 24, 58, 18),
        _item("Filet-O-Fish", 340, 15, 36, 14),
    ]),
    ("kfc", "MY", "KFC", "https://www.kfc.com.my/menu", [
        "kfc", "kentucky fried chicken"
    ], [
        _item("Grilled Chicken (1pc)", 180, 24, 2, 9),
        _item("Original Recipe Chicken (1pc)", 240, 22, 8, 14),
        _item("Cheezy Wedges (regular)", 260, 5, 28, 14, cat="side", veg=True),
        _item("Nasi Rice Bowl Chicken Chop", 520, 28, 66, 16),
        _item("Colonel Burger Grilled", 340, 22, 34, 12),
    ]),
    ("marrybrown", "MY", "Marrybrown", "https://www.marrybrown.com.my/menu", [
        "marrybrown", "marry brown", "mb"
    ], [
        _item("Grilled Chicken Rice", 480, 30, 52, 14),
        _item("MB Crispy Chicken (1pc)", 260, 18, 10, 16),
        _item("Nasi Ayam Penyet (grilled)", 510, 28, 60, 14),
        _item("Garden Salad", 60, 2, 8, 2, cat="side", veg=True, vgn=True),
    ]),
    ("the_chicken_rice_shop", "MY", "The Chicken Rice Shop", "https://www.thechickenriceshop.com/menu", [
        "chicken rice shop", "tcrs", "the chicken rice shop"
    ], [
        _item("Steamed Chicken + Rice (quarter)", 520, 32, 58, 16),
        _item("Roast Chicken + Rice (quarter)", 580, 32, 60, 22),
        _item("Sayur Manis", 40, 2, 6, 1, cat="side", veg=True, vgn=True),
        _item("Chicken Salad Bowl", 320, 26, 18, 14),
    ]),
    ("old_town_white_coffee", "MY", "Old Town White Coffee", "https://www.oldtown.com.my/menu", [
        "old town", "old town white coffee", "oldtown"
    ], [
        _item("Nasi Lemak Chicken Rendang", 680, 28, 78, 28),
        _item("Kaya Butter Toast Set (no sugar drink)", 340, 10, 44, 14, cat="breakfast", veg=True),
        _item("Steamed Chicken + Rice", 520, 30, 56, 16),
        _item("Wantan Mee (dry, chicken)", 440, 22, 58, 12),
    ]),
    ("secret_recipe", "MY", "Secret Recipe", "https://www.secretrecipe.com.my/menu", [
        "secret recipe"
    ], [
        _item("Grilled Chicken Chop", 440, 34, 28, 20),
        _item("Nasi Lemak Secret", 640, 26, 72, 26),
        _item("Caesar Salad (chicken)", 340, 24, 16, 20),
        _item("Tom Yam Chicken Rice", 520, 28, 54, 18),
    ]),
    ("tealive", "MY", "Tealive", "https://tealive.com.my/menu", [
        "tealive", "tea live"
    ], [
        _item("Classic Milk Tea (less sugar)", 220, 2, 40, 6, cat="beverage", veg=True),
        _item("Matcha Latte (less sugar)", 240, 6, 34, 8, cat="beverage", veg=True),
        _item("Signature Pearl Milk Tea", 340, 2, 62, 8, cat="beverage", veg=True),
    ]),
    ("subway", "MY", "Subway", "https://www.subway.com.my/menu", [
        "subway"
    ], [
        _item("6-inch Roast Chicken Sub", 280, 22, 40, 5),
        _item("6-inch Turkey Breast Sub", 260, 18, 40, 4),
        _item("Salad Bowl Chicken Teriyaki", 290, 26, 22, 10),
        _item("6-inch Veggie Delite", 230, 8, 40, 3, veg=True, vgn=True),
    ]),

    # ═══════════════ THAILAND ═══════════════
    ("mcdonalds", "TH", "McDonald's", "https://www.mcdonalds.co.th/menu", [
        "mcdonalds", "mcdonald's", "mcd"
    ], [
        _item("Grilled Chicken Burger", 380, 28, 32, 14),
        _item("McChicken Kra Prao Rice", 560, 28, 72, 18),
        _item("Salad with Grilled Chicken", 240, 24, 12, 10),
        _item("Filet-O-Fish", 340, 15, 36, 14),
    ]),
    ("kfc", "TH", "KFC", "https://www.kfc.co.th/menu", [
        "kfc", "kentucky fried chicken"
    ], [
        _item("Grilled Chicken (1pc)", 190, 26, 2, 9),
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Rice Bowl Chicken Kra Pao", 540, 28, 70, 16),
        _item("Coleslaw", 120, 1, 12, 8, cat="side", veg=True),
    ]),
    ("mk_restaurants", "TH", "MK Restaurants", "https://www.mkrestaurant.com/menu", [
        "mk", "mk restaurants", "mk suki"
    ], [
        _item("Suki Chicken Set (clear soup)", 420, 32, 36, 16),
        _item("Roasted Duck + Rice", 580, 34, 62, 22),
        _item("Tom Yum Noodle Soup Chicken", 380, 26, 48, 10),
        _item("Vegetable Set (no sauce)", 80, 4, 14, 1, cat="side", veg=True, vgn=True),
    ]),
    ("after_you", "TH", "After You", "https://afteryoudessertcafe.com/menu", [
        "after you", "after you dessert cafe"
    ], [
        _item("Shibuya Honey Toast (share)", 720, 10, 110, 24, cat="dessert", veg=True),
        _item("Matcha Latte (less sweet)", 220, 6, 30, 8, cat="beverage", veg=True),
        _item("Mango Sticky Rice", 420, 6, 78, 12, cat="dessert", veg=True, vgn=True),
    ]),
    ("yayoi", "TH", "Yayoi", "https://www.yayoirestaurants.com/menu", [
        "yayoi", "yayoi japanese teishoku"
    ], [
        _item("Chicken Teriyaki Set", 560, 36, 58, 18),
        _item("Saba Shioyaki Set", 520, 34, 56, 18),
        _item("Yakiniku Set (pork)", 620, 32, 58, 28),
        _item("Salmon Sashimi Set", 440, 36, 42, 14),
    ]),
    ("sizzler", "TH", "Sizzler", "https://www.sizzler.co.th/menu", [
        "sizzler"
    ], [
        _item("Grilled Chicken Breast Lite", 360, 38, 10, 18),
        _item("Salmon Steak (grilled)", 420, 36, 8, 26),
        _item("Salad Bar (all veggie + lean protein)", 280, 20, 22, 12, cat="side", veg=True),
    ]),
    ("oishi", "TH", "Oishi", "https://www.oishigroup.com/menu", [
        "oishi", "oishi japanese"
    ], [
        _item("Grilled Salmon Teriyaki Set", 520, 36, 54, 18),
        _item("Chicken Katsu Don (half)", 480, 26, 60, 14),
        _item("Udon Chicken Soup", 420, 24, 58, 10),
        _item("Salmon Sashimi (6pc)", 220, 22, 0, 14),
    ]),
    ("pizza_hut", "TH", "Pizza Hut", "https://www.pizzahut.co.th/menu", [
        "pizza hut"
    ], [
        _item("Personal Pan Hawaiian", 620, 28, 70, 24),
        _item("Grilled Chicken Salad", 280, 24, 18, 12),
        _item("Chicken Wings (6pc grilled)", 340, 30, 4, 22),
    ]),

    # ═══════════════ INDONESIA ═══════════════
    ("mcdonalds", "ID", "McDonald's", "https://www.mcdonalds.co.id/menu", [
        "mcdonalds", "mcdonald's", "mcd"
    ], [
        _item("PaNas 1 (grilled chicken + rice)", 540, 30, 64, 16),
        _item("McChicken Deluxe", 400, 18, 40, 18),
        _item("Nasi Uduk with Grilled Chicken", 580, 30, 70, 18),
        _item("Garden Salad", 25, 1, 4, 0, cat="side", veg=True, vgn=True),
    ]),
    ("kfc", "ID", "KFC", "https://www.kfcku.com/menu", [
        "kfc", "kfcku"
    ], [
        _item("Chicken + Nasi (1pc grilled)", 520, 30, 64, 14),
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Kol Slaw (regular)", 120, 1, 12, 8, cat="side", veg=True),
        _item("Fish Fillet Rice Bowl", 480, 26, 62, 14),
    ]),
    ("hoka_bento", "ID", "HokBen", "https://www.hokben.co.id/menu", [
        "hokben", "hoka bento", "hoka-hoka bento"
    ], [
        _item("Chicken Teriyaki Bento", 540, 32, 62, 16),
        _item("Beef Yakiniku Bento", 620, 30, 62, 26),
        _item("Salmon Bento", 520, 34, 58, 16),
        _item("Salad Bowl Chicken", 280, 26, 18, 10),
    ]),
    ("richeese_factory", "ID", "Richeese Factory", "https://richeesefactory.com/menu", [
        "richeese", "richeese factory"
    ], [
        _item("Fire Chicken Level 1 + Rice", 540, 30, 62, 18),
        _item("Grilled Chicken + Rice", 480, 32, 58, 12),
        _item("Small Salad", 60, 2, 8, 2, cat="side", veg=True, vgn=True),
    ]),
    ("es_teler_77", "ID", "Es Teler 77", "https://esteler77.com/menu", [
        "es teler 77", "es teler"
    ], [
        _item("Gado-Gado", 380, 16, 38, 20, veg=True, vgn=True),
        _item("Nasi Goreng Ayam", 540, 24, 72, 16),
        _item("Mie Ayam", 420, 22, 56, 12),
        _item("Ayam Bakar + Rice", 520, 32, 58, 16),
    ]),
    ("j_co_donuts", "ID", "J.CO Donuts & Coffee", "https://www.jcodonuts.com/menu", [
        "j.co", "jco", "j.co donuts"
    ], [
        _item("Coffee (black, no sugar)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Single Donut (glazed)", 280, 4, 34, 14, cat="dessert", veg=True),
        _item("Cappuccino (no sugar)", 120, 8, 10, 6, cat="beverage", veg=True),
    ]),
    ("ayam_geprek_bensu", "ID", "Ayam Geprek Bensu", "https://ayamgeprekbensu.co.id/menu", [
        "ayam geprek bensu", "geprek bensu", "bensu"
    ], [
        _item("Ayam Geprek + Rice (level 1)", 580, 34, 66, 18),
        _item("Ayam Bakar + Rice", 520, 32, 58, 14),
        _item("Tahu Tempe Side", 180, 12, 12, 10, cat="side", veg=True, vgn=True),
    ]),
    ("solaria", "ID", "Solaria", "https://solariaonline.com/menu", [
        "solaria"
    ], [
        _item("Nasi Ayam Bakar Kecap", 560, 32, 64, 16),
        _item("Nasi Goreng Ayam", 580, 26, 74, 18),
        _item("Cap Cay Goreng", 220, 14, 20, 10, veg=True),
        _item("Ikan Gurame Bakar", 420, 34, 8, 24),
    ]),

    # ═══════════════ INDIA EXPANSION ═══════════════
    ("cafe_coffee_day", "IN", "Café Coffee Day", "https://www.cafecoffeeday.com/menu", [
        "ccd", "cafe coffee day", "café coffee day"
    ], [
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Chicken Tikka Sandwich", 360, 22, 38, 14),
        _item("Veg Sandwich (grilled)", 280, 10, 40, 8, veg=True),
        _item("Masala Chai (less sugar)", 140, 4, 18, 5, cat="beverage", veg=True),
    ]),
    ("chaayos", "IN", "Chaayos", "https://chaayos.com/menu", [
        "chaayos"
    ], [
        _item("Masala Chai (no sugar)", 110, 4, 10, 5, cat="beverage", veg=True),
        _item("Kulhad Chai (less sugar)", 130, 4, 14, 5, cat="beverage", veg=True),
        _item("Chicken Tikka Wrap", 420, 26, 42, 16),
        _item("Paneer Tikka Wrap", 460, 20, 44, 22, veg=True),
    ]),
    ("barista", "IN", "Barista", "https://www.barista.co.in/menu", [
        "barista", "barista coffee"
    ], [
        _item("Americano (black)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 120, 7, 10, 6, cat="beverage", veg=True),
        _item("Chicken Panini", 380, 24, 38, 14),
    ]),
    ("theobroma", "IN", "Theobroma", "https://www.theobroma.in/menu", [
        "theobroma", "theo"
    ], [
        _item("Chicken Tikka Sandwich", 420, 26, 40, 16),
        _item("Multigrain Veg Sandwich", 320, 12, 42, 10, veg=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Brownie (half)", 280, 4, 34, 14, cat="dessert", veg=True),
    ]),
    ("keventers", "IN", "Keventers", "https://keventers.com/menu", [
        "keventers"
    ], [
        _item("Classic Milkshake (regular, less sugar)", 320, 8, 48, 10, cat="beverage", veg=True),
        _item("Dark Chocolate Milkshake", 420, 9, 58, 16, cat="beverage", veg=True),
        _item("Coffee Shake (less sugar)", 260, 7, 38, 8, cat="beverage", veg=True),
    ]),
    ("a2b", "IN", "Adyar Ananda Bhavan (A2B)", "https://www.aabsweets.com/menu", [
        "a2b", "adyar ananda bhavan", "adyar anandha bhavan"
    ], [
        _item("Ghee Roast Dosa", 420, 10, 58, 18, veg=True),
        _item("Idli Sambar (4pc)", 280, 10, 52, 4, veg=True, vgn=True),
        _item("Curd Rice", 320, 10, 42, 12, veg=True),
        _item("Chicken Biryani (half)", 560, 28, 62, 22),
    ]),
    ("sangeetha", "IN", "Sangeetha Restaurant", "https://www.sangeethaveg.com/menu", [
        "sangeetha", "sangeetha veg"
    ], [
        _item("Ghee Roast Dosa", 420, 10, 58, 18, veg=True),
        _item("Mini Tiffin (idli/vada/pongal)", 480, 16, 72, 14, veg=True),
        _item("Veg Meals (portion controlled)", 540, 18, 86, 14, veg=True),
        _item("Upma", 260, 8, 42, 8, veg=True, vgn=True),
    ]),
    ("meghana_foods", "IN", "Meghana Foods", "https://www.meghanafoods.com/menu", [
        "meghana", "meghana foods", "meghana's"
    ], [
        _item("Chicken Biryani (half)", 580, 32, 62, 22),
        _item("Paneer Biryani (half)", 540, 18, 64, 24, veg=True),
        _item("Chicken 65 (half)", 380, 28, 14, 24),
        _item("Andhra Chicken Curry + 2 Roti", 620, 34, 42, 32),
    ]),
    ("mainland_china", "IN", "Mainland China", "https://www.mainlandchinarestaurants.com/menu", [
        "mainland china"
    ], [
        _item("Kung Pao Chicken", 420, 30, 22, 22),
        _item("Steamed Chicken Dumplings (6pc)", 280, 18, 32, 8),
        _item("Burnt Garlic Rice + Chicken", 540, 28, 68, 18),
        _item("Hot & Sour Soup Chicken", 180, 16, 14, 8),
    ]),
    ("burger_singh", "IN", "Burger Singh", "https://www.burgersinghonline.com/menu", [
        "burger singh"
    ], [
        _item("Doon Valley Grilled Chicken Burger", 460, 28, 48, 16),
        _item("Punjabi Express Grilled Chicken Burger", 480, 30, 46, 18),
        _item("UP Wala Butter Paneer Burger", 520, 22, 52, 24, veg=True),
        _item("Peri Peri Grilled Wings (6pc)", 320, 28, 4, 22),
    ]),
    ("social", "IN", "Social", "https://socialoffline.in/menu", [
        "social", "social restaurant", "social cafe"
    ], [
        _item("Grilled Chicken Bao", 280, 20, 30, 10),
        _item("Keema Pav (half)", 420, 24, 38, 20),
        _item("Peri Peri Chicken Salad", 340, 28, 18, 16),
        _item("Chicken Tikka Roll", 440, 26, 42, 18),
    ]),
    ("goli_vada_pav", "IN", "Goli Vada Pav", "https://www.golivadapav.com/menu", [
        "goli vada pav", "goli"
    ], [
        _item("Vada Pav (single)", 290, 7, 38, 12, veg=True, vgn=True),
        _item("Schezwan Vada Pav", 310, 7, 38, 14, veg=True, vgn=True),
        _item("Samosa Pav", 320, 8, 44, 12, veg=True),
    ]),

    # ═══════════════ NEW ZEALAND ═══════════════
    ("burgerfuel", "NZ", "BurgerFuel", "https://burgerfuel.com/nz/menu", [
        "burgerfuel", "burger fuel"
    ], [
        _item("Combustion Grilled Chicken", 620, 36, 52, 28),
        _item("Bastard Grilled Chicken", 580, 34, 48, 26),
        _item("Garden Salad", 60, 2, 8, 2, cat="side", veg=True, vgn=True),
        _item("Kumara Fries (small)", 260, 3, 34, 12, cat="side", veg=True),
    ]),
    ("hell_pizza", "NZ", "Hell Pizza", "https://hell.co.nz/menu", [
        "hell pizza", "hell"
    ], [
        _item("Sloth (personal, chicken)", 540, 28, 62, 20),
        _item("Greed (personal, ham/bacon/chicken)", 620, 34, 60, 26),
        _item("Mischief (personal, veg)", 480, 18, 66, 16, veg=True),
    ]),
    ("pita_pit", "NZ", "Pita Pit", "https://www.pitapit.co.nz/menu", [
        "pita pit"
    ], [
        _item("Grilled Chicken Pita (no sauce)", 380, 30, 42, 10),
        _item("Turkey Breast Pita", 340, 24, 42, 8),
        _item("Falafel Pita", 420, 14, 54, 16, veg=True, vgn=True),
        _item("Salad Bowl Chicken", 280, 28, 14, 10),
    ]),
    ("carls_jr", "NZ", "Carl's Jr.", "https://www.carlsjr.co.nz/menu", [
        "carls jr", "carl's jr", "carls junior"
    ], [
        _item("Grilled Chicken Burger", 420, 30, 40, 16),
        _item("Charbroiled BBQ Chicken Sandwich", 440, 32, 42, 16),
        _item("Side Salad", 60, 2, 8, 2, cat="side", veg=True, vgn=True),
    ]),
    ("mcdonalds", "NZ", "McDonald's", "https://mcdonalds.co.nz/menu", [
        "mcdonalds", "mcdonald's", "maccas"
    ], [
        _item("Grilled Chicken Salad", 180, 22, 10, 6),
        _item("McChicken", 400, 16, 40, 18),
        _item("Kiwi Burger (grilled)", 520, 28, 44, 24),
        _item("Garden Salad", 25, 1, 4, 0, cat="side", veg=True, vgn=True),
    ]),
    ("kfc", "NZ", "KFC", "https://www.kfc.co.nz/menu", [
        "kfc", "kentucky fried chicken"
    ], [
        _item("Original Tender (3pc) + Salad", 380, 32, 18, 20),
        _item("Grilled Chicken Fillet", 160, 22, 2, 8),
        _item("Zinger Burger", 470, 24, 44, 22),
        _item("Coleslaw (small)", 100, 1, 10, 6, cat="side", veg=True),
    ]),
    ("subway", "NZ", "Subway", "https://www.subway.co.nz/menu", [
        "subway"
    ], [
        _item("6-inch Chicken Classic", 300, 24, 40, 5),
        _item("6-inch Turkey Breast", 280, 18, 40, 4),
        _item("Salad Bowl Chicken", 260, 28, 14, 8),
        _item("6-inch Veggie Delite", 230, 8, 40, 3, veg=True, vgn=True),
    ]),
    ("dominos", "NZ", "Domino's Pizza", "https://www.dominos.co.nz/menu", [
        "dominos", "domino's", "dominos pizza"
    ], [
        _item("Chef's Best Chicken (personal)", 540, 28, 64, 18),
        _item("Hawaiian (personal)", 580, 24, 72, 20),
        _item("Veg Supreme (personal)", 480, 18, 66, 16, veg=True),
    ]),
]


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0
    for chain_key, market, brand, url, variants, items in SEEDS:
        fname = DATA_DIR / f"{chain_key}_{market.lower()}.json"
        if fname.exists():
            skipped += 1
            continue
        seed = {
            "brand_name": brand,
            "source_type": "seed_template",
            "source_url": url,
            "store_name_variants": variants,
            "items": items,
        }
        with fname.open("w", encoding="utf-8") as f:
            json.dump(seed, f, indent=2, ensure_ascii=False)
        created += 1

    print(f"created: {created}")
    print(f"skipped (already existed): {skipped}")
    print(f"total seed files now: {len(list(DATA_DIR.glob('*.json')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
