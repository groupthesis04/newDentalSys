from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mysql_store import COLLECTIONS, MySQLStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Dental System JSON data to MySQL")
    parser.add_argument(
        "--source",
        default="database/data/app_data.json",
        help="JSON source file",
    )
    parser.add_argument("--force", action="store_true", help="Replace records already in MySQL")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("The migration source must contain a JSON object.")
    data = {collection: list(payload.get(collection, [])) for collection in COLLECTIONS}

    store = MySQLStore()
    store.initialize()
    if not store.is_empty() and not args.force:
        raise SystemExit("MySQL already contains clinic data. Re-run with --force only if replacement is intended.")
    store.save(data)
    counts = ", ".join(f"{name}={len(data[name])}" for name in COLLECTIONS)
    print(f"Migration complete: {counts}")


if __name__ == "__main__":
    main()
