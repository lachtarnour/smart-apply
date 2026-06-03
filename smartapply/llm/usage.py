"""Token pricing and cost estimation.

Prices are in USD per 1M tokens. Update as OpenAI changes them. Falls back
to a safe estimate when a model is unknown.
"""

from __future__ import annotations

# (input $/M, output $/M)
OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "o4-mini": (1.10, 4.40),
    "text-embedding-3-small": (0.02, 0.00),
    "text-embedding-3-large": (0.13, 0.00),
}

FALLBACK_PRICING = (1.00, 4.00)


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = OPENAI_PRICING.get(model, FALLBACK_PRICING)
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000.0
