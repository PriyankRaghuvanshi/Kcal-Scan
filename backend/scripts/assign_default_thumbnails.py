#!/usr/bin/env python3
"""
Assign a default thumbnail (Wikimedia Commons, CC-licensed) to every chain
item whose image_url is empty. Uses item_name keyword matching (not category,
which is usually just "entree" and too coarse).

First match in KEYWORD_TO_IMAGE wins. Everything that doesn't match stays
empty -> the app falls back to the backend's tiered category picker.

Run:
    cd backend
    python scripts/assign_default_thumbnails.py --dry-run
    python scripts/assign_default_thumbnails.py

Idempotent: only fills blank image_url fields, never overwrites.
"""
import argparse
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"

W = "https://upload.wikimedia.org/wikipedia/commons/thumb"

# Order matters: more specific keywords must come before general ones.
# E.g. "paneer tikka" before "paneer", "chicken biryani" before "biryani".
KEYWORD_TO_IMAGE: list[tuple[str, str]] = [
    # --- pizza ---
    ("pepperoni", f"{W}/a/a3/Eq_it-na_pizza-margherita_sep2005_sml.jpg/640px-Eq_it-na_pizza-margherita_sep2005_sml.jpg"),
    ("margherita", f"{W}/a/a3/Eq_it-na_pizza-margherita_sep2005_sml.jpg/640px-Eq_it-na_pizza-margherita_sep2005_sml.jpg"),
    ("pizza", f"{W}/a/a3/Eq_it-na_pizza-margherita_sep2005_sml.jpg/640px-Eq_it-na_pizza-margherita_sep2005_sml.jpg"),

    # --- burgers / sliders ---
    ("cheeseburger", f"{W}/0/0b/RedDot_Burger.jpg/640px-RedDot_Burger.jpg"),
    ("hamburger", f"{W}/0/0b/RedDot_Burger.jpg/640px-RedDot_Burger.jpg"),
    ("burger", f"{W}/0/0b/RedDot_Burger.jpg/640px-RedDot_Burger.jpg"),
    ("slider", f"{W}/0/0b/RedDot_Burger.jpg/640px-RedDot_Burger.jpg"),

    # --- fried chicken / nuggets / wings ---
    ("chicken nugget", f"{W}/3/3a/Chicken_McNuggets_%28cropped%29.jpg/640px-Chicken_McNuggets_%28cropped%29.jpg"),
    ("chicken wings", f"{W}/1/14/Chicken_wings.jpg/640px-Chicken_wings.jpg"),
    ("hot wings", f"{W}/1/14/Chicken_wings.jpg/640px-Chicken_wings.jpg"),
    ("fried chicken", f"{W}/5/57/Fried-Chicken-Dinner.jpg/640px-Fried-Chicken-Dinner.jpg"),

    # --- fries ---
    ("french fries", f"{W}/4/47/FrenchFries.jpg/640px-FrenchFries.jpg"),
    ("fries", f"{W}/4/47/FrenchFries.jpg/640px-FrenchFries.jpg"),
    ("wedges", f"{W}/4/47/FrenchFries.jpg/640px-FrenchFries.jpg"),

    # --- hot dogs / sausages ---
    ("hot dog", f"{W}/b/b1/Hot_dog_with_mustard.png/640px-Hot_dog_with_mustard.png"),
    ("hotdog", f"{W}/b/b1/Hot_dog_with_mustard.png/640px-Hot_dog_with_mustard.png"),
    ("sausage", f"{W}/b/b1/Hot_dog_with_mustard.png/640px-Hot_dog_with_mustard.png"),

    # --- tacos / burritos / quesadilla ---
    ("quesadilla", f"{W}/2/28/Quesadilla_2.jpg/640px-Quesadilla_2.jpg"),
    ("burrito", f"{W}/f/f3/Shredded_beef_burrito.jpg/640px-Shredded_beef_burrito.jpg"),
    ("taco", f"{W}/7/7e/001_Tacos_de_carnitas%2C_carne_asada_y_al_pastor.jpg/640px-001_Tacos_de_carnitas%2C_carne_asada_y_al_pastor.jpg"),
    ("nachos", f"{W}/a/a8/Nachos.jpg/640px-Nachos.jpg"),

    # --- sushi / sashimi ---
    ("sashimi", f"{W}/7/76/Salmon_sashimi.jpg/640px-Salmon_sashimi.jpg"),
    ("nigiri", f"{W}/8/89/Sushi_2016-05-08.jpg/640px-Sushi_2016-05-08.jpg"),
    ("sushi", f"{W}/8/89/Sushi_2016-05-08.jpg/640px-Sushi_2016-05-08.jpg"),
    ("maki", f"{W}/8/89/Sushi_2016-05-08.jpg/640px-Sushi_2016-05-08.jpg"),

    # --- ramen / noodles / pho ---
    ("ramen", f"{W}/4/4e/Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg/640px-Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg"),
    ("pho", f"{W}/8/86/Pho-Beef-Noodles-2008.jpg/640px-Pho-Beef-Noodles-2008.jpg"),
    ("pad thai", f"{W}/1/13/Phat_Thai_kung_Chang_Khien_street_stall.jpg/640px-Phat_Thai_kung_Chang_Khien_street_stall.jpg"),
    ("udon", f"{W}/9/90/Kitsune_udon_by_kunecomaster.jpg/640px-Kitsune_udon_by_kunecomaster.jpg"),
    ("noodle", f"{W}/4/4e/Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg/640px-Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg"),
    ("chow mein", f"{W}/4/4e/Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg/640px-Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg"),
    ("hakka", f"{W}/4/4e/Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg/640px-Tonkotsu_Ramen%2C_at_Ippudo_Waikiki_%2823348761110%29.jpg"),

    # --- Indian ---
    ("paneer tikka", f"{W}/d/d3/Paneer_tikka_at_Punjabi_Restaurant.jpg/640px-Paneer_tikka_at_Punjabi_Restaurant.jpg"),
    ("paneer", f"{W}/d/d3/Paneer_tikka_at_Punjabi_Restaurant.jpg/640px-Paneer_tikka_at_Punjabi_Restaurant.jpg"),
    ("chicken tikka", f"{W}/c/cb/Tandoori_chicken_001.jpg/640px-Tandoori_chicken_001.jpg"),
    ("tandoori", f"{W}/c/cb/Tandoori_chicken_001.jpg/640px-Tandoori_chicken_001.jpg"),
    ("butter chicken", f"{W}/e/e1/Butter_chicken-Bhishan_Kitchen_1.jpg/640px-Butter_chicken-Bhishan_Kitchen_1.jpg"),
    ("biryani", f"{W}/5/55/Hyderabadi_Chicken_Biryani.jpg/640px-Hyderabadi_Chicken_Biryani.jpg"),
    ("chicken curry", f"{W}/c/c8/Kukuł_z_curry.jpg/640px-Kukuł_z_curry.jpg"),
    ("curry", f"{W}/c/c8/Kukuł_z_curry.jpg/640px-Kukuł_z_curry.jpg"),
    ("dal", f"{W}/2/29/Plain_dal.jpg/640px-Plain_dal.jpg"),
    ("masala dosa", f"{W}/4/45/Masala_Dosa_at_Saravanaa_Bhavan_London.jpg/640px-Masala_Dosa_at_Saravanaa_Bhavan_London.jpg"),
    ("dosa", f"{W}/4/45/Masala_Dosa_at_Saravanaa_Bhavan_London.jpg/640px-Masala_Dosa_at_Saravanaa_Bhavan_London.jpg"),
    ("idli", f"{W}/3/3a/Idli.jpg/640px-Idli.jpg"),
    ("samosa", f"{W}/4/49/Samosa_and_chutney.JPG/640px-Samosa_and_chutney.JPG"),
    ("pakora", f"{W}/f/f2/Bhajji.jpg/640px-Bhajji.jpg"),
    ("naan", f"{W}/9/92/Naan_bread.jpg/640px-Naan_bread.jpg"),
    ("roti", f"{W}/9/92/Naan_bread.jpg/640px-Naan_bread.jpg"),
    ("chapati", f"{W}/9/92/Naan_bread.jpg/640px-Naan_bread.jpg"),
    ("thali", f"{W}/3/3a/Indian_thali.jpg/640px-Indian_thali.jpg"),
    ("chole", f"{W}/2/29/Plain_dal.jpg/640px-Plain_dal.jpg"),
    ("rajma", f"{W}/2/29/Plain_dal.jpg/640px-Plain_dal.jpg"),

    # --- Middle East ---
    ("shawarma", f"{W}/7/7a/Shawarma_sandwich.jpg/640px-Shawarma_sandwich.jpg"),
    ("kebab", f"{W}/2/26/Doner_kebab_Prague.jpg/640px-Doner_kebab_Prague.jpg"),
    ("falafel", f"{W}/3/3f/Falafel_balls.jpg/640px-Falafel_balls.jpg"),
    ("hummus", f"{W}/1/17/Hummus_0002.jpg/640px-Hummus_0002.jpg"),

    # --- sandwiches ---
    ("panini", f"{W}/8/8e/Panini_sandwich.jpg/640px-Panini_sandwich.jpg"),
    ("bagel", f"{W}/7/73/Assorted_bagels_%28sliced_side_up%29.jpg/640px-Assorted_bagels_%28sliced_side_up%29.jpg"),
    ("wrap", f"{W}/7/7a/Shawarma_sandwich.jpg/640px-Shawarma_sandwich.jpg"),
    ("sandwich", f"{W}/5/5c/Ham_sandwich_in_brown_bread.jpg/640px-Ham_sandwich_in_brown_bread.jpg"),
    ("sub ", f"{W}/5/5c/Ham_sandwich_in_brown_bread.jpg/640px-Ham_sandwich_in_brown_bread.jpg"),

    # --- salads / bowls ---
    ("caesar salad", f"{W}/a/a0/Caesar-salad.jpg/640px-Caesar-salad.jpg"),
    ("salad", f"{W}/3/34/Ensalada_de_pollo_a_la_parrilla.jpg/640px-Ensalada_de_pollo_a_la_parrilla.jpg"),
    ("buddha bowl", f"{W}/a/a7/Buddha_bowl_%284%29.jpg/640px-Buddha_bowl_%284%29.jpg"),
    ("grain bowl", f"{W}/a/a7/Buddha_bowl_%284%29.jpg/640px-Buddha_bowl_%284%29.jpg"),
    ("rice bowl", f"{W}/a/a7/Buddha_bowl_%284%29.jpg/640px-Buddha_bowl_%284%29.jpg"),
    ("poke", f"{W}/a/a7/Buddha_bowl_%284%29.jpg/640px-Buddha_bowl_%284%29.jpg"),

    # --- pasta ---
    ("lasagna", f"{W}/5/53/Lasagne_-_stonesoup.jpg/640px-Lasagne_-_stonesoup.jpg"),
    ("spaghetti", f"{W}/0/01/Spaghetti_aglio_e_olio.jpg/640px-Spaghetti_aglio_e_olio.jpg"),
    ("pasta", f"{W}/0/01/Spaghetti_aglio_e_olio.jpg/640px-Spaghetti_aglio_e_olio.jpg"),
    ("penne", f"{W}/0/01/Spaghetti_aglio_e_olio.jpg/640px-Spaghetti_aglio_e_olio.jpg"),
    ("ravioli", f"{W}/0/01/Spaghetti_aglio_e_olio.jpg/640px-Spaghetti_aglio_e_olio.jpg"),

    # --- breakfast ---
    ("pancake", f"{W}/a/a6/Pancakes.jpg/640px-Pancakes.jpg"),
    ("waffle", f"{W}/a/a8/Round_waffles_on_a_plate.jpg/640px-Round_waffles_on_a_plate.jpg"),
    ("french toast", f"{W}/a/a6/Pancakes.jpg/640px-Pancakes.jpg"),
    ("omelette", f"{W}/2/23/Cheese_Omelette.jpg/640px-Cheese_Omelette.jpg"),
    ("omelet", f"{W}/2/23/Cheese_Omelette.jpg/640px-Cheese_Omelette.jpg"),
    ("eggs benedict", f"{W}/0/0c/Eggs_benedict.jpg/640px-Eggs_benedict.jpg"),
    ("scrambled eggs", f"{W}/2/23/Cheese_Omelette.jpg/640px-Cheese_Omelette.jpg"),
    ("croissant", f"{W}/2/28/Croissant-Petr_Kratochvil.jpg/640px-Croissant-Petr_Kratochvil.jpg"),
    ("muffin", f"{W}/7/75/Muffin_NIH.jpg/640px-Muffin_NIH.jpg"),

    # --- drinks ---
    ("smoothie", f"{W}/e/ec/Smoothie.jpg/640px-Smoothie.jpg"),
    ("milkshake", f"{W}/4/49/Chocolate_milkshake.jpg/640px-Chocolate_milkshake.jpg"),
    ("shake", f"{W}/4/49/Chocolate_milkshake.jpg/640px-Chocolate_milkshake.jpg"),
    ("latte", f"{W}/a/a9/Caffe_latte_at_Pulse_Cafe.jpg/640px-Caffe_latte_at_Pulse_Cafe.jpg"),
    ("cappuccino", f"{W}/a/a9/Caffe_latte_at_Pulse_Cafe.jpg/640px-Caffe_latte_at_Pulse_Cafe.jpg"),
    ("americano", f"{W}/a/a9/Caffe_latte_at_Pulse_Cafe.jpg/640px-Caffe_latte_at_Pulse_Cafe.jpg"),
    ("espresso", f"{W}/a/a9/Caffe_latte_at_Pulse_Cafe.jpg/640px-Caffe_latte_at_Pulse_Cafe.jpg"),
    ("cold brew", f"{W}/a/a9/Caffe_latte_at_Pulse_Cafe.jpg/640px-Caffe_latte_at_Pulse_Cafe.jpg"),
    ("coffee", f"{W}/a/a9/Caffe_latte_at_Pulse_Cafe.jpg/640px-Caffe_latte_at_Pulse_Cafe.jpg"),
    ("bubble tea", f"{W}/3/3d/Bubble_Tea.png/640px-Bubble_Tea.png"),
    ("boba", f"{W}/3/3d/Bubble_Tea.png/640px-Bubble_Tea.png"),

    # --- desserts ---
    ("brownie", f"{W}/e/e6/Chocolate_brownie_%284368624516%29.jpg/640px-Chocolate_brownie_%284368624516%29.jpg"),
    ("cheesecake", f"{W}/d/d2/Raspberry_cheesecake.jpg/640px-Raspberry_cheesecake.jpg"),
    ("ice cream", f"{W}/3/31/Chocolate_ice_cream.jpg/640px-Chocolate_ice_cream.jpg"),
    ("gelato", f"{W}/3/31/Chocolate_ice_cream.jpg/640px-Chocolate_ice_cream.jpg"),
    ("frozen yogurt", f"{W}/3/31/Chocolate_ice_cream.jpg/640px-Chocolate_ice_cream.jpg"),
    ("donut", f"{W}/9/91/Glazed-Donut.jpg/640px-Glazed-Donut.jpg"),
    ("doughnut", f"{W}/9/91/Glazed-Donut.jpg/640px-Glazed-Donut.jpg"),
    ("cupcake", f"{W}/4/40/Chocolate_cupcake.jpg/640px-Chocolate_cupcake.jpg"),

    # --- proteins (grilled etc.) ---
    ("grilled salmon", f"{W}/7/76/Salmon_sashimi.jpg/640px-Salmon_sashimi.jpg"),
    ("grilled chicken", f"{W}/3/34/Ensalada_de_pollo_a_la_parrilla.jpg/640px-Ensalada_de_pollo_a_la_parrilla.jpg"),
    ("grilled fish", f"{W}/7/76/Salmon_sashimi.jpg/640px-Salmon_sashimi.jpg"),
    ("steak", f"{W}/f/f6/Grilled_Steak.jpg/640px-Grilled_Steak.jpg"),

    # --- soups ---
    ("miso soup", f"{W}/6/6a/Mussel_soup_in_a_Quimper_bowl.jpg/640px-Mussel_soup_in_a_Quimper_bowl.jpg"),
    ("soup", f"{W}/6/6a/Mussel_soup_in_a_Quimper_bowl.jpg/640px-Mussel_soup_in_a_Quimper_bowl.jpg"),

    # --- sides / snacks ---
    ("onion rings", f"{W}/a/a8/Onion_rings.jpg/640px-Onion_rings.jpg"),
    ("mashed potato", f"{W}/e/e8/Mashed_potato.jpg/640px-Mashed_potato.jpg"),
    ("coleslaw", f"{W}/7/78/Coleslaw.jpg/640px-Coleslaw.jpg"),
    ("popcorn", f"{W}/1/19/Popcorn_fresh.jpg/640px-Popcorn_fresh.jpg"),

    # --- bread ---
    ("garlic bread", f"{W}/3/36/Garlic_bread.jpg/640px-Garlic_bread.jpg"),
    ("breadstick", f"{W}/3/36/Garlic_bread.jpg/640px-Garlic_bread.jpg"),
]


def pick_image(item_name: str) -> str:
    n = item_name.lower()
    if not n:
        return ""
    for kw, url in KEYWORD_TO_IMAGE:
        if kw in n:
            return url
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chains", nargs="*")
    args = ap.parse_args()

    files = sorted(DATA_DIR.glob("*.json"))
    if args.chains:
        wanted = set(args.chains)
        files = [f for f in files if any(f.name.startswith(p + "_") or f.stem == p for p in wanted)]

    total_items = 0
    assigned = 0
    files_touched = 0

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data.get("items") or []
        if not isinstance(items, list):
            continue
        file_changed = False
        for it in items:
            if not isinstance(it, dict):
                continue
            total_items += 1
            if str(it.get("image_url") or "").strip():
                continue
            url = pick_image(str(it.get("item_name") or ""))
            if url:
                it["image_url"] = url
                assigned += 1
                file_changed = True
        if file_changed:
            files_touched += 1
            if not args.dry_run:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'DRY-RUN' if args.dry_run else 'APPLIED'}: scanned {total_items} items, assigned {assigned}, touched {files_touched} files")
    if args.dry_run:
        print("Re-run without --dry-run to persist, then re-run sync_chain_files_to_supabase.py.")


if __name__ == "__main__":
    main()
