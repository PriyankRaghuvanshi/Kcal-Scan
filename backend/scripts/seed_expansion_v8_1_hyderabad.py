#!/usr/bin/env python3
"""
v8.1: Hyderabad + regional gap fill. Chains that appeared in prod results but weren't covered.
"""
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"


def _item(name, cal, pro, carb, fat, cat="entree", conf=0.82, veg=False, vgn=False):
    return {
        "item_name": name, "category": cat,
        "estimated_calories": cal, "estimated_protein_g": pro,
        "estimated_carbs_g": carb, "estimated_fat_g": fat,
        "confidence": conf, "vegetarian_possible": veg, "vegan_possible": vgn,
    }


SEEDS = [
    ("cafe_niloufer", "IN", "Cafe Niloufer", "https://cafeniloufer.com/menu", [
        "cafe niloufer", "niloufer cafe", "niloufer"
    ], [
        _item("Irani Chai (no sugar)", 100, 3, 10, 5, cat="beverage", veg=True),
        _item("Osmania Biscuits (4pc)", 260, 4, 32, 12, cat="snack", veg=True),
        _item("Keema Samosa (2pc)", 340, 14, 38, 16),
        _item("Chicken Tangdi (2pc)", 420, 34, 4, 28),
        _item("Mutton Paya (1 bowl)", 380, 28, 8, 26),
    ]),
    ("manam_chocolate", "IN", "Manam Chocolate", "https://manamchocolate.com/menu", [
        "manam chocolate", "manam"
    ], [
        _item("Dark Chocolate Bar (50g)", 260, 4, 28, 16, cat="dessert", veg=True),
        _item("70% Single Origin (50g)", 250, 4, 26, 16, cat="dessert", veg=True),
        _item("Hot Chocolate (no sugar)", 180, 8, 22, 8, cat="beverage", veg=True),
    ]),
    ("haiku", "IN", "Haiku The Asian Kitchen", "https://haikuasiankitchen.com/menu", [
        "haiku", "haiku the asian kitchen", "haiku asian kitchen"
    ], [
        _item("Chicken Teriyaki Rice Bowl", 540, 32, 60, 18),
        _item("Thai Basil Chicken + Rice", 520, 30, 58, 20),
        _item("Steamed Chicken Dimsum (6pc)", 280, 18, 32, 8),
        _item("Kung Pao Chicken", 440, 30, 22, 22),
        _item("Veg Pad Thai", 480, 14, 66, 16, veg=True),
    ]),
    ("shah_ghouse", "IN", "Shah Ghouse", "https://shahghouse.com/menu", [
        "shah ghouse", "shahghouse"
    ], [
        _item("Shah Ghouse Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Dum Biryani", 640, 28, 62, 30),
        _item("Haleem (mutton, 1 bowl)", 440, 32, 28, 22),
        _item("Chicken Kebab (4pc)", 320, 28, 6, 20),
        _item("Prawn Biryani", 560, 28, 60, 22),
    ]),
    ("sarvi", "IN", "Sarvi Restaurant", "https://sarvirestaurant.com/menu", [
        "sarvi", "sarvi restaurant"
    ], [
        _item("Chicken Biryani (half)", 560, 28, 62, 22),
        _item("Mutton Biryani (half)", 620, 26, 60, 30),
        _item("Chicken Tangdi Kebab", 340, 28, 6, 22),
        _item("Mutton Seekh (2pc)", 340, 26, 4, 22),
    ]),
    ("persis", "IN", "Persis Biryani", "https://persis.in/menu", [
        "persis", "persis biryani"
    ], [
        _item("Persis Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("Chicken 65", 360, 28, 14, 22),
    ]),
    ("hotel_minerva", "IN", "Hotel Minerva Coffee Shop", "https://minerva.co.in/menu", [
        "hotel minerva", "minerva", "minerva coffee shop"
    ], [
        _item("Minerva Special Biryani (chicken)", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("South Indian Thali", 480, 16, 72, 12, veg=True),
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
    ]),
    ("truffles", "IN", "Truffles", "https://trufflesbangalore.com/menu", [
        "truffles"
    ], [
        _item("Grilled Chicken Burger", 520, 32, 44, 22),
        _item("Chicken Avocado Sandwich", 440, 28, 38, 18),
        _item("Pepper Steak (portion)", 440, 36, 14, 24),
        _item("Truffles Caesar Salad (chicken)", 420, 30, 18, 24),
    ]),
    ("empire", "IN", "Empire Restaurant", "https://hotelempire.co.in/menu", [
        "empire", "empire restaurant", "hotel empire"
    ], [
        _item("Empire Chicken Biryani", 580, 30, 64, 22),
        _item("Butter Chicken", 520, 32, 14, 34),
        _item("Kulcha Chicken", 540, 30, 52, 22),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
    ]),
    ("nandhini", "IN", "Nandhini Restaurant", "https://nandhinihoteliers.com/menu", [
        "nandhini", "nandhini deluxe", "nandhini restaurant"
    ], [
        _item("Andhra Chicken Biryani", 580, 30, 64, 24),
        _item("Natukodi Curry (country chicken)", 440, 34, 12, 28),
        _item("Prawn Pulusu", 420, 28, 22, 24),
        _item("Andhra Meals (veg)", 620, 20, 88, 18, veg=True),
    ]),
    ("black_rabbit", "IN", "The Black Rabbit", "https://blackrabbit.in/menu", [
        "the black rabbit", "black rabbit"
    ], [
        _item("Grilled Chicken Platter", 480, 38, 14, 28),
        _item("BBQ Chicken Burger", 540, 32, 44, 24),
        _item("Chicken Caesar", 420, 32, 18, 24),
    ]),
    ("barbeque_company", "IN", "Barbeque Company", "https://barbequecompany.com/menu", [
        "barbeque company", "barbeque co", "bbq company"
    ], [
        _item("Grilled Chicken Tikka", 280, 28, 4, 16),
        _item("Tandoori Fish", 260, 28, 4, 14),
        _item("Mutton Seekh", 320, 24, 4, 22),
        _item("Paneer Tikka", 280, 16, 10, 18, veg=True),
    ]),
]


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    created = skipped = 0
    for chain_key, market, brand, url, variants, items in SEEDS:
        fname = DATA_DIR / f"{chain_key}_{market.lower()}.json"
        if fname.exists():
            skipped += 1
            continue
        seed = {
            "brand_name": brand, "source_type": "seed_template",
            "source_url": url, "store_name_variants": variants, "items": items,
        }
        with fname.open("w", encoding="utf-8") as f:
            json.dump(seed, f, indent=2, ensure_ascii=False)
        created += 1
    print(f"created: {created}, skipped: {skipped}, total: {len(list(DATA_DIR.glob('*.json')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
