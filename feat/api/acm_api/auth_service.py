# -*- coding: utf-8 -*-
"""Web account password hashing and validation helpers."""
import hashlib
import hmac
import ipaddress
import re
import secrets


PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), PASSWORD_ITERATIONS
    ).hex()
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False
    try:
        scheme, rounds, salt, expected = encoded.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(rounds)
        if not 100_000 <= iterations <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), iterations
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, UnicodeError):
        return False


def generate_temporary_password(used_passwords=None) -> str:
    """Generate a six-digit code, preserving leading zeroes and optional batch uniqueness."""
    used_passwords = used_passwords if used_passwords is not None else set()
    for _ in range(10_000):
        candidate = f"{secrets.randbelow(1_000_000):06d}"
        if candidate not in used_passwords:
            used_passwords.add(candidate)
            return candidate
    raise RuntimeError("无法生成不重复的临时密码，请重试。")


def temporary_password_expiry(now, ttl_hours=72) -> int:
    try:
        ttl_hours = int(ttl_hours)
    except (TypeError, ValueError):
        ttl_hours = 72
    if not 1 <= ttl_hours <= 720:
        ttl_hours = 72
    return int(now) + ttl_hours * 3600


def resolve_client_ip(remote_addr, forwarded_for="", trusted_proxies=None) -> str:
    """Trust forwarded addresses only when the direct peer is a configured proxy."""
    trusted_proxies = list(trusted_proxies or ()) + ["127.0.0.0/8", "::1/128"]

    def parse_address(value):
        value = str(value or "").strip()
        if value.startswith("[") and "]" in value:
            value = value[1:value.index("]")]
        if "%" in value:
            value = value.split("%", 1)[0]
        return ipaddress.ip_address(value)

    try:
        peer = parse_address(remote_addr)
    except ValueError:
        return "unknown"

    networks = []
    for value in trusted_proxies:
        try:
            networks.append(ipaddress.ip_network(str(value).strip(), strict=False))
        except ValueError:
            continue

    def is_trusted(address):
        return any(address.version == network.version and address in network for network in networks)

    if not is_trusted(peer):
        return str(peer)

    forwarded = str(forwarded_for or "").strip()
    if not forwarded:
        return str(peer)
    try:
        chain = [parse_address(item) for item in forwarded.split(",")]
    except ValueError:
        return str(peer)

    current = peer
    for hop in reversed(chain):
        if not is_trusted(current):
            break
        current = hop
    return str(current)


def validate_password(password: str) -> str | None:
    if not isinstance(password, str):
        return "密码格式无效。"
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        return f"密码长度须为 {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} 个字符。"
    if any(char.isspace() for char in password):
        return "密码不能包含空白字符。"
    classes = sum((
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"[0-9]", password)),
        bool(re.search(r"[^A-Za-z0-9]", password)),
    ))
    if classes < 3:
        return "密码需至少包含小写字母、大写字母、数字、符号中的三类。"
    return None
