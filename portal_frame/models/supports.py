"""Support condition data model."""

from dataclasses import dataclass


@dataclass
class SupportCondition:
    """Support conditions for portal frame bases."""
    left_base: str = "pinned"   # "pinned" or "fixed"
    right_base: str = "pinned"  # "pinned" or "fixed"
