"""Token-cost pricing table for configured LLM models.

Prices are in USD per token.  Update this table when models change.

Gemini 3.1 Flash Lite pricing (current as of project development):
  Confirmed experimentally; the "lite" tier is cheaper than standard Flash.
  Using Gemini 2.5 Flash pricing as a conservative upper bound when the
  exact lite price is not available.  The token cost is a rough guide, not
  a billing-accurate figure.
"""

# Model name → (input_usd_per_token, output_usd_per_token)
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # Gemini 3.x Flash Lite — inferred from Flash-Lite tier pricing
    "gemini-3.1-flash-lite": (3.75e-8, 1.50e-7),
    # Gemini 2.5 Flash (standard)
    "gemini-2.5-flash": (7.5e-8, 3.0e-7),
    "gemini-2.5-flash-lite": (3.75e-8, 1.50e-7),
    # Gemini 2.0 / 1.5 Flash
    "gemini-2.0-flash": (7.5e-8, 3.0e-7),
    "gemini-1.5-flash": (7.5e-8, 3.0e-7),
    "gemini-1.5-flash-8b": (3.75e-8, 1.50e-7),
}

_FALLBACK_INPUT = 7.5e-8  # USD / token — generous fallback
_FALLBACK_OUTPUT = 3.0e-7  # USD / token


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for the given token counts."""
    in_price, out_price = _PRICE_TABLE.get(model, (_FALLBACK_INPUT, _FALLBACK_OUTPUT))
    return in_price * input_tokens + out_price * output_tokens
