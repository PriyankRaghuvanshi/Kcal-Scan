#!/usr/bin/env python3
"""v13: more flagship depth — IN/US/AU long-tail."""
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
    # ═════════ INDIA +15 ═════════
    ("jimmy_boy", "IN", "Jimmy Boy", "https://jimmyboycafe.com/menu", [
        "jimmy boy", "jimmy boy cafe"
    ], [
        _item("Berry Pulao Chicken", 580, 28, 72, 22),
        _item("Chicken Dhansak + Rice", 620, 32, 64, 26),
        _item("Salli Boti", 480, 30, 24, 30),
        _item("Caramel Custard", 220, 4, 28, 10, cat="dessert", veg=True),
    ]),
    ("kyani_and_co", "IN", "Kyani & Co.", "https://kyaniandco.com/menu", [
        "kyani", "kyani and co", "kyani & co"
    ], [
        _item("Keema Pav (half)", 420, 24, 38, 20),
        _item("Omelette Pav", 380, 18, 30, 22, cat="breakfast"),
        _item("Mutton Cutlet (2pc)", 320, 24, 8, 22),
    ]),
    ("yazdani_bakery", "IN", "Yazdani Bakery", "https://yazdanibakery.com/menu", [
        "yazdani", "yazdani bakery"
    ], [
        _item("Bun Maska (no jam)", 280, 8, 32, 14, cat="breakfast", veg=True),
        _item("Mawa Cake Slice", 360, 6, 42, 16, cat="dessert", veg=True),
        _item("Cheese Omelette", 320, 18, 4, 26, cat="breakfast", veg=True),
    ]),
    ("chaina_ram", "IN", "Chaina Ram", "https://chainaram.com/menu", [
        "chaina ram", "chaina ram sindhi"
    ], [
        _item("Karachi Halwa (100g)", 420, 4, 60, 18, cat="dessert", veg=True),
        _item("Gulab Jamun (2pc)", 260, 4, 42, 10, cat="dessert", veg=True),
        _item("Motichoor Ladoo (2pc)", 320, 6, 44, 14, cat="dessert", veg=True),
    ]),
    ("natraj_daribari", "IN", "Natraj Daribari", "https://natrajdaribari.com/menu", [
        "natraj daribari", "natraj dariba"
    ], [
        _item("Dahi Bhalla (2pc)", 320, 10, 42, 14, veg=True),
        _item("Aloo Tikki Chaat", 380, 8, 52, 14, veg=True),
    ]),
    ("paragon", "IN", "Paragon Restaurant", "https://paragonrestaurant.net/menu", [
        "paragon", "paragon restaurant", "paragon calicut"
    ], [
        _item("Malabar Chicken Biryani", 580, 32, 64, 22),
        _item("Appam + Chicken Stew", 520, 28, 52, 20),
        _item("Fish Curry + Rice (Malabar)", 520, 30, 54, 20),
    ]),
    ("kream_kastle", "IN", "Kream Kastle", "https://kreamkastle.com/menu", [
        "kream kastle"
    ], [
        _item("Malabar Chicken Biryani", 580, 32, 64, 22),
        _item("Fish Pollichathu", 380, 32, 6, 24),
    ]),
    ("french_loaf", "IN", "French Loaf", "https://frenchloaf.co.in/menu", [
        "french loaf"
    ], [
        _item("Chicken Croissant", 380, 18, 36, 18),
        _item("Plain Croissant", 260, 6, 26, 14, cat="breakfast", veg=True),
        _item("Chocolate Slice", 340, 4, 42, 18, cat="dessert", veg=True),
    ]),
    ("mrs_bakeshop", "IN", "Mrs. Bakeshop", "https://mrsbakeshop.in/menu", [
        "mrs bakeshop", "mrs. bakeshop"
    ], [
        _item("Chocolate Brownie", 340, 5, 42, 18, cat="dessert", veg=True),
        _item("Red Velvet Slice", 360, 4, 44, 20, cat="dessert", veg=True),
    ]),
    ("mojo_pizza", "IN", "Mojo Pizza", "https://mojopizza.in/menu", [
        "mojo pizza", "mojo"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("BBQ Chicken Personal", 560, 28, 60, 22),
        _item("Margherita Personal", 460, 18, 60, 14, veg=True),
    ]),
    ("fingerlix", "IN", "Fingerlix", "https://fingerlix.com/menu", [
        "fingerlix"
    ], [
        _item("Chicken Curry Ready Meal", 420, 30, 18, 24),
        _item("Dal Makhani Ready Meal", 340, 12, 30, 18, veg=True),
        _item("Paneer Butter Masala Ready Meal", 420, 18, 22, 28, veg=True),
    ]),
    ("ministry_of_kebabs", "IN", "Ministry Of Kebabs", "https://ministryofkebabs.com/menu", [
        "ministry of kebabs"
    ], [
        _item("Chicken Seekh Kebab (6pc)", 340, 28, 6, 22),
        _item("Mutton Kebab Platter", 480, 32, 12, 32),
        _item("Paneer Tikka Kebab", 320, 18, 10, 22, veg=True),
    ]),
    ("yazdani_cafe", "IN", "Yazdani Restaurant & Bakery", "https://yazdanibakeryrestaurant.com/menu", [
        "yazdani cafe", "yazdani restaurant"
    ], [
        _item("Bun Maska + Chai", 320, 8, 42, 14, cat="breakfast", veg=True),
        _item("Mawa Cake", 360, 6, 42, 16, cat="dessert", veg=True),
    ]),
    ("bombay_duck", "IN", "Bombay Duck Bistro", "https://bombayduckbistro.com/menu", [
        "bombay duck", "bombay duck bistro"
    ], [
        _item("Bombay Duck Fry (6pc)", 320, 26, 10, 18),
        _item("Grilled Pomfret", 360, 34, 2, 22),
        _item("Prawn Koliwada", 380, 30, 14, 22),
    ]),
    ("kareems", "IN", "Kareem's", "https://kareemsrestaurant.com/menu", [
        "kareems", "kareem's"
    ], [
        _item("Mutton Burra (half)", 420, 34, 4, 30),
        _item("Chicken Jahangiri", 440, 32, 12, 28),
        _item("Mutton Biryani (half)", 620, 28, 60, 30),
    ]),

    # ═════════ USA +10 ═════════
    ("fuddruckers", "US", "Fuddruckers", "https://www.fuddruckers.com/menu", [
        "fuddruckers"
    ], [
        _item("1/3 lb Original Burger", 520, 32, 36, 28),
        _item("Grilled Chicken Breast Sandwich", 440, 32, 38, 18),
        _item("Veggie Burger", 440, 18, 54, 16, veg=True),
    ]),
    ("mooyah", "US", "Mooyah Burgers", "https://mooyah.com/menu", [
        "mooyah", "mooyah burgers"
    ], [
        _item("Classic Beef Burger (1 patty)", 460, 26, 30, 24),
        _item("Grilled Chicken Burger", 420, 32, 40, 16),
        _item("Veggie Burger", 480, 18, 56, 20, veg=True),
    ]),
    ("5_napkin_burger", "US", "5 Napkin Burger", "https://5napkinburger.com/menu", [
        "5 napkin burger", "five napkin burger"
    ], [
        _item("Original 5 Napkin Burger (half)", 540, 30, 34, 28),
        _item("Grilled Chicken Burger", 480, 34, 42, 20),
        _item("Caesar Salad (chicken)", 420, 30, 18, 24),
    ]),
    ("sub_zero_nitrogen", "US", "Sub Zero Nitrogen Ice Cream", "https://subzeroicecream.com/menu", [
        "sub zero nitrogen", "subzero ice cream"
    ], [
        _item("Single Scoop (any flavor)", 240, 4, 28, 14, cat="dessert", veg=True),
    ]),
    ("checkers_rallys", "US", "Checkers / Rally's", "https://www.checkers.com/menu", [
        "checkers", "rallys", "rally's"
    ], [
        _item("Big Buford Burger (half)", 460, 24, 32, 22),
        _item("Grilled Chicken Sandwich", 420, 28, 40, 16),
        _item("Baja Chicken Club", 540, 30, 42, 22),
    ]),
    ("brio", "US", "Brio Italian Grille", "https://brioitalian.com/menu", [
        "brio", "brio tuscan grille", "brio italian grille"
    ], [
        _item("Grilled Chicken Milanese", 480, 42, 24, 22),
        _item("Grilled Salmon", 460, 42, 8, 28),
        _item("Caesar Salad + Chicken", 440, 32, 18, 26),
    ]),
    ("bravo", "US", "Bravo Italian Kitchen", "https://bravoitalian.com/menu", [
        "bravo", "bravo italian", "bravo italian kitchen"
    ], [
        _item("Grilled Chicken Piccata", 540, 42, 38, 26),
        _item("Grilled Salmon + Vegetables", 480, 42, 10, 28),
    ]),
    ("romanos_macaroni_grill", "US", "Romano's Macaroni Grill", "https://www.macaronigrill.com/menu", [
        "romanos macaroni grill", "romano's macaroni grill", "macaroni grill"
    ], [
        _item("Chicken Marsala", 540, 42, 38, 26),
        _item("Grilled Salmon", 460, 42, 8, 28),
    ]),
    ("caribou_coffee_us", "US", "Caribou Coffee", "https://www.cariboucoffee.com/menu", [
        "caribou coffee", "caribou"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Turkey Bacon Breakfast Sandwich", 380, 22, 36, 16, cat="breakfast"),
    ]),
    ("freshii_us", "US", "Freshii", "https://www.freshii.com/menu", [
        "freshii"
    ], [
        _item("Pangoa Bowl (chicken)", 460, 32, 54, 12),
        _item("Oaxaca Wrap (chicken)", 480, 30, 46, 18),
        _item("Buddha's Satay (vegan)", 420, 14, 62, 12, veg=True, vgn=True),
    ]),

    # ═════════ AUSTRALIA +8 ═════════
    ("messina", "AU", "Gelato Messina", "https://gelatomessina.com/menu", [
        "messina", "gelato messina"
    ], [
        _item("Single Scoop Gelato", 160, 4, 20, 7, cat="dessert", veg=True),
        _item("Sorbet Scoop", 120, 1, 28, 0, cat="dessert", veg=True, vgn=True),
    ]),
    ("bourke_street_bakery", "AU", "Bourke Street Bakery", "https://bourkestreetbakery.com.au/menu", [
        "bourke street bakery", "bourke st bakery"
    ], [
        _item("Grilled Chicken Sandwich", 380, 24, 40, 14),
        _item("Sourdough + Butter", 240, 7, 40, 6, veg=True),
        _item("Beef Pie (regular)", 460, 22, 40, 24),
    ]),
    ("mecca_coffee", "AU", "Mecca Coffee", "https://mecca.coffee/menu", [
        "mecca coffee", "mecca"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Flat White (no sugar)", 110, 6, 8, 6, cat="beverage", veg=True),
        _item("Cold Brew (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("fonda_mexican", "AU", "Fonda Mexican", "https://fondamexican.com.au/menu", [
        "fonda", "fonda mexican"
    ], [
        _item("Chicken Burrito Bowl", 540, 34, 58, 18),
        _item("Beef Taco (1pc)", 240, 16, 22, 10),
        _item("Veg Quesadilla", 480, 18, 52, 22, veg=True),
    ]),
    ("chicken_treat", "AU", "Chicken Treat", "https://chickentreat.com.au/menu", [
        "chicken treat"
    ], [
        _item("Quarter Chicken + Salad", 420, 34, 14, 24),
        _item("Chicken Treat Classic Burger", 480, 32, 42, 20),
        _item("Grilled Chicken Breast", 340, 42, 4, 14),
    ]),
    ("lot_burger", "AU", "Lot Burger", "https://lotburger.com.au/menu", [
        "lot burger", "lot"
    ], [
        _item("Classic Burger", 560, 32, 42, 28),
        _item("Grilled Chicken Burger", 480, 34, 42, 20),
        _item("Veggie Burger", 460, 16, 54, 20, veg=True),
    ]),
    ("5_and_dime_bagel", "AU", "5 & Dime Bagel", "https://5anddime.com.au/menu", [
        "5 and dime", "5 & dime", "five and dime bagel"
    ], [
        _item("Smoked Salmon Bagel", 420, 24, 44, 14),
        _item("Grilled Chicken Bagel", 380, 26, 42, 12),
        _item("Plain Bagel + Cream Cheese", 340, 12, 52, 10, cat="breakfast", veg=True),
    ]),
    ("iggys", "AU", "Iggy's Bread", "https://iggysbread.com.au/menu", [
        "iggys", "iggy's", "iggys bread"
    ], [
        _item("Sourdough Sandwich (chicken)", 380, 24, 42, 12),
        _item("Veg Sandwich", 320, 10, 42, 12, veg=True),
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
