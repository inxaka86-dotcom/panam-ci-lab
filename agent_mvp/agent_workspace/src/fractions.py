"""Small division helpers."""


def safe_divide(a, b):
    """Return a divided by b, or None when b is zero."""
    if b == 0:
        return None
    return a / b
