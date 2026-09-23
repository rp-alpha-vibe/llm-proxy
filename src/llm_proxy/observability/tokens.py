def count_tokens(text: str) -> int:
    """Count input tokens for TPS.

    The competition does not name an LLM tokenizer. TPS uses this whitespace
    definition: one token is one non-empty Unicode whitespace-separated piece.
    `processed_tokens_total` counts these tokens, and TPS is their rate.
    """

    if not text:
        return 0
    return len(text.split())
