#!/usr/bin/env python3
"""Sync: Migration-SQL aus Remote supabase_migrations.schema_migrations exportieren.

Liest per `supabase db query --linked` und schreibt Dateien unter supabase/migrations/
im Format <14-digit-version>_<name>.sql.

Warum das noetig ist: Migrationen die nur ueber das Dashboard oder db query
angewendet wurden, haben keinen lokalen Datei-Eintrag. Das fuehrt zu
"Remote migration versions not found" Fehlern bei db push.

Aufruf: python3 supabase/scripts/sync_migrations_from_remote.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "supabase" / "migrations"

SQL = "SELECT version, name, statements FROM supabase_migrations.schema_migrations ORDER BY version;"


def run_query() -> str:
    r = subprocess.run(
        ["supabase", "db", "query", "--linked", "--yes", "-o", "json", SQL],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stderr or r.stdout, file=sys.stderr)
        sys.exit(r.returncode)
    return r.stdout


def parse_json(stdout: str) -> dict:
    m = re.search(r"\{[\s\S]*\}\s*$", stdout.strip())
    if not m:
        raise SystemExit("Kein JSON in supabase db query Ausgabe gefunden")
    return json.loads(m.group(0))


def pad_version(version: str) -> str:
    """Stelle sicher dass die Version 14 Stellen hat (YYYYMMDDHHMMSS).
    Kuerzere Versionen (z.B. '20260423') werden mit Nullen aufgefuellt.
    """
    digits = re.sub(r"\D", "", version)
    return digits.ljust(14, "0")[:14]


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)


def existing_files_by_version(migrations_dir: Path) -> dict[str, Path]:
    """Gibt {version: path} fuer alle SQL-Dateien in migrations/ zurueck."""
    result: dict[str, Path] = {}
    for p in migrations_dir.glob("*.sql"):
        m = re.match(r"^(\d+)", p.name)
        if m:
            result[m.group(1)] = p
    return result


def main() -> None:
    data = parse_json(run_query())
    rows = data.get("rows") or []
    MIGRATIONS.mkdir(parents=True, exist_ok=True)

    existing = existing_files_by_version(MIGRATIONS)
    written = 0
    renamed = 0

    for row in rows:
        version_raw = str(row["version"])
        version = pad_version(version_raw)
        name = safe_name(str(row["name"]))
        stmts = row.get("statements") or []
        body = "\n\n".join(stmts).strip() + "\n"
        desired_filename = f"{version}_{name}.sql"
        desired_path = MIGRATIONS / desired_filename

        if desired_path.exists():
            continue  # bereits aktuell

        # Gibt es eine Datei mit der RAW-Version (kurz, z.B. 20260423)?
        old_path = existing.get(version_raw)
        if old_path and old_path != desired_path:
            old_path.rename(desired_path)
            print(f"renamed {old_path.name} → {desired_filename}")
            renamed += 1
            continue

        # Gibt es schon eine Datei mit padded version aber anderem Namen?
        old_padded = existing.get(version)
        if old_padded and old_padded != desired_path:
            continue  # Inhalt koennte abweichen, nicht ueberschreiben

        # Neu schreiben
        header = (
            f"-- Exportiert aus Remote schema_migrations"
            f" (version={version_raw}, name={row['name']})\n"
            f"-- Generator: supabase/scripts/sync_migrations_from_remote.py\n\n"
        )
        desired_path.write_text(header + body, encoding="utf-8")
        print(f"wrote   {desired_filename}")
        written += 1

    print(f"\nFertig: {written} neue, {renamed} umbenannte Dateien ({len(rows)} Remote-Migrationen).")


if __name__ == "__main__":
    main()
