#!/usr/bin/env python3
"""
Seed expansion v6: depth push for India, US, Australia, Canada, UK.
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
    # ═══════════════ INDIA depth (15) ═══════════════
    ("biryani_by_kilo", "IN", "Biryani By Kilo", "https://biryanibykilo.com/menu", [
        "biryani by kilo", "bbk"
    ], [
        _item("Chicken Biryani (half kg)", 620, 34, 66, 24),
        _item("Mutton Biryani (half kg)", 680, 32, 64, 32),
        _item("Paneer Biryani (half kg)", 560, 22, 66, 22, veg=True),
        _item("Veg Biryani", 480, 14, 66, 16, veg=True, vgn=True),
    ]),
    ("biryani_blues", "IN", "Biryani Blues", "https://biryaniblues.in/menu", [
        "biryani blues"
    ], [
        _item("Chicken Hyderabadi Biryani", 580, 30, 64, 22),
        _item("Mutton Lucknowi Biryani", 640, 28, 62, 30),
        _item("Veg Dum Biryani", 460, 14, 66, 14, veg=True, vgn=True),
    ]),
    ("khan_chacha", "IN", "Khan Chacha", "https://khanchacha.com/menu", [
        "khan chacha"
    ], [
        _item("Chicken Tikka Kathi Roll", 440, 28, 42, 18),
        _item("Mutton Seekh Roll", 520, 30, 44, 22),
        _item("Chicken Malai Tikka Roll", 480, 28, 42, 22),
        _item("Paneer Tikka Roll", 460, 20, 42, 24, veg=True),
    ]),
    ("chowman", "IN", "Chowman", "https://chowman.com/menu", [
        "chowman"
    ], [
        _item("Hakka Chicken Noodles", 520, 26, 62, 18),
        _item("Kung Pao Chicken", 440, 30, 22, 22),
        _item("Steamed Chicken Momos (6pc)", 280, 18, 32, 8),
        _item("Hot & Sour Soup Chicken", 180, 16, 14, 8),
        _item("Chilli Paneer", 380, 18, 18, 26, veg=True),
    ]),
    ("smokin_joes", "IN", "Smokin' Joe's Pizza", "https://smokinjoes.co.in/menu", [
        "smokin joes", "smokin' joes", "smokin joes pizza"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 62, 18),
        _item("BBQ Chicken Personal", 560, 28, 60, 22),
        _item("Paneer Tikka Personal", 540, 20, 62, 22, veg=True),
        _item("Veggie Supreme Personal", 480, 16, 66, 14, veg=True),
    ]),
    ("wat_a_burger", "IN", "Wat-a-Burger", "https://watafood.in/menu", [
        "wat a burger", "wat-a-burger", "wata burger"
    ], [
        _item("Grilled Chicken Burger", 440, 28, 42, 18),
        _item("Tandoori Chicken Burger", 460, 30, 42, 20),
        _item("Paneer Makhani Burger", 500, 20, 46, 26, veg=True),
        _item("Classic Chicken Wrap", 420, 26, 40, 18),
    ]),
    ("colonels_kababz", "IN", "Colonel's Kababz", "https://colonelskababz.com/menu", [
        "colonels kababz", "colonel's kababz", "colonel kababz"
    ], [
        _item("Chicken Seekh Kebab Roll", 440, 26, 42, 18),
        _item("Mutton Seekh Roll", 500, 30, 42, 22),
        _item("Chicken Tikka Roll", 420, 26, 40, 18),
        _item("Chicken Shawarma Wrap", 440, 28, 44, 16),
    ]),
    ("monginis", "IN", "Monginis", "https://monginis.net/menu", [
        "monginis"
    ], [
        _item("Chicken Puff (single)", 280, 12, 28, 14),
        _item("Veg Puff", 240, 6, 30, 12, veg=True),
        _item("Chocolate Cake Slice", 340, 4, 42, 18, cat="dessert", veg=True),
        _item("Cream Roll", 260, 4, 34, 12, cat="dessert", veg=True),
    ]),
    ("hyderabad_biryani_house", "IN", "Hyderabad Biryani House", "https://hyderabadbiryanihouse.com/menu", [
        "hyderabad biryani house", "hbh"
    ], [
        _item("Hyderabadi Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Dum Biryani", 640, 28, 62, 30),
        _item("Prawn Biryani", 540, 28, 60, 20),
        _item("Paneer Dum Biryani", 540, 20, 64, 22, veg=True),
    ]),
    ("auntie_annes", "IN", "Auntie Anne's", "https://auntieannesindia.com/menu", [
        "auntie annes", "auntie anne's", "auntie anne"
    ], [
        _item("Original Pretzel", 340, 10, 72, 2, cat="snack", veg=True, vgn=True),
        _item("Jalapeño Pretzel", 360, 10, 72, 4, cat="snack", veg=True, vgn=True),
        _item("Pretzel Dog", 420, 16, 52, 18),
        _item("Mini Pretzels (10pc)", 340, 10, 70, 3, cat="snack", veg=True, vgn=True),
    ]),
    ("krispy_kreme", "IN", "Krispy Kreme", "https://www.krispykreme.in/menu", [
        "krispy kreme"
    ], [
        _item("Original Glazed Donut (single)", 190, 2, 22, 11, cat="dessert", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
    ]),
    ("eatsure", "IN", "EatSure", "https://eatsure.com/menu", [
        "eatsure", "eat sure"
    ], [
        _item("Grilled Chicken Rice Bowl", 480, 32, 58, 12),
        _item("Peri Peri Chicken Wrap", 460, 28, 44, 18),
        _item("Protein Paneer Bowl", 420, 26, 40, 18, veg=True),
        _item("Tandoori Chicken Salad", 340, 30, 16, 16),
    ]),
    ("oven_story", "IN", "Oven Story Pizza", "https://eatsure.com/oven-story/menu", [
        "oven story", "oven story pizza"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 62, 18),
        _item("Peri Peri Chicken Personal", 540, 28, 60, 22),
        _item("Veggie Supreme Personal", 480, 16, 66, 14, veg=True),
        _item("Margherita Personal", 440, 16, 60, 14, veg=True),
    ]),
    ("the_good_bowl", "IN", "The Good Bowl", "https://eatsure.com/the-good-bowl/menu", [
        "the good bowl", "good bowl"
    ], [
        _item("Classic Chicken Biryani Bowl", 540, 28, 62, 20),
        _item("Handi Chicken Curry Bowl + Rice", 520, 30, 56, 18),
        _item("Paneer Tikka Rice Bowl", 500, 20, 58, 22, veg=True),
        _item("Veg Biryani Bowl", 440, 14, 64, 14, veg=True, vgn=True),
    ]),
    ("nirulas", "IN", "Nirula's", "https://nirulas.com/menu", [
        "nirulas", "nirula's"
    ], [
        _item("Grilled Chicken Burger", 420, 26, 42, 16),
        _item("Chicken Maharaja Burger", 480, 28, 44, 20),
        _item("Veg Maharaja Burger", 440, 14, 50, 22, veg=True),
        _item("Chicken Tikka Pizza (personal)", 520, 28, 60, 18),
    ]),

    # ═══════════════ USA depth (15) ═══════════════
    ("tim_hortons", "US", "Tim Hortons", "https://www.timhortons.com/menu", [
        "tim hortons", "timmies"
    ], [
        _item("Turkey Bacon Club", 440, 28, 42, 16),
        _item("Grilled Chicken Wrap", 340, 24, 36, 10),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Egg White Turkey Sausage Wrap", 280, 20, 26, 10),
    ]),
    ("dairy_queen", "US", "Dairy Queen", "https://www.dairyqueen.com/menu", [
        "dairy queen", "dq"
    ], [
        _item("Grilled Chicken Sandwich", 380, 28, 38, 14),
        _item("Crispy Chicken Salad", 320, 26, 18, 14),
        _item("Small Vanilla Cone", 240, 6, 38, 7, cat="dessert", veg=True),
        _item("Small Fries", 310, 4, 42, 14, cat="side", veg=True, vgn=True),
    ]),
    ("jimmy_johns", "US", "Jimmy John's", "https://www.jimmyjohns.com/menu", [
        "jimmy johns", "jimmy john's"
    ], [
        _item("Turkey Tom (8in)", 520, 24, 50, 22),
        _item("Slim 1 (Ham Only)", 360, 18, 48, 10),
        _item("Unwich Turkey Tom (no bread)", 280, 22, 10, 18),
        _item("Roast Beef (8in)", 540, 28, 52, 22),
    ]),
    ("just_salad", "US", "Just Salad", "https://justsalad.com/menu", [
        "just salad"
    ], [
        _item("Classic Cobb Salad", 420, 34, 16, 24),
        _item("Mediterranean Bowl (chicken)", 440, 30, 46, 14),
        _item("Grain Bowl with Grilled Chicken", 460, 32, 52, 12),
        _item("Vegan Power Bowl", 380, 16, 48, 14, veg=True, vgn=True),
    ]),
    ("chopt", "US", "Chopt Creative Salad", "https://www.choptsalad.com/menu", [
        "chopt", "chopt salad", "chopt creative salad"
    ], [
        _item("Mexican Caesar (chicken)", 420, 32, 22, 22),
        _item("Greek Salad (grilled chicken)", 440, 34, 18, 26),
        _item("Santa Fe Rice Bowl (chicken)", 480, 32, 44, 18),
        _item("Mediterranean Chicken Wrap", 460, 28, 46, 18),
    ]),
    ("dig", "US", "Dig", "https://www.diginn.com/menu", [
        "dig", "dig inn"
    ], [
        _item("Classic Marketplate (chicken)", 440, 34, 46, 14),
        _item("Steak Marketplate", 520, 34, 44, 22),
        _item("Roasted Salmon Bowl", 460, 32, 42, 18),
        _item("Vegan Bowl (seasonal)", 380, 14, 54, 12, veg=True, vgn=True),
    ]),
    ("dutch_bros", "US", "Dutch Bros Coffee", "https://www.dutchbros.com/menu", [
        "dutch bros", "dutch brothers"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Sugar-Free Cappuccino", 90, 6, 8, 4, cat="beverage", veg=True),
        _item("Cold Brew (black)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("peets_coffee", "US", "Peet's Coffee", "https://www.peets.com/menu", [
        "peets", "peet's", "peets coffee", "peet's coffee"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Turkey Apple Chutney Sandwich", 380, 24, 40, 12),
        _item("Garden Veggie Wrap", 340, 10, 44, 14, veg=True),
    ]),
    ("blue_bottle", "US", "Blue Bottle Coffee", "https://bluebottlecoffee.com/menu", [
        "blue bottle", "blue bottle coffee"
    ], [
        _item("Espresso (no sugar)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cortado (no sugar)", 80, 4, 6, 4, cat="beverage", veg=True),
        _item("Cold Brew (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("krispy_kreme", "US", "Krispy Kreme", "https://www.krispykreme.com/menu", [
        "krispy kreme"
    ], [
        _item("Original Glazed Donut", 190, 2, 22, 11, cat="dessert", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("cinnabon", "US", "Cinnabon", "https://www.cinnabon.com/menu", [
        "cinnabon"
    ], [
        _item("MiniBon Roll", 300, 5, 49, 9, cat="dessert", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("auntie_annes", "US", "Auntie Anne's", "https://www.auntieannes.com/menu", [
        "auntie annes", "auntie anne's"
    ], [
        _item("Original Pretzel", 340, 10, 72, 2, cat="snack", veg=True, vgn=True),
        _item("Pretzel Dog", 420, 16, 52, 18),
        _item("Mini Pretzels (10pc)", 340, 10, 70, 3, cat="snack", veg=True, vgn=True),
    ]),
    ("applebees", "US", "Applebee's", "https://www.applebees.com/menu", [
        "applebees", "applebee's"
    ], [
        _item("Grilled Chicken Caesar Salad", 520, 38, 24, 30),
        _item("6oz Sirloin + Vegetables", 480, 44, 20, 24),
        _item("Classic Grilled Chicken Burger", 540, 34, 46, 22),
        _item("Fiesta Lime Chicken + Rice", 620, 38, 54, 24),
    ]),
    ("chilis", "US", "Chili's", "https://www.chilis.com/menu", [
        "chilis", "chili's", "chilis grill and bar"
    ], [
        _item("Grilled Chicken Salad (no dressing)", 420, 38, 18, 22),
        _item("6oz Sirloin + Broccoli", 460, 42, 18, 24),
        _item("Margarita Grilled Chicken + Rice", 580, 40, 50, 22),
        _item("Classic Bacon Burger (half)", 520, 28, 42, 28),
    ]),
    ("buffalo_wild_wings", "US", "Buffalo Wild Wings", "https://www.buffalowildwings.com/menu", [
        "buffalo wild wings", "bww"
    ], [
        _item("Naked Tenders (6pc)", 280, 42, 4, 8),
        _item("Traditional Wings (6pc, no sauce)", 440, 38, 2, 30),
        _item("Grilled Chicken Caesar Salad", 420, 34, 16, 24),
        _item("Bunless Burger + Side Salad", 420, 32, 12, 26),
    ]),
    ("texas_roadhouse", "US", "Texas Roadhouse", "https://www.texasroadhouse.com/menu", [
        "texas roadhouse"
    ], [
        _item("8oz Sirloin + Steamed Veg", 540, 48, 22, 28),
        _item("Grilled Chicken Salad (no dressing)", 420, 38, 18, 22),
        _item("Grilled BBQ Chicken", 480, 42, 24, 22),
        _item("Pulled Pork Dinner", 620, 38, 46, 30),
    ]),

    # ═══════════════ AUSTRALIA depth (8) ═══════════════
    ("bakers_delight", "AU", "Bakers Delight", "https://bakersdelight.com.au/menu", [
        "bakers delight"
    ], [
        _item("Chicken Salad Roll", 380, 24, 42, 12),
        _item("Multigrain Sandwich (turkey)", 340, 22, 36, 10),
        _item("Egg & Lettuce Roll", 300, 14, 36, 10, veg=True),
        _item("Pumpkin & Feta Roll", 320, 12, 44, 10, veg=True),
    ]),
    ("chatime", "AU", "Chatime", "https://chatime.com.au/menu", [
        "chatime"
    ], [
        _item("Classic Milk Tea (less sugar)", 280, 2, 52, 6, cat="beverage", veg=True),
        _item("Taro Milk Tea (less sugar)", 320, 4, 58, 8, cat="beverage", veg=True),
        _item("Jasmine Tea (unsweetened)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("sumo_salad", "AU", "SumoSalad", "https://sumosalad.com/menu", [
        "sumo salad", "sumosalad"
    ], [
        _item("Classic Caesar Salad (grilled chicken)", 420, 34, 18, 22),
        _item("Greek Salad + Grilled Chicken", 380, 30, 18, 18),
        _item("Mediterranean Chicken Bowl", 460, 32, 44, 14),
        _item("Vegan Buddha Bowl", 380, 14, 54, 12, veg=True, vgn=True),
    ]),
    ("the_coffee_club", "AU", "The Coffee Club", "https://coffeeclub.com.au/menu", [
        "the coffee club", "coffee club"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Grilled Chicken Caesar Salad", 480, 34, 20, 26),
        _item("Eggs Benedict (ham)", 520, 28, 38, 28, cat="breakfast"),
        _item("Chicken Schnitzel + Side Salad", 540, 36, 40, 24),
    ]),
    ("jamaica_blue", "AU", "Jamaica Blue", "https://jamaicablue.com.au/menu", [
        "jamaica blue"
    ], [
        _item("Cafe Latte (no sugar)", 120, 7, 10, 6, cat="beverage", veg=True),
        _item("Grilled Chicken Caesar", 440, 32, 20, 24),
        _item("Grainy Chicken Sandwich", 380, 26, 38, 12),
        _item("Smoked Salmon Bagel", 420, 22, 44, 14),
    ]),
    ("gloria_jeans", "AU", "Gloria Jean's Coffees", "https://gloriajeanscoffees.com.au/menu", [
        "gloria jeans", "gloria jean's", "gloria jean's coffees"
    ], [
        _item("Long Black (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Grilled Chicken Wrap", 360, 24, 36, 12),
    ]),
    ("pizza_capers", "AU", "Pizza Capers", "https://www.pizzacapers.com.au/menu", [
        "pizza capers"
    ], [
        _item("Grilled Chicken Personal", 520, 28, 62, 18),
        _item("Mediterranean Personal", 540, 24, 62, 22),
        _item("Capricciosa Personal", 560, 26, 62, 24),
        _item("Garden Salad (side)", 60, 2, 8, 2, cat="side", veg=True, vgn=True),
    ]),
    ("rolld", "AU", "Roll'd", "https://www.rolld.com.au/menu", [
        "rolld", "roll'd", "rolld vietnamese"
    ], [
        _item("Chicken Rice Paper Rolls (3pc)", 180, 14, 24, 2),
        _item("Grilled Chicken Vermicelli Bowl", 440, 30, 52, 12),
        _item("Pho Chicken (regular)", 420, 26, 52, 10),
        _item("Banh Mi Grilled Chicken", 380, 24, 42, 12),
    ]),

    # ═══════════════ CANADA depth (8) ═══════════════
    ("boston_pizza", "CA", "Boston Pizza", "https://bostonpizza.com/menu", [
        "boston pizza"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 62, 18),
        _item("Chicken Caesar Salad", 420, 32, 18, 24),
        _item("Thai Chicken Bites", 320, 24, 22, 14),
        _item("BBQ Chicken Pasta (half)", 480, 26, 60, 14),
    ]),
    ("pizza_pizza", "CA", "Pizza Pizza", "https://www.pizzapizza.ca/menu", [
        "pizza pizza"
    ], [
        _item("Grilled Chicken Personal", 520, 28, 62, 18),
        _item("Canadian Personal", 540, 26, 62, 22),
        _item("Veggie Personal", 460, 16, 66, 14, veg=True),
    ]),
    ("second_cup", "CA", "Second Cup", "https://www.secondcup.com/menu", [
        "second cup", "second cup cafe"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Turkey Sandwich", 360, 24, 38, 12),
    ]),
    ("booster_juice", "CA", "Booster Juice", "https://boosterjuice.com/menu", [
        "booster juice"
    ], [
        _item("Protein Smoothie (chocolate, small)", 280, 22, 30, 6, cat="beverage", veg=True),
        _item("Funky Monkey Smoothie (small)", 240, 5, 48, 4, cat="beverage", veg=True, vgn=True),
        _item("Matcha Mania Smoothie", 260, 4, 52, 4, cat="beverage", veg=True, vgn=True),
    ]),
    ("mr_sub", "CA", "Mr. Sub", "https://www.mrsub.ca/menu", [
        "mr sub", "mr. sub", "mister sub"
    ], [
        _item("Turkey Sub (6in, no mayo)", 340, 22, 42, 6),
        _item("Grilled Chicken Sub (6in)", 360, 26, 42, 8),
        _item("Veggie Sub (6in)", 260, 10, 42, 4, veg=True, vgn=True),
    ]),
    ("country_style", "CA", "Country Style", "https://countrystyle.com/menu", [
        "country style", "country style donuts"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Turkey Bacon Breakfast Sandwich", 320, 18, 30, 14, cat="breakfast"),
        _item("Grilled Chicken Wrap", 360, 24, 36, 12),
    ]),
    ("wendys", "CA", "Wendy's", "https://www.wendys.com/en-ca/menu", [
        "wendys", "wendy's"
    ], [
        _item("Grilled Chicken Sandwich", 360, 28, 38, 12),
        _item("Jr. Cheeseburger", 280, 15, 26, 14),
        _item("Apple Pecan Chicken Salad", 440, 36, 26, 22),
        _item("Chili (small)", 170, 14, 22, 5),
    ]),
    ("popeyes", "CA", "Popeyes", "https://www.popeyes.com/menu", [
        "popeyes", "popeyes louisiana kitchen"
    ], [
        _item("Blackened Chicken Tenders (3pc)", 230, 26, 6, 11),
        _item("Chicken Sandwich (classic, no mayo)", 540, 28, 50, 26),
        _item("Red Beans and Rice", 230, 8, 32, 8, cat="side", veg=True),
    ]),

    # ═══════════════ UK depth (8) ═══════════════
    ("caffe_nero", "GB", "Caffè Nero", "https://caffenero.com/uk/menu", [
        "caffe nero", "caffè nero"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Chicken Caesar Panini", 420, 28, 40, 16),
        _item("Smoked Salmon Bagel", 380, 22, 42, 12),
    ]),
    ("wetherspoons", "GB", "Wetherspoons", "https://www.jdwetherspoon.com/menu", [
        "wetherspoons", "j d wetherspoon", "jd wetherspoon"
    ], [
        _item("Chicken Breast Salad (no dressing)", 380, 36, 16, 18),
        _item("Gammon Steak + Eggs + Chips", 680, 42, 58, 28),
        _item("8oz Sirloin Steak (no chips)", 420, 44, 8, 22),
        _item("Vegetarian Curry + Rice", 560, 16, 86, 14, veg=True),
    ]),
    ("byron", "GB", "Byron Burger", "https://www.byronburgers.com/menu", [
        "byron", "byron burger", "byron burgers"
    ], [
        _item("Classic Hamburger", 580, 32, 40, 30),
        _item("Grilled Chicken Burger", 520, 34, 42, 24),
        _item("Skinny Fries (small)", 240, 3, 34, 10, cat="side", veg=True, vgn=True),
        _item("Buttermilk Chicken Burger", 580, 30, 48, 28),
    ]),
    ("gbk", "GB", "GBK (Gourmet Burger Kitchen)", "https://www.gbk.co.uk/menu", [
        "gbk", "gourmet burger kitchen"
    ], [
        _item("Classic Beef Burger", 620, 34, 42, 32),
        _item("Grilled Chicken Burger", 520, 36, 42, 22),
        _item("Kiwiburger", 640, 34, 44, 34),
        _item("Veggie Burger", 480, 18, 52, 20, veg=True),
    ]),
    ("honest_burgers", "GB", "Honest Burgers", "https://www.honestburgers.co.uk/menu", [
        "honest burgers", "honest"
    ], [
        _item("Honest Burger", 620, 36, 42, 34),
        _item("Chicken Burger (grilled)", 540, 36, 42, 24),
        _item("Plant Burger", 520, 18, 52, 24, veg=True, vgn=True),
        _item("Rosemary Salted Chips (small)", 260, 3, 36, 12, cat="side", veg=True, vgn=True),
    ]),
    ("yo_sushi", "GB", "YO! Sushi", "https://yosushi.com/menu", [
        "yo sushi", "yo! sushi", "yo"
    ], [
        _item("Salmon Sashimi (6pc)", 140, 20, 0, 7),
        _item("Tuna Nigiri (2pc)", 100, 10, 12, 2),
        _item("Chicken Katsu Curry (small)", 540, 28, 62, 20),
        _item("Edamame (side)", 140, 12, 10, 6, cat="side", veg=True, vgn=True),
    ]),
    ("pizza_hut", "GB", "Pizza Hut", "https://www.pizzahut.co.uk/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal Pizza", 540, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
        _item("Vegi Supreme Personal", 480, 16, 66, 14, veg=True),
    ]),
    ("pure", "GB", "Pure", "https://www.pure.co.uk/menu", [
        "pure", "pure london"
    ], [
        _item("Chicken & Avocado Salad", 420, 32, 18, 22),
        _item("Grilled Chicken Sandwich", 380, 28, 38, 14),
        _item("Falafel Wrap (veg)", 440, 14, 54, 16, veg=True, vgn=True),
        _item("Super Greens Bowl (chicken)", 460, 32, 42, 16),
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
