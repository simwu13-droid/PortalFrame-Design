"""Section properties — cold-formed steel and future material types."""

from dataclasses import dataclass


@dataclass
class CFS_Section:
    """Cold-formed steel section properties from SpaceGass library."""
    name: str
    library: str         # Which library file it came from (full filename)
    library_name: str    # Normalized display name (e.g., "FS") — set at parse time
    group: str           # Group code within the library
    Ax: float            # Cross-sectional area (mm2)
    J: float             # Torsion constant (mm4)
    Iy: float            # Second moment — principal y-axis (mm4)
    Iz: float            # Second moment — principal z-axis (mm4)
    Iw: float = 0.0      # Warping constant (mm6)
    Sy: float = 0.0      # Plastic section modulus y (mm3)
    Sz: float = 0.0      # Plastic section modulus z (mm3)

    # Converted to metres for SpaceGass text file output
    @property
    def Ax_m(self) -> float:
        return self.Ax * 1e-6   # mm2 -> m2

    @property
    def J_m(self) -> float:
        return self.J * 1e-12   # mm4 -> m4

    @property
    def Iy_m(self) -> float:
        return self.Iy * 1e-12  # mm4 -> m4

    @property
    def Iz_m(self) -> float:
        return self.Iz * 1e-12  # mm4 -> m4
