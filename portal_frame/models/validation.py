"""Geometry validation helpers — returns lists of warning strings (never raises)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from portal_frame.models.geometry import PortalFrameGeometry

_MIN_PITCH = 3.0   # degrees — below this, water ponding is a risk
_MAX_PITCH = 30.0  # degrees — above this, pitch is unusually steep


def validate_roof_pitch(pitch_deg: float) -> list[str]:
    """Return a list of warning strings for the given roof pitch (degrees).

    Returns an empty list when the pitch is within the normal range
    [3.0, 30.0] degrees inclusive.

    Args:
        pitch_deg: Roof pitch in degrees.

    Returns:
        List of warning strings (may be empty).
    """
    warnings: list[str] = []
    if pitch_deg < _MIN_PITCH:
        warnings.append(
            f"Pitch {pitch_deg:.2f} deg is below {_MIN_PITCH} deg — "
            "water ponding risk on low-slope roof."
        )
    elif pitch_deg > _MAX_PITCH:
        warnings.append(
            f"Pitch {pitch_deg:.2f} deg exceeds {_MAX_PITCH} deg — "
            "unusually steep pitch, verify structural and cladding suitability."
        )
    return warnings


def validate_geometry_pitch(geom: "PortalFrameGeometry") -> list[str]:
    """Return pitch warnings for a PortalFrameGeometry instance.

    For mono roofs only the single rafter pitch is checked.
    For gable roofs both the left and right rafter pitches are checked,
    with warnings prefixed by "Left rafter: " or "Right rafter: ".

    Args:
        geom: A PortalFrameGeometry dataclass instance.

    Returns:
        List of warning strings (may be empty).
    """
    warnings: list[str] = []
    if geom.roof_type == "mono":
        warnings.extend(validate_roof_pitch(geom.roof_pitch))
    else:
        for side, pitch in (("Left rafter", geom.left_pitch), ("Right rafter", geom.right_pitch)):
            for w in validate_roof_pitch(pitch):
                warnings.append(f"{side}: {w}")
    return warnings
