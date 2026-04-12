#!/usr/bin/env python3
"""v16: more local Indian food giants — multi-outlet regional chains."""
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"


def _item(name, cal, pro, carb, fat, cat="entree", conf=0.8, veg=False, vgn=False):
    return {
        "item_name": name, "category": cat,
        "estimated_calories": cal, "estimated_protein_g": pro,
        "estimated_carbs_g": carb, "estimated_fat_g": fat,
        "confidence": conf, "vegetarian_possible": veg, "vegan_possible": vgn,
    }


SEEDS = [
    ("shanti_sagar", "IN", "Shanti Sagar", "https://shantisagarhotels.com/menu", [
        "shanti sagar", "shanti sagar hotel"
    ], [
        _item("Masala Dosa", 380, 10, 56, 14),
        _item("Ghee Roast Dosa", 420, 10, 58, 18),
        _item("Idli Sambar (4pc)", 280, 10, 52, 4),
        _item("Mini Meals", 480, 16, 72, 14),
        _item("Khara Bath + Kesari Bath (set)", 440, 12, 68, 14),
    ]),
    ("kamat", "IN", "Kamat", "https://kamathotels.com/menu", [
        "kamat", "kamat hotels", "kamat yatri niwas"
    ], [
        _item("Kamat Special Thali (veg)", 580, 18, 86, 14),
        _item("Masala Dosa", 380, 10, 56, 14),
        _item("Upma", 260, 8, 42, 8),
        _item("Poha", 320, 7, 52, 8),
    ]),
    ("haveli", "IN", "Haveli", "https://haveliheritage.com/menu", [
        "haveli", "haveli heritage"
    ], [
        _item("Haveli Special Thali", 680, 24, 92, 24),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
        _item("Dal Makhani + 2 Roti", 520, 18, 56, 22),
        _item("Paneer Makhani + 2 Roti", 580, 22, 56, 28),
    ]),
    ("hotel_nayab", "IN", "Hotel Nayab", "https://hotelnayab.com/menu", [
        "hotel nayab", "nayab"
    ], [
        _item("Nayab Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("Chicken Tangdi", 340, 28, 6, 22),
    ]),
    ("wah_ji_wah", "IN", "Wah Ji Wah", "https://wahjiwah.com/menu", [
        "wah ji wah"
    ], [
        _item("Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("Paneer Biryani", 540, 20, 66, 22),
    ]),
    ("chappan_bhog", "IN", "Chappan Bhog", "https://chappanbhog.com/menu", [
        "chappan bhog", "chappan"
    ], [
        _item("Rasmalai (2pc)", 240, 6, 32, 10, cat="dessert"),
        _item("Gulab Jamun (2pc)", 260, 4, 42, 10, cat="dessert"),
        _item("Motichoor Ladoo (2pc)", 320, 6, 44, 14, cat="dessert"),
        _item("Kaju Katli (100g)", 520, 12, 56, 28, cat="dessert"),
    ]),
    ("bengali_sweet_house", "IN", "Bengali Sweet House", "https://bengalisweethouse.com/menu", [
        "bengali sweet house", "bsh"
    ], [
        _item("Rosogolla (2pc)", 180, 4, 32, 4, cat="dessert"),
        _item("Sandesh (100g)", 320, 10, 42, 12, cat="dessert"),
        _item("Rasmalai (2pc)", 240, 6, 32, 10, cat="dessert"),
        _item("Mishti Doi (small cup)", 220, 6, 42, 4, cat="dessert"),
    ]),
    ("shiv_sagar", "IN", "Shiv Sagar", "https://shivsagarhotels.com/menu", [
        "shiv sagar"
    ], [
        _item("Gujarati Thali", 580, 18, 88, 14),
        _item("Pav Bhaji", 440, 10, 54, 20),
        _item("Masala Dosa", 380, 10, 56, 14),
        _item("Sada Dosa", 260, 8, 42, 6),
    ]),
    ("tewari_bros", "IN", "Tewari Brothers", "https://tewaribrothers.com/menu", [
        "tewari bros", "tewari brothers", "tewari"
    ], [
        _item("Malai Kulfi Stick", 220, 4, 28, 10, cat="dessert"),
        _item("Jalebi (100g)", 420, 4, 72, 12, cat="dessert"),
        _item("Gulab Jamun (2pc)", 260, 4, 42, 10, cat="dessert"),
        _item("Kaju Katli (100g)", 520, 12, 56, 28, cat="dessert"),
    ]),
    ("shree_mithai", "IN", "Shree Mithai", "https://shreemithai.com/menu", [
        "shree mithai", "shree"
    ], [
        _item("Motichoor Ladoo (2pc)", 320, 6, 44, 14, cat="dessert"),
        _item("Kaju Katli (100g)", 520, 12, 56, 28, cat="dessert"),
        _item("Gulab Jamun (2pc)", 260, 4, 42, 10, cat="dessert"),
    ]),
    ("delhi_zaika", "IN", "Delhi Zaika", "https://delhizaika.in/menu", [
        "delhi zaika"
    ], [
        _item("Chicken Biryani", 580, 30, 64, 22),
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
        _item("Dal Makhani", 340, 12, 30, 18),
    ]),
    ("embassy_restaurant", "IN", "Embassy Restaurant", "https://embassyrestaurant.in/menu", [
        "embassy", "embassy restaurant"
    ], [
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
        _item("Chicken Shami Kebab (2pc)", 260, 22, 8, 14),
    ]),
    ("natraj_aliwale", "IN", "Natraj Dahi Bhalle Wale", "https://natrajdahibhalle.in/menu", [
        "natraj", "natraj aliwale", "natraj dahi bhalle"
    ], [
        _item("Dahi Bhalla (2pc)", 320, 10, 42, 14),
        _item("Aloo Tikki Chaat", 380, 8, 52, 14),
        _item("Chole Bhature", 640, 18, 78, 26),
    ]),
    ("bombay_chaat", "IN", "Bombay Chaat House", "https://bombaychaat.com/menu", [
        "bombay chaat", "bombay chaat house"
    ], [
        _item("Bhel Puri", 280, 7, 46, 8),
        _item("Sev Puri (6pc)", 340, 8, 52, 12),
        _item("Pani Puri (6pc)", 180, 5, 32, 4),
        _item("Pav Bhaji", 440, 10, 54, 20),
    ]),
    ("punjabi_tadka", "IN", "Punjabi Tadka", "https://punjabitadka.in/menu", [
        "punjabi tadka"
    ], [
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Dal Makhani + 2 Roti", 520, 18, 56, 22),
        _item("Seekh Kebab Mutton (2pc)", 340, 26, 4, 22),
    ]),
    ("desi_punjab", "IN", "Desi Punjab", "https://desipunjab.in/menu", [
        "desi punjab"
    ], [
        _item("Sarson Ka Saag + Makki Roti", 380, 14, 46, 16),
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Dal Makhani + Rice", 460, 16, 60, 16),
    ]),
    ("konkan_cafe", "IN", "Konkan Cafe", "https://konkancafe.in/menu", [
        "konkan cafe", "konkan"
    ], [
        _item("Malvani Chicken Curry + Rice", 520, 32, 54, 20),
        _item("Prawn Gassi + Neer Dosa", 520, 30, 52, 20),
        _item("Solkadhi (small glass)", 60, 2, 10, 2, cat="beverage"),
        _item("Fish Thali", 620, 38, 66, 22),
    ]),
    ("punjab_sindh", "IN", "Punjab Sindh", "https://punjabsindh.in/menu", [
        "punjab sindh", "punjab sind"
    ], [
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Dal Makhani", 340, 12, 30, 18),
        _item("Sindhi Kadhi + Rice", 440, 14, 56, 18),
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
