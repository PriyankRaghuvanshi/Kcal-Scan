#!/usr/bin/env python3
"""v15: chains surfaced by find_coverage_gaps.py from real prod data."""
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
    # ═════════ USA ═════════
    ("blaze_pizza", "US", "Blaze Pizza", "https://www.blazepizza.com/menu", [
        "blaze pizza", "blaze"
    ], [
        _item("Build-Your-Own 11in (veg)", 580, 20, 82, 18, veg=True),
        _item("Red Vine (chicken)", 620, 30, 78, 22),
        _item("BBQ Chicken Pizza", 640, 32, 78, 22),
        _item("High Rise Dough (smaller base)", 420, 18, 58, 12, veg=True),
    ]),
    ("tender_greens", "US", "Tender Greens", "https://www.tendergreens.com/menu", [
        "tender greens"
    ], [
        _item("Simple Salad with Grilled Chicken", 420, 34, 18, 22),
        _item("Salmon Niçoise Salad", 480, 32, 24, 28),
        _item("Falafel Salad (vegan)", 440, 18, 50, 18, veg=True, vgn=True),
        _item("Grilled Flat Iron Steak Plate", 520, 38, 40, 22),
    ]),
    ("800_degrees", "US", "800 Degrees Woodfired Kitchen", "https://www.800degrees.com/menu", [
        "800 degrees", "800 degrees woodfired", "800 degrees woodfired kitchen"
    ], [
        _item("Build-Your-Own Neopolitan (veg)", 540, 20, 68, 18, veg=True),
        _item("Margherita", 560, 22, 64, 20, veg=True),
        _item("Chicken Parmigiana Pizza", 620, 32, 70, 22),
    ]),
    ("carmines", "US", "Carmine's", "https://www.carminesnyc.com/menu", [
        "carmines", "carmine's"
    ], [
        _item("Chicken Scarpariello (share, per portion)", 520, 42, 22, 28),
        _item("Rigatoni Country Style (half)", 540, 24, 62, 22),
        _item("Grilled Salmon", 440, 42, 8, 24),
    ]),
    ("juniors", "US", "Junior's Restaurant & Bakery", "https://www.juniorscheesecake.com/menu", [
        "juniors", "junior's", "juniors restaurant", "junior's restaurant & bakery"
    ], [
        _item("Grilled Chicken Deli Sandwich", 480, 32, 44, 20),
        _item("Turkey Club", 520, 32, 44, 22),
        _item("Junior's Original Cheesecake Slice", 410, 7, 40, 24, cat="dessert", veg=True),
    ]),
    ("annas_taqueria", "US", "Anna's Taqueria", "https://annastaqueria.com/menu", [
        "annas taqueria", "anna's taqueria"
    ], [
        _item("Grilled Chicken Burrito", 620, 34, 62, 26),
        _item("Steak Taco (1pc)", 240, 18, 22, 10),
        _item("Veggie Burrito", 540, 18, 72, 18, veg=True),
    ]),
    ("eataly", "US", "Eataly", "https://www.eataly.com/us_en/menu", [
        "eataly"
    ], [
        _item("Margherita Pizza (personal)", 540, 22, 62, 20, veg=True),
        _item("Grilled Salmon + Vegetables", 460, 42, 8, 28),
        _item("Pasta Pomodoro (half)", 420, 14, 58, 14, veg=True),
    ]),
    ("fairgrounds_coffee", "US", "Fairgrounds Craft Coffee", "https://fairgroundscoffee.com/menu", [
        "fairgrounds", "fairgrounds coffee", "fairgrounds craft coffee"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Turkey Sandwich", 380, 26, 38, 14),
    ]),
    ("chiya_chai", "US", "Chiya Chai", "https://chiyachai.com/menu", [
        "chiya chai"
    ], [
        _item("Masala Chai (no sugar)", 110, 4, 10, 5, cat="beverage", veg=True),
        _item("Chicken Momos (6pc)", 320, 22, 36, 10),
        _item("Veg Momos (6pc)", 260, 10, 42, 8, veg=True),
    ]),
    ("jaho_coffee", "US", "Jaho Coffee Roaster", "https://jahocoffee.com/menu", [
        "jaho", "jaho coffee", "jaho coffee roaster"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Flat White (no sugar)", 110, 6, 8, 6, cat="beverage", veg=True),
        _item("Turkey Avocado Sandwich", 420, 26, 42, 18),
    ]),

    # ═════════ AUSTRALIA ═════════
    ("tobys_estate", "AU", "Toby's Estate Coffee", "https://tobysestate.com.au/menu", [
        "tobys estate", "toby's estate", "tobys estate coffee"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Flat White (no sugar)", 110, 6, 8, 6, cat="beverage", veg=True),
        _item("Cold Brew (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("cali_press", "AU", "Cali Press", "https://calipress.com.au/menu", [
        "cali press"
    ], [
        _item("Green Juice (cold-pressed)", 110, 3, 24, 1, cat="beverage", veg=True, vgn=True),
        _item("Acai Bowl (small)", 380, 8, 62, 10, cat="dessert", veg=True),
        _item("Protein Smoothie Bowl", 420, 26, 52, 10, cat="beverage", veg=True),
    ]),
    ("govindas", "AU", "Govinda's Restaurant", "https://govindas.com.au/menu", [
        "govindas", "govinda's", "govindas hare krishna", "govinda's restaurant"
    ], [
        _item("Vegetarian Thali", 540, 18, 80, 16, veg=True),
        _item("Dal + Rice", 380, 14, 62, 8, veg=True, vgn=True),
        _item("Aloo Gobi + Roti", 440, 14, 58, 16, veg=True),
    ]),

    # ═════════ CANADA ═════════
    ("banh_mi_boys", "CA", "Banh Mi Boys", "https://banhmiboys.com/menu", [
        "banh mi boys"
    ], [
        _item("Classic Banh Mi (pork)", 520, 24, 52, 22),
        _item("Grilled Chicken Banh Mi", 460, 30, 50, 16),
        _item("Tofu Banh Mi", 440, 16, 54, 16, veg=True, vgn=True),
        _item("Steamed Bao (2pc)", 280, 14, 34, 10),
    ]),
    ("artigiano", "CA", "Caffè Artigiano", "https://www.caffeartigiano.com/menu", [
        "artigiano", "caffe artigiano", "caffè artigiano"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Flat White (no sugar)", 110, 6, 8, 6, cat="beverage", veg=True),
    ]),
    ("chickpea", "CA", "Chickpea", "https://chickpea.ca/menu", [
        "chickpea", "chickpea vancouver"
    ], [
        _item("Falafel Pita", 440, 14, 54, 16, veg=True, vgn=True),
        _item("Chickpea Bowl", 480, 18, 62, 14, veg=True, vgn=True),
        _item("Shakshuka", 380, 22, 28, 22, veg=True, cat="breakfast"),
    ]),

    # ═════════ INDIA ═════════
    ("bikkgane_biryani", "IN", "Bikkgane Biryani", "https://bikkgane.com/menu", [
        "bikkgane biryani", "bikkgane"
    ], [
        _item("Chicken Dum Biryani", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("Paneer Biryani", 540, 20, 66, 22, veg=True),
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
