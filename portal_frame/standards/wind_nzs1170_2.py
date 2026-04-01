"""NZS 1170.2:2021 Wind Pressure Tables & Calculations.

All wind pressure calculations for portal frame loading.
Pure functions — no I/O, no formatting, no GUI dependencies.
"""

import math
from dataclasses import dataclass

from portal_frame.models.loads import RafterZoneLoad, WindCase
from portal_frame.standards.utils import lerp


# ──────────────────────────────────────────────────────────────────────
# Wind coefficient lookup functions
# ──────────────────────────────────────────────────────────────────────

def leeward_cpe_lookup(d_over_b, alpha=0.0):
    """Table 5.2(B) -- leeward wall Cp,e for gable roofs.

    Args:
        d_over_b: along-wind depth / across-wind breadth ratio
        alpha: roof pitch in degrees
    """
    if alpha < 10:
        if d_over_b <= 1:
            return -0.5
        elif d_over_b <= 2:
            return lerp(d_over_b, 1, 2, -0.5, -0.3)
        elif d_over_b <= 4:
            return lerp(d_over_b, 2, 4, -0.3, -0.2)
        else:
            return -0.2
    elif alpha <= 15:
        return -0.3
    elif alpha <= 20:
        return lerp(alpha, 15, 20, -0.3, -0.4)
    elif alpha < 25:
        return lerp(alpha, 20, 25, -0.4, -0.5)
    else:
        if d_over_b <= 0.1:
            return -0.75
        elif d_over_b <= 0.3:
            return lerp(d_over_b, 0.1, 0.3, -0.75, -0.5)
        else:
            return -0.5


def cfig(cp_e, cp_i, kc_e, kc_i):
    """NZS 1170.2:2021 net aerodynamic shape factor.

    Cfig = Cp,e * Kc,e - Cp,i * Kc,i

    Kc,e is the combined Ka * Kc,e product (floored at 0.8 per Cl 5.4.3).
    Kc,i = 1.0 when |Cp,i| < 0.4 (internal not an effective surface).
    """
    return cp_e * kc_e - cp_i * kc_i


# ──────────────────────────────────────────────────────────────────────
# Table 5.3(A) -- Roof Cp,e zones
# ──────────────────────────────────────────────────────────────────────

# Format: (start_h_mult, end_h_mult, cpe_uplift, cpe_downward)
# end_h_mult = None means extends to end of building
_TABLE_53A_HD_LOW = [  # h/d <= 0.5
    (0.0, 0.5,  -0.9, -0.4),
    (0.5, 1.0,  -0.9, -0.4),
    (1.0, 2.0,  -0.5,  0.0),
    (2.0, 3.0,  -0.3,  0.1),
    (3.0, None, -0.2,  0.2),
]
_TABLE_53A_HD_HIGH = [  # h/d >= 1.0
    (0.0, 0.5,  -1.3, -0.6),
    (0.5, 1.0,  -0.7, -0.3),
    (1.0, 2.0,  -0.7, -0.3),
]

# Legacy table for backward compatibility with GUI imports
TABLE_5_3A_ZONES = [
    (0, 1,   -0.9, -0.4),
    (1, 2,   -0.5,  0.0),
    (2, 3,   -0.3,  0.1),
    (3, None, -0.2,  0.2),
]


def roof_cpe_zones(h_over_d):
    """Table 5.3(A) roof Cp,e zones, interpolated by h/d ratio.

    Returns list of (start_h_mult, end_h_mult, cpe_uplift, cpe_downward).
    Interpolates between h/d=0.5 and h/d=1.0 columns (same-sign only).
    """
    if h_over_d <= 0.5:
        return list(_TABLE_53A_HD_LOW)
    elif h_over_d >= 1.0:
        return list(_TABLE_53A_HD_HIGH)
    else:
        t = (h_over_d - 0.5) / 0.5
        result = []
        for low, high in zip(_TABLE_53A_HD_LOW[:3], _TABLE_53A_HD_HIGH):
            s, e = low[0], low[1]
            up_interp = low[2] + (high[2] - low[2]) * t
            if low[3] * high[3] >= 0:
                dn_interp = low[3] + (high[3] - low[3]) * t
            else:
                dn_interp = low[3]
            result.append((s, e, round(up_interp, 3), round(dn_interp, 3)))
        for zone in _TABLE_53A_HD_LOW[3:]:
            result.append(zone)
        return result


# ──────────────────────────────────────────────────────────────────────
# Zone-based rafter load calculations
# ──────────────────────────────────────────────────────────────────────

