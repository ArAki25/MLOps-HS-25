#!/usr/bin/env python3
"""
CLI-Wrapper fuer dieselbe Seed-Logik wie im localhost-Dashboard
(/admin/test-runs -> Button „Jetzt 5 Test-Firmen anlegen“).

Siehe: supabase_client.seed_test_companies, TEST_COMPANY_SEEDS
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "simap_ui"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from supabase_client import init_supabase, seed_test_companies  # noqa: E402


def main() -> None:
    init_supabase()
    out_path = ROOT / "scripts" / "test_companies.json"
    result = seed_test_companies(write_json_path=str(out_path))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("success"):
        sys.exit(1)
    print(f"\nJSON: {out_path}")


if __name__ == "__main__":
    main()
