#!/usr/bin/env python3
"""
Seed expansion v5: Asia breadth.
New markets: Taiwan (TW), Hong Kong (HK), Vietnam (VN), Pakistan (PK), Bangladesh (BD).
Expand existing: Japan, Korea, Philippines.
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
    # ═══════════ TAIWAN ═══════════
    ("din_tai_fung", "TW", "Din Tai Fung", "https://www.dintaifung.com.tw/menu", [
        "din tai fung", "dtf", "鼎泰豐"
    ], [
        _item("Xiao Long Bao (10pc)", 280, 16, 30, 10),
        _item("Steamed Chicken Dumplings (10pc)", 260, 18, 28, 8),
        _item("Shrimp & Pork Wonton Soup", 300, 20, 30, 10),
        _item("Vegetarian Dumplings (10pc)", 240, 10, 32, 8, veg=True),
        _item("Stir-Fried Greens with Garlic", 100, 5, 10, 4, cat="side", veg=True, vgn=True),
    ]),
    ("85c_bakery", "TW", "85°C Bakery Cafe", "https://www.85cafe.com/menu", [
        "85c bakery", "85 degrees", "85 degrees bakery cafe", "85c"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Ham & Cheese Croissant", 380, 14, 40, 18),
        _item("Sea Salt Coffee", 160, 3, 20, 7, cat="beverage", veg=True),
        _item("Multigrain Sandwich (chicken)", 340, 24, 36, 12),
    ]),
    ("tkk_fried_chicken", "TW", "TKK Fried Chicken", "https://www.tkkinc.com/menu", [
        "tkk", "tkk fried chicken", "台塑"
    ], [
        _item("Grilled Chicken Meal", 460, 32, 42, 18),
        _item("Fried Chicken (1pc) + Rice", 520, 28, 56, 22),
        _item("Chicken Sandwich", 400, 24, 40, 16),
        _item("Side Salad", 60, 2, 8, 2, cat="side", veg=True, vgn=True),
    ]),
    ("mos_burger", "TW", "MOS Burger", "https://www.mos.com.tw/menu", [
        "mos burger", "mos"
    ], [
        _item("Teriyaki Chicken Burger", 380, 24, 42, 14),
        _item("Rice Burger (Teriyaki Chicken)", 420, 22, 56, 14),
        _item("Hot Dog (plain)", 320, 12, 32, 16),
        _item("Mos Green Salad", 80, 3, 10, 3, cat="side", veg=True, vgn=True),
    ]),
    ("chun_shui_tang", "TW", "Chun Shui Tang", "https://www.chunshuitang.com.tw/menu", [
        "chun shui tang", "春水堂"
    ], [
        _item("Classic Pearl Milk Tea (less sugar)", 340, 3, 62, 8, cat="beverage", veg=True),
        _item("Iron Goddess Tea (unsweetened)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Dan Dan Noodles (small)", 480, 18, 56, 18),
    ]),
    ("mcdonalds", "TW", "McDonald's", "https://www.mcdonalds.com.tw/menu", [
        "mcdonalds", "mcdonald's", "麥當勞"
    ], [
        _item("Grilled Chicken Deluxe", 380, 28, 34, 14),
        _item("McChicken", 400, 16, 40, 18),
        _item("Taiwan Rice Burger (chicken)", 440, 24, 50, 18),
        _item("Side Salad", 25, 1, 4, 0, cat="side", veg=True, vgn=True),
    ]),

    # ═══════════ HONG KONG ═══════════
    ("cafe_de_coral", "HK", "Cafe de Coral", "https://www.cafedecoral.com/menu", [
        "cafe de coral", "大家樂"
    ], [
        _item("Roast Chicken Rice (half)", 480, 32, 56, 14),
        _item("BBQ Pork Rice", 560, 26, 62, 22),
        _item("Steamed Chicken + Rice", 440, 30, 56, 10),
        _item("Wonton Noodles", 380, 20, 52, 10),
        _item("Congee (chicken)", 260, 18, 38, 4),
    ]),
    ("fairwood", "HK", "Fairwood", "https://www.fairwood.com.hk/menu", [
        "fairwood", "大快活"
    ], [
        _item("Soy Sauce Chicken Rice", 520, 28, 62, 18),
        _item("Roast Pork Rice", 580, 26, 64, 24),
        _item("Steamed Beef + Rice", 480, 28, 56, 16),
        _item("Wonton Soup", 180, 14, 20, 6),
    ]),
    ("maxims", "HK", "Maxim's MX", "https://www.maxims.com.hk/menu", [
        "maxims", "maxim's", "maxim's mx", "美心mx"
    ], [
        _item("Cantonese Roast Goose Rice (quarter)", 620, 30, 62, 28),
        _item("BBQ Pork Rice", 560, 26, 62, 22),
        _item("Steamed Fish Rice", 420, 32, 56, 8),
        _item("Wonton Noodles", 380, 20, 52, 10),
    ]),
    ("tai_hing", "HK", "Tai Hing", "https://www.taihing.com/menu", [
        "tai hing", "太興"
    ], [
        _item("Swiss Chicken Wings + Rice", 540, 30, 60, 20),
        _item("Soy Sauce Chicken (half)", 420, 34, 8, 28),
        _item("Beef Brisket Noodles", 440, 26, 52, 16),
        _item("Congee (pork)", 280, 18, 38, 6),
    ]),
    ("tsui_wah", "HK", "Tsui Wah", "https://www.tsuiwahrestaurant.com/menu", [
        "tsui wah", "翠華"
    ], [
        _item("Swiss Sauce Chicken Wings + Rice", 520, 30, 58, 18),
        _item("Baked Pork Chop Rice", 620, 30, 62, 28),
        _item("Instant Noodles + Chicken Wings", 420, 22, 52, 14),
        _item("Crispy Bun + Condensed Milk", 320, 6, 42, 14, cat="dessert", veg=True),
    ]),
    ("mcdonalds", "HK", "McDonald's", "https://www.mcdonalds.com.hk/menu", [
        "mcdonalds", "mcdonald's", "麥當勞"
    ], [
        _item("Grilled Chicken Twister", 400, 28, 36, 16),
        _item("McChicken", 400, 16, 40, 18),
        _item("Filet-O-Fish", 340, 15, 36, 14),
        _item("Garden Salad", 25, 1, 4, 0, cat="side", veg=True, vgn=True),
    ]),

    # ═══════════ VIETNAM ═══════════
    ("pho_24", "VN", "Pho 24", "https://www.pho24.com.vn/menu", [
        "pho 24", "phở 24"
    ], [
        _item("Pho Bo (beef noodle soup)", 420, 28, 52, 10),
        _item("Pho Ga (chicken noodle soup)", 380, 26, 52, 8),
        _item("Pho Tai (rare beef)", 400, 26, 50, 10),
        _item("Rice Noodles + Grilled Chicken", 440, 30, 54, 10),
    ]),
    ("highlands_coffee", "VN", "Highlands Coffee", "https://www.highlandscoffee.com.vn/menu", [
        "highlands coffee", "highlands"
    ], [
        _item("Black Coffee (phin, unsweetened)", 10, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Vietnamese Iced Coffee (less sugar)", 140, 3, 22, 4, cat="beverage", veg=True),
        _item("Grilled Chicken Banh Mi", 380, 24, 42, 12),
        _item("Freeze Chocolate (less sugar)", 380, 7, 56, 14, cat="beverage", veg=True),
    ]),
    ("the_coffee_house", "VN", "The Coffee House", "https://www.thecoffeehouse.com/menu", [
        "the coffee house", "coffee house vn"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Grilled Chicken Bowl", 420, 28, 44, 14),
        _item("Banh Mi Grilled Chicken", 380, 24, 42, 12),
    ]),
    ("phuc_long", "VN", "Phuc Long", "https://phuclong.com.vn/menu", [
        "phuc long", "phúc long"
    ], [
        _item("Oolong Milk Tea (less sugar)", 280, 2, 52, 6, cat="beverage", veg=True),
        _item("Peach Tea (unsweetened)", 20, 0, 4, 0, cat="beverage", veg=True, vgn=True),
        _item("Lotus Seed Tea", 120, 1, 28, 0, cat="beverage", veg=True, vgn=True),
    ]),
    ("trung_nguyen", "VN", "Trung Nguyen Legend", "https://www.trungnguyenlegend.com/menu", [
        "trung nguyen", "trung nguyen legend", "trung nguyên"
    ], [
        _item("Robusta Black Coffee", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Weasel Coffee (no sugar)", 15, 0, 2, 0, cat="beverage", veg=True, vgn=True),
        _item("Vietnamese Milk Coffee (less sugar)", 160, 3, 26, 4, cat="beverage", veg=True),
    ]),
    ("wrap_and_roll", "VN", "Wrap & Roll", "https://wrap-roll.com/menu", [
        "wrap and roll", "wrap & roll", "wrap roll"
    ], [
        _item("Spring Rolls (grilled pork, 4pc)", 320, 18, 42, 8),
        _item("Rice Paper Rolls (shrimp, 4pc)", 180, 14, 24, 2),
        _item("Grilled Beef + Vermicelli Bowl", 460, 30, 54, 14),
        _item("Veg Summer Rolls (4pc)", 160, 5, 30, 2, veg=True, vgn=True),
    ]),

    # ═══════════ PAKISTAN ═══════════
    ("afc", "PK", "AFC (American Fried Chicken)", "https://afc.com.pk/menu", [
        "afc", "american fried chicken"
    ], [
        _item("Grilled Chicken (half)", 340, 32, 8, 20),
        _item("Crispy Chicken (2pc) + Rice", 540, 28, 56, 24),
        _item("Zinger Burger", 480, 24, 42, 22),
        _item("Chicken Roll", 440, 24, 42, 20),
    ]),
    ("broadway_pizza", "PK", "Broadway Pizza", "https://www.broadwaypizza.com.pk/menu", [
        "broadway pizza"
    ], [
        _item("Grilled Chicken Personal Pizza", 540, 28, 64, 18),
        _item("Chicken Tikka Personal Pizza", 560, 28, 62, 22),
        _item("Veg Supreme Personal", 480, 16, 66, 14, veg=True),
        _item("Chicken Wings (6pc)", 340, 28, 4, 22),
    ]),
    ("student_biryani", "PK", "Student Biryani", "https://www.studentbiryani.com/menu", [
        "student biryani", "students biryani"
    ], [
        _item("Chicken Biryani (regular)", 580, 28, 68, 22),
        _item("Mutton Biryani (regular)", 640, 26, 64, 32),
        _item("Beef Biryani (regular)", 600, 28, 62, 28),
        _item("Chicken Pulao", 520, 26, 60, 20),
    ]),
    ("pie_in_the_sky", "PK", "Pie In The Sky", "https://www.pieinthesky.com.pk/menu", [
        "pie in the sky", "pits"
    ], [
        _item("Grilled Chicken Personal Pizza", 520, 28, 62, 18),
        _item("Chicken Tikka Pie", 460, 22, 48, 22),
        _item("Beef Pie (small)", 440, 20, 42, 22),
        _item("Caesar Salad + Grilled Chicken", 340, 28, 14, 18),
    ]),
    ("mcdonalds", "PK", "McDonald's", "https://mcdonalds.com.pk/menu", [
        "mcdonalds", "mcdonald's"
    ], [
        _item("McChicken", 400, 16, 40, 18),
        _item("McArabia Grilled Chicken", 520, 28, 52, 22),
        _item("Chicken McDeluxe", 480, 24, 44, 22),
        _item("Garden Salad", 25, 1, 4, 0, cat="side", veg=True, vgn=True),
    ]),

    # ═══════════ BANGLADESH ═══════════
    ("kacchi_bhai", "BD", "Kacchi Bhai", "https://www.kacchibhai.com/menu", [
        "kacchi bhai"
    ], [
        _item("Kacchi Biryani (mutton, regular)", 720, 32, 74, 34),
        _item("Chicken Biryani (regular)", 560, 28, 62, 22),
        _item("Beef Tehari", 620, 28, 60, 28),
    ]),
    ("star_kabab", "BD", "Star Kabab", "https://www.starkabab.com/menu", [
        "star kabab", "star kabab and restaurant"
    ], [
        _item("Chicken Kabab (2pc)", 320, 26, 6, 20),
        _item("Beef Kabab (2pc)", 360, 28, 6, 24),
        _item("Chicken Biryani (regular)", 560, 28, 62, 22),
        _item("Beef Tehari", 620, 28, 60, 28),
    ]),
    ("fakruddin", "BD", "Fakruddin Biryani", "https://www.fakruddin.com/menu", [
        "fakruddin", "fakruddin biryani", "fakhruddin"
    ], [
        _item("Kacchi Biryani (mutton)", 720, 32, 74, 34),
        _item("Chicken Biryani", 560, 28, 62, 22),
        _item("Beef Tehari", 620, 28, 60, 28),
    ]),
    ("coopers", "BD", "Cooper's Bakery", "https://www.coopers-bd.com/menu", [
        "coopers", "cooper's", "coopers bakery"
    ], [
        _item("Chicken Sandwich", 340, 22, 38, 12),
        _item("Plain Croissant", 260, 6, 26, 14, cat="breakfast", veg=True),
        _item("Black Coffee", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
    ]),
    ("pizza_hut", "BD", "Pizza Hut", "https://www.pizzahut.com.bd/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal", 560, 28, 64, 20),
        _item("Hawaiian Personal", 540, 22, 68, 18),
        _item("Veg Supreme Personal", 480, 16, 66, 14, veg=True),
    ]),

    # ═══════════ JAPAN EXPANSION ═══════════
    ("ichiran", "JP", "Ichiran Ramen", "https://www.ichiran.com/menu", [
        "ichiran", "一蘭"
    ], [
        _item("Tonkotsu Ramen (classic)", 540, 24, 64, 20),
        _item("Ramen with Extra Chashu", 680, 36, 64, 30),
        _item("Kaedama (extra noodles)", 180, 6, 40, 1, cat="side", veg=True),
    ]),
    ("sushiro", "JP", "Sushiro", "https://www.akindo-sushiro.co.jp/menu", [
        "sushiro", "スシロー"
    ], [
        _item("Salmon Nigiri (2pc)", 120, 8, 12, 4),
        _item("Tuna Nigiri (2pc)", 100, 10, 12, 2),
        _item("Shrimp Nigiri (2pc)", 100, 9, 14, 1),
        _item("Mackerel Nigiri (2pc)", 140, 10, 12, 6),
        _item("Salmon Roe Gunkan", 140, 8, 12, 6),
    ]),
    ("kura_sushi", "JP", "Kura Sushi", "https://www.kurasushi.co.jp/menu", [
        "kura sushi", "kura", "くら寿司"
    ], [
        _item("Salmon Nigiri (2pc)", 120, 8, 12, 4),
        _item("Tuna Nigiri (2pc)", 100, 10, 12, 2),
        _item("Eel Nigiri (2pc)", 180, 12, 14, 8),
        _item("Miso Soup", 40, 3, 4, 1, cat="side", veg=True),
    ]),
    ("ootoya", "JP", "Ootoya", "https://www.ootoya.com/menu", [
        "ootoya", "大戸屋"
    ], [
        _item("Grilled Salmon Set", 520, 36, 58, 14),
        _item("Chicken Katsu Teishoku", 640, 32, 62, 26),
        _item("Saba Shioyaki Set", 540, 34, 58, 18),
        _item("Hamburg Steak Set", 580, 30, 56, 24),
    ]),
    ("doutor", "JP", "Doutor Coffee", "https://www.doutor.co.jp/menu", [
        "doutor", "doutor coffee", "ドトール"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cafe Latte (no sugar)", 120, 7, 10, 6, cat="beverage", veg=True),
        _item("Milano Sandwich (ham)", 340, 18, 38, 14),
        _item("Hot Dog", 320, 12, 32, 16),
    ]),

    # ═══════════ KOREA EXPANSION ═══════════
    ("paris_baguette", "KR", "Paris Baguette", "https://www.paris.co.kr/menu", [
        "paris baguette", "파리바게뜨"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Cappuccino (no sugar)", 110, 6, 9, 5, cat="beverage", veg=True),
        _item("Ham & Cheese Croissant", 380, 14, 40, 18),
        _item("Grilled Chicken Sandwich", 360, 22, 40, 12),
        _item("Vegetable Sandwich", 280, 10, 40, 8, veg=True),
    ]),
    ("tous_les_jours", "KR", "Tous Les Jours", "https://www.tlj.co.kr/menu", [
        "tous les jours", "tlj", "뚜레쥬르"
    ], [
        _item("Americano (black)", 5, 0, 1, 0, cat="beverage", veg=True, vgn=True),
        _item("Whole Wheat Sandwich (chicken)", 340, 24, 36, 12),
        _item("Plain Bagel", 260, 10, 52, 2, cat="breakfast", veg=True, vgn=True),
    ]),
    ("goobne_chicken", "KR", "Goobne Chicken", "https://www.goobne.co.kr/menu", [
        "goobne", "goobne chicken", "굽네치킨"
    ], [
        _item("Oven Roasted Chicken (half)", 420, 38, 8, 24),
        _item("Cheese Oven Chicken (half)", 520, 40, 12, 32),
        _item("Sweet Potato Chicken", 560, 30, 42, 28),
        _item("Salad Bowl", 180, 12, 16, 8, cat="side", veg=True),
    ]),
    ("nene_chicken", "KR", "Nene Chicken", "https://www.nenechicken.com/menu", [
        "nene chicken", "nene", "네네치킨"
    ], [
        _item("Fried Chicken Half (original)", 540, 32, 20, 34),
        _item("Snowing Cheese Chicken (half)", 620, 30, 28, 40),
        _item("Soy Garlic Chicken (half)", 560, 32, 24, 34),
    ]),
    ("moms_touch", "KR", "Mom's Touch", "https://www.momstouch.co.kr/menu", [
        "moms touch", "mom's touch", "맘스터치"
    ], [
        _item("Thighburger", 480, 26, 46, 20),
        _item("Grilled Chicken Burger", 420, 28, 42, 14),
        _item("Chicken Tender (3pc)", 320, 26, 18, 14),
        _item("Salad Bowl", 160, 10, 14, 8, cat="side", veg=True),
    ]),

    # ═══════════ PHILIPPINES EXPANSION ═══════════
    ("mang_inasal", "PH", "Mang Inasal", "https://manginasal.com/menu", [
        "mang inasal"
    ], [
        _item("Chicken Inasal (regular) + Rice", 540, 36, 62, 16),
        _item("Paa Large (chicken leg + rice)", 620, 38, 64, 24),
        _item("Pecho Regular (breast + rice)", 520, 40, 58, 14),
        _item("Halo-Halo (regular)", 320, 6, 62, 6, cat="dessert", veg=True),
    ]),
    ("maxs_restaurant", "PH", "Max's Restaurant", "https://maxschicken.com/menu", [
        "maxs restaurant", "max's restaurant", "max's", "maxs fried chicken"
    ], [
        _item("Fried Chicken (1pc leg) + Rice", 520, 30, 54, 22),
        _item("Chicken Sisig + Rice", 560, 28, 58, 22),
        _item("Sinigang na Baboy", 380, 26, 22, 20),
        _item("Grilled Chicken + Rice", 480, 34, 54, 14),
    ]),
    ("shakeys", "PH", "Shakey's Pizza", "https://shakeyspizza.ph/menu", [
        "shakeys", "shakey's", "shakeys pizza"
    ], [
        _item("Chicken 'n' Mojos (1pc + mojos)", 540, 26, 48, 28),
        _item("Manager's Choice Personal Pizza", 560, 24, 62, 22),
        _item("Hawaiian Delight Personal", 540, 22, 68, 18),
        _item("Caesar Salad + Chicken", 320, 26, 16, 16),
    ]),
    ("yellow_cab_pizza", "PH", "Yellow Cab Pizza", "https://yellowcabpizza.com/menu", [
        "yellow cab pizza", "yellow cab"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("New York's Finest Personal", 580, 28, 64, 22),
        _item("Hawaiian Classic Personal", 540, 22, 68, 18),
        _item("Charlie Chan Chicken Pasta (regular)", 520, 28, 60, 18),
    ]),
    ("pizza_hut", "PH", "Pizza Hut", "https://www.pizzahut.com.ph/menu", [
        "pizza hut"
    ], [
        _item("Grilled Chicken Personal", 540, 28, 62, 18),
        _item("Hawaiian Personal", 540, 22, 68, 18),
        _item("Super Supreme Personal", 600, 30, 64, 24),
        _item("Caesar Salad + Chicken", 320, 26, 16, 16),
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
