#!/usr/bin/env python3
"""
One-shot hygiene: strip empty-string / whitespace-only / non-https image_url
fields from every data/chains/*.json seed. Valid https URLs are preserved.

Supabase CHECK constraint `chain_menu_items_image_url_https` rejects empty
strings; the sync layer already coerces, this keeps seeds clean on disk.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"


def main() -> None:
    files_touched = 0
    fields_removed = 0
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"skip {path.name}: {exc}")
            continue
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        changed = False
        for item in items:
            if not isinstance(item, dict) or "image_url" not in item:
                continue
            url = str(item.get("image_url") or "").strip()
            if not url or not url.lower().startswith("https://"):
                item.pop("image_url", None)
                fields_removed += 1
                changed = True
            elif item["image_url"] != url:
                item["image_url"] = url
                changed = True
        if changed:
            files_touched += 1
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
    print(f"cleaned {fields_removed} blank/non-https image_url entries across {files_touched} files")


if __name__ == "__main__":
    main()
