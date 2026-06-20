def score(accuracy: int, speed: int) -> int:
    """Bonus added for high-accuracy runs."""
    base = accuracy * 10 + speed * 5
    if accuracy >= 90:
        base = base + 50
    return base
