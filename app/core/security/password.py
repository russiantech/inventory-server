# app/utils/password.py
# v3 - add scrypt with bcrypt fallback

from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["scrypt", "bcrypt"],  # Try scrypt first, fallback to bcrypt
    default="scrypt",
    deprecated="auto",
)

def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def needs_rehash(hashed_password: str) -> bool:
    return pwd_context.needs_update(hashed_password)
