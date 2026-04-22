import bcrypt

from app.core.security import hash_password, verify_password


def test_hash_password_uses_bcrypt_and_roundtrip():
    password = "StrongPassword!123"

    hashed = hash_password(password)

    assert hashed.startswith("$2")
    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_password_rejects_invalid_password():
    password = "StrongPassword!123"
    wrong_password = "WrongPassword!123"

    hashed = hash_password(password)

    assert verify_password(wrong_password, hashed) is False


def test_verify_password_supports_existing_bcrypt_hashes():
    password = "LegacyPassword!123"
    legacy_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    assert verify_password(password, legacy_hash) is True


def test_verify_password_handles_invalid_hash_gracefully():
    assert verify_password("password", "not-a-valid-bcrypt-hash") is False
