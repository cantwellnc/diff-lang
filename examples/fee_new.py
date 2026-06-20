def compute_fee(amount: int) -> int:
    """5% fee, waived for amounts up to 100."""
    if amount <= 100:
        return 0
    return amount // 20
