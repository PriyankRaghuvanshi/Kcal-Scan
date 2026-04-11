#!/usr/bin/env python3
"""
Bulk-seed ALL covered chains into Supabase in one run.

Usage:
    cd backend && python scripts/bulk_seed_all_chains.py

What it does:
1. Writes seed JSON files to data/chains/ for every chain×market combo
2. Syncs each to Supabase via the existing pipeline
3. Prints a summary table

Items are real menu items with publicly-known approximate nutrition.
Run time: ~1-2 minutes for all 31 chains × 3 markets.
"""
import json
import os
import sys
import time
from pathlib import Path

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chain_menu_supabase_sync import sync_chain_menu_to_supabase

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"

# ── Helper ──────────────────────────────────────────────────────────────
def _item(name, cal, pro, carb, fat, cat="entree", conf=0.85, veg=False, vgn=False):
    return {
        "item_name": name,
        "category": cat,
        "estimated_calories": cal,
        "estimated_protein_g": pro,
        "estimated_carbs_g": carb,
        "estimated_fat_g": fat,
        "confidence": conf,
        "vegetarian_possible": veg,
        "vegan_possible": vgn,
    }

# ── ALL CHAIN SEED DATA ────────────────────────────────────────────────
# Each entry: (chain_key, market, brand_name, source_url, variants, items)
# Items use publicly known nutrition data from official chain websites.

