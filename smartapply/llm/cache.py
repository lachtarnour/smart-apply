"""Cache key generation and helpers for LLM calls."""

from __future__ import annotations

import hashlib
import json


def make_cache_key(
    *,
    model: str,
    system: str,
    user: str,
    schema_name: str,
    extra: dict | None = None,
) -> str:
    """Stable SHA-256 key uniquely identifying a (model, prompt, schema) tuple."""
    payload = {
        "model": model,
        "system": system,
        "user": user,
        "schema": schema_name,
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
