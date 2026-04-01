"""Shared utilities for NZ standards calculations."""


def lerp(x, x0, x1, y0, y1):
    """Linear interpolation between two points."""
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