def calculate_crosswind_zones(
    building_depth: float,
    h: float,
    use_max_suction: bool = True,
) -> list[RafterZoneLoad]:
    """Legacy wrapper -- calculate zone-based rafter loads using h/d <= 0.5 table.

    Kept for backward compatibility. New code should use
    _compute_zone_loads() which supports h/d interpolation.
    """
    zones = []
    for start_mult, end_mult, cp_max, cp_alt in TABLE_5_3A_ZONES:
        start_m = start_mult * h
        if start_m >= building_depth:
            break
        end_m = building_depth if end_mult is None else min(end_mult * h, building_depth)
        start_pct = (start_m / building_depth) * 100.0
        end_pct = (end_m / building_depth) * 100.0
        pressure = cp_max if use_max_suction else cp_alt
        zones.append(RafterZoneLoad(
            start_pct=round(start_pct, 1),
            end_pct=round(end_pct, 1),
            pressure=pressure,
        ))
    return zones


def _compute_zone_loads(span, h, h_over_d, cp_i, kc_e, kc_i, qu, use_uplift):
    """Compute zone-based rafter loads using Table 5.3(A) with Cfig formula.

    Returns list of RafterZoneLoad with net Wu pressures (kPa).
    Zones are measured along the frame span in multiples of h.
    """
    zone_table = roof_cpe_zones(h_over_d)
    zones = []
    for start_mult, end_mult, cpe_up, cpe_dn in zone_table:
        start_m = start_mult * h
        if start_m >= span:
            break
        end_m = span if end_mult is None else min(end_mult * h, span)
        start_pct = (start_m / span) * 100.0
        end_pct = (end_m / span) * 100.0
        cpe = cpe_up if use_uplift else cpe_dn
        wu = round(cfig(cpe, cp_i, kc_e, kc_i) * qu, 4)
        zones.append(RafterZoneLoad(
            start_pct=round(start_pct, 1),
            end_pct=round(end_pct, 1),
            pressure=wu,
        ))
    return zones


def _mirror_zones(zones):
    """Mirror zone list (measure from far end instead of near end)."""
    return [
        RafterZoneLoad(
            start_pct=round(100.0 - z.end_pct, 1),
            end_pct=round(100.0 - z.start_pct, 1),
            pressure=z.pressure,
        ) for z in reversed(zones)
    ]


def _split_zones_to_rafters(full_zones, split_pct=50.0):
    """Split full-span zones into left and right rafter zones.

    full_zones have start/end as % of the FULL span.
    Member 2 (left rafter) covers 0 to split_pct of the span.
    Member 3 (right rafter) covers split_pct to 100% of the span.

    Returns (left_zones, right_zones) remapped to 0-100% of each member.
    """
    left_zones = []
    right_zones = []
    right_span = 100.0 - split_pct

    for z in full_zones:
        # Left rafter: 0 to split_pct -> 0 to 100%
        if z.start_pct < split_pct and z.end_pct > 0:
            l_start = z.start_pct / split_pct * 100.0
            l_end = min(z.end_pct, split_pct) / split_pct * 100.0
            if l_end > l_start + 0.05:
                left_zones.append(RafterZoneLoad(
                    start_pct=round(l_start, 1),
                    end_pct=round(l_end, 1),
                    pressure=z.pressure,
                ))

        # Right rafter: split_pct to 100% -> 0 to 100%
        if z.end_pct > split_pct and z.start_pct < 100.0:
            r_start = (max(z.start_pct, split_pct) - split_pct) / right_span * 100.0
            r_end = (z.end_pct - split_pct) / right_span * 100.0
            if r_end > r_start + 0.05:
                right_zones.append(RafterZoneLoad(
                    start_pct=round(r_start, 1),
                    end_pct=round(r_end, 1),
                    pressure=z.pressure,
                ))

    return left_zones, right_zones


# ──────────────────────────────────────────────────────────────────────
# Wind Coefficient Inputs
# ──────────────────────────────────────────────────────────────────────

@dataclass
class WindCpInputs:
    """Inputs for auto-generating 8 standard wind cases per NZS 1170.2:2021.

    All Cp,e values looked up from standard tables based on geometry.
    User provides: qu, qs, Kc factors, Cp,i envelope values, windward Cp,e.
    """
    # Wind pressures (kPa)
    qu: float = 1.2           # ULS design wind pressure
    qs: float = 0.9           # SLS design wind pressure

    # Combination factors (Table 5.5, Clause 5.4.3)
    kc_e: float = 0.8         # Combined Ka * Kc,e (floored at 0.8)
    kc_i: float = 1.0         # Kc,i (1.0 when |Cp,i| < 0.4)

    # Internal pressure coefficients (Table 5.1(A))
    cpi_uplift: float = 0.2    # Cp,i for max uplift envelope
    cpi_downward: float = -0.3 # Cp,i for max downward envelope

    # Windward wall -- Table 5.2(A)
    windward_wall_cpe: float = 0.7  # For h <= 25m, wind speed at z=h


# ──────────────────────────────────────────────────────────────────────
# Standard 8-case wind generation
# ──────────────────────────────────────────────────────────────────────

