"""Cost estimation. Prices change; workspace-level overrides (per provider, per model)
take precedence. Unknown models are costed at 0 and flagged as 'unpriced' so dashboards
never silently invent numbers."""

# USD per 1M tokens (input, output). Kept deliberately small; override per provider.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {}


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  overrides: dict | None = None) -> tuple[float, bool]:
    price = None
    if overrides and model in overrides:
        p = overrides[model]
        price = (float(p["input_per_mtok_usd"]), float(p["output_per_mtok_usd"]))
    elif model in DEFAULT_PRICES:
        price = DEFAULT_PRICES[model]
    if price is None:
        return 0.0, False
    return round(input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1], 8), True
