#!/usr/bin/env python3
"""v12: more depth for flagship markets IN/US/AU."""
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
    # ═════════ INDIA +20 ═════════
    ("chai_sutta_bar", "IN", "Chai Sutta Bar", "https://chaisuttabarindia.com/menu", [
        "chai sutta bar", "csb"
    ], [
        _item("Kulhad Chai (no sugar)", 120, 4, 14, 5, cat="beverage", veg=True),
        _item("Elaichi Chai (less sugar)", 130, 4, 16, 5, cat="beverage", veg=True),
        _item("Maggi (regular)", 340, 8, 52, 10, veg=True),
    ]),
    ("tea_villa_cafe", "IN", "Tea Villa Cafe", "https://teavilla.com/menu", [
        "tea villa cafe", "tvc"
    ], [
        _item("Masala Chai (no sugar)", 110, 4, 10, 5, cat="beverage", veg=True),
        _item("Chicken Tikka Wrap", 420, 26, 42, 16),
        _item("Paneer Tikka Wrap", 440, 18, 42, 22, veg=True),
        _item("Grilled Veggie Sandwich", 320, 12, 42, 10, veg=True),
    ]),
    ("cafe_delhi_heights", "IN", "Café Delhi Heights", "https://cafedelhiheights.com/menu", [
        "cafe delhi heights", "café delhi heights"
    ], [
        _item("Chicken Burger (grilled)", 480, 32, 44, 18),
        _item("Paneer Tikka Wrap", 440, 18, 42, 22, veg=True),
        _item("Grilled Chicken Caesar", 440, 32, 18, 26),
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
    ]),
    ("sodabottleopenerwala", "IN", "SodaBottleOpenerWala", "https://sodabottleopenerwala.com/menu", [
        "sodabottleopenerwala", "sbow"
    ], [
        _item("Berry Pulao Chicken", 580, 28, 72, 22),
        _item("Chicken Dhansak + Rice", 620, 32, 64, 26),
        _item("Salli Boti", 480, 30, 24, 30),
        _item("Keema Pav (half)", 420, 24, 38, 20),
    ]),
    ("goila_butter_chicken", "IN", "Goila Butter Chicken", "https://goilabutterchicken.com/menu", [
        "goila butter chicken", "goila"
    ], [
        _item("Butter Chicken (small)", 520, 32, 14, 34),
        _item("Paneer Makhani (small)", 420, 18, 22, 28, veg=True),
        _item("Chicken Tikka Roll", 440, 28, 42, 18),
    ]),
    ("pizza_by_the_bay", "IN", "Pizza by the Bay", "https://pizzabythebay.in/menu", [
        "pizza by the bay"
    ], [
        _item("Grilled Chicken Personal", 520, 28, 60, 18),
        _item("Margherita Personal", 440, 18, 60, 14, veg=True),
        _item("BBQ Chicken Personal", 560, 28, 60, 22),
    ]),
    ("imperfecto", "IN", "The Imperfecto", "https://imperfectorestaurant.com/menu", [
        "imperfecto", "the imperfecto"
    ], [
        _item("Grilled Chicken Platter", 480, 38, 14, 28),
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
        _item("Peri Peri Chicken (portion)", 420, 34, 10, 26),
    ]),
    ("lucknowi_biryani_co", "IN", "Lucknowi Biryani Co.", "https://lucknowibiryanico.com/menu", [
        "lucknowi biryani co", "lucknowi biryani"
    ], [
        _item("Lucknowi Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Dum Biryani", 640, 28, 62, 30),
        _item("Chicken Korma + Roti", 540, 30, 44, 26),
    ]),
    ("ram_ashrey", "IN", "Ram Ashrey", "https://ramashrey.in/menu", [
        "ram ashrey", "ram ashraya"
    ], [
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Idli Sambar (4pc)", 280, 10, 52, 4, veg=True, vgn=True),
        _item("Mini Meals", 480, 16, 72, 12, veg=True),
    ]),
    ("sukh_sagar", "IN", "Sukh Sagar", "https://sukhsagar.in/menu", [
        "sukh sagar"
    ], [
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Pav Bhaji", 440, 10, 54, 20, veg=True),
        _item("South Indian Thali", 560, 18, 86, 14, veg=True),
    ]),
    ("kake_da_hotel", "IN", "Kake Da Hotel", "https://kakedahotel.com/menu", [
        "kake da hotel", "kake da"
    ], [
        _item("Chicken Curry + 2 Roti", 580, 32, 44, 28),
        _item("Butter Chicken + Rice", 620, 32, 62, 28),
        _item("Dal Makhani + Roti", 420, 14, 48, 18, veg=True),
    ]),
    ("dasaprakash", "IN", "Dasaprakash", "https://dasaprakashindia.com/menu", [
        "dasaprakash"
    ], [
        _item("Rava Dosa", 380, 10, 56, 14, veg=True),
        _item("Madras Mini Tiffin", 480, 16, 72, 14, veg=True),
        _item("Chettinad Thali", 580, 20, 86, 14, veg=True),
    ]),
    ("dhaba_junction", "IN", "Dhaba Junction", "https://dhabajunction.com/menu", [
        "dhaba junction"
    ], [
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Dal Tadka + Roti", 380, 14, 46, 16, veg=True),
    ]),
    ("masala_craft", "IN", "Masala Craft", "https://masalacraft.in/menu", [
        "masala craft"
    ], [
        _item("Chicken Tikka Masala + Roti", 540, 32, 44, 26),
        _item("Dal Makhani", 340, 12, 30, 18, veg=True),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
    ]),
    ("lazeez_affaire", "IN", "Lazeez Affaire", "https://lazeezaffaire.com/menu", [
        "lazeez affaire", "lazeez"
    ], [
        _item("Chicken Biryani (half)", 560, 28, 62, 22),
        _item("Mutton Biryani (half)", 620, 26, 60, 30),
        _item("Chicken Tandoori (half)", 420, 36, 6, 26),
    ]),
    ("jalebi", "IN", "Jalebi", "https://jalebi.in/menu", [
        "jalebi"
    ], [
        _item("Jalebi (100g)", 420, 4, 72, 12, cat="dessert", veg=True),
        _item("Rabri + Jalebi (portion)", 520, 8, 80, 16, cat="dessert", veg=True),
    ]),
    ("honest", "IN", "Honest", "https://honestrestaurant.com/menu", [
        "honest", "honest restaurant"
    ], [
        _item("Pav Bhaji", 440, 10, 54, 20, veg=True),
        _item("Dal Tadka + Roti", 380, 14, 46, 16, veg=True),
        _item("Paneer Tikka Masala + Roti", 540, 20, 46, 28, veg=True),
    ]),
    ("chai_patti", "IN", "Chai Patti", "https://chaipatti.com/menu", [
        "chai patti"
    ], [
        _item("Masala Chai (no sugar)", 110, 4, 10, 5, cat="beverage", veg=True),
        _item("Chicken Tikka Sandwich", 380, 24, 40, 12),
        _item("Veggie Sandwich", 280, 10, 40, 8, veg=True),
    ]),
    ("curry_leaf", "IN", "Curry Leaf", "https://curryleaf.in/menu", [
        "curry leaf"
    ], [
        _item("South Indian Thali", 560, 18, 86, 14, veg=True),
        _item("Chettinad Chicken Curry + Rice", 540, 32, 56, 20),
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
    ]),
    ("jai_hind_dhaba", "IN", "Jai Hind Dhaba", "https://jaihindhaba.com/menu", [
        "jai hind dhaba", "jai hind"
    ], [
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Dal Makhani", 340, 12, 30, 18, veg=True),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
    ]),

    # ═════════ USA +15 ═════════
    ("bojangles", "US", "Bojangles", "https://www.bojangles.com/menu", [
        "bojangles"
    ], [
        _item("Grilled Chicken Breast", 180, 24, 1, 9),
        _item("Chicken Supremes (4pc)", 320, 28, 18, 16),
        _item("Cajun Filet Biscuit (no butter)", 420, 22, 38, 22, cat="breakfast"),
    ]),
    ("cook_out", "US", "Cook Out", "https://cookout.com/menu", [
        "cook out", "cookout"
    ], [
        _item("Grilled Chicken Sandwich", 420, 30, 42, 16),
        _item("Big Double Burger (no cheese)", 560, 32, 40, 30),
        _item("Chicken Wrap", 380, 26, 40, 14),
    ]),
    ("captain_ds", "US", "Captain D's", "https://www.captainds.com/menu", [
        "captain ds", "captain d's"
    ], [
        _item("Grilled Tilapia (plain)", 180, 34, 0, 4),
        _item("Grilled Shrimp Skewers", 220, 28, 4, 10),
        _item("Wild Alaskan Salmon (grilled)", 280, 36, 0, 14),
    ]),
    ("long_john_silvers", "US", "Long John Silver's", "https://www.ljsilvers.com/menu", [
        "long john silvers", "long john silver's", "ljs"
    ], [
        _item("Grilled Pacific Salmon", 300, 34, 2, 18),
        _item("Grilled Tilapia", 180, 32, 0, 4),
        _item("Shrimp Scampi", 240, 22, 2, 14),
    ]),
    ("steak_n_shake", "US", "Steak 'n Shake", "https://www.steaknshake.com/menu", [
        "steak n shake", "steak 'n shake", "steak and shake"
    ], [
        _item("Single Steakburger", 380, 22, 28, 20),
        _item("Grilled Chicken Sandwich", 420, 28, 38, 18),
        _item("Taco Salad (no shell)", 340, 28, 20, 16),
    ]),
    ("maggianos", "US", "Maggiano's Little Italy", "https://www.maggianos.com/menu", [
        "maggianos", "maggiano's", "maggianos little italy"
    ], [
        _item("Grilled Chicken Piccata", 540, 42, 38, 26),
        _item("Herb-Grilled Salmon", 460, 44, 10, 28),
        _item("Caesar Salad (chicken)", 480, 34, 18, 32),
    ]),
    ("carrabbas", "US", "Carrabba's Italian Grill", "https://www.carrabbas.com/menu", [
        "carrabbas", "carrabba's"
    ], [
        _item("Chicken Bryan (grilled)", 520, 44, 14, 32),
        _item("Grilled Salmon + Spinach", 480, 44, 8, 28),
        _item("Pollo Rosa Maria", 540, 42, 16, 32),
    ]),
    ("bonefish_grill", "US", "Bonefish Grill", "https://www.bonefishgrill.com/menu", [
        "bonefish grill", "bonefish"
    ], [
        _item("Atlantic Salmon (grilled)", 440, 42, 6, 26),
        _item("Bang Bang Shrimp Tacos", 420, 24, 46, 16),
        _item("Sea Bass (grilled)", 400, 42, 4, 22),
    ]),
    ("joes_crab_shack", "US", "Joe's Crab Shack", "https://www.joescrabshack.com/menu", [
        "joes crab shack", "joe's crab shack", "joes crab"
    ], [
        _item("Snow Crab Legs (1 lb)", 220, 48, 0, 2),
        _item("Grilled Salmon", 360, 40, 2, 18),
        _item("Grilled Shrimp Skewers", 260, 32, 4, 12),
    ]),
    ("johnny_rockets", "US", "Johnny Rockets", "https://www.johnnyrockets.com/menu", [
        "johnny rockets"
    ], [
        _item("Original Burger (half)", 460, 24, 28, 26),
        _item("Grilled Chicken Sandwich", 440, 32, 42, 16),
    ]),
    ("chicken_salad_chick", "US", "Chicken Salad Chick", "https://chickensaladchick.com/menu", [
        "chicken salad chick"
    ], [
        _item("Classic Carol (chicken salad sandwich)", 440, 28, 36, 20),
        _item("Grilled Chicken Salad", 380, 32, 16, 20),
    ]),
    ("pollo_tropical", "US", "Pollo Tropical", "https://www.pollotropical.com/menu", [
        "pollo tropical"
    ], [
        _item("Grilled Chicken Quarter + Veg", 420, 40, 14, 22),
        _item("Tropichops (chicken, small)", 480, 36, 52, 12),
        _item("Black Beans & Rice", 180, 7, 32, 1, cat="side", veg=True, vgn=True),
    ]),
    ("krystal", "US", "Krystal", "https://www.krystal.com/menu", [
        "krystal"
    ], [
        _item("Original Krystal (1pc)", 160, 7, 16, 7),
        _item("Chicken Krystal (1pc)", 200, 10, 20, 9),
    ]),
    ("godiva", "US", "Godiva Chocolatier", "https://www.godiva.com/menu", [
        "godiva", "godiva chocolatier"
    ], [
        _item("Dark Chocolate Truffle (single)", 70, 1, 7, 5, cat="dessert", veg=True),
        _item("Milk Chocolate Bar (50g)", 270, 4, 28, 16, cat="dessert", veg=True),
    ]),
    ("sees_candies", "US", "See's Candies", "https://www.sees.com/menu", [
        "sees candies", "see's candies"
    ], [
        _item("Dark Chocolate Lollypop", 80, 1, 12, 4, cat="dessert", veg=True),
        _item("California Brittle (1oz)", 140, 2, 16, 8, cat="dessert", veg=True),
    ]),

    # ═════════ AUSTRALIA +10 ═════════
    ("zeus_street_greek", "AU", "Zeus Street Greek", "https://zeusstreetgreek.com.au/menu", [
        "zeus street greek", "zeus"
    ], [
        _item("Chicken Gyro (grilled)", 480, 32, 42, 18),
        _item("Greek Salad + Chicken", 380, 30, 18, 22),
        _item("Lamb Souvlaki Wrap", 520, 34, 46, 22),
    ]),
    ("salsas_fresh_mex", "AU", "Salsa's Fresh Mex Grill", "https://salsas.com.au/menu", [
        "salsas", "salsa's", "salsas fresh mex"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 34, 58, 16),
        _item("Beef Burrito Bowl", 560, 32, 58, 22),
        _item("Veggie Bowl", 420, 14, 60, 12, veg=True),
    ]),
    ("pie_face", "AU", "Pie Face", "https://pieface.com.au/menu", [
        "pie face", "pieface"
    ], [
        _item("Chicken & Mushroom Pie", 440, 24, 38, 22),
        _item("Beef & Veg Pie", 460, 22, 40, 24),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
    ]),
    ("degani", "AU", "Degani", "https://degani.com.au/menu", [
        "degani", "degani bakery", "degani bakery cafe"
    ], [
        _item("Grilled Chicken Focaccia", 440, 28, 42, 16),
        _item("Caesar Salad (chicken)", 440, 32, 18, 26),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
    ]),
    ("olivers_real_food", "AU", "Oliver's Real Food", "https://oliversrealfood.com.au/menu", [
        "olivers real food", "oliver's real food", "olivers"
    ], [
        _item("Organic Grilled Chicken Salad", 380, 32, 18, 18),
        _item("Vegan Wrap", 360, 12, 44, 14, veg=True, vgn=True),
        _item("Turkey & Cranberry Wrap", 420, 26, 42, 16),
    ]),
    ("cibo", "AU", "Cibo Espresso", "https://cibo.com.au/menu", [
        "cibo", "cibo espresso"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Panino Pollo (chicken)", 420, 28, 42, 16),
        _item("Insalata + Pollo", 380, 30, 18, 20),
    ]),
    ("three_beans", "AU", "Three Beans", "https://threebeans.com.au/menu", [
        "three beans", "3 beans"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Grilled Chicken Wrap", 380, 26, 40, 12),
    ]),
    ("nene_chicken_au", "AU", "Nene Chicken", "https://nenechicken.com.au/menu", [
        "nene chicken", "nene"
    ], [
        _item("Half Chicken (original)", 540, 32, 20, 34),
        _item("Chicken Tenders (4pc)", 380, 32, 16, 20),
        _item("Soy Garlic Wings (6pc)", 360, 30, 10, 22),
    ]),
    ("pita_pit_au", "AU", "Pita Pit", "https://pitapit.com.au/menu", [
        "pita pit"
    ], [
        _item("Grilled Chicken Pita", 380, 30, 42, 10),
        _item("Turkey Breast Pita", 340, 24, 42, 8),
        _item("Falafel Pita", 420, 14, 54, 16, veg=True, vgn=True),
    ]),
    ("boost_juice_au_v2", "AU", "Boost Juice Smoothies", "https://www.boostjuice.com.au/menu", [
        "boost juice smoothies"
    ], [
        _item("Protein Supreme Smoothie (medium)", 360, 26, 42, 8, cat="beverage", veg=True),
        _item("Mango Magic (medium, no sugar add)", 220, 2, 52, 1, cat="beverage", veg=True, vgn=True),
        _item("Berry Bang (medium)", 200, 2, 46, 1, cat="beverage", veg=True, vgn=True),
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
