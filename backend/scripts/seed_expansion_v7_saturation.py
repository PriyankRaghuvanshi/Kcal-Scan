#!/usr/bin/env python3
"""
Seed expansion v7: saturation of 5 anchor markets.
IN +25, US +20, AU +12, GB +12, CA +12 = 81 chains.
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
    # ═════════ INDIA +25 ═════════
    ("papa_johns", "IN", "Papa John's", "https://www.papajohns.co.in/menu", [
        "papa johns", "papa john's"
    ], [
        _item("Grilled Chicken Personal Pizza", 540, 28, 62, 20),
        _item("Hawaiian Personal", 560, 22, 70, 18),
        _item("Veg Supreme Personal", 480, 16, 66, 14, veg=True),
    ]),
    ("cpk", "IN", "California Pizza Kitchen", "https://cpk.co.in/menu", [
        "cpk", "california pizza kitchen"
    ], [
        _item("Thai Chicken Pizza (personal)", 560, 30, 58, 22),
        _item("BBQ Chicken Pizza (personal)", 580, 28, 62, 22),
        _item("Garden Salad with Chicken", 320, 26, 18, 14),
    ]),
    ("sbarro", "IN", "Sbarro", "https://www.sbarroindia.com/menu", [
        "sbarro"
    ], [
        _item("Grilled Chicken Pasta", 520, 28, 58, 18),
        _item("Cheese Pizza Slice (NY style)", 360, 16, 42, 14, veg=True),
        _item("Pepperoni Pizza Slice", 400, 18, 42, 18),
    ]),
    ("bercos", "IN", "Berco's", "https://bercos.com/menu", [
        "bercos", "berco's"
    ], [
        _item("Chicken Hakka Noodles", 540, 28, 62, 18),
        _item("Kung Pao Chicken", 440, 30, 22, 22),
        _item("Chicken Manchurian", 420, 28, 18, 22),
        _item("Veg Noodles + Chilli Paneer", 520, 20, 62, 22, veg=True),
    ]),
    ("hotel_shadab", "IN", "Hotel Shadab", "https://hotelshadab.in/menu", [
        "hotel shadab", "shadab"
    ], [
        _item("Hyderabadi Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Dum Biryani", 640, 28, 62, 30),
        _item("Haleem (mutton, 1 bowl)", 420, 32, 28, 22),
        _item("Chicken Mandi + Rice", 580, 34, 58, 20),
    ]),
    ("pista_house", "IN", "Pista House", "https://pistahouse.com/menu", [
        "pista house"
    ], [
        _item("Hyderabadi Haleem (regular)", 440, 32, 28, 22),
        _item("Chicken Biryani (regular)", 560, 28, 62, 22),
        _item("Mutton Biryani (regular)", 620, 26, 60, 30),
        _item("Chicken 65", 360, 28, 14, 22),
    ]),
    ("jaffer_bhais", "IN", "Jaffer Bhai's Delhi Darbar", "https://jafferbhais.com/menu", [
        "jaffer bhais", "jaffer bhai's", "jaffer bhai delhi darbar"
    ], [
        _item("Chicken Biryani (half)", 580, 30, 62, 22),
        _item("Mutton Biryani (half)", 640, 28, 60, 30),
        _item("Chicken Tikka (half)", 360, 30, 6, 22),
        _item("Mutton Seekh Kebab (2pc)", 340, 26, 4, 22),
    ]),
    ("hot_breads", "IN", "Hot Breads", "https://hotbreads.in/menu", [
        "hot breads"
    ], [
        _item("Chicken Puff (single)", 280, 12, 28, 14),
        _item("Veg Puff", 240, 6, 30, 12, veg=True),
        _item("Grilled Chicken Sandwich", 380, 24, 40, 14),
        _item("Cream Donut", 280, 4, 34, 14, cat="dessert", veg=True),
    ]),
    ("sri_krishna_sweets", "IN", "Sri Krishna Sweets", "https://srikrishnasweets.com/menu", [
        "sri krishna sweets", "skrishna sweets"
    ], [
        _item("Mysore Pak (100g)", 480, 6, 58, 22, cat="dessert", veg=True),
        _item("Badam Halwa (100g)", 440, 10, 48, 22, cat="dessert", veg=True),
        _item("Rava Kesari (100g)", 380, 4, 60, 14, cat="dessert", veg=True),
    ]),
    ("amul_parlour", "IN", "Amul Parlour", "https://www.amul.com/products", [
        "amul parlour", "amul", "amul ice cream parlour"
    ], [
        _item("Amul Cone (single scoop)", 180, 3, 22, 8, cat="dessert", veg=True),
        _item("Amul Kulfi Stick", 160, 4, 18, 9, cat="dessert", veg=True),
        _item("Amul Lassi (unsweetened)", 120, 6, 14, 4, cat="beverage", veg=True),
    ]),
    ("mother_dairy", "IN", "Mother Dairy", "https://www.motherdairy.com/products", [
        "mother dairy", "mother dairy booth"
    ], [
        _item("Mother Dairy Cone", 170, 3, 22, 7, cat="dessert", veg=True),
        _item("Frozen Dessert (small cup)", 120, 2, 18, 5, cat="dessert", veg=True),
        _item("Lassi (unsweetened)", 120, 6, 14, 4, cat="beverage", veg=True),
    ]),
    ("kwality_walls", "IN", "Kwality Wall's", "https://www.kwalitywalls.in/menu", [
        "kwality walls", "kwality wall's"
    ], [
        _item("Kulfi Stick", 180, 3, 22, 9, cat="dessert", veg=True),
        _item("Cornetto (single)", 240, 4, 30, 12, cat="dessert", veg=True),
        _item("Paddle Pop", 80, 1, 16, 2, cat="dessert", veg=True),
    ]),
    ("99_pancakes", "IN", "99 Pancakes", "https://99pancakes.com/menu", [
        "99 pancakes"
    ], [
        _item("Chocolate Pancake (single)", 420, 8, 52, 18, cat="dessert", veg=True),
        _item("Nutella Waffle", 460, 10, 54, 22, cat="dessert", veg=True),
        _item("Protein Pancake Stack", 380, 24, 42, 12, veg=True),
    ]),
    ("belgian_waffle_co", "IN", "The Belgian Waffle Co.", "https://thebelgianwaffle.co/menu", [
        "belgian waffle co", "the belgian waffle", "belgian waffle"
    ], [
        _item("Chocolate Overloaded Waffle", 520, 8, 62, 26, cat="dessert", veg=True),
        _item("Nutella Waffle", 460, 8, 52, 22, cat="dessert", veg=True),
        _item("Cheese Waffle", 420, 12, 46, 20, cat="dessert", veg=True),
    ]),
    ("wafflo", "IN", "Wafflo", "https://wafflo.in/menu", [
        "wafflo"
    ], [
        _item("Chocolate Waffle", 460, 8, 54, 22, cat="dessert", veg=True),
        _item("Cheesy Waffle Savory", 420, 14, 44, 22, veg=True),
        _item("Fruit Waffle", 380, 6, 58, 12, cat="dessert", veg=True),
    ]),
    ("slay_coffee", "IN", "Slay Coffee", "https://slaycoffee.in/menu", [
        "slay coffee", "slay"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Cold Brew (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Pesto Sandwich", 380, 24, 38, 14),
    ]),
    ("frozen_bottle", "IN", "Frozen Bottle", "https://frozenbottle.in/menu", [
        "frozen bottle"
    ], [
        _item("Chocolate Milkshake (regular, less sugar)", 380, 8, 56, 12, cat="beverage", veg=True),
        _item("Peanut Butter Shake", 460, 12, 48, 22, cat="beverage", veg=True),
    ]),
    ("sweet_truth", "IN", "Sweet Truth", "https://eatsure.com/sweet-truth/menu", [
        "sweet truth"
    ], [
        _item("Chocolate Truffle Slice", 340, 5, 42, 18, cat="dessert", veg=True),
        _item("Red Velvet Slice", 360, 4, 44, 20, cat="dessert", veg=True),
        _item("Sugar-Free Brownie", 220, 4, 24, 12, cat="dessert", veg=True),
    ]),
    ("lunchbox", "IN", "LunchBox", "https://eatsure.com/lunchbox/menu", [
        "lunchbox", "lunch box"
    ], [
        _item("Chicken Biryani Meal", 620, 30, 68, 24),
        _item("Paneer Tikka Meal", 580, 22, 62, 26, veg=True),
        _item("Dal Makhani Thali", 540, 16, 66, 18, veg=True),
        _item("Chicken Curry Thali", 620, 32, 62, 24),
    ]),
    ("sigree_global_grill", "IN", "Sigree Global Grill", "https://sigreeglobalgrill.com/menu", [
        "sigree global grill", "sigree"
    ], [
        _item("Grilled Chicken Tikka", 280, 28, 4, 16),
        _item("Tandoori Fish", 260, 28, 4, 14),
        _item("Grilled Prawns", 240, 24, 2, 14),
        _item("Veg Kebab Platter", 320, 14, 24, 18, veg=True),
    ]),
    ("big_chill", "IN", "Big Chill", "https://bigchill.in/menu", [
        "big chill", "big chill cafe"
    ], [
        _item("Grilled Chicken Pasta", 520, 28, 58, 18),
        _item("Chicken Caesar Salad", 420, 32, 18, 24),
        _item("Veg Lasagna (half)", 480, 18, 54, 22, veg=True),
        _item("Chocolate Cake Slice", 420, 5, 52, 20, cat="dessert", veg=True),
    ]),
    ("indigo", "IN", "Indigo", "https://www.foodindigo.com/menu", [
        "indigo", "indigo restaurant", "indigo deli"
    ], [
        _item("Grilled Chicken Breast + Vegetables", 420, 38, 20, 20),
        _item("Pan-Seared Seabass", 380, 32, 8, 22),
        _item("Caesar Salad (grilled chicken)", 380, 30, 16, 22),
        _item("Lamb Chops (4pc)", 480, 40, 8, 30),
    ]),
    ("bukhara", "IN", "Bukhara", "https://www.itchotels.com/bukhara/menu", [
        "bukhara"
    ], [
        _item("Sikandari Raan (shared portion)", 620, 44, 12, 44),
        _item("Murgh Malai Kebab", 380, 30, 6, 26),
        _item("Dal Bukhara (portion)", 380, 14, 30, 22, veg=True),
        _item("Tandoori Jhinga (4pc)", 360, 34, 4, 22),
    ]),
    ("masala_library", "IN", "Masala Library", "https://masalalibrary.com/menu", [
        "masala library"
    ], [
        _item("Grilled Seabass Recheado", 380, 34, 10, 22),
        _item("Murgh Malai Kebab", 380, 30, 6, 26),
        _item("Palak Patta Chaat", 240, 8, 24, 12, veg=True),
        _item("Dal Makhani (portion)", 340, 12, 28, 18, veg=True),
    ]),
    ("indian_accent", "IN", "Indian Accent", "https://indianaccent.com/menu", [
        "indian accent"
    ], [
        _item("Tandoori Bacon Prawns", 360, 30, 8, 22),
        _item("Kashmiri Morel Musallam (half)", 380, 12, 20, 26, veg=True),
        _item("Soy Keema Pav (half)", 320, 22, 26, 14, veg=True, vgn=True),
        _item("Duck Khurchan Cornetto", 280, 22, 14, 16),
    ]),

    # ═════════ USA +20 ═════════
    ("waffle_house", "US", "Waffle House", "https://www.wafflehouse.com/menu", [
        "waffle house"
    ], [
        _item("Grilled Chicken Melt (no bread)", 340, 30, 12, 18),
        _item("T-Bone Steak + Eggs", 560, 44, 4, 40, cat="breakfast"),
        _item("Hashbrowns (plain, small)", 200, 2, 22, 12, cat="side", veg=True, vgn=True),
        _item("Ham & Cheese Omelet", 360, 26, 4, 26, cat="breakfast"),
    ]),
    ("white_castle", "US", "White Castle", "https://www.whitecastle.com/menu", [
        "white castle"
    ], [
        _item("Original Slider (1pc)", 140, 7, 13, 7),
        _item("Grilled Chicken Slider", 180, 12, 18, 6),
        _item("Veggie Slider", 150, 5, 20, 5, veg=True),
    ]),
    ("del_taco", "US", "Del Taco", "https://www.deltaco.com/menu", [
        "del taco"
    ], [
        _item("Del Inferno Grilled Chicken Taco", 210, 15, 20, 8),
        _item("Carne Asada Taco", 220, 16, 19, 10),
        _item("Crunchy Veggie Taco", 170, 5, 22, 7, veg=True),
        _item("Grilled Chicken Salad (no dressing)", 330, 28, 18, 14),
    ]),
    ("hardees", "US", "Hardee's", "https://www.hardees.com/menu", [
        "hardees", "hardee's"
    ], [
        _item("Grilled Chicken Sandwich", 360, 26, 38, 12),
        _item("Charbroiled Chicken Club", 480, 34, 40, 20),
        _item("Side Salad", 60, 2, 8, 2, cat="side", veg=True, vgn=True),
    ]),
    ("baskin_robbins", "US", "Baskin-Robbins", "https://www.baskinrobbins.com/menu", [
        "baskin robbins", "baskin-robbins", "baskin"
    ], [
        _item("Small Scoop (any flavor)", 170, 3, 20, 9, cat="dessert", veg=True),
        _item("Sugar-Free Scoop", 110, 3, 14, 4, cat="dessert", veg=True),
        _item("Sherbet Scoop", 130, 1, 28, 2, cat="dessert", veg=True, vgn=True),
    ]),
    ("cold_stone", "US", "Cold Stone Creamery", "https://www.coldstonecreamery.com/menu", [
        "cold stone", "cold stone creamery"
    ], [
        _item("Like It Size (any flavor)", 260, 4, 28, 14, cat="dessert", veg=True),
        _item("Sinless Sans Fat (scoop)", 140, 6, 22, 0, cat="dessert", veg=True),
    ]),
    ("yogurtland", "US", "Yogurtland", "https://www.yogurt-land.com/menu", [
        "yogurtland"
    ], [
        _item("Small Yogurt Cup (plain + fruit)", 200, 8, 32, 4, cat="dessert", veg=True),
        _item("Regular Cup with Toppings", 320, 10, 48, 8, cat="dessert", veg=True),
    ]),
    ("sbarro", "US", "Sbarro", "https://www.sbarro.com/menu", [
        "sbarro"
    ], [
        _item("NY Cheese Pizza Slice", 380, 16, 48, 14, veg=True),
        _item("Pepperoni Pizza Slice", 420, 18, 48, 18),
        _item("Chicken Parm Pasta (regular)", 540, 28, 58, 20),
    ]),
    ("marcos_pizza", "US", "Marco's Pizza", "https://www.marcos.com/menu", [
        "marcos pizza", "marco's pizza"
    ], [
        _item("Garden Personal Pizza", 480, 18, 62, 16, veg=True),
        _item("Pepperoni Personal", 520, 24, 60, 20),
        _item("Chicken Club Personal", 540, 28, 60, 20),
    ]),
    ("papa_murphys", "US", "Papa Murphy's", "https://www.papamurphys.com/menu", [
        "papa murphys", "papa murphy's"
    ], [
        _item("Papa's Favorite Personal", 540, 26, 60, 22),
        _item("Veggie Mediterranean Personal", 480, 18, 62, 18, veg=True),
        _item("Chicken Bacon Artichoke Personal", 520, 30, 58, 20),
    ]),
    ("olive_garden", "US", "Olive Garden", "https://www.olivegarden.com/menu", [
        "olive garden"
    ], [
        _item("Grilled Chicken Salad (no dressing)", 380, 34, 16, 22),
        _item("Herb-Grilled Salmon", 460, 44, 10, 28),
        _item("Chicken Piccata", 560, 38, 48, 22),
        _item("Minestrone Soup", 110, 5, 20, 2, cat="side", veg=True, vgn=True),
    ]),
    ("red_lobster", "US", "Red Lobster", "https://www.redlobster.com/menu", [
        "red lobster"
    ], [
        _item("Grilled Salmon (no sides)", 360, 46, 2, 18),
        _item("Garlic Shrimp Skewers", 320, 30, 10, 18),
        _item("Chicken Caesar Salad", 420, 34, 18, 24),
        _item("Snow Crab Legs (1 lb, steamed)", 220, 48, 0, 2),
    ]),
    ("outback", "US", "Outback Steakhouse", "https://www.outback.com/menu", [
        "outback", "outback steakhouse"
    ], [
        _item("6oz Sirloin + Steamed Vegetables", 380, 40, 12, 18),
        _item("Grilled Chicken on the Barbie", 340, 42, 4, 14),
        _item("Grilled Salmon + Asparagus", 380, 38, 8, 20),
    ]),
    ("longhorn", "US", "LongHorn Steakhouse", "https://www.longhornsteakhouse.com/menu", [
        "longhorn", "longhorn steakhouse"
    ], [
        _item("6oz Renegade Sirloin + Veg", 420, 42, 14, 22),
        _item("Grilled Chicken", 340, 44, 4, 14),
        _item("Grilled Salmon", 380, 40, 4, 20),
    ]),
    ("tgi_fridays", "US", "TGI Fridays", "https://www.tgifridays.com/menu", [
        "tgi fridays", "tgif", "tgi friday's"
    ], [
        _item("Grilled Chicken Caesar Salad", 440, 34, 18, 26),
        _item("Jack Daniel's Grilled Chicken", 520, 38, 32, 24),
        _item("6oz Sirloin + Broccoli", 420, 42, 12, 22),
    ]),
    ("bob_evans", "US", "Bob Evans", "https://www.bobevans.com/menu", [
        "bob evans"
    ], [
        _item("Grilled Chicken + Vegetables", 360, 38, 14, 14),
        _item("Turkey & Dressing Dinner", 540, 36, 52, 20),
        _item("Roasted Turkey Breast", 320, 42, 4, 12),
    ]),
    ("einstein_bros", "US", "Einstein Bros. Bagels", "https://www.einsteinbros.com/menu", [
        "einstein bros", "einstein bros bagels", "einstein bagels"
    ], [
        _item("Turkey Bacon Egg White Bagel Thin", 320, 22, 30, 10, cat="breakfast"),
        _item("Plain Bagel with Light Cream Cheese", 320, 12, 52, 10, cat="breakfast", veg=True),
        _item("Turkey Sandwich", 380, 28, 42, 10),
    ]),
    ("jamba", "US", "Jamba", "https://www.jamba.com/menu", [
        "jamba", "jamba juice"
    ], [
        _item("Protein Berry Workout Smoothie (16oz)", 320, 22, 52, 2, cat="beverage", veg=True),
        _item("Greens 'n Ginger Smoothie (16oz)", 220, 3, 52, 1, cat="beverage", veg=True, vgn=True),
        _item("Acai Super-Antioxidant (16oz)", 360, 4, 74, 7, cat="beverage", veg=True, vgn=True),
    ]),
    ("smoothie_king", "US", "Smoothie King", "https://www.smoothieking.com/menu", [
        "smoothie king"
    ], [
        _item("Gladiator Chocolate (20oz)", 240, 45, 12, 2, cat="beverage", veg=True),
        _item("Lean1 Chocolate (20oz)", 260, 20, 34, 3, cat="beverage", veg=True),
        _item("Slim-N-Trim Vanilla", 240, 12, 40, 3, cat="beverage", veg=True),
    ]),
    ("pf_changs", "US", "P.F. Chang's", "https://www.pfchangs.com/menu", [
        "pf changs", "p.f. chang's", "pf chang's"
    ], [
        _item("Chicken Lettuce Wraps", 580, 32, 48, 28),
        _item("Kung Pao Chicken", 660, 38, 42, 36),
        _item("Mongolian Beef", 720, 42, 46, 40),
        _item("Cantonese Shrimp", 420, 32, 22, 20),
    ]),

    # ═════════ AUSTRALIA +12 ═════════
    ("krispy_kreme", "AU", "Krispy Kreme", "https://www.krispykreme.com.au/menu", [
        "krispy kreme"
    ], [
        _item("Original Glazed Donut", 190, 2, 22, 11, cat="dessert", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("muffin_break", "AU", "Muffin Break", "https://www.muffinbreak.com.au/menu", [
        "muffin break"
    ], [
        _item("Chicken Caesar Wrap", 380, 26, 40, 12),
        _item("Blueberry Muffin (regular)", 380, 6, 52, 16, cat="dessert", veg=True),
        _item("Multigrain Sandwich (chicken)", 360, 24, 38, 12),
    ]),
    ("pizza_hut", "AU", "Pizza Hut", "https://www.pizzahut.com.au/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
        _item("Vegetarian Supreme Personal", 480, 16, 66, 14, veg=True),
    ]),
    ("crust_pizza", "AU", "Crust Pizza", "https://www.crust.com.au/menu", [
        "crust pizza", "crust"
    ], [
        _item("BBQ Chicken Personal", 540, 28, 60, 22),
        _item("Veggie Mediterranean Personal", 480, 16, 62, 18, veg=True),
        _item("Prosciutto & Rocket Personal", 520, 26, 58, 22),
    ]),
    ("max_brenner", "AU", "Max Brenner", "https://maxbrenner.com.au/menu", [
        "max brenner"
    ], [
        _item("Chocolate Pizza (slice)", 380, 6, 48, 18, cat="dessert", veg=True),
        _item("Hot Chocolate (regular, no sugar)", 160, 8, 16, 8, cat="beverage", veg=True),
        _item("Dark Chocolate Fondue (small)", 340, 4, 40, 18, cat="dessert", veg=True),
    ]),
    ("gelatissimo", "AU", "Gelatissimo", "https://gelatissimo.com.au/menu", [
        "gelatissimo"
    ], [
        _item("Single Scoop Gelato", 140, 3, 20, 5, cat="dessert", veg=True),
        _item("Sorbet Scoop", 110, 1, 26, 0, cat="dessert", veg=True, vgn=True),
    ]),
    ("san_churro", "AU", "San Churro", "https://www.sanchurro.com/menu", [
        "san churro"
    ], [
        _item("Churros for One", 460, 8, 54, 22, cat="dessert", veg=True),
        _item("Dark Hot Chocolate (no sugar)", 180, 8, 22, 8, cat="beverage", veg=True),
    ]),
    ("chargrill_charlies", "AU", "Chargrill Charlie's", "https://chargrillcharlies.com.au/menu", [
        "chargrill charlies", "chargrill charlie's"
    ], [
        _item("Quarter Chicken + Salad", 340, 32, 10, 18),
        _item("Chicken Roll", 420, 26, 42, 18),
        _item("Half Chicken", 560, 58, 4, 30),
        _item("Greek Salad (side)", 140, 6, 8, 10, cat="side", veg=True),
    ]),
    ("ribs_and_burgers", "AU", "Ribs & Burgers", "https://www.ribsandburgers.com/menu", [
        "ribs and burgers", "ribs & burgers"
    ], [
        _item("Grilled Chicken Burger", 520, 34, 42, 22),
        _item("The Classic Burger", 620, 34, 42, 34),
        _item("Baby Back Ribs (half rack)", 620, 48, 22, 36),
    ]),
    ("rashays", "AU", "Rashays", "https://rashays.com/menu", [
        "rashays"
    ], [
        _item("Grilled Chicken Breast + Rice", 480, 40, 52, 12),
        _item("Chicken Caesar Salad", 420, 32, 18, 24),
        _item("Grilled Salmon + Vegetables", 440, 38, 14, 24),
    ]),
    ("brumbys", "AU", "Brumby's Bakery", "https://www.brumbys.com.au/menu", [
        "brumbys", "brumby's", "brumbys bakery"
    ], [
        _item("Chicken Salad Sandwich", 360, 24, 42, 10),
        _item("Ham & Salad Roll", 340, 18, 42, 10),
        _item("Multigrain Roll (cheese + veg)", 320, 12, 44, 10, veg=True),
    ]),
    ("new_york_minute", "AU", "New York Minute", "https://newyorkminute.com.au/menu", [
        "new york minute", "ny minute"
    ], [
        _item("Grilled Chicken NY Bagel", 380, 26, 42, 12),
        _item("Smoked Salmon Bagel", 420, 22, 44, 14),
        _item("Plain Bagel + Cream Cheese", 340, 12, 52, 10, cat="breakfast", veg=True),
    ]),

    # ═════════ UK +12 ═════════
    ("frankie_and_bennys", "GB", "Frankie & Benny's", "https://www.frankieandbennys.com/menu", [
        "frankie and bennys", "frankie & benny's", "frankie bennys"
    ], [
        _item("Grilled Chicken Pasta", 540, 38, 56, 18),
        _item("Classic Margherita Pizza (personal)", 520, 22, 60, 18, veg=True),
        _item("BBQ Chicken Pizza (personal)", 580, 32, 62, 22),
    ]),
    ("harvester", "GB", "Harvester", "https://www.harvester.co.uk/menu", [
        "harvester"
    ], [
        _item("Rotisserie Chicken (half) + Salad", 560, 44, 20, 30),
        _item("8oz Gammon Steak", 540, 46, 18, 30),
        _item("Grilled Salmon + Vegetables", 420, 36, 14, 24),
    ]),
    ("las_iguanas", "GB", "Las Iguanas", "https://www.lasiguanas.co.uk/menu", [
        "las iguanas"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 36, 58, 16),
        _item("Xinxim (chicken Brazilian stew)", 540, 34, 38, 28),
        _item("Grilled Salmon + Rice", 480, 34, 48, 18),
    ]),
    ("chiquito", "GB", "Chiquito", "https://www.chiquito.co.uk/menu", [
        "chiquito"
    ], [
        _item("Grilled Chicken Fajitas", 580, 42, 54, 22),
        _item("Chicken Quesadilla (half)", 460, 28, 38, 22),
        _item("Burrito Bowl Chicken", 520, 34, 58, 18),
    ]),
    ("tgi_fridays", "GB", "TGI Fridays", "https://www.tgifridays.co.uk/menu", [
        "tgi fridays", "tgi friday's", "tgif"
    ], [
        _item("Jack Daniel's Grilled Chicken", 520, 38, 32, 24),
        _item("Grilled Chicken Caesar", 440, 34, 18, 26),
        _item("Ribeye 8oz + Broccoli", 520, 44, 12, 34),
    ]),
    ("zizzi", "GB", "Zizzi", "https://www.zizzi.co.uk/menu", [
        "zizzi"
    ], [
        _item("Grilled Chicken Pasta", 520, 36, 56, 18),
        _item("Rustica Classic Pizza (personal)", 560, 26, 62, 20),
        _item("King Prawn Linguine", 480, 32, 52, 14),
    ]),
    ("prezzo", "GB", "Prezzo", "https://www.prezzorestaurants.co.uk/menu", [
        "prezzo"
    ], [
        _item("Grilled Chicken Pasta", 520, 34, 56, 18),
        _item("Classic Margherita (personal)", 540, 22, 62, 18, veg=True),
        _item("Grilled Salmon + Vegetables", 440, 36, 18, 22),
    ]),
    ("ask_italian", "GB", "ASK Italian", "https://www.askitalian.co.uk/menu", [
        "ask italian", "ask"
    ], [
        _item("Pollo Milanese (grilled chicken)", 540, 40, 38, 24),
        _item("Classic Margherita (personal)", 520, 22, 58, 18, veg=True),
        _item("Grilled Salmon + Veg", 460, 36, 12, 26),
    ]),
    ("carluccios", "GB", "Carluccio's", "https://www.carluccios.com/menu", [
        "carluccios", "carluccio's"
    ], [
        _item("Pollo Milanese", 540, 40, 38, 24),
        _item("Grilled Salmon + Vegetables", 460, 36, 14, 24),
        _item("Classic Margherita (personal)", 520, 22, 58, 18, veg=True),
    ]),
    ("bills", "GB", "Bill's", "https://bills-website.co.uk/menu", [
        "bills", "bill's", "bills restaurant"
    ], [
        _item("Grilled Chicken Caesar Salad", 440, 32, 18, 24),
        _item("Eggs Royale", 480, 26, 34, 26, cat="breakfast"),
        _item("Bill's Burger (half)", 520, 30, 38, 26),
    ]),
    ("patisserie_valerie", "GB", "Patisserie Valerie", "https://www.patisserie-valerie.co.uk/menu", [
        "patisserie valerie", "patisserie"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Ham & Cheese Croissant", 380, 14, 40, 18),
        _item("Chocolate Slice", 340, 4, 42, 18, cat="dessert", veg=True),
    ]),
    ("paul", "GB", "Paul", "https://www.paul-uk.com/menu", [
        "paul", "paul bakery", "paul boulangerie"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Ham & Cheese Baguette", 460, 22, 52, 18),
        _item("Chicken Caesar Salad", 420, 32, 18, 22),
        _item("Plain Croissant", 260, 6, 26, 14, cat="breakfast", veg=True),
    ]),

    # ═════════ CANADA +12 ═════════
    ("the_keg", "CA", "The Keg Steakhouse", "https://www.kegsteakhouse.com/menu", [
        "the keg", "keg steakhouse", "the keg steakhouse"
    ], [
        _item("Teriyaki Sirloin 7oz + Broccoli", 420, 42, 16, 22),
        _item("Grilled Chicken", 360, 44, 6, 16),
        _item("Grilled Salmon + Veg", 460, 40, 8, 26),
    ]),
    ("earls", "CA", "Earls Kitchen + Bar", "https://earls.ca/menu", [
        "earls", "earls kitchen", "earls kitchen + bar"
    ], [
        _item("Grilled Chicken Dragon Bowl", 520, 36, 58, 18),
        _item("Classic Caesar Salad (chicken)", 440, 32, 18, 26),
        _item("Blackened Chicken Bowl", 540, 38, 52, 20),
    ]),
    ("cactus_club", "CA", "Cactus Club Cafe", "https://www.cactusclubcafe.com/menu", [
        "cactus club", "cactus club cafe"
    ], [
        _item("Teriyaki Chicken Rice Bowl", 540, 36, 60, 18),
        _item("Grilled Salmon Fillet", 420, 40, 14, 22),
        _item("Spicy Chicken Sandwich", 620, 34, 44, 34),
    ]),
    ("milestones", "CA", "Milestones", "https://milestonesrestaurants.com/menu", [
        "milestones", "milestones grill and bar"
    ], [
        _item("Grilled Chicken Breast", 360, 44, 6, 16),
        _item("Caesar Salad (chicken)", 420, 32, 18, 24),
        _item("Milestones Burger (half)", 540, 30, 44, 26),
    ]),
    ("east_side_marios", "CA", "East Side Mario's", "https://eastsidemarios.com/menu", [
        "east side marios", "east side mario's"
    ], [
        _item("Grilled Chicken Pasta", 540, 34, 56, 18),
        _item("Chicken Caesar Salad", 420, 32, 18, 24),
        _item("Margherita Personal Pizza", 520, 22, 58, 20, veg=True),
    ]),
    ("kelseys", "CA", "Kelseys Original Roadhouse", "https://www.kelseys.ca/menu", [
        "kelseys", "kelsey's", "kelseys roadhouse"
    ], [
        _item("Grilled Chicken Breast", 360, 44, 6, 16),
        _item("Kelseys Caesar Salad (chicken)", 440, 32, 18, 26),
        _item("7oz Sirloin + Veg", 420, 42, 12, 22),
    ]),
    ("montanas", "CA", "Montana's BBQ", "https://www.montanas.ca/menu", [
        "montanas", "montana's", "montana's bbq"
    ], [
        _item("BBQ Chicken (half)", 540, 44, 22, 28),
        _item("Baby Back Ribs (half rack)", 620, 42, 22, 36),
        _item("Grilled Sirloin 6oz + Veg", 400, 40, 16, 18),
    ]),
    ("moxies", "CA", "Moxies", "https://moxies.com/menu", [
        "moxies"
    ], [
        _item("Tandoori Chicken Bowl", 520, 36, 58, 18),
        _item("Grilled Chicken Caesar", 420, 32, 18, 24),
        _item("Blackened Cajun Chicken", 480, 40, 22, 22),
    ]),
    ("pizza_hut", "CA", "Pizza Hut", "https://www.pizzahut.ca/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
    ]),
    ("new_york_fries", "CA", "New York Fries", "https://newyorkfries.com/menu", [
        "new york fries", "ny fries"
    ], [
        _item("Small Fries (plain)", 300, 4, 40, 14, cat="side", veg=True, vgn=True),
        _item("Grilled Chicken Sandwich", 380, 26, 38, 14),
    ]),
    ("quesada", "CA", "Quesada Burritos & Tacos", "https://quesada.ca/menu", [
        "quesada", "quesada burritos"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 34, 58, 16),
        _item("Chicken Quesadilla", 620, 32, 48, 32),
        _item("Veggie Burrito Bowl", 440, 14, 64, 12, veg=True),
    ]),
    ("mucho_burrito", "CA", "Mucho Burrito", "https://www.muchoburrito.com/menu", [
        "mucho burrito"
    ], [
        _item("Grilled Chicken Burrito Bowl", 520, 34, 58, 16),
        _item("Carnitas Burrito Bowl", 580, 32, 58, 22),
        _item("Veggie Bowl", 420, 14, 60, 12, veg=True, vgn=True),
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
