"""
hash_existing_passwords.py - Einmaliges Backfill: Klartext-Passwörter -> bcrypt

Hasht alle noch im Klartext gespeicherten Passwörter in ui.admins und
ui.pro_users. Idempotent: bereits gehashte Zeilen werden übersprungen.

Lokal ausführen (braucht SUPABASE_SERVICE_ROLE_KEY in .env):
    python scripts/hash_existing_passwords.py [--dry-run]
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'simap_ui'))
from security import hash_password, is_bcrypt_hash  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

TABLES = ('admins', 'pro_users')


def backfill(dry_run: bool = False) -> None:
    load_dotenv()
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        raise RuntimeError('SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY müssen gesetzt sein.')

    client = create_client(url, key)
    for table in TABLES:
        rows = client.schema('ui').table(table).select('id, password').execute().data or []
        migrated = skipped = 0
        for row in rows:
            stored = row.get('password') or ''
            if not stored or is_bcrypt_hash(stored):
                skipped += 1
                continue
            if not dry_run:
                client.schema('ui').table(table) \
                    .update({'password': hash_password(stored)}) \
                    .eq('id', row['id']).execute()
            migrated += 1
        logger.info('ui.%s: %d migriert, %d übersprungen%s',
                    table, migrated, skipped, ' (dry-run)' if dry_run else '')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='Nur zählen, nichts schreiben')
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
