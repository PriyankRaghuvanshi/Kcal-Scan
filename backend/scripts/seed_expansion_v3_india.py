#!/usr/bin/env python3
"""
Seed expansion v3: India long-tail — 17 more major Indian chains.
Writes new files into data/chains/. Existing seeds are preserved
(skipped if file already exists).

Run:  cd backend && python scripts/seed_expansion_v3_india.py
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
    ("la_pinoz", "IN", "La Pino'z Pizza", "https://www.lapinozpizza.in/menu", [
        "la pinoz", "la pino'z", "lapinoz", "la pinoz pizza"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 62, 18),
        _item("Hawaiian Personal Pizza", 540, 22, 68, 18),
        _item("Peri Peri Chicken Pizza (personal)", 560, 28, 60, 22),
        _item("Veg Exotica Personal Pizza", 480, 16, 66, 14, veg=True),
        _item("Tandoori Paneer Personal Pizza", 540, 20, 62, 22, veg=True),
    ]),
    ("kaati_zone", "IN", "Kaati Zone", "https://kaatizone.com/menu", [
        "kaati zone", "kaati junction", "kaati roll", "kati zone"
    ], [
        _item("Chicken Tikka Kaati Roll", 420, 26, 44, 14),
        _item("Paneer Tikka Kaati Roll", 440, 18, 42, 22, veg=True),
        _item("Egg Chicken Roll", 460, 28, 42, 18),
        _item("Veg Roll", 340, 10, 48, 12, veg=True),
        _item("Mutton Seekh Roll", 520, 28, 44, 24),
    ]),
    ("third_wave_coffee", "IN", "Third Wave Coffee", "https://thirdwavecoffeeroasters.com/menu", [
        "third wave coffee", "third wave", "twc"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Cold Brew (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Pesto Sandwich", 380, 24, 38, 14),
        _item("Veg Pesto Sandwich", 320, 12, 40, 12, veg=True),
    ]),
    ("blue_tokai", "IN", "Blue Tokai Coffee Roasters", "https://bluetokaicoffee.com/menu", [
        "blue tokai", "blue tokai coffee"
    ], [
        _item("Pour-over (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Flat White (no sugar)", 110, 6, 8, 6, cat="beverage", veg=True),
        _item("Cold Brew (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Sourdough Sandwich", 420, 28, 40, 16),
        _item("Avocado Toast (multigrain)", 360, 10, 42, 16, veg=True, vgn=True),
    ]),
    ("bakingo", "IN", "Bakingo", "https://www.bakingo.com/menu", [
        "bakingo"
    ], [
        _item("Fresh Cream Chocolate Slice", 340, 4, 42, 18, cat="dessert", veg=True),
        _item("Sugar-free Dry Cake Slice", 220, 4, 24, 12, cat="dessert", veg=True),
        _item("Multigrain Sandwich (chicken)", 340, 22, 38, 12),
        _item("Veg Sandwich", 280, 10, 40, 8, veg=True),
    ]),
    ("abs_absolute_barbecues", "IN", "AB's Absolute Barbecues", "https://www.absolutebarbecues.com/menu", [
        "abs", "ab's", "absolute barbecues", "ab's absolute barbecues"
    ], [
        _item("Grilled Chicken Tikka", 280, 28, 4, 16),
        _item("Tandoori Fish Tikka", 260, 28, 4, 14),
        _item("Grilled Prawns", 240, 24, 2, 14),
        _item("Veg Kebab Platter", 320, 14, 24, 18, veg=True),
        _item("Salad Bar (portion)", 120, 6, 14, 4, cat="side", veg=True, vgn=True),
    ]),
    ("smoke_house_deli", "IN", "Smoke House Deli", "https://smokehousedeli.com/menu", [
        "smoke house deli", "smokehouse deli", "shd"
    ], [
        _item("Grilled Chicken Salad", 380, 32, 18, 18),
        _item("Smoked Chicken Sandwich", 440, 28, 40, 18),
        _item("Caesar Salad with Grilled Chicken", 360, 28, 14, 22),
        _item("Mediterranean Bowl", 420, 22, 44, 18, veg=True),
        _item("Grilled Fish Fillet", 320, 32, 6, 16),
    ]),
    ("jumboking", "IN", "JumboKing", "https://www.jumboking.in/menu", [
        "jumboking", "jumbo king"
    ], [
        _item("Classic Vada Pav", 280, 7, 38, 10, veg=True, vgn=True),
        _item("Cheese Vada Pav", 340, 10, 38, 14, veg=True),
        _item("Schezwan Vada Pav", 300, 7, 40, 12, veg=True, vgn=True),
        _item("Veggie Burger", 320, 10, 44, 12, veg=True),
    ]),
    ("punjab_grill", "IN", "Punjab Grill", "https://www.punjabgrill.in/menu", [
        "punjab grill"
    ], [
        _item("Tandoori Chicken (half)", 380, 36, 6, 22),
        _item("Dal Makhani (portion)", 320, 12, 28, 18, veg=True),
        _item("Paneer Tikka Masala", 420, 18, 22, 28, veg=True),
        _item("Seekh Kebab (mutton, 2pc)", 320, 24, 4, 22),
        _item("Tawa Roti (whole wheat)", 110, 4, 20, 2, cat="side", veg=True, vgn=True),
    ]),
    ("oh_calcutta", "IN", "Oh! Calcutta", "https://www.ohcalcutta.in/menu", [
        "oh calcutta", "oh! calcutta"
    ], [
        _item("Kosha Mangsho (mutton)", 520, 30, 8, 38),
        _item("Daab Chingri (prawn)", 380, 28, 8, 24),
        _item("Bhetki Paturi (fish)", 320, 30, 4, 20),
        _item("Dhokar Dalna", 280, 12, 24, 16, veg=True, vgn=True),
        _item("Steamed Rice (portion)", 180, 4, 40, 0, cat="side", veg=True, vgn=True),
    ]),
    ("kailash_parbat", "IN", "Kailash Parbat", "https://kailashparbat.in/menu", [
        "kailash parbat", "kp"
    ], [
        _item("Pav Bhaji", 440, 10, 54, 20, veg=True),
        _item("Ragda Pattice", 380, 12, 56, 12, veg=True, vgn=True),
        _item("Chole Bhature (portion)", 620, 18, 78, 26, veg=True),
        _item("Dal Rice", 340, 12, 58, 6, veg=True, vgn=True),
        _item("Sada Dosa", 260, 8, 42, 6, veg=True, vgn=True),
    ]),
    ("rajdhani", "IN", "Rajdhani Thali Restaurant", "https://rajdhanirestaurants.com/menu", [
        "rajdhani", "rajdhani thali"
    ], [
        _item("Rajdhani Thali (unlimited — eat 1 serving)", 620, 20, 92, 18, veg=True),
        _item("Gujarati Kadhi + Rice", 320, 10, 52, 8, veg=True),
        _item("Dal Baati Churma (one set)", 540, 16, 68, 22, veg=True),
    ]),
    ("copper_chimney", "IN", "Copper Chimney", "https://www.copperchimney.in/menu", [
        "copper chimney"
    ], [
        _item("Tandoori Chicken (half)", 420, 38, 8, 24),
        _item("Chicken Tikka Masala", 440, 32, 14, 26),
        _item("Dal Makhani", 340, 12, 30, 18, veg=True),
        _item("Paneer Tikka", 320, 18, 8, 22, veg=True),
        _item("Tawa Roti", 110, 4, 20, 2, cat="side", veg=True, vgn=True),
    ]),
    ("sagar_ratna", "IN", "Sagar Ratna", "https://sagarratna.in/menu", [
        "sagar ratna"
    ], [
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Idli Sambar (4pc)", 280, 10, 52, 4, veg=True, vgn=True),
        _item("Rava Dosa", 360, 9, 54, 12, veg=True),
        _item("Mini Meals (portion)", 440, 14, 72, 10, veg=True),
        _item("Plain Dosa", 260, 8, 42, 6, veg=True, vgn=True),
    ]),
    ("cream_centre", "IN", "Cream Centre", "https://creamcentre.com/menu", [
        "cream centre", "cream center"
    ], [
        _item("Chole Bhature", 660, 18, 80, 28, veg=True),
        _item("Mexican Burrito Bowl (veg)", 480, 18, 58, 18, veg=True),
        _item("Paneer Tikka Masala + Roti", 540, 22, 52, 24, veg=True),
        _item("Lebanese Mezze Platter", 420, 14, 42, 20, veg=True, vgn=True),
        _item("Salad Bowl (hummus + falafel)", 380, 16, 40, 16, veg=True, vgn=True),
    ]),
    ("pind_balluchi", "IN", "Pind Balluchi", "https://www.pindballuchi.com/menu", [
        "pind balluchi"
    ], [
        _item("Tandoori Chicken (half)", 440, 38, 8, 26),
        _item("Chicken Tikka Masala + 2 Roti", 580, 32, 44, 28),
        _item("Dal Bukhara", 340, 12, 28, 18, veg=True),
        _item("Paneer Lababdar", 440, 18, 22, 30, veg=True),
        _item("Seekh Kebab (mutton, 2pc)", 340, 26, 4, 22),
    ]),
    ("vaango", "IN", "Vaango", "https://www.vaango.in/menu", [
        "vaango"
    ], [
        _item("Chicken Biryani (regular)", 540, 30, 62, 20),
        _item("Paneer Biryani (regular)", 520, 18, 64, 22, veg=True),
        _item("Chicken 65", 340, 28, 12, 20),
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Curd Rice", 320, 10, 42, 12, veg=True),
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