ALL_CHAINS = [

    # ═══════════════════ AUSTRALIA ═══════════════════

    ("mcdonalds", "AU", "McDonald's", "https://mcdonalds.com.au/menu", ["mcdonalds", "mcdonald's", "maccas"], [
        _item("Grilled Chicken Wrap", 380, 27, 30, 14),
        _item("McChicken (no mayo)", 340, 18, 36, 12),
        _item("6 Chicken McNuggets", 260, 16, 16, 14),
        _item("Big Mac (no sauce)", 430, 26, 38, 18),
        _item("Filet-O-Fish", 340, 15, 36, 14),
        _item("Garden Side Salad", 25, 1, 4, 0, cat="side", veg=True, vgn=True),
        _item("Egg McMuffin", 300, 18, 26, 13),
    ]),
    ("kfc", "AU", "KFC", "https://www.kfc.com.au/menu", ["kfc", "kentucky fried chicken"], [
        _item("Original Tender (3pc) with Slaw", 420, 32, 22, 22),
        _item("Grilled Chicken Piece", 160, 22, 1, 8),
        _item("Zinger Burger", 480, 24, 42, 22),
        _item("Popcorn Chicken (regular)", 310, 18, 20, 18),
        _item("Supercharged Slider", 310, 14, 28, 16),
        _item("Coleslaw (regular)", 130, 1, 14, 8, cat="side", veg=True),
    ]),
    ("hungry_jacks", "AU", "Hungry Jack's", "https://www.hungryjacks.com.au/menu", ["hungry jacks", "hungry jack's"], [
        _item("Grilled Chicken Burger", 420, 28, 38, 16),
        _item("Whopper Junior", 340, 16, 28, 18),
        _item("Chicken Royale", 480, 22, 44, 24),
        _item("Veggie Burger", 390, 14, 46, 16, veg=True),
        _item("6 Nuggets", 260, 14, 18, 14),
        _item("Garden Salad", 40, 2, 6, 1, cat="side", veg=True, vgn=True),
    ]),
    ("subway", "AU", "Subway", "https://www.subway.com/en-AU/MenuNutrition/Menu", ["subway"], [
        _item("6-inch Grilled Chicken", 390, 30, 40, 8),
        _item("6-inch Turkey Breast", 280, 18, 40, 4),
        _item("6-inch Veggie Delite", 230, 8, 40, 3, veg=True, vgn=True),
        _item("6-inch Steak & Cheese", 380, 26, 40, 10),
        _item("Chicken & Bacon Ranch Wrap", 530, 34, 44, 22),
        _item("6-inch Tuna", 420, 18, 40, 20),
    ]),
    ("dominos", "AU", "Domino's", "https://www.dominos.com.au/menu", ["dominos", "domino's"], [
        _item("Chicken Dominator (Medium, Thin Crust)", 680, 42, 54, 28),
        _item("Chicken & Feta (Medium, Thin Crust)", 600, 36, 50, 24),
        _item("BBQ Chicken & Bacon (Medium, Classic)", 720, 38, 68, 28),
        _item("Loaded Pepperoni (Medium, Thin Crust)", 660, 30, 52, 32),
        _item("Veg Trio (Medium, Classic)", 580, 22, 66, 22, veg=True),
        _item("Chicken Caesar Salad", 340, 28, 12, 20, cat="side"),
    ]),
    ("grilld", "AU", "Grill'd", "https://www.grilld.com.au/menu", ["grilld", "grill'd"], [
        _item("Simply Grill'd Chicken Burger", 420, 34, 32, 14),
        _item("Garden Goodness Burger", 380, 12, 40, 18, veg=True),
        _item("Mighty Melbourne Burger", 520, 36, 38, 22),
        _item("Beefy Patty Burger (Low Carb)", 380, 30, 12, 24),
        _item("Sweet Chilli Chicken Burger", 460, 30, 38, 18),
        _item("Healthy Chips (small)", 280, 4, 36, 14, cat="side", veg=True),
    ]),
    ("guzman_y_gomez", "AU", "Guzman y Gomez", "https://www.guzmanygomez.com.au/menu", ["guzman y gomez", "gyg"], [
        _item("Grilled Chicken Burrito Bowl", 520, 38, 48, 16),
        _item("Chicken Mini Burrito", 380, 22, 36, 14),
        _item("Veggie Burrito Bowl", 440, 14, 56, 16, veg=True, vgn=True),
        _item("Grilled Chicken Nachos", 620, 34, 52, 26),
        _item("Chicken Taco (2pk)", 340, 22, 28, 14),
        _item("Black Beans & Rice", 280, 10, 46, 4, cat="side", veg=True, vgn=True),
    ]),
    ("zambrero", "AU", "Zambrero", "https://www.zambrero.com.au/menu", ["zambrero"], [
        _item("Grilled Chicken Power Bowl", 480, 36, 42, 14),
        _item("Pulled Pork Burrito", 540, 28, 52, 20),
        _item("Veggie Bowl", 400, 12, 52, 14, veg=True, vgn=True),
        _item("Chicken Quesadilla", 460, 28, 34, 22),
        _item("Grilled Chicken Burrito", 520, 32, 50, 16),
    ]),
    ("oporto", "AU", "Oporto", "https://www.oporto.com.au/menu", ["oporto"], [
        _item("Bondi Chicken Burger", 480, 28, 40, 20),
        _item("Grilled Chicken Wrap", 420, 30, 36, 14),
        _item("Single Bondi Fillet", 220, 24, 8, 10),
        _item("Flame Grilled Chicken (Quarter)", 280, 32, 2, 16),
        _item("Chicken Salad Bowl", 320, 28, 14, 16, cat="side"),
    ]),
    ("starbucks", "AU", "Starbucks", "https://www.starbucks.com.au/menu", ["starbucks"], [
        _item("Protein Box (Eggs & Cheese)", 380, 24, 30, 18, cat="snack"),
        _item("Turkey & Pesto Sandwich", 420, 26, 38, 16),
        _item("Spinach & Feta Wrap", 300, 14, 34, 12, veg=True),
        _item("Almond Latte (Grande, no sugar)", 100, 4, 8, 6, cat="drink", veg=True),
        _item("Banana (whole)", 105, 1, 27, 0, cat="snack", veg=True, vgn=True),
    ]),
    ("boost_juice", "AU", "Boost Juice", "https://www.boostjuice.com.au/menu", ["boost juice", "boost"], [
        _item("Protein Supreme Smoothie", 340, 22, 40, 8, cat="drink"),
        _item("All Berry Bang Smoothie", 220, 4, 48, 1, cat="drink", veg=True, vgn=True),
        _item("Green Goddess Smoothie", 180, 4, 38, 1, cat="drink", veg=True, vgn=True),
        _item("Mango Magic Smoothie", 240, 4, 52, 1, cat="drink", veg=True, vgn=True),
    ]),

    # ═══════════════════ UNITED STATES ═══════════════════

    ("mcdonalds", "US", "McDonald's", "https://www.mcdonalds.com/us/en-us/full-menu.html", ["mcdonalds", "mcdonald's"], [
        _item("McChicken", 400, 14, 40, 21),
        _item("Grilled Chicken Sandwich", 380, 28, 38, 12),
        _item("Egg McMuffin", 310, 17, 30, 13),
        _item("6pc Chicken McNuggets", 250, 15, 15, 15),
        _item("Big Mac", 550, 25, 45, 30),
        _item("Southwest Grilled Chicken Salad", 350, 30, 22, 14),
        _item("Fruit & Yogurt Parfait", 150, 4, 30, 2, cat="snack", veg=True),
    ]),
    ("chipotle", "US", "Chipotle", "https://www.chipotle.com/nutrition-calculator", ["chipotle", "chipotle mexican grill"], [
        _item("High Protein Bowl", 820, 60, 55, 35),
        _item("Chicken Burrito Bowl (no rice)", 510, 42, 22, 18),
        _item("Chicken Salad", 480, 38, 20, 24),
        _item("Barbacoa Bowl", 620, 36, 52, 24),
        _item("Sofritas Bowl", 540, 18, 58, 22, veg=True, vgn=True),
        _item("Chicken Tacos (3)", 540, 36, 42, 18),
    ]),
    ("subway", "US", "Subway", "https://www.subway.com/en-US/MenuNutrition/Menu", ["subway"], [
        _item("6-inch Rotisserie Chicken", 350, 28, 38, 8),
        _item("6-inch Turkey Breast", 270, 18, 40, 4),
        _item("6-inch Veggie Delite", 230, 8, 40, 3, veg=True, vgn=True),
        _item("Protein Bowl (Chicken)", 250, 30, 12, 8),
        _item("6-inch Italian BMT", 360, 16, 40, 14),
        _item("6-inch Steak & Cheese", 390, 24, 40, 12),
    ]),
    ("sweetgreen", "US", "Sweetgreen", "https://www.sweetgreen.com/menu", ["sweetgreen", "sweet green"], [
        _item("Harvest Bowl", 640, 22, 56, 36, veg=True),
        _item("Chicken Pesto Parm", 620, 38, 42, 28),
        _item("Super Green Goddess", 460, 28, 32, 24),
        _item("Crispy Rice Bowl", 580, 30, 52, 22),
        _item("Kale Caesar Salad", 440, 18, 26, 30, veg=True),
        _item("Garden Cobb", 520, 36, 18, 34),
    ]),
    ("cava", "US", "CAVA", "https://cava.com/menu", ["cava", "cava grill"], [
        _item("Grilled Chicken Bowl", 520, 38, 42, 18),
        _item("Braised Lamb Bowl", 580, 32, 46, 24),
        _item("Falafel Bowl", 540, 16, 58, 24, veg=True, vgn=True),
        _item("Grilled Chicken Pita", 480, 34, 40, 16),
        _item("Greens + Grains Bowl", 440, 30, 38, 18),
        _item("Harissa Chicken Bowl", 550, 36, 44, 20),
    ]),
    ("chick_fil_a", "US", "Chick-fil-A", "https://www.chick-fil-a.com/menu", ["chick-fil-a", "chick fil a"], [
        _item("Grilled Chicken Sandwich", 390, 28, 40, 12),
        _item("Grilled Nuggets (8ct)", 140, 25, 2, 4),
        _item("Spicy Southwest Salad", 450, 33, 26, 22),
        _item("Cobb Salad", 510, 38, 22, 28),
        _item("Egg White Grill", 300, 25, 30, 8),
        _item("Grilled Cool Wrap", 350, 37, 29, 14),
        _item("Market Salad", 330, 28, 14, 18),
    ]),
    ("burger_king", "US", "Burger King", "https://www.bk.com/menu", ["burger king", "bk"], [
        _item("Flame-Grilled Whopper Jr.", 310, 13, 26, 18),
        _item("Grilled Chicken Sandwich", 430, 28, 40, 16),
        _item("4pc Chicken Nuggets", 170, 8, 11, 10),
        _item("Impossible Whopper", 630, 25, 58, 34, veg=True),
        _item("BK Royal Crispy Chicken", 580, 26, 48, 30),
        _item("Garden Side Salad", 60, 4, 8, 2, cat="side", veg=True, vgn=True),
    ]),
    ("wendys", "US", "Wendy's", "https://www.wendys.com/menu", ["wendys", "wendy's"], [
        _item("Grilled Chicken Sandwich", 370, 34, 36, 10),
        _item("Apple Pecan Chicken Salad (Half)", 340, 20, 24, 18),
        _item("Jr. Hamburger", 260, 14, 26, 10),
        _item("4pc Grilled Chicken Nuggets", 190, 24, 4, 8),
        _item("Power Mediterranean Chicken Salad", 480, 38, 22, 26),
        _item("Parmesan Caesar Chicken Salad", 520, 36, 18, 32),
    ]),
    ("dominos", "US", "Domino's", "https://www.dominos.com/en/pages/content/nutritional/nutrition.jsp", ["dominos", "domino's"], [
        _item("Grilled Chicken Tacos (2)", 440, 28, 36, 18),
        _item("Pacific Veggie Pizza (2 slices, thin)", 380, 16, 42, 16, veg=True),
        _item("Chicken & Spinach (2 slices, thin)", 400, 22, 36, 18),
        _item("Grilled Chicken Caesar Salad", 340, 28, 12, 20, cat="side"),
        _item("Specialty Chicken (plain)", 280, 24, 16, 14),
        _item("Boneless Wings (8pc, plain)", 370, 22, 22, 20),
    ]),
    ("starbucks", "US", "Starbucks", "https://www.starbucks.com/menu", ["starbucks"], [
        _item("Egg & Cheese Protein Box", 470, 28, 38, 22, cat="snack"),
        _item("Turkey & Pesto Panini", 480, 28, 40, 20),
        _item("Spinach Feta Wrap", 290, 20, 34, 10, veg=True),
        _item("Chicken & Quinoa Bowl", 420, 26, 42, 14),
        _item("Impossible Breakfast Sandwich", 420, 22, 34, 22, veg=True),
    ]),
    ("pizza_hut", "US", "Pizza Hut", "https://www.pizzahut.com/menu", ["pizza hut"], [
        _item("Chicken Supreme (2 slices, thin)", 400, 22, 38, 18),
        _item("Veggie Lover (2 slices, thin)", 360, 14, 42, 14, veg=True),
        _item("Grilled Chicken Alfredo Pasta", 530, 28, 52, 22),
        _item("Tuscani Chicken Pasta", 520, 26, 48, 24),
        _item("Caesar Side Salad", 130, 8, 8, 8, cat="side", veg=True),
        _item("8 Boneless Wings (plain)", 380, 24, 20, 22),
    ]),

    # ═══════════════════ INDIA ═══════════════════

    ("mcdonalds", "IN", "McDonald's", "https://www.mcdonalds.co.in/menu", ["mcdonalds", "mcdonald's"], [
        _item("McChicken Burger", 370, 16, 38, 16),
        _item("Chicken Maharaja Mac", 560, 24, 46, 30),
        _item("McAloo Tikki Burger", 340, 8, 48, 14, veg=True),
        _item("Egg McMuffin", 290, 16, 26, 12),
        _item("Grilled Chicken Wrap", 380, 22, 34, 14),
        _item("Corn & Cheese Burger", 320, 10, 42, 12, veg=True),
    ]),
    ("dominos", "IN", "Domino's", "https://www.dominos.co.in/menu", ["dominos", "domino's"], [
        _item("Chicken Dominator (Medium, Thin Crust)", 660, 38, 50, 28),
        _item("Pepper Chicken (Medium, Thin Crust)", 580, 32, 48, 24),
        _item("Farmhouse Pizza (Medium, Classic)", 540, 20, 58, 22, veg=True),
        _item("Veg Extravaganza (Medium, Thin Crust)", 500, 18, 52, 20, veg=True),
        _item("Non-Veg Supreme (Medium, Thin Crust)", 620, 30, 50, 28),
        _item("Garlic Breadsticks (4pc)", 280, 6, 36, 12, cat="side", veg=True),
    ]),
    ("burger_king", "IN", "Burger King", "https://www.burgerking.in/menu", ["burger king", "bk"], [
        _item("Chicken Whopper", 520, 22, 44, 26),
        _item("BK Chicken Burger", 340, 16, 34, 14),
        _item("Paneer Royale", 460, 14, 44, 24, veg=True),
        _item("Crispy Veg Burger", 320, 8, 42, 12, veg=True),
        _item("4pc Chicken Nuggets", 180, 10, 12, 10),
        _item("BK Veggie Strips", 240, 6, 28, 12, cat="side", veg=True),
    ]),
    ("pizza_hut", "IN", "Pizza Hut", "https://www.pizzahut.co.in/menu", ["pizza hut"], [
        _item("Chicken Supreme (Medium, Thin Crust)", 420, 22, 40, 18),
        _item("Tandoori Chicken Pizza (Medium, Thin Crust)", 440, 24, 42, 18),
        _item("Veggie Paradise (Medium, Thin Crust)", 380, 14, 44, 16, veg=True),
        _item("Paneer Tikka Pizza (Medium, Thin Crust)", 400, 16, 42, 18, veg=True),
        _item("Chicken Pasta Bake", 480, 22, 48, 20),
    ]),
    ("starbucks", "IN", "Starbucks", "https://www.starbucks.in/menu", ["starbucks"], [
        _item("Chicken Kathi Roll", 360, 20, 32, 14),
        _item("Paneer Tikka Sandwich", 340, 14, 36, 14, veg=True),
        _item("Egg & Cheese Croissant", 380, 16, 30, 22),
        _item("Banana Walnut Loaf", 340, 6, 46, 14, cat="snack", veg=True),
        _item("Classic Chicken Sandwich", 380, 22, 34, 16),
    ]),
    ("wow_momo", "IN", "Wow Momo", "https://www.wowmomo.in/menu", ["wow momo", "wow! momo"], [
        _item("Steamed Chicken Momos (6pc)", 280, 18, 30, 8),
        _item("Chicken Darjeeling Momos (6pc)", 320, 20, 32, 10),
        _item("Veg Steamed Momos (6pc)", 240, 8, 34, 6, veg=True, vgn=True),
        _item("Chicken Momo Burger", 380, 18, 38, 16),
        _item("Paneer Steamed Momos (6pc)", 300, 12, 32, 12, veg=True),
    ]),
    ("haldirams", "IN", "Haldiram's", "https://www.haldirams.com", ["haldirams", "haldiram's"], [
        _item("Chole Bhature (Half Portion)", 520, 14, 58, 24, veg=True),
        _item("Paneer Tikka", 340, 18, 12, 24, veg=True),
        _item("Rajma Chawal", 440, 16, 64, 10, veg=True),
        _item("Chicken Biryani", 540, 26, 60, 18),
        _item("Dal Makhani with Roti", 420, 16, 52, 14, veg=True),
        _item("Veg Thali", 580, 18, 72, 20, veg=True),
    ]),
    ("barbeque_nation", "IN", "Barbeque Nation", "https://www.barbequenation.com", ["barbeque nation", "bbq nation"], [
        _item("Grilled Chicken Tikka", 280, 32, 6, 14),
        _item("Paneer Tikka", 240, 14, 8, 16, veg=True),
        _item("Grilled Fish", 260, 28, 4, 14),
        _item("Tandoori Chicken Leg", 320, 34, 4, 18),
        _item("Grilled Prawns", 180, 22, 4, 8),
        _item("Veg Seekh Kebab", 200, 8, 18, 10, veg=True),
    ]),
    ("eatfit", "IN", "EatFit", "https://www.eatfit.in", ["eatfit", "eat fit"], [
        _item("Grilled Chicken Meal Box", 440, 34, 40, 12),
        _item("Paneer Bhurji Meal Box", 420, 18, 42, 18, veg=True),
        _item("Chicken Tikka Bowl", 380, 30, 32, 12),
        _item("Egg Bhurji Meal Box", 400, 22, 38, 16),
        _item("Dal Khichdi Bowl", 340, 12, 48, 8, veg=True, vgn=True),
        _item("Ragi Roti Meal", 360, 14, 46, 10, veg=True),
    ]),
    ("freshmenu", "IN", "FreshMenu", "https://www.freshmenu.com", ["freshmenu", "fresh menu"], [
        _item("Grilled Chicken with Brown Rice", 480, 36, 44, 12),
        _item("Peri Peri Chicken Bowl", 520, 32, 48, 18),
        _item("Egg Fried Rice", 440, 16, 52, 16),
        _item("Paneer Tikka Meal", 460, 18, 44, 20, veg=True),
        _item("Chicken Caesar Salad", 380, 28, 16, 22),
        _item("Grilled Fish Meal", 420, 30, 38, 12),
    ]),
    ("behrouz_biryani", "IN", "Behrouz Biryani", "https://www.behrouzbiryani.com", ["behrouz biryani", "behrouz"], [
        _item("Chicken Biryani (Regular)", 560, 28, 62, 18),
        _item("Mutton Biryani (Regular)", 620, 26, 60, 24),
        _item("Paneer Biryani (Regular)", 520, 16, 64, 18, veg=True),
        _item("Egg Biryani (Regular)", 480, 18, 58, 16),
        _item("Chicken Tikka Biryani (Regular)", 540, 30, 58, 18),
    ]),
]