def generate_standard_wind_cases(
    span: float,
    eave_height: float,
    roof_pitch: float,
    building_depth: float,
    cp: WindCpInputs,
    split_pct: float = 50.0,
) -> list[WindCase]:
    """Generate 8 standard wind cases per NZS 1170.2:2021.

    Cases:
        W1  Crosswind L-R   max uplift     (theta=0)
        W2  Crosswind R-L   max uplift     (theta=180)
        W3  Crosswind L-R   max downward   (theta=0)
        W4  Crosswind R-L   max downward   (theta=180)
        W5  Transverse       max uplift     (theta=90)
        W6  Transverse       max downward   (theta=90)
        W7  Transverse mir.  max uplift     (theta=270)
        W8  Transverse mir.  max downward   (theta=270)

    All pressures are Wu (ULS). SLS uses qs/qu scaling in combinations.
    """
    qu = cp.qu
    kc_e = cp.kc_e
    kc_i = cp.kc_i

    # Frame geometry
    ridge = eave_height + (span / 2.0) * math.tan(math.radians(roof_pitch))
    h = (eave_height + ridge) / 2.0

    # Crosswind (theta=0/180): wind across ridge, in frame plane
    d_over_b_cross = span / building_depth if building_depth > 0 else 1.0
    h_over_d = h / span if span > 0 else 0.5

    # Leeward Cp,e from Table 5.2(B)
    lw_cpe = leeward_cpe_lookup(d_over_b_cross, roof_pitch)

    # Side wall Cp,e -- Table 5.2(C), worst-case zone (conservative)
    side_wall_cpe = -0.65  # zone 0-1h

    def wu(cp_e, cp_i):
        return round(cfig(cp_e, cp_i, kc_e, kc_i) * qu, 4)

    cases = []

    # ================================================================
    # CROSSWIND CASES (W1-W4): wind across the ridge, in frame plane
    # ================================================================
    for case_num, theta, cpi_val, envelope, desc_env in [
        (1, 0,   cp.cpi_uplift,   "max_uplift",   "max uplift"),
        (2, 180, cp.cpi_uplift,   "max_uplift",   "max uplift"),
        (3, 0,   cp.cpi_downward, "max_downward", "max downward"),
        (4, 180, cp.cpi_downward, "max_downward", "max downward"),
    ]:
        is_LR = (theta == 0)
        dir_label = "L-R" if is_LR else "R-L"
        direction = "crosswind_LR" if is_LR else "crosswind_RL"

        ww_p = wu(cp.windward_wall_cpe, cpi_val)
        lw_p = wu(lw_cpe, cpi_val)

        use_uplift = (envelope == "max_uplift")
        full_zones = _compute_zone_loads(
            span, h, h_over_d, cpi_val, kc_e, kc_i, qu, use_uplift
        )
        left_zones, right_zones = _split_zones_to_rafters(full_zones, split_pct)

        if is_LR:
            left_wall, right_wall = ww_p, lw_p
        else:
            left_wall, right_wall = lw_p, ww_p
            left_zones, right_zones = (
                _mirror_zones(right_zones),
                _mirror_zones(left_zones),
            )

        cases.append(WindCase(
            name=f"W{case_num}",
            description=f"Crosswind {dir_label} - {desc_env}",
            direction=direction, envelope=envelope,
            is_crosswind=True,
            left_wall=left_wall, right_wall=right_wall,
            left_rafter_zones=left_zones,
            right_rafter_zones=right_zones,
        ))

    # ================================================================
    # TRANSVERSE CASES (W5-W8): wind along ridge, into gable end
    # ================================================================
    zone_table = roof_cpe_zones(h_over_d)
    worst_cpe_uplift = zone_table[0][2]
    worst_cpe_downward = zone_table[0][3]

    for case_num, theta, cpi_val, envelope, desc_env, is_mirrored in [
        (5, 90,  cp.cpi_uplift,   "max_uplift",   "max uplift",   False),
        (6, 90,  cp.cpi_downward, "max_downward", "max downward", False),
        (7, 270, cp.cpi_uplift,   "max_uplift",   "max uplift",   True),
        (8, 270, cp.cpi_downward, "max_downward", "max downward", True),
    ]:
        mir_label = " (mirrored)" if is_mirrored else ""
        direction = "transverse_mirrored" if is_mirrored else "transverse"

        sw_p = wu(side_wall_cpe, cpi_val)

        use_uplift = (envelope == "max_uplift")
        roof_cpe = worst_cpe_uplift if use_uplift else worst_cpe_downward
        roof_p = wu(roof_cpe, cpi_val)

        cases.append(WindCase(
            name=f"W{case_num}",
            description=f"Transverse{mir_label} - {desc_env}",
            direction=direction, envelope=envelope,
            is_crosswind=False,
            left_wall=sw_p, right_wall=sw_p,
            left_rafter=roof_p, right_rafter=roof_p,
        ))

    return cases
