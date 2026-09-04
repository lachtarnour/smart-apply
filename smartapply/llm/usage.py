"""Token pricing and cost estimation.

Prices are in USD per 1M tokens. Update as OpenAI changes them. Falls back
to a safe estimate when a model is unknown.
"""

from __future__ import annotations

# (input $/M, output $/M)
OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-sol": (4.00, 20.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "o4-mini": (1.10, 4.40),
    "text-embedding-3-small": (0.02, 0.00),
    "text-embedding-3-large": (0.13, 0.00),
}

# Cached input $/M. Models omitted here fall back to their normal input rate,
# which avoids claiming a discount that may not exist.
OPENAI_CACHED_INPUT_PRICING: dict[str, float] = {
    "gpt-4o-mini": 0.075,
    "gpt-4o": 1.25,
    "gpt-4o-2024-08-06": 1.25,
    "gpt-4.1": 0.50,
    "gpt-4.1-mini": 0.10,
    "o4-mini": 0.275,
    "gpt-5.4-mini": 0.075,
    "gpt-5.4-nano": 0.02,
    "gpt-5.4": 0.25,
    "gpt-5.6-luna": 0.02,
    "gpt-5.6-terra": 0.20,
    "gpt-5.6-sol": 0.40,
}

OPENAI_CACHE_WRITE_MULTIPLIER: dict[str, float] = {
    "gpt-5.6-luna": 1.25,
    "gpt-5.6-terra": 1.25,
    "gpt-5.6-sol": 1.25,
}

FALLBACK_PRICING = (1.00, 4.00)


def _model_rate_key(model: str) -> str | None:
    """Resolve aliases and dated snapshots to the longest known model name."""
    if model in OPENAI_PRICING:
        return model
    for candidate in sorted(OPENAI_PRICING, key=len, reverse=True):
        if model.startswith(f"{candidate}-"):
            return candidate
    return None


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cached_prompt_tokens: int = 0,
    cache_write_prompt_tokens: int = 0,
) -> float:
    rate_key = _model_rate_key(model)
    in_price, out_price = OPENAI_PRICING[rate_key] if rate_key is not None else FALLBACK_PRICING
    cached_tokens = min(max(cached_prompt_tokens, 0), max(prompt_tokens, 0))
    cache_write_tokens = min(
        max(cache_write_prompt_tokens, 0),
        max(prompt_tokens, 0) - cached_tokens,
    )
    uncached_tokens = max(prompt_tokens, 0) - cached_tokens - cache_write_tokens
    cached_price = (
        OPENAI_CACHED_INPUT_PRICING.get(rate_key, in_price) if rate_key is not None else in_price
    )
    cache_write_price = in_price * (
        OPENAI_CACHE_WRITE_MULTIPLIER.get(rate_key, 1.0) if rate_key is not None else 1.0
    )
    return (
        uncached_tokens * in_price
        + cached_tokens * cached_price
        + cache_write_tokens * cache_write_price
        + max(completion_tokens, 0) * out_price
    ) / 1_000_000.0
