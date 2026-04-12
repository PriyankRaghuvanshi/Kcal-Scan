#!/usr/bin/env python3
"""
Seed expansion v4: India final saturation — 20 more major chains.
Covers US brands with India menus, premium casual dining, and regional
institutions (MTR Bangalore, Murugan Idli Chennai, Karim's Delhi,
Britannia Cafe Mumbai, Bhojohori Manna Kolkata).

Run:  cd backend && python scripts/seed_expansion_v4_india.py
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
    ("wendys", "IN", "Wendy's", "https://www.wendysindia.com/menu", [
        "wendys", "wendy's"
    ], [
        _item("Classic Grilled Chicken Wrap", 340, 26, 34, 12),
        _item("Grilled Chicken Sandwich", 380, 28, 38, 14),
        _item("Spicy Chicken Wrap", 360, 24, 38, 14),
        _item("Veg Wrap", 320, 10, 44, 12, veg=True),
        _item("Caesar Salad (grilled chicken)", 320, 28, 14, 16),
    ]),
    ("carls_jr", "IN", "Carl's Jr.", "https://www.carlsjrindia.com/menu", [
        "carls jr", "carl's jr", "carls junior"
    ], [
        _item("Grilled Chicken Sandwich", 400, 30, 40, 14),
        _item("Charbroiled BBQ Chicken", 420, 32, 40, 16),
        _item("Original Angus Burger (half)", 440, 26, 38, 20),
        _item("Beyond Famous Star (veg)", 540, 28, 46, 28, veg=True),
        _item("Grilled Chicken Salad", 280, 28, 14, 12),
    ]),
    ("dunkin", "IN", "Dunkin'", "https://www.dunkinindia.com/menu", [
        "dunkin", "dunkin'", "dunkin donuts", "dunkin' donuts"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Grilled Chicken Sub (6in)", 360, 26, 38, 10),
        _item("Paneer Kathi Wrap", 420, 18, 42, 20, veg=True),
        _item("Classic Glazed Donut (single)", 260, 3, 31, 14, cat="dessert", veg=True),
    ]),
    ("olive_bistro", "IN", "Olive Bistro", "https://olivebarandkitchen.com/menu", [
        "olive bistro", "olive bar and kitchen", "olive bar & kitchen"
    ], [
        _item("Grilled Chicken Breast + Quinoa", 420, 38, 34, 14),
        _item("Burrata Salad (small)", 380, 18, 14, 28, veg=True),
        _item("Seabass + Vegetables", 380, 36, 12, 22),
        _item("Beetroot Risotto", 440, 16, 56, 18, veg=True),
        _item("Lamb Loin (small portion)", 420, 36, 8, 28),
    ]),
    ("farzi_cafe", "IN", "Farzi Cafe", "https://farzicafe.com/menu", [
        "farzi cafe", "farzi café"
    ], [
        _item("Tandoori Chicken Tikka (half)", 340, 32, 6, 22),
        _item("Dal Chawal Arancini", 380, 14, 48, 14, veg=True),
        _item("Seabass Recheado", 360, 32, 6, 22),
        _item("Galouti Kebab (2pc)", 320, 22, 6, 22),
        _item("Mushroom Galouti (veg, 2pc)", 280, 12, 14, 20, veg=True),
    ]),
    ("mtr", "IN", "MTR (Mavalli Tiffin Rooms)", "https://www.mtrfoods.com/menu", [
        "mtr", "mavalli tiffin rooms", "mtr restaurant"
    ], [
        _item("Rava Idli (2pc)", 240, 7, 44, 5, veg=True, vgn=True),
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Bisi Bele Bath", 340, 11, 50, 10, veg=True),
        _item("Ragi Idli (2pc)", 220, 6, 40, 4, veg=True, vgn=True),
        _item("Curd Rice", 320, 10, 42, 12, veg=True),
        _item("Filter Coffee (no sugar)", 80, 3, 8, 4, cat="beverage", veg=True),
    ]),
    ("murugan_idli_shop", "IN", "Murugan Idli Shop", "https://muruganidlishop.com/menu", [
        "murugan idli shop", "murugan idli"
    ], [
        _item("Idli (2pc)", 140, 6, 28, 1, veg=True, vgn=True),
        _item("Ghee Pongal", 360, 10, 48, 14, veg=True),
        _item("Kaara Dosa", 340, 10, 48, 12, veg=True, vgn=True),
        _item("Ven Pongal + Vada", 420, 12, 58, 14, veg=True),
        _item("Chettinad Chicken Curry + Idiyappam", 520, 28, 48, 24),
    ]),
    ("anjappar", "IN", "Anjappar Chettinad", "https://anjappar.com/menu", [
        "anjappar", "anjappar chettinad"
    ], [
        _item("Chettinad Chicken (half)", 440, 34, 14, 26),
        _item("Chicken 65 (half)", 380, 28, 14, 24),
        _item("Mutton Sukka (portion)", 480, 30, 10, 32),
        _item("Kothu Parotta (chicken)", 560, 26, 62, 22),
        _item("Idiyappam + Chicken Salna", 480, 22, 56, 18),
    ]),
    ("dindigul_thalappakatti", "IN", "Dindigul Thalappakatti", "https://www.thalappakatti.com/menu", [
        "dindigul thalappakatti", "thalappakatti", "dindigul"
    ], [
        _item("Chicken Biryani (regular)", 560, 30, 64, 22),
        _item("Mutton Biryani (regular)", 620, 28, 62, 30),
        _item("Chicken 65 (portion)", 360, 28, 12, 22),
        _item("Boneless Chicken Kola Urundai", 340, 26, 14, 18),
        _item("Prawn Biryani", 540, 26, 62, 20),
    ]),
    ("bhojohori_manna", "IN", "Bhojohori Manna", "https://bhojohorimanna.com/menu", [
        "bhojohori manna", "bhojohori"
    ], [
        _item("Kosha Mangsho (mutton, half)", 460, 28, 8, 32),
        _item("Chicken Kosha", 380, 28, 10, 22),
        _item("Bhetki Paturi", 320, 30, 4, 20),
        _item("Daab Chingri", 380, 26, 8, 26),
        _item("Bengali Veg Thali", 580, 18, 88, 18, veg=True),
    ]),
    ("mamagoto", "IN", "Mamagoto", "https://mamagoto.com/menu", [
        "mamagoto"
    ], [
        _item("Grilled Chicken Bowl (Teriyaki)", 460, 30, 52, 14),
        _item("Bangkok Basil Chicken", 440, 28, 44, 18),
        _item("Kung Pao Chicken + Rice", 520, 28, 60, 20),
        _item("Veg Pad Thai", 480, 14, 66, 16, veg=True),
        _item("Chicken Dim Sum (4pc)", 260, 18, 28, 8),
    ]),
    ("us_pizza", "IN", "US Pizza", "https://uspizza.in/menu", [
        "us pizza", "us pizza india"
    ], [
        _item("Chicken Tikka Personal Pizza", 520, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
        _item("BBQ Chicken Personal", 560, 28, 60, 22),
        _item("Veg Supreme Personal", 480, 16, 66, 14, veg=True),
        _item("Paneer Tikka Personal", 540, 20, 62, 22, veg=True),
    ]),
    ("karims", "IN", "Karim's", "https://karimhoteldelhi.com/menu", [
        "karims", "karim's", "karim hotel"
    ], [
        _item("Mutton Burra (half)", 420, 34, 4, 30),
        _item("Chicken Jahangiri", 440, 32, 12, 28),
        _item("Mutton Seekh Kebab (2pc)", 340, 26, 4, 22),
        _item("Chicken Tikka (half)", 360, 30, 4, 22),
        _item("Biryani (chicken, half)", 520, 28, 60, 20),
    ]),
    ("bademiya", "IN", "Bademiya", "https://bademiya.com/menu", [
        "bademiya", "bade miya"
    ], [
        _item("Seekh Kebab (mutton, 2pc)", 340, 26, 4, 22),
        _item("Chicken Tikka Roll", 440, 26, 42, 18),
        _item("Mutton Masala Roll", 500, 30, 42, 22),
        _item("Chicken Baida Roti", 540, 28, 42, 24),
        _item("Chicken Kebab (boneless, 4pc)", 320, 28, 6, 18),
    ]),
    ("britannia_cafe", "IN", "Britannia & Co.", "https://britanniaco.com/menu", [
        "britannia cafe", "britannia and co", "britannia & co"
    ], [
        _item("Berry Pulao (chicken)", 580, 28, 72, 22),
        _item("Chicken Dhansak + Rice", 620, 32, 64, 26),
        _item("Mutton Berry Pulao", 640, 30, 72, 28),
        _item("Salli Boti", 480, 30, 24, 30),
        _item("Caramel Custard (small)", 220, 4, 28, 10, cat="dessert", veg=True),
    ]),
    ("havmor", "IN", "Havmor", "https://havmor.com/menu", [
        "havmor", "hav mor"
    ], [
        _item("Single Scoop (any flavor)", 140, 3, 18, 7, cat="dessert", veg=True),
        _item("Kulfi Stick", 180, 4, 20, 10, cat="dessert", veg=True),
        _item("Sundae (regular)", 340, 6, 44, 14, cat="dessert", veg=True),
        _item("Havmor Pav Bhaji", 440, 10, 54, 20, veg=True),
    ]),
    ("gianis", "IN", "Giani's", "https://gianis.in/menu", [
        "gianis", "giani's", "giani ice cream", "giani's ice cream"
    ], [
        _item("Single Scoop", 150, 3, 18, 8, cat="dessert", veg=True),
        _item("Belgian Chocolate Scoop", 180, 4, 22, 10, cat="dessert", veg=True),
        _item("Falooda (regular)", 380, 8, 52, 14, cat="dessert", veg=True),
        _item("Thick Shake (small)", 320, 7, 44, 12, cat="beverage", veg=True),
    ]),
    ("mithaas", "IN", "Mithaas", "https://www.mithaas.com/menu", [
        "mithaas", "mithas"
    ], [
        _item("Paneer Butter Masala + Roti", 520, 22, 46, 28, veg=True),
        _item("Chole Bhature", 640, 18, 78, 26, veg=True),
        _item("Rajma Chawal", 380, 14, 62, 8, veg=True, vgn=True),
        _item("Dal Makhani + Roti", 420, 14, 48, 18, veg=True),
        _item("Samosa (single)", 260, 6, 32, 12, cat="side", veg=True),
    ]),
    ("punjabi_by_nature", "IN", "Punjabi by Nature", "https://www.punjabibynature.in/menu", [
        "punjabi by nature", "pbn"
    ], [
        _item("Tandoori Chicken (half)", 440, 38, 8, 26),
        _item("Dal Makhani", 340, 12, 30, 18, veg=True),
        _item("Murgh Tikka Masala", 460, 32, 14, 28),
        _item("Sarson Ka Saag + Makki Roti", 380, 14, 46, 16, veg=True),
        _item("Seekh Kebab (mutton, 2pc)", 340, 26, 4, 22),
    ]),
    ("wow_chicken", "IN", "Wow! Chicken", "https://eatsure.com/wow-chicken/menu", [
        "wow chicken", "wow! chicken"
    ], [
        _item("Grilled Chicken + Rice Bowl", 480, 32, 58, 12),
        _item("Peri Peri Grilled Chicken Wings (6pc)", 320, 28, 4, 22),
        _item("Chicken Tikka Rice Bowl", 520, 30, 62, 16),
        _item("Chicken Shawarma Wrap", 440, 28, 46, 16),
        _item("Grilled Chicken Caesar Salad", 340, 30, 14, 18),
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
    print(f"created: {created}, skipped: {skipped}, total seeds: {len(list(DATA_DIR.glob('*.json')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
