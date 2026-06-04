# # app/core/security/password.py
# from passlib.context import CryptContext

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# def hash_password(password: str) -> str:
#     if not password:
#         raise ValueError("Password cannot be empty")
#     return pwd_context.hash(password)


# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     if not plain_password or not hashed_password:
#         return False
#     return pwd_context.verify(plain_password, hashed_password)


# v2
# # app/core/security/password.py

# import hashlib
# from passlib.context import CryptContext

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# def hash_password(password: str) -> str:
#     # Pre-hash with SHA256 → fixed length
#     hashed = hashlib.sha256(password.encode()).hexdigest()
#     return pwd_context.hash(hashed)


# def verify_password(password: str, hashed_password: str) -> bool:
#     hashed = hashlib.sha256(password.encode()).hexdigest()
#     return pwd_context.verify(hashed, hashed_password)


# v3 - add scrypt with bcrypt fallback
# app/utils/password.py

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
