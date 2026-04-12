#!/usr/bin/env python3
"""
v11 — Option F: global expansion push.
IN +20 long-tail, US +15 specialty, LatAm +20 (AR/CO/CL/PE), Africa +15 (NG/KE/MA),
more Asia +10 (LK/NP/MM). Total ~80.
"""
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
    ("toit", "IN", "Toit", "https://toit.in/menu", [
        "toit", "toit brewery"
    ], [
        _item("Toit Pizza Personal", 540, 22, 60, 22, veg=True),
        _item("Grilled Chicken Platter", 480, 38, 14, 28),
        _item("Caesar Salad (chicken)", 420, 32, 18, 24),
    ]),
    ("hoppipola", "IN", "Hoppipola", "https://hoppipola.in/menu", [
        "hoppipola"
    ], [
        _item("Grilled Chicken Caesar", 440, 32, 18, 26),
        _item("Peri Peri Chicken Wings (6pc)", 320, 28, 4, 22),
        _item("Margherita Personal Pizza", 520, 22, 58, 20, veg=True),
    ]),
    ("beer_cafe", "IN", "The Beer Cafe", "https://thebeercafe.com/menu", [
        "beer cafe", "the beer cafe"
    ], [
        _item("Grilled Chicken Platter", 480, 38, 14, 28),
        _item("Classic Caesar Salad (chicken)", 420, 30, 18, 24),
        _item("Peri Peri Wings (6pc)", 320, 28, 4, 22),
    ]),
    ("hitchki", "IN", "Hitchki", "https://hitchki.in/menu", [
        "hitchki"
    ], [
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
        _item("Dal Makhani", 340, 12, 30, 18, veg=True),
    ]),
    ("hard_rock_cafe", "IN", "Hard Rock Cafe", "https://www.hardrockcafe.com/location/mumbai-india/menu", [
        "hard rock cafe", "hrc", "hard rock"
    ], [
        _item("Grilled Norwegian Salmon", 460, 42, 8, 26),
        _item("Legendary Burger (half)", 560, 32, 42, 28),
        _item("Grilled Chicken Sandwich", 540, 34, 44, 22),
    ]),
    ("mad_over_donuts", "IN", "Mad Over Donuts", "https://madoverdonuts.com/menu", [
        "mad over donuts", "mod", "modonuts"
    ], [
        _item("Classic Glazed Donut", 280, 4, 32, 14, cat="dessert", veg=True),
        _item("Chocolate Overload Donut", 340, 5, 42, 18, cat="dessert", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("oye_24", "IN", "Oye24", "https://oye24.com/menu", [
        "oye24", "oye 24"
    ], [
        _item("Grilled Chicken Tikka Bowl", 460, 32, 44, 16),
        _item("Protein Paneer Bowl", 420, 26, 40, 18, veg=True),
        _item("Chicken Shawarma Wrap", 440, 28, 42, 18),
    ]),
    ("bombay_blue", "IN", "Bombay Blue", "https://bombayblue.in/menu", [
        "bombay blue"
    ], [
        _item("Chicken Hakka Noodles", 520, 28, 62, 18),
        _item("Kung Pao Chicken", 440, 30, 22, 22),
        _item("Veg Manchurian Noodles", 480, 16, 62, 18, veg=True),
    ]),
    ("candies", "IN", "Candies", "https://candies.in/menu", [
        "candies"
    ], [
        _item("Chicken Pesto Sandwich", 420, 26, 42, 16),
        _item("Grilled Veg Sandwich", 320, 10, 42, 12, veg=True),
        _item("Chicken Tikka Wrap", 440, 26, 42, 18),
    ]),
    ("salt_water_cafe", "IN", "Salt Water Cafe", "https://saltwatergroup.com/menu", [
        "salt water cafe", "saltwater"
    ], [
        _item("Grilled Chicken Caesar", 440, 32, 18, 26),
        _item("Seabass Fillet + Vegetables", 420, 36, 12, 24),
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
    ]),
    ("nagarjuna", "IN", "Nagarjuna", "https://nagarjunarestaurants.com/menu", [
        "nagarjuna"
    ], [
        _item("Andhra Chicken Biryani", 580, 30, 64, 24),
        _item("Natukodi Curry", 440, 34, 12, 28),
        _item("Andhra Meals Veg", 580, 20, 86, 14, veg=True),
    ]),
    ("andhra_spice", "IN", "Andhra Spice", "https://andhraspice.com/menu", [
        "andhra spice"
    ], [
        _item("Andhra Chicken Biryani", 580, 30, 64, 24),
        _item("Prawn Pulusu", 420, 28, 22, 24),
        _item("Gongura Chicken (half)", 440, 32, 12, 28),
    ]),
    ("kebabsville", "IN", "Kebabsville", "https://kebabsville.in/menu", [
        "kebabsville"
    ], [
        _item("Seekh Kebab (mutton, 2pc)", 340, 26, 4, 22),
        _item("Chicken Tikka", 340, 30, 6, 20),
        _item("Paneer Tikka (veg)", 280, 16, 10, 18, veg=True),
    ]),
    ("dakshin_express", "IN", "Dakshin Express", "https://dakshinexpress.com/menu", [
        "dakshin express", "dakshin"
    ], [
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Mini Meals", 480, 16, 72, 12, veg=True),
        _item("Idli Sambar (4pc)", 280, 10, 52, 4, veg=True, vgn=True),
    ]),
    ("south_indies", "IN", "SouthIndies", "https://southindies.in/menu", [
        "southindies", "south indies"
    ], [
        _item("Chettinad Chicken Curry + Rice", 540, 32, 56, 20),
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Hyderabadi Biryani (chicken)", 580, 30, 64, 22),
    ]),
    ("wok_to_walk", "IN", "Wok to Walk", "https://woktowalk.in/menu", [
        "wok to walk", "wok to walk india"
    ], [
        _item("Chicken Noodle Bowl", 520, 28, 62, 18),
        _item("Beef Udon Bowl", 560, 30, 62, 22),
        _item("Veg Rice Bowl", 460, 14, 66, 14, veg=True),
    ]),
    ("jamoon", "IN", "Jamoon", "https://jamoon.in/menu", [
        "jamoon"
    ], [
        _item("Gulab Jamun (2pc)", 260, 4, 42, 10, cat="dessert", veg=True),
        _item("Rasmalai (2pc)", 240, 6, 32, 10, cat="dessert", veg=True),
    ]),
    ("dakshin", "IN", "Dakshin", "https://www.itchotels.com/dakshin-chennai/menu", [
        "dakshin", "itc dakshin"
    ], [
        _item("Chettinad Chicken Curry + Appam", 520, 32, 52, 20),
        _item("Kozhi Milagu Varuval", 380, 32, 10, 22),
        _item("Mini Tiffin (veg)", 480, 16, 72, 14, veg=True),
    ]),
    ("koramangala_social", "IN", "Social (Koramangala variant)", "https://socialoffline.in/menu", [
        "koramangala social", "indiranagar social", "social offline"
    ], [
        _item("Chicken Wings Peri Peri (6pc)", 340, 28, 6, 22),
        _item("Grilled Chicken Bao (2pc)", 320, 22, 30, 12),
        _item("Keema Pav", 460, 26, 40, 22),
    ]),
    ("cupcake_factory", "IN", "The Cupcake Factory", "https://thecupcakefactory.in/menu", [
        "cupcake factory", "the cupcake factory"
    ], [
        _item("Chocolate Cupcake (single)", 320, 4, 42, 16, cat="dessert", veg=True),
        _item("Vanilla Cupcake (single)", 300, 4, 40, 14, cat="dessert", veg=True),
    ]),

    # ═════════ USA +15 ═════════
    ("philz_coffee", "US", "Philz Coffee", "https://www.philzcoffee.com/menu", [
        "philz", "philz coffee"
    ], [
        _item("Mint Mojito (unsweetened)", 140, 3, 24, 3, cat="beverage", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Flat White (no sugar)", 110, 6, 8, 6, cat="beverage", veg=True),
    ]),
    ("stumptown", "US", "Stumptown Coffee Roasters", "https://www.stumptowncoffee.com/menu", [
        "stumptown", "stumptown coffee"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cold Brew (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("intelligentsia", "US", "Intelligentsia Coffee", "https://www.intelligentsia.com/menu", [
        "intelligentsia", "intelligentsia coffee"
    ], [
        _item("Espresso (no sugar)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cortado (no sugar)", 80, 4, 6, 4, cat="beverage", veg=True),
    ]),
    ("la_colombe", "US", "La Colombe Coffee Roasters", "https://www.lacolombe.com/menu", [
        "la colombe", "lacolombe"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Draft Latte (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
    ]),
    ("snooze", "US", "Snooze A.M. Eatery", "https://www.snoozeeatery.com/menu", [
        "snooze", "snooze am eatery", "snooze a.m. eatery"
    ], [
        _item("Juan Benedict", 640, 30, 42, 40, cat="breakfast"),
        _item("Lean & Mean Scramble", 420, 32, 16, 22, cat="breakfast"),
        _item("Chicken & Waffle (half)", 540, 28, 58, 22, cat="breakfast"),
    ]),
    ("eggslut", "US", "Eggslut", "https://eggslut.com/menu", [
        "eggslut"
    ], [
        _item("Fairfax Sandwich", 520, 22, 42, 28, cat="breakfast"),
        _item("Slut (soft egg over potato)", 380, 14, 26, 24, cat="breakfast", veg=True),
        _item("Bacon Egg Cheese", 540, 24, 36, 32, cat="breakfast"),
    ]),
    ("mendocino_farms", "US", "Mendocino Farms", "https://www.mendocinofarms.com/menu", [
        "mendocino farms", "mendocino"
    ], [
        _item("Not So Fried Chicken Sandwich", 540, 38, 52, 18),
        _item("Farm Club Sandwich", 620, 36, 52, 28),
        _item("Vegan Banh Mi", 460, 18, 66, 16, veg=True, vgn=True),
    ]),
    ("sweetfin", "US", "Sweetfin", "https://www.sweetfin.com/menu", [
        "sweetfin"
    ], [
        _item("Tuna Poke Bowl", 460, 34, 54, 10),
        _item("Salmon Bowl", 480, 34, 52, 14),
        _item("Vegan Nourish Bowl", 420, 16, 58, 14, veg=True, vgn=True),
    ]),
    ("teds_montana_grill", "US", "Ted's Montana Grill", "https://www.tedsmontanagrill.com/menu", [
        "teds montana grill", "ted's montana grill"
    ], [
        _item("Bison Sirloin 6oz + Veg", 380, 42, 14, 18),
        _item("Grilled Chicken Salad", 440, 34, 18, 24),
        _item("Grilled Salmon", 420, 40, 6, 24),
    ]),
    ("j_alexanders", "US", "J. Alexander's", "https://www.jalexanders.com/menu", [
        "j alexanders", "j. alexander's"
    ], [
        _item("Grilled Salmon + Vegetables", 460, 40, 10, 28),
        _item("Filet Mignon 6oz + Veg", 420, 42, 10, 22),
        _item("Grilled Chicken Breast", 360, 44, 6, 16),
    ]),
    ("cousins_subs", "US", "Cousins Subs", "https://www.cousinssubs.com/menu", [
        "cousins subs", "cousins"
    ], [
        _item("Turkey Sub (small)", 360, 22, 42, 10),
        _item("Grilled Chicken Sub", 400, 28, 42, 12),
        _item("Veggie Sub", 320, 10, 42, 10, veg=True),
    ]),
    ("charleys", "US", "Charleys Philly Steaks", "https://www.charleys.com/menu", [
        "charleys", "charley's", "charleys philly steaks"
    ], [
        _item("Chicken Philly (small)", 540, 30, 48, 22),
        _item("Philly Steak (small)", 580, 32, 48, 26),
        _item("Grilled Chicken Salad", 380, 32, 16, 20),
    ]),
    ("menchies", "US", "Menchie's Frozen Yogurt", "https://www.menchies.com/menu", [
        "menchies", "menchie's"
    ], [
        _item("Small Froyo (plain + fruit)", 200, 8, 32, 4, cat="dessert", veg=True),
        _item("Medium Froyo + Toppings", 340, 10, 50, 8, cat="dessert", veg=True),
    ]),
    ("orange_leaf", "US", "Orange Leaf Frozen Yogurt", "https://www.orangeleafyogurt.com/menu", [
        "orange leaf", "orange leaf frozen yogurt"
    ], [
        _item("Small Froyo (plain)", 180, 8, 30, 4, cat="dessert", veg=True),
        _item("Medium Froyo + Toppings", 320, 10, 48, 8, cat="dessert", veg=True),
    ]),
    ("red_mango", "US", "Red Mango", "https://www.redmangousa.com/menu", [
        "red mango"
    ], [
        _item("Small Plain Froyo + Fruit", 180, 10, 26, 2, cat="dessert", veg=True),
        _item("Acai Bowl (small)", 320, 6, 52, 8, cat="dessert", veg=True),
    ]),

    # ═════════ ARGENTINA +5 ═════════
    ("mostaza", "AR", "Mostaza", "https://www.mostaza.com.ar/menu", [
        "mostaza"
    ], [
        _item("Doble Cheese Classic", 620, 32, 44, 34),
        _item("Pollo Grill Burger", 480, 32, 42, 20),
        _item("Ensalada César con Pollo", 420, 32, 18, 24),
    ]),
    ("havanna", "AR", "Havanna", "https://www.havanna.com.ar/menu", [
        "havanna"
    ], [
        _item("Alfajor Clásico", 280, 4, 34, 14, cat="dessert", veg=True),
        _item("Alfajor Chocolate", 300, 4, 36, 16, cat="dessert", veg=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
    ]),
    ("freddo", "AR", "Freddo", "https://www.freddo.com.ar/menu", [
        "freddo"
    ], [
        _item("Helado Small (2 scoops)", 260, 5, 32, 14, cat="dessert", veg=True),
        _item("Dulce de Leche Scoop", 180, 3, 26, 8, cat="dessert", veg=True),
    ]),
    ("mcdonalds", "AR", "McDonald's", "https://mcdonalds.com.ar/menu", [
        "mcdonalds", "mcdonald's"
    ], [
        _item("McChicken", 400, 16, 40, 18),
        _item("Big Mac (no sauce)", 430, 26, 38, 18),
        _item("Ensalada César Pollo", 320, 28, 16, 16),
    ]),
    ("burger_king", "AR", "Burger King", "https://www.burgerking.com.ar/menu", [
        "burger king"
    ], [
        _item("Grilled Chicken Burger", 420, 30, 40, 16),
        _item("Whopper Junior", 340, 16, 28, 18),
    ]),

    # ═════════ COLOMBIA +5 ═════════
    ("crepes_waffles", "CO", "Crepes & Waffles", "https://www.crepesywaffles.com/menu", [
        "crepes y waffles", "crepes and waffles", "crepes & waffles"
    ], [
        _item("Crepe de Pollo al Curry", 520, 28, 54, 20),
        _item("Ensalada César con Pollo", 420, 32, 18, 24),
        _item("Waffle Clásico", 380, 8, 52, 14, cat="dessert", veg=True),
    ]),
    ("el_corral", "CO", "El Corral", "https://www.elcorral.com/menu", [
        "el corral"
    ], [
        _item("Corral Grilled Chicken", 480, 32, 42, 22),
        _item("Classic Hamburger", 560, 30, 42, 30),
    ]),
    ("frisby", "CO", "Frisby", "https://www.frisby.com.co/menu", [
        "frisby"
    ], [
        _item("Frisby Pollo Broaster (1pc)", 320, 26, 12, 18),
        _item("Pollo Apanado (2pc) + Arroz", 540, 32, 56, 22),
        _item("Ensalada + Pollo Grill", 380, 30, 18, 18),
    ]),
    ("presto", "CO", "Presto", "https://www.presto.com.co/menu", [
        "presto"
    ], [
        _item("Pollo Presto + Papas", 520, 30, 42, 26),
        _item("Hamburguesa Clásica", 520, 28, 42, 26),
    ]),
    ("mcdonalds", "CO", "McDonald's", "https://mcdonalds.com.co/menu", [
        "mcdonalds", "mcdonald's"
    ], [
        _item("McChicken", 400, 16, 40, 18),
        _item("Big Mac (no sauce)", 430, 26, 38, 18),
    ]),

    # ═════════ CHILE +5 ═════════
    ("doggis", "CL", "Doggis", "https://www.doggis.cl/menu", [
        "doggis"
    ], [
        _item("Completo Italiano", 540, 18, 58, 24),
        _item("Chacarero (beef)", 620, 32, 62, 26),
    ]),
    ("melt", "CL", "Melt Burger", "https://www.meltburger.cl/menu", [
        "melt", "melt burger"
    ], [
        _item("Classic Melt Burger", 560, 32, 42, 30),
        _item("Grilled Chicken Burger", 480, 32, 42, 20),
    ]),
    ("juan_maestro", "CL", "Juan Maestro", "https://www.juanmaestro.cl/menu", [
        "juan maestro"
    ], [
        _item("Completo Italiano", 540, 18, 58, 24),
        _item("Chacarero Completo", 680, 32, 62, 32),
    ]),
    ("mcdonalds", "CL", "McDonald's", "https://mcdonalds.cl/menu", [
        "mcdonalds", "mcdonald's"
    ], [
        _item("McChicken", 400, 16, 40, 18),
        _item("Big Mac (no sauce)", 430, 26, 38, 18),
    ]),
    ("kfc", "CL", "KFC", "https://www.kfc.cl/menu", [
        "kfc"
    ], [
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Grilled Chicken (1pc)", 180, 24, 2, 9),
    ]),

    # ═════════ PERU +5 ═════════
    ("bembos", "PE", "Bembos", "https://www.bembos.com.pe/menu", [
        "bembos"
    ], [
        _item("Hamburguesa Clásica", 520, 28, 42, 26),
        _item("Pollo Grillado Burger", 460, 30, 42, 18),
    ]),
    ("don_belisario", "PE", "Don Belisario", "https://www.donbelisario.pe/menu", [
        "don belisario"
    ], [
        _item("Quarter Chicken + Rice", 560, 34, 58, 22),
        _item("Half Chicken", 640, 52, 8, 40),
    ]),
    ("pardos_chicken", "PE", "Pardo's Chicken", "https://www.pardoschicken.pe/menu", [
        "pardos chicken", "pardo's chicken", "pardos"
    ], [
        _item("Quarter Pollo a la Brasa + Rice", 560, 34, 58, 22),
        _item("Half Pollo a la Brasa", 640, 52, 8, 40),
        _item("Ensalada + Chicken", 380, 30, 18, 18),
    ]),
    ("la_lucha", "PE", "La Lucha Sanguchería", "https://www.lalucha.com.pe/menu", [
        "la lucha", "la lucha sangucheria", "la lucha sanguchería"
    ], [
        _item("Chicharrón Sandwich", 620, 32, 48, 32),
        _item("Pavo Sandwich (turkey)", 440, 28, 44, 18),
    ]),
    ("mcdonalds", "PE", "McDonald's", "https://mcdonalds.com.pe/menu", [
        "mcdonalds", "mcdonald's"
    ], [
        _item("McChicken", 400, 16, 40, 18),
        _item("Cuarto de Libra (no sauce)", 520, 30, 40, 26),
    ]),

    # ═════════ NIGERIA +5 ═════════
    ("chicken_republic", "NG", "Chicken Republic", "https://chicken-republic.com/menu", [
        "chicken republic"
    ], [
        _item("Refuel Max (chicken + rice)", 620, 32, 68, 24),
        _item("Grilled Chicken + Rice", 520, 34, 58, 16),
        _item("Jollof Rice + Chicken", 560, 30, 62, 20),
    ]),
    ("mr_biggs", "NG", "Mr. Biggs", "https://www.mrbiggs.com/menu", [
        "mr biggs", "mr. biggs", "mrbiggs"
    ], [
        _item("Meat Pie (1pc)", 320, 12, 32, 16),
        _item("Chicken + Rice", 540, 30, 62, 18),
        _item("Scotch Egg (1pc)", 280, 14, 16, 18),
    ]),
    ("tantalizers", "NG", "Tantalizers", "https://www.tantalizers.com/menu", [
        "tantalizers"
    ], [
        _item("Jollof Rice + Chicken", 560, 30, 62, 20),
        _item("Fried Rice + Chicken", 580, 28, 68, 18),
        _item("Moi Moi (beans cake)", 220, 14, 24, 8, veg=True),
    ]),
    ("sweet_sensation", "NG", "Sweet Sensation", "https://sweetsensationng.com/menu", [
        "sweet sensation"
    ], [
        _item("Jollof Rice + Chicken", 560, 30, 62, 20),
        _item("Moi Moi", 220, 14, 24, 8, veg=True),
        _item("Chicken Suya", 320, 28, 4, 22),
    ]),
    ("kfc", "NG", "KFC", "https://www.kfc.com.ng/menu", [
        "kfc"
    ], [
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Grilled Chicken (1pc)", 180, 24, 2, 9),
        _item("Zinger Burger", 470, 24, 44, 22),
    ]),

    # ═════════ KENYA +5 ═════════
    ("java_house", "KE", "Java House", "https://javahouseafrica.com/menu", [
        "java house", "nairobi java house"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Caesar Salad", 440, 32, 18, 26),
        _item("Grilled Chicken Sandwich", 420, 28, 42, 16),
        _item("Chicken Tikka Wrap", 460, 28, 44, 18),
    ]),
    ("artcaffe", "KE", "Artcaffe", "https://artcaffegroup.com/menu", [
        "artcaffe", "art caffe"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Grilled Chicken Caesar", 440, 32, 18, 26),
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
    ]),
    ("kfc", "KE", "KFC", "https://www.kfc.co.ke/menu", [
        "kfc"
    ], [
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Grilled Chicken (1pc)", 180, 24, 2, 9),
    ]),
    ("pizza_inn", "KE", "Pizza Inn", "https://pizzainn.co.ke/menu", [
        "pizza inn"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 60, 20),
        _item("Hawaiian Personal", 540, 22, 68, 18),
    ]),
    ("debonairs", "KE", "Debonairs Pizza", "https://www.debonairspizza.co.ke/menu", [
        "debonairs", "debonairs pizza"
    ], [
        _item("Chicken Tikka Personal", 540, 28, 60, 20),
        _item("Veg Supreme Personal", 480, 16, 66, 14, veg=True),
    ]),

    # ═════════ MOROCCO +5 ═════════
    ("paul", "MA", "Paul", "https://www.paul.ma/menu", [
        "paul", "paul bakery"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Caesar Salad", 420, 32, 18, 22),
        _item("Plain Croissant", 260, 6, 26, 14, cat="breakfast", veg=True),
    ]),
    ("pizza_hut", "MA", "Pizza Hut", "https://pizzahut.ma/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
    ]),
    ("mcdonalds", "MA", "McDonald's", "https://mcdonalds.ma/menu", [
        "mcdonalds", "mcdonald's"
    ], [
        _item("McChicken", 400, 16, 40, 18),
        _item("Grilled Chicken Deluxe", 380, 28, 34, 14),
    ]),
    ("kfc", "MA", "KFC", "https://www.kfc.ma/menu", [
        "kfc"
    ], [
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Grilled Chicken Piece", 160, 22, 1, 8),
    ]),
    ("cafe_maure", "MA", "Café Maure", "https://cafemaure.ma/menu", [
        "cafe maure", "café maure"
    ], [
        _item("Moroccan Mint Tea (no sugar)", 15, 0, 3, 0, cat="beverage", veg=True, vgn=True),
        _item("Grilled Chicken Tagine", 440, 36, 22, 22),
        _item("Vegetable Couscous", 460, 14, 72, 12, veg=True, vgn=True),
    ]),

    # ═════════ SRI LANKA +4 ═════════
    ("pizza_hut", "LK", "Pizza Hut", "https://www.pizzahut.lk/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
    ]),
    ("kfc", "LK", "KFC", "https://www.kfclanka.com/menu", [
        "kfc"
    ], [
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Rice Bowl Chicken", 520, 30, 62, 18),
    ]),
    ("dinemore", "LK", "Dinemore", "https://dinemore.lk/menu", [
        "dinemore"
    ], [
        _item("Grilled Chicken + Rice", 520, 32, 58, 16),
        _item("Chicken Fried Rice", 560, 28, 68, 18),
        _item("Chicken Kottu", 640, 30, 74, 22),
    ]),
    ("burgers_king", "LK", "Burger's King LK", "https://burgerslk.com/menu", [
        "burgers king", "burger's king"
    ], [
        _item("Grilled Chicken Burger", 460, 30, 42, 20),
        _item("Classic Cheeseburger", 520, 28, 42, 26),
    ]),

    # ═════════ NEPAL +3 ═════════
    ("bakery_cafe", "NP", "Bakery Cafe", "https://www.bakerycafe.com.np/menu", [
        "bakery cafe", "bakery cafe nepal"
    ], [
        _item("Chicken Momo (10pc)", 420, 28, 42, 14),
        _item("Veg Momo (10pc)", 340, 12, 44, 12, veg=True),
        _item("Chicken Sandwich", 340, 22, 38, 10),
    ]),
    ("kfc", "NP", "KFC", "https://www.kfcnepal.com/menu", [
        "kfc"
    ], [
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Grilled Chicken (1pc)", 180, 24, 2, 9),
    ]),
    ("roadhouse_cafe", "NP", "Roadhouse Cafe", "https://roadhousecafe.com.np/menu", [
        "roadhouse cafe"
    ], [
        _item("Grilled Chicken Pasta", 540, 30, 56, 18),
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
    ]),

    # ═════════ MYANMAR +3 ═════════
    ("kfc", "MM", "KFC", "https://www.kfcmyanmar.com/menu", [
        "kfc"
    ], [
        _item("Original Recipe (1pc breast)", 340, 32, 10, 20),
        _item("Rice Bowl Chicken", 520, 30, 62, 18),
    ]),
    ("city_mart", "MM", "City Mart Food Center", "https://citymart.com.mm/menu", [
        "city mart", "citymart"
    ], [
        _item("Grilled Chicken + Rice", 480, 30, 58, 14),
        _item("Chicken Noodles", 460, 24, 58, 14),
    ]),
    ("shwe_pu_zun", "MM", "Shwe Pu Zun", "https://shwepuzun.com/menu", [
        "shwe pu zun"
    ], [
        _item("Mohinga (fish noodle soup)", 440, 24, 52, 14),
        _item("Chicken Biryani", 580, 30, 64, 22),
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
