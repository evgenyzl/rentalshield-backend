"""
Gemini API pricing and cost tracking.

Pricing (as of Sept 2024):
  Gemini 3.5 Flash:
    - Input:  $0.075 per 1M tokens (base64 images included)
    - Output: $0.3   per 1M tokens

  Component Identifier (uses Gemini 2.0 Flash):
    - Same as above

USD to NIS conversion: 1 USD = 3.67 NIS (approximately)
"""

# Gemini 3.5 Flash pricing (in USD per 1M tokens)
GEMINI_INPUT_COST_PER_1M = 0.075    # $0.075 per 1M input tokens
GEMINI_OUTPUT_COST_PER_1M = 0.3     # $0.3 per 1M output tokens

# Conversion rate
USD_TO_NIS = 3.67


def calculate_vision_cost(input_tokens: int, output_tokens: int) -> tuple[float, float]:
    """
    Calculate cost for a single Gemini vision API call.

    Returns:
        (cost_usd, cost_nis)
    """
    input_cost = (input_tokens / 1_000_000) * GEMINI_INPUT_COST_PER_1M
    output_cost = (output_tokens / 1_000_000) * GEMINI_OUTPUT_COST_PER_1M
    cost_usd = input_cost + output_cost
    cost_nis = cost_usd * USD_TO_NIS
    return cost_usd, cost_nis


def calculate_text_cost(input_tokens: int, output_tokens: int) -> tuple[float, float]:
    """
    Calculate cost for a Gemini text-only API call.
    (Uses same pricing as vision)
    """
    return calculate_vision_cost(input_tokens, output_tokens)


def format_cost(usd: float, nis: float) -> str:
    """Format cost for display."""
    return f"${usd:.4f} ({nis:.2f} NIS)"
