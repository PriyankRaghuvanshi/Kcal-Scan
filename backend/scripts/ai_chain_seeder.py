#!/usr/bin/env python3
"""
AI-powered chain menu seeder — generates menu items for ANY food chain worldwide
using Claude API, writes seed files, and syncs to Supabase.

Usage:
    cd backend
    export ANTHROPIC_API_KEY="sk-ant-..."
    export SUPABASE_URL="https://..."
    export SUPABASE_SERVICE_ROLE_KEY="..."

    # Generate + sync all chains in the expanded list:
    python scripts/ai_chain_seeder.py

    # Only specific chains:
    python scripts/ai_chain_seeder.py --chains "five_guys:US,greggs:GB,jollibee:PH"

    # Skip Supabase sync (just generate seed files):
    python scripts/ai_chain_seeder.py --no-sync

    # Only a specific market:
    python scripts/ai_chain_seeder.py --market US
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"
REGISTRY_FILE = Path(__file__).resolve().parent.parent / "chain_menu_registry.py"

# ── EXPANDED WORLDWIDE CHAIN LIST ──────────────────────────────────────
# Format: (chain_key, market, display_name, aliases)
# Includes current 31 + ~170 new chains across 15+ countries.

EXPANDED_CHAINS = [
    # ═══ AUSTRALIA ═══
    ("mcdonalds", "AU", "McDonald's", ["mcdonalds", "mcdonald's", "maccas"]),
    ("kfc", "AU", "KFC", ["kfc", "kentucky fried chicken"]),
    ("hungry_jacks", "AU", "Hungry Jack's", ["hungry jacks", "hungry jack's"]),
    ("subway", "AU", "Subway", ["subway"]),
    ("dominos", "AU", "Domino's", ["dominos", "domino's"]),
    ("grilld", "AU", "Grill'd", ["grilld", "grill'd"]),
    ("guzman_y_gomez", "AU", "Guzman y Gomez", ["guzman y gomez", "gyg"]),
    ("zambrero", "AU", "Zambrero", ["zambrero"]),
    ("oporto", "AU", "Oporto", ["oporto"]),
    ("starbucks", "AU", "Starbucks", ["starbucks"]),
    ("boost_juice", "AU", "Boost Juice", ["boost juice", "boost"]),
    ("nandos", "AU", "Nando's", ["nandos", "nando's"]),
    ("red_rooster", "AU", "Red Rooster", ["red rooster"]),
    ("mad_mex", "AU", "Mad Mex", ["mad mex"]),
    ("sushi_hub", "AU", "Sushi Hub", ["sushi hub"]),
    ("soul_origin", "AU", "Soul Origin", ["soul origin"]),
    ("schnitz", "AU", "Schnitz", ["schnitz"]),
    ("betty_burgers", "AU", "Betty's Burgers", ["betty's burgers", "bettys burgers"]),
    ("fishbowl", "AU", "Fishbowl", ["fishbowl"]),
    ("sushi_sushi", "AU", "Sushi Sushi", ["sushi sushi"]),

    # ═══ UNITED STATES ═══
    ("mcdonalds", "US", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("chipotle", "US", "Chipotle", ["chipotle", "chipotle mexican grill"]),
    ("subway", "US", "Subway", ["subway"]),
    ("sweetgreen", "US", "Sweetgreen", ["sweetgreen"]),
    ("cava", "US", "CAVA", ["cava", "cava grill"]),
    ("chick_fil_a", "US", "Chick-fil-A", ["chick-fil-a", "chick fil a"]),
    ("burger_king", "US", "Burger King", ["burger king", "bk"]),
    ("wendys", "US", "Wendy's", ["wendys", "wendy's"]),
    ("dominos", "US", "Domino's", ["dominos", "domino's"]),
    ("starbucks", "US", "Starbucks", ["starbucks"]),
    ("pizza_hut", "US", "Pizza Hut", ["pizza hut"]),
    ("taco_bell", "US", "Taco Bell", ["taco bell"]),
    ("panera", "US", "Panera Bread", ["panera", "panera bread"]),
    ("five_guys", "US", "Five Guys", ["five guys"]),
    ("popeyes", "US", "Popeyes", ["popeyes"]),
    ("panda_express", "US", "Panda Express", ["panda express"]),
    ("shake_shack", "US", "Shake Shack", ["shake shack"]),
    ("wingstop", "US", "Wingstop", ["wingstop"]),
    ("in_n_out", "US", "In-N-Out Burger", ["in-n-out", "in n out"]),
    ("raising_canes", "US", "Raising Cane's", ["raising cane's", "raising canes"]),
    ("el_pollo_loco", "US", "El Pollo Loco", ["el pollo loco"]),
    ("jersey_mikes", "US", "Jersey Mike's", ["jersey mike's", "jersey mikes"]),
    ("jason_deli", "US", "Jason's Deli", ["jason's deli", "jasons deli"]),
    ("noodles_co", "US", "Noodles & Company", ["noodles & company", "noodles and company"]),
    ("tropical_smoothie", "US", "Tropical Smoothie Cafe", ["tropical smoothie"]),
    ("zaxbys", "US", "Zaxby's", ["zaxby's", "zaxbys"]),
    ("culvers", "US", "Culver's", ["culver's", "culvers"]),
    ("qdoba", "US", "Qdoba", ["qdoba"]),
    ("firehouse_subs", "US", "Firehouse Subs", ["firehouse subs"]),
    ("mod_pizza", "US", "MOD Pizza", ["mod pizza"]),
    ("portillos", "US", "Portillo's", ["portillo's", "portillos"]),
    ("whataburger", "US", "Whataburger", ["whataburger"]),
    ("jack_in_the_box", "US", "Jack in the Box", ["jack in the box"]),
    ("sonic", "US", "Sonic Drive-In", ["sonic"]),
    ("arbys", "US", "Arby's", ["arby's", "arbys"]),
    ("little_caesars", "US", "Little Caesars", ["little caesars"]),
    ("papa_johns", "US", "Papa John's", ["papa john's", "papa johns"]),
    ("dunkin", "US", "Dunkin'", ["dunkin", "dunkin donuts"]),
    ("kfc", "US", "KFC", ["kfc", "kentucky fried chicken"]),
    ("dennys", "US", "Denny's", ["denny's", "dennys"]),
    ("ihop", "US", "IHOP", ["ihop"]),
    ("cracker_barrel", "US", "Cracker Barrel", ["cracker barrel"]),
    ("boston_market", "US", "Boston Market", ["boston market"]),
    ("cosi", "US", "Cosi", ["cosi"]),

    # ═══ INDIA ═══
    ("mcdonalds", "IN", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("dominos", "IN", "Domino's", ["dominos", "domino's"]),
    ("burger_king", "IN", "Burger King", ["burger king"]),
    ("pizza_hut", "IN", "Pizza Hut", ["pizza hut"]),
    ("starbucks", "IN", "Starbucks", ["starbucks"]),
    ("wow_momo", "IN", "Wow Momo", ["wow momo", "wow! momo"]),
    ("haldirams", "IN", "Haldiram's", ["haldirams", "haldiram's"]),
    ("barbeque_nation", "IN", "Barbeque Nation", ["barbeque nation", "bbq nation"]),
    ("eatfit", "IN", "EatFit", ["eatfit", "eat fit"]),
    ("freshmenu", "IN", "FreshMenu", ["freshmenu"]),
    ("behrouz_biryani", "IN", "Behrouz Biryani", ["behrouz biryani", "behrouz"]),
    ("faasos", "IN", "Faasos", ["faasos"]),
    ("subway", "IN", "Subway", ["subway"]),
    ("kfc", "IN", "KFC", ["kfc"]),
    ("paradise_biryani", "IN", "Paradise Biryani", ["paradise biryani", "paradise"]),
    ("saravana_bhavan", "IN", "Saravana Bhavan", ["saravana bhavan"]),
    ("bikanervala", "IN", "Bikanervala", ["bikanervala"]),
    ("moti_mahal", "IN", "Moti Mahal", ["moti mahal"]),
    ("chai_point", "IN", "Chai Point", ["chai point"]),
    ("box8", "IN", "Box8", ["box8"]),
    ("licious", "IN", "Licious", ["licious"]),
    ("rebel_foods", "IN", "Rebel Foods", ["rebel foods"]),
    ("natural_icecream", "IN", "Natural Ice Cream", ["natural ice cream", "naturals"]),
    ("baskin_robbins", "IN", "Baskin Robbins", ["baskin robbins"]),

    # ═══ UNITED KINGDOM ═══
    ("mcdonalds", "GB", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("kfc", "GB", "KFC", ["kfc"]),
    ("nandos", "GB", "Nando's", ["nandos", "nando's"]),
    ("greggs", "GB", "Greggs", ["greggs"]),
    ("pret", "GB", "Pret a Manger", ["pret a manger", "pret"]),
    ("leon", "GB", "LEON", ["leon"]),
    ("wagamama", "GB", "Wagamama", ["wagamama"]),
    ("subway", "GB", "Subway", ["subway"]),
    ("dominos", "GB", "Domino's", ["dominos", "domino's"]),
    ("burger_king", "GB", "Burger King", ["burger king"]),
    ("five_guys", "GB", "Five Guys", ["five guys"]),
    ("pizza_express", "GB", "Pizza Express", ["pizza express"]),
    ("itsu", "GB", "Itsu", ["itsu"]),
    ("wasabi", "GB", "Wasabi", ["wasabi"]),
    ("tortilla", "GB", "Tortilla", ["tortilla"]),
    ("franco_manca", "GB", "Franco Manca", ["franco manca"]),
    ("starbucks", "GB", "Starbucks", ["starbucks"]),
    ("costa", "GB", "Costa Coffee", ["costa", "costa coffee"]),

    # ═══ CANADA ═══
    ("mcdonalds", "CA", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("tim_hortons", "CA", "Tim Hortons", ["tim hortons", "tims"]),
    ("subway", "CA", "Subway", ["subway"]),
    ("a_and_w", "CA", "A&W", ["a&w", "a and w"]),
    ("harveys", "CA", "Harvey's", ["harvey's", "harveys"]),
    ("mary_browns", "CA", "Mary Brown's", ["mary brown's", "mary browns"]),
    ("swiss_chalet", "CA", "Swiss Chalet", ["swiss chalet"]),
    ("popeyes", "CA", "Popeyes", ["popeyes"]),
    ("kfc", "CA", "KFC", ["kfc"]),
    ("freshii", "CA", "Freshii", ["freshii"]),

    # ═══ UAE / MIDDLE EAST ═══
    ("mcdonalds", "AE", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("kfc", "AE", "KFC", ["kfc"]),
    ("shawarma_press", "AE", "Shawarma Press", ["shawarma press"]),
    ("al_baik", "AE", "Al Baik", ["al baik"]),
    ("hardees", "AE", "Hardee's", ["hardee's", "hardees"]),
    ("subway", "AE", "Subway", ["subway"]),
    ("papa_johns", "AE", "Papa John's", ["papa john's", "papa johns"]),
    ("shake_shack", "AE", "Shake Shack", ["shake shack"]),
    ("texas_chicken", "AE", "Texas Chicken", ["texas chicken"]),

    # ═══ JAPAN ═══
    ("mcdonalds", "JP", "McDonald's", ["mcdonalds", "mcdonald's", "マクドナルド"]),
    ("yoshinoya", "JP", "Yoshinoya", ["yoshinoya", "吉野家"]),
    ("sukiya", "JP", "Sukiya", ["sukiya", "すき家"]),
    ("matsuya", "JP", "Matsuya", ["matsuya", "松屋"]),
    ("mos_burger", "JP", "MOS Burger", ["mos burger"]),
    ("coco_ichibanya", "JP", "CoCo Ichibanya", ["coco ichibanya", "cocoichi"]),
    ("subway", "JP", "Subway", ["subway"]),
    ("starbucks", "JP", "Starbucks", ["starbucks"]),
    ("freshness_burger", "JP", "Freshness Burger", ["freshness burger"]),

    # ═══ SOUTH KOREA ═══
    ("mcdonalds", "KR", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("lotteria", "KR", "Lotteria", ["lotteria", "롯데리아"]),
    ("bbq_chicken", "KR", "BBQ Chicken", ["bbq chicken"]),
    ("kfc", "KR", "KFC", ["kfc"]),
    ("subway", "KR", "Subway", ["subway"]),
    ("kyochon", "KR", "Kyochon", ["kyochon", "교촌"]),

    # ═══ SOUTHEAST ASIA ═══
    ("jollibee", "PH", "Jollibee", ["jollibee"]),
    ("mcdonalds", "PH", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("chowking", "PH", "Chowking", ["chowking"]),
    ("greenwich", "PH", "Greenwich", ["greenwich"]),
    ("mcdonalds", "SG", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("ya_kun", "SG", "Ya Kun Kaya Toast", ["ya kun", "ya kun kaya toast"]),
    ("subway", "SG", "Subway", ["subway"]),
    ("stuff_d", "SG", "Stuff'd", ["stuff'd", "stuffd"]),

    # ═══ EUROPE ═══
    ("mcdonalds", "DE", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("burger_king", "DE", "Burger King", ["burger king"]),
    ("nordsee", "DE", "Nordsee", ["nordsee"]),
    ("vapiano", "DE", "Vapiano", ["vapiano"]),
    ("subway", "DE", "Subway", ["subway"]),
    ("mcdonalds", "FR", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("paul", "FR", "Paul", ["paul"]),
    ("quick", "FR", "Quick", ["quick"]),
    ("flunch", "FR", "Flunch", ["flunch"]),

    # ═══ LATIN AMERICA ═══
    ("mcdonalds", "BR", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("bobs", "BR", "Bob's", ["bob's", "bobs"]),
    ("habib_s", "BR", "Habib's", ["habib's", "habibs"]),
    ("giraffas", "BR", "Giraffas", ["giraffas"]),
    ("subway", "BR", "Subway", ["subway"]),
    ("mcdonalds", "MX", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("subway", "MX", "Subway", ["subway"]),
    ("el_pollo_loco", "MX", "El Pollo Loco", ["el pollo loco"]),

    # ═══ AFRICA ═══
    ("nandos", "ZA", "Nando's", ["nandos", "nando's"]),
    ("steers", "ZA", "Steers", ["steers"]),
    ("debonairs", "ZA", "Debonairs Pizza", ["debonairs"]),
    ("kfc", "ZA", "KFC", ["kfc"]),
    ("mcdonalds", "ZA", "McDonald's", ["mcdonalds", "mcdonald's"]),
    ("chicken_licken", "ZA", "Chicken Licken", ["chicken licken"]),
]


# ── CLAUDE API MENU GENERATOR ──────────────────────────────────────────

PROMPT_TEMPLATE = """You are a nutrition data specialist. Generate exactly {count} real menu items from {chain_name} in {country_name}.

