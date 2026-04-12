#!/usr/bin/env python3
"""
Probe prod /places/healthy at a representative grid of major city coords.
Identifies place names that return chain=None — these are coverage gaps OR
genuine single-location venues.

Output: data/coverage_gaps.json  with de-duped unmatched place names per city.

Run: cd backend && python scripts/find_coverage_gaps.py [--prod URL]
"""
import argparse
import json
import sys
import subprocess
import urllib.parse
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DEFAULT_PROD = "https://kcal-scan-production.up.railway.app"
OUT_PATH = BACKEND / "data" / "coverage_gaps.json"

# Chain-dense coords (urban cores) across flagship markets.
PROBE_COORDS = [
    # India
    ("Mumbai Lower Parel", 18.9951, 72.8254),
    ("Delhi Connaught Place", 28.6315, 77.2167),
    ("Bangalore MG Road", 12.9716, 77.5946),
    ("Bangalore Indiranagar", 12.9784, 77.6408),
    ("Chennai T Nagar", 13.0418, 80.2341),
    ("Hyderabad Banjara Hills", 17.4126, 78.4294),
    ("Kolkata Park Street", 22.5546, 88.3500),
    ("Pune Koregaon Park", 18.5362, 73.8935),
    ("Ahmedabad SG Road", 23.0333, 72.5000),
    ("Gurgaon DLF Phase 3", 28.4900, 77.0900),
    # USA
    ("NYC Times Square", 40.7580, -73.9855),
    ("SF Union Square", 37.7879, -122.4074),
    ("LA Hollywood", 34.0983, -118.3267),
    ("Chicago Loop", 41.8827, -87.6233),
    ("Boston Back Bay", 42.3476, -71.0806),
    ("Austin 6th Street", 30.2672, -97.7402),
    ("Seattle Downtown", 47.6062, -122.3321),
    ("Atlanta Midtown", 33.7831, -84.3832),
    # Australia
    ("Sydney CBD", -33.8688, 151.2093),
    ("Melbourne CBD", -37.8136, 144.9631),
    ("Brisbane CBD", -27.4698, 153.0251),
    ("Perth CBD", -31.9505, 115.8605),
    # Other flagships
    ("London Soho", 51.5138, -0.1352),
    ("London Oxford Circus", 51.5154, -0.1410),
    ("Toronto Yonge Dundas", 43.6564, -79.3806),
    ("Vancouver Downtown", 49.2827, -123.1207),
]

FALLBACK_PREFIXES = (
    "Lighter menu option", "Protein bowl", "Grilled or baked protein",
    "Savory lighter plates", "Needs menu check", "Simpler tandoori",
    "Idli or plain dosa", "Tandoori or grilled kebab", "Egg, yogurt",
    "Lighter thin-crust", "Sashimi or simple", "Lighter bowl or taco",
    "Grilled meat/fish", "Eggs, yogurt", "Grilled/tandoori protein",
    "Single grilled chicken", "Lean protein stir-fry",
)


def fetch(base_url: str, lat: float, lng: float, radius: int = 600) -> list[dict]:
    q = urllib.parse.urlencode({"lat": lat, "lng": lng, "radius": radius})
    url = f"{base_url}/places/healthy?{q}"
    # Use curl — avoids macOS Python SSL cert-chain issues in CLI contexts.
    out = subprocess.run(
        ["curl", "-s", "-m", "25", "-A", "kcal-gap-finder/1", url],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    return data.get("places") or data.get("results") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prod", default=DEFAULT_PROD)
    ap.add_argument("--radius", type=int, default=600)
    args = ap.parse_args()

    print(f"probing {len(PROBE_COORDS)} coords against {args.prod}")
    unmatched_by_city = defaultdict(list)
    covered_by_city = defaultdict(int)
    all_unmatched_names = []

    for city, lat, lng in PROBE_COORDS:
        try:
            places = fetch(args.prod, lat, lng, args.radius)
        except Exception as e:
            print(f"  {city}: ERROR {e}")
            continue
        for p in places:
            name = (p.get("name") or "").strip()
            chain = p.get("covered_chain_key")
            if chain:
                covered_by_city[city] += 1
            else:
                unmatched_by_city[city].append(name)
                all_unmatched_names.append(name)
        print(f"  {city:<28} covered={covered_by_city[city]:>2}  unmatched={len(unmatched_by_city[city])}")

    # Find repeat offenders — names appearing in multiple cities (likely real chains)
    from collections import Counter
    name_counts = Counter(all_unmatched_names)
    repeats = [(n, c) for n, c in name_counts.most_common() if c > 1]

    print(f"\n=== UNMATCHED NAMES APPEARING IN 2+ CITIES (likely chain gaps) ===")
    for name, count in repeats[:30]:
        print(f"  {count}× {name}")

    # Write report
    report = {
        "prod_url": args.prod,
        "coords_probed": len(PROBE_COORDS),
        "unmatched_by_city": dict(unmatched_by_city),
        "covered_count_by_city": dict(covered_by_city),
        "repeat_unmatched": [{"name": n, "occurrences": c} for n, c in repeats],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nreport: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
