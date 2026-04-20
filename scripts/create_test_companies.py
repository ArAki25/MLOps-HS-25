#!/usr/bin/env python3
"""
Seed-Skript fuer Testdurchlaeufe.

Legt 5 realistische Test-Firmen an (Supabase Auth + ui.user_profiles) und
gibt die Login-Credentials als Tabelle + JSON aus. Idempotent: bereits
existierende Test-User werden uebersprungen, ihr Profil wird ggf. aktualisiert.

Nutzung:
    export SUPABASE_URL=...
    export SUPABASE_ANON_KEY=...                # fuer Registrierung
    export SUPABASE_SERVICE_ROLE_KEY=...        # fuer Profil-Upsert
    python scripts/create_test_companies.py

Die 5 Firmen haben bewusst verschiedene (Kanton, project_subtype)-Profile,
damit wir im Test sehen, ob die Empfehlungen pro Firma unterschiedlich
aussehen und sich durch Likes/Dislikes weiter spezialisieren.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# simap_ui in den Python-Pfad legen, damit wir supabase_client wiederverwenden
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "simap_ui"))

from supabase import create_client  # type: ignore

# Nach dem sys.path-Hack: unseren Client laden
import supabase_client  # noqa: E402


TEST_COMPANIES = [
    {
        "email": "test.bau.zh@recommender.dev",
        "password": "TestBauZH!2026",
        "company_name": "Muster Bau AG Zuerich",
        "employee_count": 45,
        "headquarters": "Zuerich",
        "canton": "ZH",
        "project_subtype": "construction",
        "award_amount_min": 100000,
        "award_amount_max": 5000000,
    },
    {
        "email": "test.bau.be@recommender.dev",
        "password": "TestBauBE!2026",
        "company_name": "Alpen Hochbau Bern AG",
        "employee_count": 30,
        "headquarters": "Bern",
        "canton": "BE",
        "project_subtype": "construction",
        "award_amount_min": 50000,
        "award_amount_max": 2000000,
    },
    {
        "email": "test.service.zh@recommender.dev",
        "password": "TestServZH!2026",
        "company_name": "City Services ZH GmbH",
        "employee_count": 12,
        "headquarters": "Zuerich",
        "canton": "ZH",
        "project_subtype": "service",
        "award_amount_min": 20000,
        "award_amount_max": 800000,
    },
    {
        "email": "test.supply.zh@recommender.dev",
        "password": "TestSuppZH!2026",
        "company_name": "Tech Supply Zuerich AG",
        "employee_count": 80,
        "headquarters": "Zuerich",
        "canton": "ZH",
        "project_subtype": "supply",
        "award_amount_min": 10000,
        "award_amount_max": 1500000,
    },
    {
        "email": "test.bau.gr@recommender.dev",
        "password": "TestBauGR!2026",
        "company_name": "Graubuenden Holzbau AG",
        "employee_count": 22,
        "headquarters": "Chur",
        "canton": "GR",
        "project_subtype": "construction",
        "award_amount_min": 80000,
        "award_amount_max": 3000000,
    },
]


def _env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"[FEHLER] ENV {name} nicht gesetzt.")
        sys.exit(1)
    return v


def main() -> None:
    url = _env("SUPABASE_URL")
    anon = _env("SUPABASE_ANON_KEY")
    service = _env("SUPABASE_SERVICE_ROLE_KEY")

    # Service-Role-Client fuer Upserts in ui.user_profiles + ui.users
    admin = create_client(url, service)

    results = []
    for c in TEST_COMPANIES:
        email = c["email"]
        print(f"\n=== {c['company_name']} ({email}) ===")

        # 1) Register (idempotent): ignoriere "already registered"
        reg = supabase_client.register_user(email, c["password"], c["company_name"])
        if reg.get("success"):
            user_id = reg["user"]["id"]
            status = "created"
        else:
            # User existiert schon -> via Login die user_id holen
            login = supabase_client.login_user(email, c["password"])
            if not login.get("success"):
                print(f"  [SKIP] Register & Login fehlgeschlagen: {reg.get('error')} / {login.get('error')}")
                continue
            user_id = login["user"]["id"]
            status = "exists"

        # 2) Profil upserten (service-role, bypasst RLS)
        profile = {
            "user_id": user_id,
            "company_name": c["company_name"],
            "employee_count": c["employee_count"],
            "headquarters": c["headquarters"],
            "canton": c["canton"],
            "project_subtype": c["project_subtype"],
            "award_amount_min": c["award_amount_min"],
            "award_amount_max": c["award_amount_max"],
            "onboarding_completed": False,  # damit wir den Onboarding-Flow testen
        }
        try:
            admin.schema("ui").table("user_profiles").upsert(
                profile, on_conflict="user_id"
            ).execute()
            admin.schema("ui").table("users").update(
                {"company_name": c["company_name"]}
            ).eq("id", user_id).execute()
            print(f"  [OK] Profil upsert: canton={c['canton']} subtype={c['project_subtype']}")
        except Exception as e:
            print(f"  [WARN] Profil-Upsert Fehler: {e}")

        results.append({
            "status": status,
            "user_id": user_id,
            "email": email,
            "password": c["password"],
            "company_name": c["company_name"],
            "canton": c["canton"],
            "project_subtype": c["project_subtype"],
        })

    print("\n" + "=" * 60)
    print("TEST-ZUGÄNGE (Copy & Paste):")
    print("=" * 60)
    for r in results:
        print(f"  {r['company_name']:<35}  {r['email']:<40}  {r['password']}")
    print("=" * 60)

    out = ROOT / "scripts" / "test_companies.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nGespeichert nach: {out}")
    print(f"{len(results)} / {len(TEST_COMPANIES)} Firmen bereit.")


if __name__ == "__main__":
    main()
