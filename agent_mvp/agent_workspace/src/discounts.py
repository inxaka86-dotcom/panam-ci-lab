"""Calculate a discount on a nonnegative amount."""


def discounted_total(price: float, percent: float) -> float:
    """Return amount after a percentage discount. Percent is in 0..100."""
    return price - percent