Rules:
- Use ONLY items that actually exist on this chain's menu in {country_name}
- Prioritize higher-protein, lower-calorie options (healthier picks)
- Include a mix: salads/bowls, sandwiches/wraps, grilled items, sides
- Include at least 1 vegetarian option if available
- Use approximate but realistic nutrition data from published sources
- Item names must be the EXACT names used on the menu (not generic descriptions)

Return ONLY a JSON array, no other text:
[
  {{
    "item_name": "exact menu item name",
    "category": "entree|side|drink|snack|salad|bowl|wrap|sandwich",
    "estimated_calories": integer,
    "estimated_protein_g": integer,
    "estimated_carbs_g": integer,
    "estimated_fat_g": integer,
    "confidence": 0.82,
    "vegetarian_possible": boolean,
    "vegan_possible": boolean
  }}
]"""

COUNTRY_NAMES = {
    "AU": "Australia", "US": "United States", "IN": "India", "GB": "United Kingdom",
    "CA": "Canada", "AE": "UAE", "JP": "Japan", "KR": "South Korea",
    "PH": "Philippines", "SG": "Singapore", "DE": "Germany", "FR": "France",
    "BR": "Brazil", "MX": "Mexico", "ZA": "South Africa",
}


def generate_menu_items_with_ai(chain_name: str, market: str, count: int = 7) -> list:
    """Call Claude API to generate real menu items for a chain."""
    import anthropic
    client = anthropic.Anthropic()

    country = COUNTRY_NAMES.get(market, market)
    prompt = PROMPT_TEMPLATE.format(chain_name=chain_name, country_name=country, count=count)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extract JSON array from response
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            items = json.loads(match.group())
            # Validate each item
            valid = []
            for item in items:
                if not isinstance(item, dict) or not item.get("item_name"):
                    continue
                valid.append({
                    "item_name": str(item["item_name"]).strip(),
                    "category": str(item.get("category", "entree")).strip(),
                    "estimated_calories": int(item.get("estimated_calories", 500)),
                    "estimated_protein_g": int(item.get("estimated_protein_g", 25)),
                    "estimated_carbs_g": int(item.get("estimated_carbs_g", 40)),
                    "estimated_fat_g": int(item.get("estimated_fat_g", 18)),
                    "confidence": min(0.90, max(0.70, float(item.get("confidence", 0.82)))),
                    "vegetarian_possible": bool(item.get("vegetarian_possible", False)),
                    "vegan_possible": bool(item.get("vegan_possible", False)),
                })
            return valid[:count]
    except Exception as e:
        print(f"    AI error for {chain_name} ({market}): {e}")
    return []


def write_seed_file(chain_key, market, brand_name, aliases, items):
    """Write seed JSON file."""
    filename = f"{chain_key}_{market.lower()}.json"
    filepath = DATA_DIR / filename
    seed = {
        "brand_name": brand_name,
        "source_type": "ai_generated_seed",
        "source_url": "",
        "store_name_variants": aliases,
        "items": items,
    }
    filepath.write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    return filepath


def update_chain_registry(chain_key, aliases):
    """Add chain_key to CHAIN_KEYS in chain_menu_registry.py if not already present."""
    content = REGISTRY_FILE.read_text(encoding="utf-8")
    # Check if already registered
    if f'"{chain_key}"' in content and "CHAIN_KEYS" in content:
        return False
    # Find the closing brace of CHAIN_KEYS dict and insert before it
    pattern = r'(CHAIN_KEYS:\s*Dict\[str,\s*List\[str\]\]\s*=\s*\{[\s\S]*?)(^\})'
    alias_str = json.dumps(aliases)
    insertion = f'    "{chain_key}": {alias_str},\n'
    new_content = re.sub(
        pattern,
        lambda m: m.group(1) + insertion + m.group(2),
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if new_content != content:
        REGISTRY_FILE.write_text(new_content, encoding="utf-8")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="AI-powered chain menu seeder")
    parser.add_argument("--chains", help="Comma-separated chain:market pairs (e.g. five_guys:US,greggs:GB)")
    parser.add_argument("--market", help="Only process chains for this market (e.g. US)")
    parser.add_argument("--no-sync", action="store_true", help="Skip Supabase sync")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip chains with existing seed files")
    parser.add_argument("--force", action="store_true", help="Regenerate even if seed file exists")
    parser.add_argument("--items", type=int, default=7, help="Items per chain (default 7)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Determine which chains to process
    if args.chains:
        pairs = []
        for pair in args.chains.split(","):
            parts = pair.strip().split(":")
            if len(parts) == 2:
                ck, mk = parts[0].strip(), parts[1].strip().upper()
                # Find display name from EXPANDED_CHAINS or use chain_key
                entry = next((e for e in EXPANDED_CHAINS if e[0] == ck and e[1] == mk), None)
                if entry:
                    pairs.append(entry)
                else:
                    pairs.append((ck, mk, ck.replace("_", " ").title(), [ck]))
        chains = pairs
    else:
        chains = EXPANDED_CHAINS

    if args.market:
        chains = [c for c in chains if c[1] == args.market.upper()]

    print(f"{'Chain':<30} {'Market':<6} {'Items':<6} {'Source':<12} {'Registry':<10} {'Supabase':<12}")
    print("─" * 86)

    total = 0
    generated = 0
    skipped = 0
    errors = []
    started = time.time()

    for chain_key, market, display_name, aliases in chains:
        total += 1
        filename = f"{chain_key}_{market.lower()}.json"
        filepath = DATA_DIR / filename

        # Skip if seed exists and not forced
        if filepath.exists() and not args.force:
            skipped += 1
            print(f"{display_name:<30} {market:<6} {'--':<6} {'exists':<12} {'--':<10} {'skipped'}")
            continue

        # Generate with AI
        items = generate_menu_items_with_ai(display_name, market, count=args.items)
        if not items:
            errors.append((chain_key, market, "AI returned no items"))
            print(f"{display_name:<30} {market:<6} {'0':<6} {'FAILED':<12} {'--':<10} {'--'}")
            continue

        write_seed_file(chain_key, market, display_name, aliases, items)
        source = "AI"

        # Update registry
        reg_status = "added" if update_chain_registry(chain_key, aliases) else "exists"

        # Sync to Supabase
        supa_status = "skipped"
        if not args.no_sync:
            try:
                from chain_menu_supabase_sync import sync_chain_menu_to_supabase
                result = sync_chain_menu_to_supabase(chain_key, market)
                supa_status = f"✓ {result.get('item_count', 0)}" if result.get("ok") else f"✗ {result.get('error', '?')[:15]}"
            except Exception as e:
                supa_status = f"✗ {str(e)[:15]}"

        generated += 1
        print(f"{display_name:<30} {market:<6} {len(items):<6} {source:<12} {reg_status:<10} {supa_status}")

        # Small delay to respect API rate limits
        time.sleep(0.3)

    elapsed = time.time() - started
    print("─" * 86)
    print(f"Done in {elapsed:.1f}s: {total} chains, {generated} generated, {skipped} skipped, {len(errors)} errors")
    if errors:
        print(f"\nErrors:")
        for ck, m, e in errors:
            print(f"  {ck}::{m}: {e}")


if __name__ == "__main__":
    main()
