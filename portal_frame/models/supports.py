"""Support condition data model."""

from dataclasses import dataclass


@dataclass
class SupportCondition:
    """Support conditions for portal frame bases.

    left_base / right_base: "pinned" | "fixed" | "partial".
    fixity_percent: 0-100, used only when either side is "partial".
    Interpreted as alpha in k_theta = alpha * 4EI/L (linear fixity-factor convention).
    """
    left_base: str = "pinned"
    right_base: str = "pinned"
    fixity_percent: float = 0.0
    sls_partial_only: bool = True  # when True, ULS falls back to pinned; SLS uses the partial spring