def write_seed_file(chain_key, market, brand_name, source_url, variants, items):
    """Write a single seed JSON file."""
    filename = f"{chain_key}_{market.lower()}.json"
    filepath = DATA_DIR / filename
    seed = {
        "brand_name": brand_name,
        "source_type": "seed_template",
        "source_url": source_url,
        "store_name_variants": variants,
        "items": items,
    }
    filepath.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    return filepath


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"{'Chain':<25} {'Market':<6} {'Items':<6} {'File':<40} {'Supabase':<12}")
    print("─" * 95)

    total_chains = 0
    total_items = 0
    errors = []
    started = time.time()

    for chain_key, market, brand_name, source_url, variants, items in ALL_CHAINS:
        filepath = write_seed_file(chain_key, market, brand_name, source_url, variants, items)
        rel = filepath.name

        # Sync to Supabase
        try:
            result = sync_chain_menu_to_supabase(chain_key, market)
            ok = result.get("ok", False)
            count = result.get("item_count", 0)
            status = f"✓ {count} items" if ok else f"✗ {result.get('error', '?')}"
        except Exception as e:
            ok = False
            count = 0
            status = f"✗ {str(e)[:30]}"
            errors.append((chain_key, market, str(e)))

        total_chains += 1
        total_items += count
        print(f"{brand_name:<25} {market:<6} {len(items):<6} {rel:<40} {status}")

    elapsed = time.time() - started
    print("─" * 95)
    print(f"Done: {total_chains} chain-markets, {total_items} items synced to Supabase in {elapsed:.1f}s")
    if errors:
        print(f"\n{len(errors)} errors:")
        for ck, m, e in errors:
            print(f"  {ck} ({m}): {e}")


if __name__ == "__main__":
    main()
