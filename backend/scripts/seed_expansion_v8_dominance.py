#!/usr/bin/env python3
"""
Seed expansion v8: total market dominance for IN, US, AU.
IN +30 (regional institutions, Mumbai seafood, Kolkata biryani, Delhi classics, coffee/tea).
US +20 (Mexican chains, specialty coffee, breakfast, salads).
AU +10 (donuts, ice cream, vegan burger, premium).
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
    # ═════════════ INDIA +30 ═════════════
    ("aminia", "IN", "Aminia", "https://aminia.com/menu", [
        "aminia", "aminia restaurant"
    ], [
        _item("Aminia Chicken Biryani", 580, 30, 64, 22),
        _item("Aminia Mutton Biryani", 640, 28, 62, 30),
        _item("Chicken Rezala (half)", 420, 32, 8, 28),
        _item("Mutton Rezala (half)", 520, 32, 8, 36),
    ]),
    ("arsalan", "IN", "Arsalan", "https://www.arsalan.in/menu", [
        "arsalan", "arsalan restaurant"
    ], [
        _item("Arsalan Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("Chicken Chaap (half)", 380, 28, 8, 24),
        _item("Mughlai Mutton (half)", 520, 32, 8, 36),
    ]),
    ("shiraz", "IN", "Shiraz Golden Restaurant", "https://shirazgoldenrestaurant.com/menu", [
        "shiraz", "shiraz golden", "shiraz restaurant"
    ], [
        _item("Shiraz Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("Chicken Rezala", 420, 32, 8, 28),
    ]),
    ("gajalee", "IN", "Gajalee", "https://gajalee.com/menu", [
        "gajalee"
    ], [
        _item("Bombay Duck Fry (6pc)", 320, 26, 10, 18),
        _item("Prawn Koliwada", 380, 30, 14, 22),
        _item("Grilled Pomfret", 360, 34, 2, 22),
        _item("Crab Masala (small)", 440, 32, 14, 26),
    ]),
    ("trishna", "IN", "Trishna", "https://trishnamumbai.com/menu", [
        "trishna"
    ], [
        _item("Koliwada Prawns", 380, 30, 14, 22),
        _item("Hyderabadi Pomfret", 380, 34, 4, 22),
        _item("Butter Garlic Crab (small)", 440, 32, 14, 26),
        _item("Prawn Curry + Rice", 520, 32, 54, 18),
    ]),
    ("mahesh_lunch_home", "IN", "Mahesh Lunch Home", "https://maheshlunchhome.com/menu", [
        "mahesh lunch home", "mahesh"
    ], [
        _item("Grilled Pomfret", 360, 34, 2, 22),
        _item("Prawn Gassi + Rice", 520, 32, 54, 20),
        _item("Bombil Fry (6pc)", 320, 26, 10, 18),
        _item("Crab Curry + Rice", 540, 32, 54, 24),
    ]),
    ("swagath", "IN", "Swagath", "https://swagathmumbai.com/menu", [
        "swagath"
    ], [
        _item("Grilled Pomfret", 360, 34, 2, 22),
        _item("Mangalore Chicken Ghee Roast", 420, 32, 14, 26),
        _item("Prawn Curry + Neer Dosa", 520, 30, 52, 20),
    ]),
    ("highway_gomantak", "IN", "Highway Gomantak", "https://highwaygomantak.in/menu", [
        "highway gomantak", "gomantak"
    ], [
        _item("Fish Thali (pomfret)", 620, 38, 66, 22),
        _item("Prawn Thali", 640, 34, 64, 26),
        _item("Crab Thali", 680, 38, 60, 30),
    ]),
    ("bhagat_tarachand", "IN", "Bhagat Tarachand", "https://bhagattarachand.com/menu", [
        "bhagat tarachand", "bhagat"
    ], [
        _item("Dal Bati (1 set)", 540, 16, 68, 22, veg=True),
        _item("Gatta Curry + Roti (2)", 480, 16, 60, 18, veg=True),
        _item("Veg Thali (portion)", 620, 22, 88, 18, veg=True),
    ]),
    ("veer_ji_malai_chaap", "IN", "Veer Ji Malai Chaap Wale", "https://veerjimalaichaap.com/menu", [
        "veer ji malai chaap", "veer ji"
    ], [
        _item("Malai Chaap (half, veg)", 380, 22, 14, 24, veg=True),
        _item("Afghani Chaap (half)", 420, 24, 12, 28, veg=True),
        _item("Chaap Curry + 2 Roti", 520, 24, 56, 24, veg=True),
    ]),
    ("gulati", "IN", "Gulati", "https://www.gulatirestaurant.com/menu", [
        "gulati", "gulati restaurant"
    ], [
        _item("Tandoori Chicken (half)", 440, 38, 8, 26),
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Dal Makhani", 340, 12, 30, 18, veg=True),
        _item("Seekh Kebab (mutton, 2pc)", 340, 26, 4, 22),
    ]),
    ("chor_bizarre", "IN", "Chor Bizarre", "https://chorbizarrre.com/menu", [
        "chor bizarre"
    ], [
        _item("Kashmiri Rogan Josh", 520, 32, 14, 34),
        _item("Tandoori Chicken", 380, 32, 6, 22),
        _item("Shammi Kebab (2pc)", 260, 22, 8, 14),
        _item("Kashmiri Pulao (veg)", 480, 12, 72, 16, veg=True),
    ]),
    ("chutneys", "IN", "Chutneys", "https://chutneys.in/menu", [
        "chutneys"
    ], [
        _item("Pesarattu Upma", 420, 14, 58, 14, veg=True, vgn=True),
        _item("Special Dosa", 380, 10, 54, 14, veg=True),
        _item("Idli Vada (3pc idli + 2 vada)", 380, 14, 56, 12, veg=True),
        _item("Mini Tiffin", 460, 16, 66, 14, veg=True),
    ]),
    ("bawarchi", "IN", "Bawarchi", "https://bawarchibiryani.com/menu", [
        "bawarchi", "bawarchi biryani"
    ], [
        _item("Hyderabadi Chicken Biryani (half)", 580, 30, 64, 22),
        _item("Mutton Biryani (half)", 640, 28, 62, 30),
        _item("Chicken 65 (portion)", 360, 28, 14, 22),
    ]),
    ("pindi", "IN", "Pindi Restaurant", "https://pindirestaurant.com/menu", [
        "pindi", "pindi restaurant"
    ], [
        _item("Tandoori Chicken (half)", 440, 38, 8, 26),
        _item("Mutton Rogan Josh + Roti", 580, 32, 38, 32),
        _item("Dal Makhani", 340, 12, 30, 18, veg=True),
        _item("Seekh Kebab (2pc)", 340, 26, 4, 22),
    ]),
    ("6_ballygunge_place", "IN", "6 Ballygunge Place", "https://6ballygunge.com/menu", [
        "6 ballygunge place", "6bp", "ballygunge place"
    ], [
        _item("Kosha Mangsho (half)", 460, 30, 8, 32),
        _item("Chicken Kosha", 380, 28, 10, 22),
        _item("Bhetki Paturi", 320, 30, 4, 20),
        _item("Daab Chingri", 380, 28, 8, 26),
    ]),
    ("karachi_bakery", "IN", "Karachi Bakery", "https://karachibakery.com/menu", [
        "karachi bakery"
    ], [
        _item("Fruit Biscuit (100g)", 440, 8, 60, 18, cat="snack", veg=True),
        _item("Cashew Badam Biscuit (100g)", 520, 10, 54, 28, cat="snack", veg=True),
        _item("Plum Cake Slice", 320, 5, 48, 10, cat="dessert", veg=True),
    ]),
    ("kayani_bakery", "IN", "Kayani Bakery", "https://kayanibakery.com/menu", [
        "kayani bakery", "kayani"
    ], [
        _item("Shrewsbury Biscuits (100g)", 480, 6, 58, 24, cat="snack", veg=True),
        _item("Mawa Cake Slice", 360, 6, 44, 16, cat="dessert", veg=True),
    ]),
    ("ghasitarams", "IN", "Ghasitaram's", "https://ghasitarams.com/menu", [
        "ghasitarams", "ghasitaram's"
    ], [
        _item("Kaju Katli (100g)", 520, 12, 56, 28, cat="dessert", veg=True),
        _item("Motichoor Ladoo (2pc)", 320, 6, 44, 14, cat="dessert", veg=True),
        _item("Kalakand (100g)", 440, 14, 48, 22, cat="dessert", veg=True),
    ]),
    ("di_bella_coffee", "IN", "Di Bella Coffee", "https://dibellacoffee.in/menu", [
        "di bella coffee", "di bella", "dibella"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Chicken Focaccia Sandwich", 420, 26, 42, 16),
    ]),
    ("tea_trails", "IN", "Tea Trails", "https://teatrails.in/menu", [
        "tea trails"
    ], [
        _item("Masala Chai (no sugar)", 110, 4, 10, 5, cat="beverage", veg=True),
        _item("Darjeeling Tea (unsweetened)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Roll (tea time)", 340, 22, 38, 12),
        _item("Grilled Veggie Sandwich", 300, 10, 42, 10, veg=True),
    ]),
    ("corner_house", "IN", "Corner House", "https://cornerhouseicecreams.com/menu", [
        "corner house", "corner house ice creams"
    ], [
        _item("Death by Chocolate (small)", 380, 6, 48, 18, cat="dessert", veg=True),
        _item("Single Scoop (any)", 180, 3, 22, 9, cat="dessert", veg=True),
        _item("Hot Chocolate Fudge (small)", 420, 7, 52, 22, cat="dessert", veg=True),
    ]),
    ("pizza_express", "IN", "Pizza Express", "https://www.pizzaexpress.in/menu", [
        "pizza express"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 62, 18),
        _item("Margherita Personal", 440, 18, 60, 14, veg=True),
        _item("Prosciutto Personal", 540, 28, 60, 22),
    ]),
    ("california_burrito", "IN", "California Burrito", "https://californiaburrito.in/menu", [
        "california burrito"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 34, 58, 16),
        _item("Carnitas Burrito Bowl", 580, 32, 58, 22),
        _item("Veggie Burrito Bowl", 440, 14, 62, 12, veg=True, vgn=True),
        _item("Chicken Quesadilla", 620, 30, 48, 34),
    ]),
    ("yauatcha", "IN", "Yauatcha", "https://yauatcha.com/menu", [
        "yauatcha"
    ], [
        _item("Har Gau (steamed prawn dumplings, 4pc)", 220, 18, 22, 6),
        _item("Chicken Siu Mai (4pc)", 280, 22, 24, 10),
        _item("Steamed Vegetable Dumplings (4pc)", 200, 8, 30, 6, veg=True),
        _item("Black Pepper Chicken + Rice", 520, 32, 56, 18),
    ]),
    ("china_bistro", "IN", "China Bistro", "https://chinabistro.in/menu", [
        "china bistro"
    ], [
        _item("Kung Pao Chicken", 440, 30, 22, 22),
        _item("Steamed Chicken Dimsum (6pc)", 280, 18, 32, 8),
        _item("Hakka Chicken Noodles", 520, 28, 62, 18),
        _item("Chilli Paneer", 380, 18, 18, 26, veg=True),
    ]),
    ("the_bombay_canteen", "IN", "The Bombay Canteen", "https://thebombaycanteen.com/menu", [
        "the bombay canteen", "bombay canteen"
    ], [
        _item("Goan Chicken Cafreal", 440, 32, 14, 28),
        _item("Rao Naga Pork (portion)", 520, 32, 10, 36),
        _item("Dal Chawal Arancini", 380, 14, 48, 14, veg=True),
        _item("Kejriwal Toast (egg)", 380, 22, 30, 18),
    ]),
    ("tea_post", "IN", "Tea Post", "https://teapost.in/menu", [
        "tea post"
    ], [
        _item("Masala Chai (no sugar)", 110, 4, 10, 5, cat="beverage", veg=True),
        _item("Elaichi Chai (less sugar)", 130, 4, 14, 5, cat="beverage", veg=True),
        _item("Sandwich (chicken)", 340, 22, 38, 10),
    ]),
    ("bru_world_cafe", "IN", "Bru World Cafe", "https://bruworldcafe.com/menu", [
        "bru world cafe", "bru world"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Chicken Sandwich", 340, 24, 38, 10),
    ]),
    ("bombay_adda", "IN", "Bombay Adda", "https://bombayadda.com/menu", [
        "bombay adda"
    ], [
        _item("Chicken Tikka Kathi Roll", 420, 26, 42, 16),
        _item("Paneer Tikka Roll", 440, 18, 42, 22, veg=True),
        _item("Grilled Chicken Frankie", 440, 28, 44, 14),
    ]),

    # ═════════════ USA +20 ═════════════
    ("moes_southwest", "US", "Moe's Southwest Grill", "https://www.moes.com/menu", [
        "moes", "moe's", "moes southwest grill", "moe's southwest grill"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 36, 58, 16),
        _item("Steak Burrito Bowl", 580, 34, 58, 22),
        _item("Tofu Bowl (vegan)", 380, 18, 54, 12, veg=True, vgn=True),
    ]),
    ("baja_fresh", "US", "Baja Fresh", "https://www.bajafresh.com/menu", [
        "baja fresh"
    ], [
        _item("Grilled Chicken Burrito (no rice)", 440, 34, 36, 18),
        _item("Grilled Chicken Taco (1pc)", 220, 18, 18, 8),
        _item("Baja Ensalada (chicken)", 340, 32, 14, 18),
    ]),
    ("rubios", "US", "Rubio's Coastal Grill", "https://www.rubios.com/menu", [
        "rubios", "rubio's", "rubio's coastal grill"
    ], [
        _item("Grilled Gourmet Taco (chicken)", 240, 18, 22, 10),
        _item("Classic Fish Taco", 280, 16, 26, 12),
        _item("Salmon Bowl", 440, 32, 48, 12),
    ]),
    ("tijuana_flats", "US", "Tijuana Flats", "https://www.tijuanaflats.com/menu", [
        "tijuana flats"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 36, 58, 16),
        _item("Chicken Quesadilla", 620, 30, 48, 34),
        _item("Chicken Taco (grilled, 1pc)", 220, 18, 22, 8),
    ]),
    ("naf_naf", "US", "Naf Naf Grill", "https://www.nafnafgrill.com/menu", [
        "naf naf", "naf naf grill"
    ], [
        _item("Chicken Shawarma Pita", 440, 30, 42, 14),
        _item("Chicken Shawarma Bowl", 520, 34, 52, 18),
        _item("Falafel Pita (veg)", 420, 14, 54, 16, veg=True, vgn=True),
    ]),
    ("daves_hot_chicken", "US", "Dave's Hot Chicken", "https://www.daveshotchicken.com/menu", [
        "daves hot chicken", "dave's hot chicken", "daves"
    ], [
        _item("No Heat Chicken Tenders (2pc)", 380, 28, 18, 22),
        _item("Mild Chicken Slider", 420, 24, 38, 20),
        _item("Chicken Tenders (3pc) + Slaw", 520, 36, 24, 28),
    ]),
    ("paris_baguette", "US", "Paris Baguette", "https://parisbaguette.com/menu", [
        "paris baguette"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Ham & Cheese Croissant", 380, 14, 40, 18),
        _item("Chicken Grain Salad", 360, 26, 32, 14),
    ]),
    ("la_madeleine", "US", "La Madeleine", "https://www.lamadeleine.com/menu", [
        "la madeleine"
    ], [
        _item("Cafe Latte (no sugar)", 120, 7, 10, 6, cat="beverage", veg=True),
        _item("Chicken Caesar Salad", 440, 32, 18, 24),
        _item("Turkey Croissant Sandwich", 420, 26, 44, 16),
    ]),
    ("first_watch", "US", "First Watch", "https://www.firstwatch.com/menu", [
        "first watch"
    ], [
        _item("Power Wrap (chicken)", 460, 32, 38, 20),
        _item("Farmhouse Bowl (quinoa + chicken)", 480, 34, 46, 16),
        _item("Egg White Omelet (veggie)", 280, 22, 14, 14, veg=True, cat="breakfast"),
    ]),
    ("mcalisters_deli", "US", "McAlister's Deli", "https://www.mcalistersdeli.com/menu", [
        "mcalisters deli", "mcalister's deli", "mcalisters"
    ], [
        _item("Turkey Club Sandwich (half)", 380, 24, 36, 14),
        _item("Grilled Chicken Cobb Salad", 420, 34, 18, 24),
        _item("Chicken Tortilla Soup (cup)", 180, 12, 22, 6),
    ]),
    ("gregorys_coffee", "US", "Gregory's Coffee", "https://www.gregoryscoffee.com/menu", [
        "gregorys coffee", "gregory's coffee"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Turkey Avocado Wrap", 380, 26, 36, 14),
    ]),
    ("perkins", "US", "Perkins Restaurant & Bakery", "https://www.perkinsrestaurants.com/menu", [
        "perkins"
    ], [
        _item("Grilled Chicken + Vegetables", 360, 38, 14, 14),
        _item("Tri-Tip Sirloin 6oz + Broccoli", 420, 42, 12, 22),
        _item("Egg White Skillet (veggie)", 380, 26, 28, 16, veg=True, cat="breakfast"),
    ]),
    ("friendlys", "US", "Friendly's", "https://www.friendlys.com/menu", [
        "friendlys", "friendly's"
    ], [
        _item("Grilled Chicken Club", 540, 32, 46, 22),
        _item("Super Melts (grilled chicken)", 620, 30, 48, 32),
        _item("Single Scoop Ice Cream", 170, 3, 22, 8, cat="dessert", veg=True),
    ]),
    ("which_wich", "US", "Which Wich", "https://www.whichwich.com/menu", [
        "which wich"
    ], [
        _item("Turkey Wich (7in)", 380, 24, 42, 10),
        _item("Grilled Chicken Wich", 420, 28, 44, 12),
        _item("Veggie Wich", 320, 12, 42, 10, veg=True),
    ]),
    ("quiznos", "US", "Quiznos", "https://www.quiznos.com/menu", [
        "quiznos"
    ], [
        _item("Mesquite Chicken Sub (6in)", 380, 26, 40, 12),
        _item("Honey Bourbon Chicken (6in)", 400, 26, 42, 12),
        _item("Veggie Sub (6in)", 320, 10, 42, 10, veg=True),
    ]),
    ("potbelly", "US", "Potbelly", "https://www.potbelly.com/menu", [
        "potbelly", "potbelly sandwich", "potbelly sandwich works"
    ], [
        _item("Turkey Breast Sandwich (original)", 400, 22, 44, 14),
        _item("Chicken Club Sandwich", 460, 28, 44, 20),
        _item("Veggie Sandwich", 340, 12, 42, 12, veg=True),
    ]),
    ("corner_bakery", "US", "Corner Bakery Cafe", "https://www.cornerbakerycafe.com/menu", [
        "corner bakery", "corner bakery cafe"
    ], [
        _item("Bacon Turkey Avocado Sandwich", 520, 32, 42, 26),
        _item("Anaheim Scrambler (scramble)", 480, 32, 22, 28, cat="breakfast"),
        _item("Chicken Pomodori Panini", 440, 30, 44, 14),
    ]),
    ("wawa", "US", "Wawa", "https://www.wawa.com/menu", [
        "wawa"
    ], [
        _item("Turkey Sandwich (short)", 360, 22, 42, 10),
        _item("Grilled Chicken Classic Hoagie", 420, 30, 42, 14),
        _item("Classic Garden Salad (chicken)", 340, 30, 16, 14),
    ]),
    ("jamba", "US", "Jamba", "https://www.jamba.com/menu", [
        "jamba", "jamba juice"
    ], [
        _item("Mango-a-Go-Go (16oz)", 280, 2, 68, 1, cat="beverage", veg=True, vgn=True),
        _item("Greens 'n Ginger (16oz)", 220, 3, 52, 1, cat="beverage", veg=True, vgn=True),
    ]),
    ("16_handles", "US", "16 Handles", "https://16handles.com/menu", [
        "16 handles"
    ], [
        _item("Small Frozen Yogurt (plain + fruit)", 200, 8, 32, 4, cat="dessert", veg=True),
        _item("Medium Froyo with Toppings", 320, 10, 48, 8, cat="dessert", veg=True),
    ]),

    # ═════════════ AUSTRALIA +10 ═════════════
    ("donut_king", "AU", "Donut King", "https://www.donutking.com.au/menu", [
        "donut king"
    ], [
        _item("Original Glazed Donut", 220, 3, 26, 12, cat="dessert", veg=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Hot Dog", 320, 14, 32, 16),
    ]),
    ("michels_patisserie", "AU", "Michel's Patisserie", "https://www.michels.com.au/menu", [
        "michels", "michel's", "michels patisserie"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Caesar Wrap", 380, 26, 40, 12),
        _item("Chocolate Cake Slice", 380, 4, 48, 20, cat="dessert", veg=True),
    ]),
    ("cold_rock", "AU", "Cold Rock Ice Creamery", "https://www.coldrock.com.au/menu", [
        "cold rock", "cold rock ice creamery"
    ], [
        _item("Small Ice Cream Cup (any)", 240, 4, 28, 14, cat="dessert", veg=True),
        _item("Sorbet Scoop", 120, 1, 28, 0, cat="dessert", veg=True, vgn=True),
    ]),
    ("lord_of_the_fries", "AU", "Lord of the Fries", "https://lordofthefries.com.au/menu", [
        "lord of the fries", "lotf"
    ], [
        _item("Classic Burger (vegan)", 460, 18, 48, 20, veg=True, vgn=True),
        _item("Mushroom Burger (vegan)", 480, 16, 50, 22, veg=True, vgn=True),
        _item("Beer Battered Fries (small)", 340, 4, 44, 16, cat="side", veg=True, vgn=True),
    ]),
    ("burger_urge", "AU", "Burger Urge", "https://burgerurge.com.au/menu", [
        "burger urge"
    ], [
        _item("Grilled Chicken Burger", 540, 36, 42, 24),
        _item("Classic Cheeseburger", 620, 32, 42, 34),
        _item("Vegan Burger", 520, 18, 54, 24, veg=True, vgn=True),
    ]),
    ("bucking_bull", "AU", "Bucking Bull", "https://www.buckingbull.com.au/menu", [
        "bucking bull"
    ], [
        _item("Roast Beef Roll", 480, 32, 44, 18),
        _item("Slow Roasted Lamb Roll", 520, 34, 44, 22),
        _item("Chicken Roll (roast)", 460, 30, 42, 18),
    ]),
    ("sushi_bay", "AU", "Sushi Bay", "https://sushibay.com.au/menu", [
        "sushi bay"
    ], [
        _item("Salmon Sashimi (6pc)", 140, 20, 0, 7),
        _item("Chicken Teriyaki Don", 520, 30, 62, 14),
        _item("Salmon Roll (8pc)", 280, 18, 40, 6),
    ]),
    ("wendys_au", "AU", "Wendy's Supa Sundaes", "https://wendys.com.au/menu", [
        "wendys", "wendy's", "wendys supa sundaes"
    ], [
        _item("Kids Cone", 120, 2, 20, 4, cat="dessert", veg=True),
        _item("Milkshake (small, less sugar)", 280, 7, 40, 10, cat="beverage", veg=True),
        _item("Sundae (small)", 260, 4, 44, 8, cat="dessert", veg=True),
    ]),
    ("noodle_box", "AU", "Noodle Box", "https://noodlebox.com.au/menu", [
        "noodle box"
    ], [
        _item("Thai Chicken Pad Thai", 560, 30, 70, 16),
        _item("Singapore Noodles (chicken)", 540, 28, 68, 18),
        _item("Teriyaki Chicken + Rice", 520, 30, 60, 18),
    ]),
    ("pana_organic", "AU", "Pana Organic", "https://panaorganic.com/menu", [
        "pana organic", "pana"
    ], [
        _item("Dark Chocolate Bar (50g)", 280, 4, 28, 18, cat="dessert", veg=True, vgn=True),
        _item("Coconut Ice Cream Scoop", 140, 2, 16, 8, cat="dessert", veg=True, vgn=True),
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
