"""Deterministic hashing primitives.

- content_hash: identifies a document by its normalized content, so the same
  circular ingested twice de-dupes to one canonical entry.
- chain_hash: builds a tamper-evident, append-only audit chain where each entry
  binds to the previous one: chain_hash = SHA256(prev_chain_hash + payload + ts).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

_WS = re.compile(r"\s+")


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    """Normalize text for stable, whitespace/encoding-insensitive hashing and
    comparison. This is used everywhere the kernel must be reproducible."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")  # non-breaking space
    text = _WS.sub(" ", text)
    return text.strip().lower()


def content_hash(text: str) -> str:
    """Stable hash of a document's textual content (after normalization).

    Two ingests of the same circular produce the same hash -> canonical de-dup.
    """
    return sha256_hex(normalize_text(text))


def canonical_json(payload: Any) -> str:
    """Deterministic JSON serialization (sorted keys, no whitespace drift)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def chain_hash(prev_chain_hash: str, payload: Any, ts: str) -> str:
    """Compute the next link in the hash-chained audit log.

    chain_hash = SHA256(prev_chain_hash + canonical(payload) + ts)
    """
    material = f"{prev_chain_hash}{canonical_json(payload)}{ts}"
    return sha256_hex(material)


GENESIS_HASH = "0" * 64


def verify_chain(entries: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """Re-derive the chain and confirm tamper-evidence.

    Each entry must contain: prev_chain_hash, payload, ts, chain_hash.
    Returns (ok, first_broken_index). ok=True means the chain is intact.
    """
    prev = GENESIS_HASH
    for i, e in enumerate(entries):
        if e.get("prev_chain_hash") != prev:
            return False, i
        expected = chain_hash(prev, e["payload"], e["ts"])
        if e.get("chain_hash") != expected:
            return False, i
        prev = expected
    return True, None
