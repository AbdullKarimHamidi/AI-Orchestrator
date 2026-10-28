"""Stable, time-ordered, prefixed string identifiers (e.g. ``agt_01J...``)."""
import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32


def _b32(n: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[n & 31])
        n >>= 5
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    ts = int(time.time() * 1000)
    rnd = int.from_bytes(os.urandom(10), "big")
    return f"{prefix}_{_b32(ts, 10)}{_b32(rnd, 16)}"
