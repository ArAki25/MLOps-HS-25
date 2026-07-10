from security import hash_password, is_bcrypt_hash, verify_password


def test_hash_password_roundtrip():
    stored = hash_password('geheim123')
    assert is_bcrypt_hash(stored)
    assert verify_password('geheim123', stored) == (True, False)


def test_verify_password_wrong_password():
    stored = hash_password('geheim123')
    assert verify_password('falsch', stored) == (False, False)


def test_verify_password_legacy_plaintext_needs_rehash():
    assert verify_password('klartext', 'klartext') == (True, True)


def test_verify_password_legacy_plaintext_wrong():
    assert verify_password('falsch', 'klartext') == (False, False)


def test_verify_password_empty_inputs():
    assert verify_password('', 'x') == (False, False)
    assert verify_password('x', '') == (False, False)
    assert verify_password('', '') == (False, False)


def test_is_bcrypt_hash_variants():
    assert is_bcrypt_hash('$2b$12$' + 'a' * 53)
    assert is_bcrypt_hash('$2a$10$abc')
    assert not is_bcrypt_hash('klartext')
    assert not is_bcrypt_hash('')
    assert not is_bcrypt_hash(None)


def test_hashes_are_salted():
    assert hash_password('gleich') != hash_password('gleich')
