"""
security.py - Passwort-Hashing (bcrypt) mit Legacy-Klartext-Migration

Bestehende Zeilen in ui.admins / ui.pro_users enthalten teils noch
Klartext-Passwörter. verify_password() akzeptiert beide Formate und
signalisiert über needs_rehash, dass der gespeicherte Wert beim
nächsten erfolgreichen Login durch einen bcrypt-Hash ersetzt werden soll.
"""

import hmac

import bcrypt

_BCRYPT_PREFIXES = ('$2a$', '$2b$', '$2y$')


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def is_bcrypt_hash(stored: str) -> bool:
    """True, wenn der gespeicherte Wert bereits ein bcrypt-Hash ist."""
    return isinstance(stored, str) and stored.startswith(_BCRYPT_PREFIXES)


def verify_password(plain: str, stored: str) -> tuple[bool, bool]:
    """Prüft ein Passwort gegen den gespeicherten Wert.

    Returns:
        (ok, needs_rehash): ok = Passwort korrekt; needs_rehash = der
        gespeicherte Wert ist Legacy-Klartext und soll ersetzt werden.
    """
    if not plain or not stored:
        return False, False
    if is_bcrypt_hash(stored):
        try:
            return bcrypt.checkpw(plain.encode('utf-8'), stored.encode('utf-8')), False
        except ValueError:
            return False, False
    # Legacy: Klartext-Vergleich, timing-sicher
    ok = hmac.compare_digest(plain.encode('utf-8'), stored.encode('utf-8'))
    return ok, ok
