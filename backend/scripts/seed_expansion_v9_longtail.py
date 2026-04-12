#!/usr/bin/env python3
"""v9: long-tail chains for IN/US/AU."""
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
    # ═════════ IN +12 ═════════
    ("woodlands", "IN", "Woodlands", "https://hotelwoodlandschennai.com/menu", [
        "woodlands", "hotel woodlands"
    ], [
        _item("Mini Tiffin", 480, 16, 72, 14, veg=True),
        _item("Ghee Roast Dosa", 420, 10, 58, 18, veg=True),
        _item("South Indian Meals", 620, 22, 90, 18, veg=True),
        _item("Rava Idli (2pc)", 260, 8, 44, 6, veg=True, vgn=True),
    ]),
    ("annalakshmi", "IN", "Annalakshmi", "https://annalakshmi.in/menu", [
        "annalakshmi"
    ], [
        _item("South Indian Meals (pure veg)", 580, 20, 88, 14, veg=True),
        _item("Thali Special", 640, 22, 94, 18, veg=True),
        _item("Khichdi + Kadhi", 440, 16, 62, 14, veg=True),
    ]),
    ("lmb", "IN", "Laxmi Mishthan Bhandar (LMB)", "https://lmb.co.in/menu", [
        "lmb", "laxmi mishthan bhandar", "laxmi misthan"
    ], [
        _item("Rajasthani Thali", 680, 22, 92, 24, veg=True),
        _item("Dal Bati Churma (set)", 620, 18, 78, 26, veg=True),
        _item("Mawa Kachori (2pc)", 380, 8, 42, 18, cat="dessert", veg=True),
        _item("Ghevar (100g)", 420, 6, 48, 22, cat="dessert", veg=True),
    ]),
    ("rawat_mishtan_bhandar", "IN", "Rawat Mishtan Bhandar", "https://rawatmishtanbhandar.com/menu", [
        "rawat", "rawat mishtan bhandar", "rawat mistan"
    ], [
        _item("Rajasthani Thali", 660, 20, 92, 22, veg=True),
        _item("Pyaaz Kachori (2pc)", 360, 7, 42, 16, veg=True),
        _item("Dal Baati (set)", 540, 16, 68, 22, veg=True),
    ]),
    ("vaishali", "IN", "Vaishali", "https://vaishalirestaurant.com/menu", [
        "vaishali", "vaishali restaurant"
    ], [
        _item("Masala Dosa", 380, 10, 56, 14, veg=True),
        _item("Idli Sambar (4pc)", 280, 10, 52, 4, veg=True, vgn=True),
        _item("Misal Pav", 420, 14, 52, 18, veg=True),
        _item("Rava Idli (2pc)", 260, 8, 44, 6, veg=True, vgn=True),
    ]),
    ("shrewsbury_pune", "IN", "Shrewsbury Cake Shop", "https://shrewsburypune.com/menu", [
        "shrewsbury", "shrewsbury cake shop", "shrewsbury pune"
    ], [
        _item("Shrewsbury Biscuits (100g)", 480, 6, 58, 24, cat="snack", veg=True),
        _item("Chocolate Walnut Brownie", 380, 5, 44, 20, cat="dessert", veg=True),
        _item("Plum Cake Slice", 320, 5, 48, 10, cat="dessert", veg=True),
    ]),
    ("brittos", "IN", "Britto's", "https://www.brittosgoa.com/menu", [
        "brittos", "britto's"
    ], [
        _item("Prawn Curry Rice", 540, 32, 54, 22),
        _item("Grilled Pomfret", 360, 34, 2, 22),
        _item("Goan Fish Curry + Rice", 520, 30, 52, 18),
        _item("Chicken Cafreal", 420, 30, 12, 26),
    ]),
    ("fishermans_wharf", "IN", "Fisherman's Wharf", "https://fishermanswharfgoa.com/menu", [
        "fishermans wharf", "fisherman's wharf", "fishermans"
    ], [
        _item("Grilled Pomfret", 360, 34, 2, 22),
        _item("Chicken Xacuti + Neer Dosa", 540, 32, 48, 24),
        _item("Prawn Balchao + Rice", 520, 30, 52, 22),
        _item("Fish Thali (Goan)", 620, 34, 58, 24),
    ]),
    ("woodside_inn", "IN", "Woodside Inn", "https://www.woodsideinn.in/menu", [
        "woodside inn", "woodside"
    ], [
        _item("Grilled Chicken + Vegetables", 440, 36, 12, 24),
        _item("Goan Chorizo Pav", 460, 22, 40, 22),
        _item("Chicken Burger", 520, 32, 42, 22),
        _item("Brewer's Platter (share)", 620, 32, 42, 32),
    ]),
    ("asia_haus", "IN", "Asian Haus", "https://asianhaus.in/menu", [
        "asia haus", "asian haus"
    ], [
        _item("Hakka Chicken Noodles", 520, 28, 62, 18),
        _item("Kung Pao Chicken", 440, 30, 22, 22),
        _item("Steamed Chicken Momos (6pc)", 280, 18, 32, 8),
        _item("Chilli Paneer (half)", 380, 18, 18, 26, veg=True),
    ]),
    ("zaffran", "IN", "Zaffran", "https://zaffranrestaurant.com/menu", [
        "zaffran"
    ], [
        _item("Zaffran Chicken Biryani", 580, 30, 64, 22),
        _item("Mutton Biryani", 640, 28, 62, 30),
        _item("Tandoori Chicken (half)", 420, 36, 6, 26),
        _item("Seekh Kebab (mutton, 2pc)", 340, 26, 4, 22),
    ]),
    ("moolchand_parathe", "IN", "Moolchand Parathe", "https://moolchandparathe.com/menu", [
        "moolchand parathe", "moolchand paranthe", "moolchand"
    ], [
        _item("Aloo Paratha (1pc)", 380, 8, 52, 14, veg=True),
        _item("Paneer Paratha (1pc)", 440, 16, 52, 20, veg=True),
        _item("Butter Chicken + 2 Roti", 580, 32, 44, 28),
        _item("Chhole Kulche", 620, 18, 82, 22, veg=True),
    ]),

    # ═════════ US +10 ═════════
    ("cheesecake_factory", "US", "The Cheesecake Factory", "https://www.thecheesecakefactory.com/menu", [
        "cheesecake factory", "the cheesecake factory"
    ], [
        _item("Grilled Salmon + Steamed Vegetables", 480, 42, 12, 28),
        _item("Herb Crusted Chicken", 520, 44, 18, 28),
        _item("SkinnyLicious Grilled Chicken", 440, 46, 24, 16),
        _item("Chinese Chicken Salad", 460, 34, 32, 20),
    ]),
    ("red_robin", "US", "Red Robin", "https://www.redrobin.com/menu", [
        "red robin"
    ], [
        _item("Grilled Chicken Club Burger", 620, 38, 46, 32),
        _item("Bunless Red's Burger", 420, 32, 12, 28),
        _item("Whiskey River BBQ Chicken Wrap", 580, 32, 56, 24),
        _item("Simply Grilled Chicken Salad", 440, 36, 22, 22),
    ]),
    ("pei_wei", "US", "Pei Wei", "https://www.peiwei.com/menu", [
        "pei wei", "pei wei asian kitchen"
    ], [
        _item("Kung Pao Chicken Bowl", 520, 30, 50, 22),
        _item("Korean Steak Bowl", 540, 32, 52, 22),
        _item("Teriyaki Chicken Bowl", 480, 30, 56, 12),
        _item("Tofu Stir-Fry (vegan)", 380, 18, 44, 14, veg=True, vgn=True),
    ]),
    ("benihana", "US", "Benihana", "https://www.benihana.com/menu", [
        "benihana"
    ], [
        _item("Hibachi Chicken (standard)", 480, 44, 22, 24),
        _item("Hibachi Steak (6oz)", 440, 42, 14, 24),
        _item("Hibachi Shrimp (6pc)", 360, 38, 12, 18),
        _item("Teriyaki Salmon", 480, 40, 8, 30),
    ]),
    ("smashburger", "US", "Smashburger", "https://smashburger.com/menu", [
        "smashburger"
    ], [
        _item("Classic Smash Burger (small)", 420, 26, 30, 22),
        _item("Grilled Chicken Sandwich", 460, 32, 38, 18),
        _item("Kale Caesar Salad (chicken)", 420, 32, 18, 24),
    ]),
    ("fatburger", "US", "Fatburger", "https://www.fatburger.com/menu", [
        "fatburger"
    ], [
        _item("Original Fatburger", 560, 32, 42, 28),
        _item("Grilled Chicken Sandwich", 460, 32, 42, 18),
        _item("Turkey Burger", 440, 30, 40, 18),
    ]),
    ("bjs_restaurant", "US", "BJ's Restaurant & Brewhouse", "https://www.bjsrestaurants.com/menu", [
        "bjs restaurant", "bj's restaurant", "bjs brewhouse", "bj's brewhouse"
    ], [
        _item("Grilled Chicken Avocado Flatbread (half)", 460, 30, 40, 22),
        _item("Atlantic Salmon + Vegetables", 480, 42, 12, 28),
        _item("Buffalo Chicken Salad", 520, 34, 22, 34),
        _item("Personal Chicken Alfredo Pizza", 520, 28, 56, 22),
    ]),
    ("mellow_mushroom", "US", "Mellow Mushroom", "https://mellowmushroom.com/menu", [
        "mellow mushroom"
    ], [
        _item("Small Veggie Pizza", 480, 18, 58, 18, veg=True),
        _item("Small Chicken Caesar Pizza", 540, 28, 58, 22),
        _item("House Salad (chicken)", 380, 30, 18, 22),
    ]),
    ("the_counter", "US", "The Counter", "https://www.thecounter.com/menu", [
        "the counter", "counter burger"
    ], [
        _item("Grilled Chicken Burger", 440, 32, 38, 18),
        _item("Build Your Own Burger (1/3lb)", 520, 30, 42, 26),
        _item("Veggie Burger", 440, 18, 56, 18, veg=True),
    ]),
    ("chuys", "US", "Chuy's", "https://www.chuys.com/menu", [
        "chuys", "chuy's"
    ], [
        _item("Grilled Chicken Taco (1pc)", 220, 18, 22, 8),
        _item("Chicken Burrito Bowl", 520, 36, 58, 16),
        _item("Chicken Tortilla Soup", 240, 18, 22, 10),
    ]),

    # ═════════ AU +8 ═════════
    ("hogs_breath_cafe", "AU", "Hog's Breath Cafe", "https://www.hogsbreath.com.au/menu", [
        "hogs breath", "hog's breath", "hogs breath cafe"
    ], [
        _item("Prime Rib (small cut)", 440, 42, 8, 28),
        _item("Grilled Chicken Breast + Veg", 380, 42, 12, 18),
        _item("Caesar Salad (chicken)", 440, 34, 18, 26),
    ]),
    ("la_porchetta", "AU", "La Porchetta", "https://laporchetta.com.au/menu", [
        "la porchetta"
    ], [
        _item("Margherita Personal Pizza", 480, 20, 58, 18, veg=True),
        _item("Capricciosa Personal Pizza", 560, 26, 62, 22),
        _item("Grilled Chicken Personal", 540, 28, 60, 20),
        _item("Fettuccine Boscaiola (half)", 520, 24, 60, 22),
    ]),
    ("fasta_pasta", "AU", "Fasta Pasta", "https://www.fastapasta.com.au/menu", [
        "fasta pasta"
    ], [
        _item("Chicken Parmigiana + Pasta", 640, 38, 60, 28),
        _item("Spaghetti Bolognese", 560, 28, 66, 22),
        _item("Chicken Carbonara (half)", 540, 26, 58, 22),
        _item("Napolitana Pasta (veg)", 460, 16, 68, 14, veg=True),
    ]),
    ("crinitis", "AU", "Criniti's", "https://www.crinitis.com.au/menu", [
        "crinitis", "criniti's"
    ], [
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
        _item("Capricciosa Personal", 580, 26, 62, 24),
        _item("Pollo alla Griglia (grilled chicken)", 420, 38, 14, 24),
    ]),
    ("veloce", "AU", "Veloce", "https://veloce.com.au/menu", [
        "veloce"
    ], [
        _item("Margherita Personal", 520, 22, 58, 20, veg=True),
        _item("Prosciutto Personal", 540, 26, 58, 22),
        _item("Quattro Formaggi (veg)", 560, 24, 58, 26, veg=True),
    ]),
    ("burger_edge", "AU", "Burger Edge", "https://burgeredge.com.au/menu", [
        "burger edge"
    ], [
        _item("Classic Beef Burger", 560, 32, 42, 28),
        _item("Grilled Chicken Burger", 480, 34, 42, 20),
        _item("Vegan Burger", 460, 16, 54, 22, veg=True, vgn=True),
    ]),
    ("wagamama", "AU", "Wagamama", "https://www.wagamama.com.au/menu", [
        "wagamama"
    ], [
        _item("Chicken Katsu Curry", 620, 36, 68, 22),
        _item("Chicken Ramen", 480, 34, 54, 14),
        _item("Teriyaki Chicken Donburi", 540, 32, 62, 16),
        _item("Vegatsu (vegan katsu)", 580, 16, 72, 24, veg=True, vgn=True),
    ]),
    ("ovation", "AU", "Ovation Bar & Kitchen", "https://ovationbar.com.au/menu", [
        "ovation", "ovation bar", "ovation bar and kitchen"
    ], [
        _item("Grilled Chicken Breast + Veg", 380, 42, 12, 18),
        _item("Barramundi Fillet + Salad", 420, 36, 12, 24),
        _item("Caesar Salad (chicken)", 440, 32, 18, 26),
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
