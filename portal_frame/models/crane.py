"""Gantry crane load data models."""

from dataclasses import dataclass, field


@dataclass
class CraneTransverseCombo:
    """Pre-factored transverse (horizontal) crane load from manufacturer.

    Sign convention: +ve = left-to-right (global +X).
    """
    name: str
    left: float = 0.0    # kN, horizontal at left bracket
    right: float = 0.0   # kN, horizontal at right bracket


@dataclass
class CraneInputs:
    """Gantry crane loading parameters.

    Gc (dead) and Qc (live) are unfactored vertical loads per bracket (kN).
    Transverse combos (Hc) are pre-factored horizontal loads from manufacturer.
    Sign convention: vertical +ve = downward, horizontal +ve = left-to-right.
    """
    rail_height: float = 3.0
    # Unfactored vertical loads per bracket (kN, +ve = downward)
    dead_left: float = 0.0       # Gc at left bracket
    dead_right: float = 0.0      # Gc at right bracket
    live_left: float = 0.0       # Qc at left bracket
    live_right: float = 0.0      # Qc at right bracket
    # Pre-factored transverse loads (flexible rows)
    transverse_uls: list = field(default_factory=list)  # List[CraneTransverseCombo]
    transverse_sls: list = field(default_factory=list)  # List[CraneTransverseCombo]
