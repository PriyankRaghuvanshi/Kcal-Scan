#!/usr/bin/env python3
"""v10: UK+CA saturation + Europe + Middle East (~69 chains)."""
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
    # ═════════ UK +13 ═════════
    ("dishoom", "GB", "Dishoom", "https://www.dishoom.com/menu", [
        "dishoom"
    ], [
        _item("Chicken Ruby", 520, 36, 18, 32),
        _item("House Black Daal", 420, 12, 32, 24, veg=True),
        _item("Chicken Biryani (family, share)", 620, 34, 62, 26),
        _item("Lamb Raan Roll", 520, 32, 44, 22),
        _item("Breakfast Bacon Naan Roll", 480, 22, 48, 22),
    ]),
    ("busaba", "GB", "Busaba", "https://busaba.com/menu", [
        "busaba", "busaba eathai"
    ], [
        _item("Green Curry Chicken", 460, 30, 30, 22),
        _item("Pad Thai Chicken", 540, 30, 62, 18),
        _item("Tom Yum Chicken Soup", 220, 22, 14, 8),
        _item("Vegan Pad Thai", 480, 14, 66, 16, veg=True, vgn=True),
    ]),
    ("pizza_pilgrims", "GB", "Pizza Pilgrims", "https://www.pizzapilgrims.co.uk/menu", [
        "pizza pilgrims"
    ], [
        _item("Margherita Pizza", 540, 22, 62, 18, veg=True),
        _item("Prosciutto Pizza", 580, 28, 60, 22),
        _item("Veggie Pizza", 500, 18, 62, 18, veg=True),
    ]),
    ("gails_bakery", "GB", "Gail's Bakery", "https://gailsbread.co.uk/menu", [
        "gails", "gail's", "gails bakery"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cheddar Rosemary Croissant", 380, 14, 34, 20),
        _item("Avocado Toast", 360, 10, 40, 16, veg=True),
        _item("Turkey & Avocado Sandwich", 420, 28, 38, 18),
    ]),
    ("ole_and_steen", "GB", "Ole & Steen", "https://www.oleandsteen.com/menu", [
        "ole and steen", "ole & steen"
    ], [
        _item("Plain Sourdough Sandwich (turkey)", 380, 26, 40, 10),
        _item("Danish Rye Open Sandwich (chicken)", 340, 24, 36, 10),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("shake_shack", "GB", "Shake Shack", "https://www.shakeshack.co.uk/menu", [
        "shake shack"
    ], [
        _item("ShackBurger (single)", 480, 26, 24, 32),
        _item("Chick'n Shack", 480, 28, 38, 22),
        _item("SmokeShack", 520, 28, 24, 36),
    ]),
    ("bella_italia", "GB", "Bella Italia", "https://www.bellaitalia.co.uk/menu", [
        "bella italia", "bella"
    ], [
        _item("Grilled Chicken Pasta", 540, 34, 56, 18),
        _item("Margherita Personal", 540, 22, 62, 18, veg=True),
        _item("Carbonara (half)", 520, 26, 58, 22),
    ]),
    ("cote_brasserie", "GB", "Côte Brasserie", "https://www.cote.co.uk/menu", [
        "cote", "côte", "cote brasserie", "côte brasserie"
    ], [
        _item("Grilled Chicken Breast + Salad", 380, 38, 12, 20),
        _item("Salmon Fillet + Vegetables", 440, 36, 10, 28),
        _item("Steak Frites 6oz (no fries)", 360, 38, 4, 22),
    ]),
    ("coco_di_mama", "GB", "Coco di Mama", "https://www.cocodimama.co.uk/menu", [
        "coco di mama"
    ], [
        _item("Chicken Pesto Pasta", 520, 30, 56, 18),
        _item("Meatball Marinara Pasta", 540, 28, 58, 22),
        _item("Caesar Salad (chicken)", 420, 30, 18, 24),
    ]),
    ("benugo", "GB", "Benugo", "https://www.benugo.com/menu", [
        "benugo"
    ], [
        _item("Grilled Chicken Focaccia", 440, 28, 42, 16),
        _item("Falafel Wrap", 420, 14, 54, 16, veg=True, vgn=True),
        _item("Soup of the Day (portion)", 180, 8, 22, 6, cat="side", veg=True),
    ]),
    ("crussh", "GB", "Crussh", "https://crussh.com/menu", [
        "crussh"
    ], [
        _item("Grilled Chicken Power Bowl", 460, 32, 46, 14),
        _item("Chicken Caesar Wrap", 380, 26, 40, 12),
        _item("Protein Smoothie (vanilla)", 280, 24, 30, 6, cat="beverage", veg=True),
    ]),
    ("taco_bell", "GB", "Taco Bell", "https://www.tacobell.co.uk/menu", [
        "taco bell"
    ], [
        _item("Crunchy Taco (chicken, 1pc)", 170, 9, 14, 9),
        _item("Power Bowl (chicken)", 480, 30, 52, 16),
        _item("Soft Taco Grilled Chicken", 180, 12, 18, 8),
    ]),
    ("chipotle", "GB", "Chipotle", "https://www.chipotle.co.uk/menu", [
        "chipotle", "chipotle mexican grill"
    ], [
        _item("Chicken Burrito Bowl", 520, 36, 58, 16),
        _item("Steak Bowl", 560, 34, 58, 22),
        _item("Sofritas Bowl (vegan)", 420, 18, 56, 12, veg=True, vgn=True),
    ]),

    # ═════════ CA +10 ═════════
    ("white_spot", "CA", "White Spot", "https://www.whitespot.ca/menu", [
        "white spot"
    ], [
        _item("Legendary Grilled Chicken Burger", 540, 34, 42, 24),
        _item("Chicken Caesar Salad", 440, 34, 18, 26),
        _item("Salmon Bowl", 480, 38, 44, 18),
    ]),
    ("panago", "CA", "Panago Pizza", "https://www.panago.com/menu", [
        "panago", "panago pizza"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 62, 18),
        _item("Vegetarian Personal", 480, 18, 64, 16, veg=True),
        _item("BBQ Chicken Personal", 540, 30, 60, 20),
    ]),
    ("greco_pizza", "CA", "Greco Pizza", "https://www.greco.ca/menu", [
        "greco pizza", "greco"
    ], [
        _item("Grilled Chicken Personal", 520, 28, 62, 18),
        _item("Donair Personal Pizza", 560, 30, 58, 24),
    ]),
    ("smokes_poutinerie", "CA", "Smoke's Poutinerie", "https://www.smokespoutinerie.com/menu", [
        "smokes poutinerie", "smoke's poutinerie", "smokes"
    ], [
        _item("Classic Poutine (small)", 640, 22, 74, 28, cat="side", veg=True),
        _item("Chicken Poutine (small)", 720, 30, 74, 32),
    ]),
    ("thai_express", "CA", "Thai Express", "https://thaiexpress.ca/menu", [
        "thai express"
    ], [
        _item("Pad Thai Chicken (regular)", 560, 30, 68, 18),
        _item("Green Curry Chicken + Rice", 520, 30, 62, 18),
        _item("Tom Yum Chicken Soup", 220, 22, 14, 8),
    ]),
    ("manchu_wok", "CA", "Manchu Wok", "https://www.manchuwok.com/menu", [
        "manchu wok"
    ], [
        _item("Orange Chicken + Rice", 540, 28, 64, 18),
        _item("Mongolian Beef + Rice", 580, 30, 62, 22),
        _item("Vegetable Lo Mein", 460, 14, 68, 14, veg=True),
    ]),
    ("opa_of_greece", "CA", "Opa! Of Greece", "https://opaofgreece.com/menu", [
        "opa", "opa of greece", "opa! of greece"
    ], [
        _item("Chicken Souvlaki Bowl", 480, 36, 44, 16),
        _item("Beef Souvlaki Wrap", 520, 32, 46, 20),
        _item("Greek Salad + Chicken", 380, 30, 18, 22),
    ]),
    ("teriyaki_experience", "CA", "Teriyaki Experience", "https://teriyakiexperience.com/menu", [
        "teriyaki experience"
    ], [
        _item("Teriyaki Chicken + Rice", 480, 32, 58, 12),
        _item("Teriyaki Salmon + Rice", 520, 36, 56, 16),
        _item("Chicken Rice Bowl", 460, 30, 60, 12),
    ]),
    ("rickys", "CA", "Ricky's All Day Grill", "https://rickys.com/menu", [
        "rickys", "ricky's", "rickys all day grill"
    ], [
        _item("Grilled Chicken + Vegetables", 380, 38, 14, 18),
        _item("Chicken Caesar Salad", 420, 32, 18, 22),
        _item("Grilled Salmon + Rice", 440, 36, 46, 18),
    ]),
    ("triple_os", "CA", "Triple O's", "https://www.tripleos.com/menu", [
        "triple os", "triple o's"
    ], [
        _item("Chicken Caesar Wrap", 460, 30, 44, 18),
        _item("Signature Legendary Burger", 620, 32, 44, 34),
        _item("Chicken Burger", 480, 32, 42, 18),
    ]),

    # ═════════ ITALY +9 ═════════
    ("autogrill", "IT", "Autogrill", "https://www.autogrill.it/menu", [
        "autogrill"
    ], [
        _item("Panino Prosciutto", 420, 22, 42, 16),
        _item("Insalata di Pollo (chicken salad)", 360, 30, 14, 18),
        _item("Primo di Pasta (small)", 420, 16, 58, 12, veg=True),
    ]),
    ("vapiano", "IT", "Vapiano", "https://www.vapiano.it/menu", [
        "vapiano"
    ], [
        _item("Pasta Pollo Aglio (chicken)", 540, 34, 56, 18),
        _item("Margherita Pizza", 520, 22, 58, 20, veg=True),
        _item("Pesto Pasta (veg)", 480, 14, 62, 18, veg=True),
    ]),
    ("old_wild_west", "IT", "Old Wild West", "https://www.oldwildwest.it/menu", [
        "old wild west"
    ], [
        _item("Grilled Chicken Breast", 340, 38, 4, 18),
        _item("Chicken Salad (grilled)", 420, 32, 18, 22),
        _item("Ribs (half rack)", 620, 38, 22, 40),
    ]),
    ("rossopomodoro", "IT", "Rossopomodoro", "https://www.rossopomodoro.it/menu", [
        "rossopomodoro"
    ], [
        _item("Margherita D.O.P.", 540, 22, 64, 18, veg=True),
        _item("Diavola Pizza", 580, 28, 62, 22),
        _item("Prosciutto e Rucola", 560, 28, 58, 22),
    ]),
    ("alice_pizza", "IT", "Alice Pizza", "https://www.alicepizza.it/menu", [
        "alice pizza", "alice"
    ], [
        _item("Margherita Slice", 380, 16, 48, 14, veg=True),
        _item("Prosciutto Crudo Slice", 440, 22, 48, 18),
        _item("Verdure Slice (veg)", 360, 14, 48, 12, veg=True),
    ]),
    ("spizzico", "IT", "Spizzico", "https://www.spizzico.com/menu", [
        "spizzico"
    ], [
        _item("Pizza Margherita Slice", 380, 16, 48, 14, veg=True),
        _item("Pollo Arrosto (grilled chicken)", 380, 38, 4, 20),
    ]),
    ("grom", "IT", "Grom", "https://www.grom.it/menu", [
        "grom"
    ], [
        _item("Small Gelato Cup (any flavor)", 180, 4, 22, 8, cat="dessert", veg=True),
        _item("Sorbet Scoop", 110, 1, 26, 0, cat="dessert", veg=True, vgn=True),
    ]),
    ("venchi", "IT", "Venchi", "https://it.venchi.com/menu", [
        "venchi"
    ], [
        _item("Dark Chocolate Gelato Scoop", 200, 4, 24, 10, cat="dessert", veg=True),
        _item("Dark Chocolate Bar (50g)", 280, 4, 28, 18, cat="dessert", veg=True),
    ]),
    ("la_piadineria", "IT", "La Piadineria", "https://lapiadineria.it/menu", [
        "la piadineria", "piadineria"
    ], [
        _item("Piadina Prosciutto", 440, 24, 42, 18),
        _item("Piadina Pollo (chicken)", 420, 28, 42, 16),
        _item("Piadina Vegetariana", 360, 14, 46, 12, veg=True),
    ]),

    # ═════════ SPAIN +5 ═════════
    ("100_montaditos", "ES", "100 Montaditos", "https://www.100montaditos.com/menu", [
        "100 montaditos", "cien montaditos"
    ], [
        _item("Jamón Serrano Montadito (2pc)", 240, 14, 26, 10),
        _item("Pollo Montadito (chicken, 2pc)", 260, 16, 28, 10),
        _item("Tortilla Española (portion)", 320, 14, 26, 18, veg=True),
    ]),
    ("rodilla", "ES", "Rodilla", "https://www.rodilla.es/menu", [
        "rodilla"
    ], [
        _item("Sandwich Pollo", 340, 24, 36, 12),
        _item("Sandwich Vegetal (veg)", 280, 10, 38, 10, veg=True),
        _item("Jamón Ibérico Sandwich", 380, 22, 36, 14),
    ]),
    ("pans_and_company", "ES", "Pans & Company", "https://www.pansandcompany.com/menu", [
        "pans", "pans and company", "pans & company"
    ], [
        _item("Grilled Chicken Baguette", 420, 30, 44, 14),
        _item("Serranito Sandwich", 460, 28, 48, 18),
        _item("Vegetal Sandwich", 340, 12, 42, 12, veg=True),
    ]),
    ("goiko", "ES", "Goiko", "https://www.goiko.com/menu", [
        "goiko", "goiko grill"
    ], [
        _item("Kevin Bacon Burger", 720, 38, 44, 44),
        _item("Classic Beef Burger", 560, 32, 42, 28),
        _item("Veggie Burger", 480, 18, 54, 22, veg=True),
    ]),
    ("fosters_hollywood", "ES", "Foster's Hollywood", "https://www.fostershollywood.es/menu", [
        "fosters hollywood", "foster's hollywood"
    ], [
        _item("Grilled Chicken Caesar", 440, 32, 18, 26),
        _item("Classic Burger", 620, 32, 42, 34),
        _item("BBQ Ribs (half)", 620, 38, 22, 38),
    ]),

    # ═════════ NETHERLANDS +3 ═════════
    ("la_place", "NL", "La Place", "https://www.laplace.nl/menu", [
        "la place"
    ], [
        _item("Grilled Chicken Salad", 380, 32, 16, 20),
        _item("Pumpkin Soup", 220, 6, 22, 10, cat="side", veg=True),
        _item("Veggie Wrap", 360, 14, 44, 14, veg=True),
    ]),
    ("febo", "NL", "FEBO", "https://www.febo.nl/menu", [
        "febo"
    ], [
        _item("Kroket", 240, 8, 20, 14, cat="snack"),
        _item("Frikandel", 280, 12, 16, 18, cat="snack"),
    ]),
    ("maoz", "NL", "Maoz Vegetarian", "https://www.maozveg.com/menu", [
        "maoz", "maoz vegetarian"
    ], [
        _item("Falafel Pita", 460, 16, 58, 18, veg=True, vgn=True),
        _item("Falafel Bowl", 440, 18, 52, 18, veg=True, vgn=True),
    ]),

    # ═════════ POLAND +4 ═════════
    ("bobby_burger", "PL", "Bobby Burger", "https://bobbyburger.pl/menu", [
        "bobby burger"
    ], [
        _item("Classic Bobby Burger", 540, 30, 42, 28),
        _item("Chicken Burger", 480, 32, 42, 20),
        _item("Veggie Burger", 440, 16, 52, 20, veg=True),
    ]),
    ("max_burgers", "PL", "Max Burgers", "https://max.pl/menu", [
        "max burgers", "max"
    ], [
        _item("Grand Deluxe Burger", 560, 32, 42, 28),
        _item("Grilled Chicken Burger", 440, 30, 42, 18),
        _item("Delifresh Salad", 280, 22, 14, 14),
    ]),
    ("telepizza", "PL", "Telepizza", "https://www.telepizza.pl/menu", [
        "telepizza"
    ], [
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
        _item("Grilled Chicken Personal", 540, 28, 60, 20),
        _item("Carbonara Personal", 560, 26, 58, 24),
    ]),
    ("pizza_hut", "PL", "Pizza Hut", "https://pizzahut.pl/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
    ]),

    # ═════════ GERMANY +5 ═════════
    ("hans_im_gluck", "DE", "Hans im Glück", "https://www.hansimglueck-burgergrill.de/menu", [
        "hans im glueck", "hans im glück"
    ], [
        _item("Grilled Chicken Burger", 520, 34, 42, 22),
        _item("Classic Burger", 600, 32, 42, 34),
        _item("Veggie Burger", 480, 18, 54, 22, veg=True),
    ]),
    ("losteria", "DE", "L'Osteria", "https://www.losteria.de/menu", [
        "losteria", "l'osteria"
    ], [
        _item("Pizza Margherita", 520, 22, 58, 20, veg=True),
        _item("Pizza Prosciutto", 540, 28, 58, 22),
        _item("Pasta Pollo (chicken)", 520, 32, 56, 18),
    ]),
    ("backwerk", "DE", "BackWerk", "https://www.back-werk.de/menu", [
        "backwerk", "back-werk"
    ], [
        _item("Grilled Chicken Sandwich", 380, 26, 38, 14),
        _item("Käsebrezel (cheese pretzel)", 340, 10, 46, 12, cat="snack", veg=True),
        _item("Ham & Cheese Baguette", 460, 22, 48, 18),
    ]),
    ("kamps", "DE", "Kamps Bäckerei", "https://www.kamps.de/menu", [
        "kamps", "kamps baeckerei", "kamps bäckerei"
    ], [
        _item("Chicken Croissant", 380, 18, 36, 18),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Vollkornbrötchen (whole grain roll + turkey)", 320, 20, 36, 8),
    ]),
    ("dunkin", "DE", "Dunkin'", "https://www.dunkin.de/menu", [
        "dunkin", "dunkin'", "dunkin donuts"
    ], [
        _item("Original Glazed Donut", 260, 3, 31, 14, cat="dessert", veg=True),
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Turkey Bagel", 360, 22, 42, 10),
    ]),

    # ═════════ FRANCE +4 ═════════
    ("brioche_doree", "FR", "Brioche Dorée", "https://www.briochedoree.fr/menu", [
        "brioche doree", "brioche dorée"
    ], [
        _item("Sandwich Poulet Crudités", 380, 26, 42, 12),
        _item("Quiche Lorraine (slice)", 380, 16, 28, 22),
        _item("Salade César Poulet", 420, 30, 18, 24),
    ]),
    ("class_croute", "FR", "Class'Croute", "https://www.classcroute.com/menu", [
        "class croute", "class'croute", "classcroute"
    ], [
        _item("Sandwich Poulet", 380, 26, 40, 12),
        _item("Salade César", 420, 30, 18, 24),
    ]),
    ("la_mie_caline", "FR", "La Mie Câline", "https://lamiecaline.com/menu", [
        "la mie caline", "la mie câline"
    ], [
        _item("Jambon Beurre Baguette", 420, 20, 48, 16),
        _item("Sandwich Poulet", 380, 26, 42, 12),
        _item("Quiche Lorraine", 380, 16, 28, 22),
    ]),
    ("poulet_reti", "FR", "Poulet Réti", "https://www.pouletreti.fr/menu", [
        "poulet reti", "poulet réti"
    ], [
        _item("Quarter Rotisserie Chicken + Veg", 440, 42, 14, 24),
        _item("Grilled Chicken Thigh + Salad", 360, 36, 8, 22),
    ]),

    # ═════════ SAUDI ARABIA +4 ═════════
    ("herfy", "SA", "Herfy", "https://www.herfy.com/menu", [
        "herfy"
    ], [
        _item("Herfy Super Burger", 540, 28, 42, 28),
        _item("Grilled Chicken Sandwich", 440, 28, 42, 18),
        _item("Chicken Strips (4pc)", 360, 28, 18, 18),
    ]),
    ("kudu", "SA", "Kudu", "https://kudu.com.sa/menu", [
        "kudu"
    ], [
        _item("Grilled Chicken Shawarma", 440, 32, 42, 14),
        _item("Kudu Classic Burger", 520, 28, 42, 26),
        _item("Chicken Meal + Rice", 580, 30, 62, 22),
    ]),
    ("al_tazaj", "SA", "Al Tazaj", "https://altazaj.com/menu", [
        "al tazaj", "altazaj"
    ], [
        _item("Half Chicken + Bread", 580, 42, 38, 30),
        _item("Chicken Combo + Rice", 620, 40, 52, 26),
        _item("Quarter Chicken + Veg", 380, 32, 8, 22),
    ]),
    ("casper_and_gambinis", "SA", "Casper & Gambini's", "https://casperandgambinis.com/menu", [
        "casper and gambinis", "casper & gambini's", "casper gambinis"
    ], [
        _item("Grilled Chicken Paillard", 440, 42, 12, 22),
        _item("Caesar Salad + Chicken", 420, 32, 18, 24),
        _item("Shrimp Pasta", 480, 28, 52, 16),
    ]),

    # ═════════ TURKEY +5 ═════════
    ("simit_sarayi", "TR", "Simit Sarayı", "https://www.simitsarayi.com/menu", [
        "simit sarayi", "simit sarayı"
    ], [
        _item("Simit (plain, 100g)", 320, 10, 62, 5, cat="snack", veg=True, vgn=True),
        _item("Peynirli Poğaça (cheese)", 260, 10, 28, 12, veg=True),
        _item("Cay (Turkish tea, unsweetened)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("kahve_dunyasi", "TR", "Kahve Dünyası", "https://www.kahvedunyasi.com/menu", [
        "kahve dunyasi", "kahve dünyası"
    ], [
        _item("Turkish Coffee (unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True),
        _item("Americano", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chocolate Bar (50g)", 280, 4, 28, 18, cat="dessert", veg=True),
    ]),
    ("tavuk_dunyasi", "TR", "Tavuk Dünyası", "https://www.tavukdunyasi.com/menu", [
        "tavuk dunyasi", "tavuk dünyası"
    ], [
        _item("Grilled Chicken (half, marinated)", 380, 40, 4, 22),
        _item("Chicken Döner + Rice", 580, 32, 62, 20),
        _item("Chicken Wings (6pc)", 420, 32, 6, 28),
    ]),
    ("bigchefs", "TR", "Big Chefs", "https://www.bigchefs.com.tr/menu", [
        "bigchefs", "big chefs"
    ], [
        _item("Grilled Chicken Paillard", 440, 40, 12, 22),
        _item("Salmon Teriyaki + Rice", 520, 36, 58, 18),
        _item("Caesar Salad + Chicken", 440, 32, 18, 26),
    ]),
    ("gunaydin", "TR", "Günaydın", "https://gunaydin.com.tr/menu", [
        "gunaydin", "günaydın", "günaydin"
    ], [
        _item("Mixed Grill (share, per portion)", 620, 48, 14, 42),
        _item("Adana Kebab (1 skewer)", 420, 32, 6, 28),
        _item("Chicken Shish Kebab (1 skewer)", 380, 34, 6, 22),
    ]),

    # ═════════ EGYPT +5 ═════════
    ("gad", "EG", "Gad", "https://gadrestaurants.com/menu", [
        "gad"
    ], [
        _item("Chicken Shawarma Sandwich", 440, 30, 44, 16),
        _item("Kofta Plate", 520, 32, 22, 32),
        _item("Chicken Fattah", 580, 30, 62, 22),
        _item("Ful Sandwich (veg)", 340, 14, 48, 10, veg=True, vgn=True),
    ]),
    ("arabiata", "EG", "Arabiata", "https://arabiata.com/menu", [
        "arabiata"
    ], [
        _item("Chicken Shawarma Plate", 540, 32, 52, 22),
        _item("Grilled Kofta", 480, 32, 18, 30),
        _item("Falafel Sandwich", 380, 14, 52, 14, veg=True, vgn=True),
    ]),
    ("cook_door", "EG", "Cook Door", "https://cookdoor.com.eg/menu", [
        "cook door", "cookdoor"
    ], [
        _item("Grilled Chicken Burger", 520, 30, 44, 24),
        _item("Shawarma Sandwich (chicken)", 460, 28, 44, 18),
        _item("Classic Burger", 580, 30, 42, 30),
    ]),
    ("momen", "EG", "Mo'men", "https://momen.com/menu", [
        "momen", "mo'men"
    ], [
        _item("Grilled Chicken Burger", 480, 30, 42, 20),
        _item("Chicken Shawarma Sandwich", 440, 28, 44, 16),
        _item("Classic Mo'men Burger", 540, 30, 42, 26),
    ]),
    ("cilantro", "EG", "Cilantro", "https://cilantro.com.eg/menu", [
        "cilantro"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Grilled Chicken Sandwich", 380, 26, 40, 12),
        _item("Chicken Caesar Wrap", 420, 28, 42, 16),
    ]),

    # ═════════ KUWAIT +2 ═════════
    ("caribou_coffee", "KW", "Caribou Coffee", "https://www.cariboucoffee.com/menu", [
        "caribou coffee", "caribou"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Turkey Sandwich", 360, 22, 40, 10),
    ]),
    ("munch_bakery", "KW", "Munch Bakery", "https://munchbakery.com/menu", [
        "munch bakery"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Chicken Croissant", 380, 18, 36, 18),
        _item("Plain Croissant", 260, 6, 26, 14, cat="breakfast", veg=True),
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
