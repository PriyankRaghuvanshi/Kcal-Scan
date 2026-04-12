#!/usr/bin/env python3
"""v14: hand-picked edge-case chains. Multi-outlet niche brands for IN/US/AU."""
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"


def _item(name, cal, pro, carb, fat, cat="entree", conf=0.78, veg=False, vgn=False):
    return {
        "item_name": name, "category": cat,
        "estimated_calories": cal, "estimated_protein_g": pro,
        "estimated_carbs_g": carb, "estimated_fat_g": fat,
        "confidence": conf, "vegetarian_possible": veg, "vegan_possible": vgn,
    }


SEEDS = [
    # ═════════ INDIA +12 ═════════
    ("mast_kalandar", "IN", "Mast Kalandar", "https://mastkalandar.com/menu", [
        "mast kalandar"
    ], [
        _item("Rajma Chawal", 380, 14, 62, 8, veg=True, vgn=True),
        _item("Chole Chawal", 420, 16, 66, 10, veg=True, vgn=True),
        _item("Dal Makhani + Rice", 440, 14, 56, 18, veg=True),
        _item("Paneer Butter Masala Bowl", 520, 20, 42, 28, veg=True),
    ]),
    ("aslam_chicken", "IN", "Aslam Chicken", "https://aslamchicken.com/menu", [
        "aslam chicken", "aslam butter chicken"
    ], [
        _item("Aslam Butter Chicken (half)", 520, 32, 12, 36),
        _item("Chicken Seekh Kebab (4pc)", 320, 26, 4, 20),
        _item("Mughlai Parantha + Chicken", 580, 28, 52, 28),
    ]),
    ("moustache_escapes", "IN", "Moustache Escapes", "https://moustacheescapes.com/menu", [
        "moustache escapes", "moustache"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 60, 18),
        _item("Margherita Personal", 440, 18, 60, 14, veg=True),
        _item("BBQ Chicken Personal", 560, 28, 60, 22),
    ]),
    ("smokeys_bbq", "IN", "Smokey's BBQ", "https://smokeysbbq.com/menu", [
        "smokeys bbq", "smokey's bbq"
    ], [
        _item("Smoked Chicken (half)", 440, 40, 12, 24),
        _item("BBQ Ribs (half rack)", 620, 40, 22, 38),
        _item("Pulled Chicken Sandwich", 540, 32, 42, 26),
    ]),
    ("burger_farm", "IN", "Burger Farm", "https://burgerfarm.in/menu", [
        "burger farm"
    ], [
        _item("Grilled Chicken Burger", 480, 32, 42, 20),
        _item("Classic Beef Burger", 560, 32, 42, 28),
        _item("Veggie Burger", 440, 16, 52, 20, veg=True),
    ]),
    ("chicago_pizza", "IN", "Chicago Pizza", "https://chicagopizza.in/menu", [
        "chicago pizza"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 60, 20),
        _item("Deep Dish Pepperoni Slice", 440, 22, 42, 22),
        _item("Margherita Personal", 480, 18, 62, 16, veg=True),
    ]),
    ("garcias_pizza", "IN", "Garcia's Pizza", "https://garciaspizza.com/menu", [
        "garcias pizza", "garcia's pizza"
    ], [
        _item("BBQ Chicken Personal", 560, 28, 60, 22),
        _item("Margherita Personal", 480, 18, 62, 16, veg=True),
    ]),
    ("barbeque_pride", "IN", "Barbeque Pride", "https://barbequepride.com/menu", [
        "barbeque pride"
    ], [
        _item("Grilled Chicken Tikka", 280, 28, 4, 16),
        _item("Tandoori Fish Tikka", 260, 28, 4, 14),
        _item("Mutton Seekh Kebab (2pc)", 340, 26, 4, 22),
    ]),
    ("bombay_salsa", "IN", "Bombay Salsa", "https://bombaysalsa.com/menu", [
        "bombay salsa"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 34, 58, 16),
        _item("Veggie Burrito Bowl", 440, 14, 62, 12, veg=True, vgn=True),
    ]),
    ("toriyard", "IN", "Toriyard", "https://toriyard.com/menu", [
        "toriyard"
    ], [
        _item("Chicken Yakitori Skewers (4pc)", 320, 28, 6, 18),
        _item("Chicken Katsu Curry", 540, 30, 58, 22),
    ]),
    ("house_of_candy", "IN", "House of Candy", "https://houseofcandy.in/menu", [
        "house of candy"
    ], [
        _item("Assorted Chocolate (100g)", 520, 6, 56, 30, cat="dessert", veg=True),
        _item("Gummy Bears (100g)", 320, 4, 76, 0, cat="dessert", veg=True),
    ]),
    ("pita_pit_in", "IN", "Pita Pit", "https://pitapit.in/menu", [
        "pita pit"
    ], [
        _item("Grilled Chicken Pita", 380, 30, 42, 10),
        _item("Falafel Pita", 420, 14, 54, 16, veg=True, vgn=True),
        _item("Salad Bowl Chicken", 280, 28, 14, 10),
    ]),

    # ═════════ USA +10 ═════════
    ("the_habit", "US", "The Habit Burger Grill", "https://www.habitburger.com/menu", [
        "the habit", "habit burger", "the habit burger grill"
    ], [
        _item("Charburger (original)", 460, 24, 30, 26),
        _item("Grilled Chicken Sandwich", 440, 30, 38, 20),
        _item("Albacore Tuna Sandwich", 400, 22, 38, 16),
    ]),
    ("saladworks", "US", "Saladworks", "https://www.saladworks.com/menu", [
        "saladworks"
    ], [
        _item("Classic Chicken Caesar", 420, 34, 18, 22),
        _item("Farmer's Harvest (chicken)", 440, 32, 32, 20),
        _item("Mediterranean Chicken Wrap", 460, 30, 46, 18),
    ]),
    ("wahoos_fish_taco", "US", "Wahoo's Fish Taco", "https://wahoos.com/menu", [
        "wahoos", "wahoo's fish taco"
    ], [
        _item("Grilled Fish Taco (1pc)", 220, 18, 22, 8),
        _item("Chicken Bowl (small)", 440, 32, 44, 14),
        _item("Carne Asada Taco", 240, 18, 22, 10),
    ]),
    ("fogo_de_chao", "US", "Fogo de Chão", "https://fogodechao.com/menu", [
        "fogo", "fogo de chao", "fogo de chão"
    ], [
        _item("Churrasco Grilled Meats (per serving)", 280, 32, 0, 18),
        _item("Market Table Salad", 120, 4, 18, 4, cat="side", veg=True, vgn=True),
        _item("Grilled Chicken Breast", 180, 32, 0, 8),
    ]),
    ("texas_de_brazil", "US", "Texas de Brazil", "https://texasdebrazil.com/menu", [
        "texas de brazil"
    ], [
        _item("Churrasco Grilled Meats (per serving)", 300, 34, 0, 18),
        _item("Salad Bar Table (veg)", 140, 6, 20, 4, cat="side", veg=True, vgn=True),
    ]),
    ("bahama_breeze", "US", "Bahama Breeze", "https://www.bahamabreeze.com/menu", [
        "bahama breeze"
    ], [
        _item("Wood-Grilled Chicken Breast", 360, 40, 8, 18),
        _item("Jamaican Grilled Chicken", 460, 40, 22, 22),
        _item("Seafood Paella (half)", 480, 32, 44, 18),
    ]),
    ("ruby_tuesday", "US", "Ruby Tuesday", "https://www.rubytuesday.com/menu", [
        "ruby tuesday"
    ], [
        _item("Grilled Sirloin 6oz + Veg", 400, 42, 12, 22),
        _item("Grilled Salmon", 440, 40, 6, 26),
        _item("Turkey Avocado Burger", 520, 36, 40, 24),
    ]),
    ("o_charleys", "US", "O'Charley's", "https://www.ocharleys.com/menu", [
        "ocharleys", "o'charleys", "o charleys"
    ], [
        _item("Grilled Chicken + Broccoli", 380, 40, 14, 18),
        _item("Grilled Salmon", 420, 38, 6, 24),
        _item("Chicken Tender Salad (no dressing)", 480, 38, 20, 24),
    ]),
    ("salata", "US", "Salata", "https://salata.com/menu", [
        "salata"
    ], [
        _item("Chicken Caesar Salad", 420, 34, 18, 22),
        _item("Mediterranean Bowl (chicken)", 460, 32, 42, 18),
        _item("Vegan Power Bowl", 380, 16, 56, 10, veg=True, vgn=True),
    ]),
    ("veggie_grill", "US", "Veggie Grill", "https://www.veggiegrill.com/menu", [
        "veggie grill"
    ], [
        _item("Kale Caesar Salad (vegan)", 380, 16, 22, 24, veg=True, vgn=True),
        _item("All Hail Kale Bowl", 480, 18, 54, 18, veg=True, vgn=True),
        _item("Buffalo Wings (vegan)", 360, 22, 36, 14, veg=True, vgn=True),
    ]),

    # ═════════ AUSTRALIA +6 ═════════
    ("chooks_fresh_tasty", "AU", "Chooks Fresh & Tasty", "https://chooks.com.au/menu", [
        "chooks", "chooks fresh tasty", "chooks fresh & tasty"
    ], [
        _item("Quarter Chicken + Salad", 420, 34, 14, 24),
        _item("Half Chicken", 560, 58, 4, 30),
        _item("Chicken Roll", 420, 26, 42, 18),
    ]),
    ("donut_time", "AU", "Donut Time", "https://donuttime.com.au/menu", [
        "donut time"
    ], [
        _item("Original Glazed Donut", 220, 3, 26, 12, cat="dessert", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("nudie_juice", "AU", "Nudie", "https://www.nudie.com.au/menu", [
        "nudie", "nudie juice"
    ], [
        _item("Orange Juice (250ml)", 120, 2, 28, 0, cat="beverage", veg=True, vgn=True),
        _item("Apple & Ginger Juice (250ml)", 110, 0, 28, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("gozleme_king", "AU", "Gozleme King", "https://gozlemeking.com.au/menu", [
        "gozleme king"
    ], [
        _item("Chicken Gözleme", 440, 26, 48, 16),
        _item("Spinach & Feta Gözleme", 380, 16, 48, 14, veg=True),
        _item("Lamb & Feta Gözleme", 480, 28, 46, 20),
    ]),
    ("pizza_napoli", "AU", "Pizza Napoli", "https://pizzanapoli.com.au/menu", [
        "pizza napoli"
    ], [
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
        _item("Napoli Personal", 560, 26, 58, 24),
        _item("Prosciutto Personal", 580, 28, 58, 26),
    ]),
    ("burger_project", "AU", "Burger Project", "https://burgerproject.com/menu", [
        "burger project"
    ], [
        _item("Classic Burger", 560, 32, 42, 28),
        _item("Grilled Chicken Burger", 480, 34, 42, 20),
        _item("Veggie Burger", 460, 16, 54, 20, veg=True),
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
