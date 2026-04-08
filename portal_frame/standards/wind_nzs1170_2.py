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
# Table 5.3(B) -- Monoslope roof, upwind slope Cp,e (alpha >= 10 deg)
# ──────────────────────────────────────────────────────────────────────

# Format: {h_over_d: {pitch_deg: (cpe_uplift, cpe_downward)}}
_TABLE_53B = {
    0.25: {10: (-0.7, -0.3), 15: (-0.5, 0.0), 20: (-0.3, 0.2), 25: (-0.2, 0.3), 30: (-0.2, 0.4), 35: (0.0, 0.5)},
    0.50: {10: (-0.9, -0.4), 15: (-0.7, -0.3), 20: (-0.4, 0.0), 25: (-0.3, 0.2), 30: (-0.2, 0.3), 35: (-0.2, 0.4)},
    1.00: {10: (-1.3, -0.6), 15: (-1.0, -0.5), 20: (-0.7, -0.3), 25: (-0.5, 0.0), 30: (-0.3, 0.2), 35: (-0.2, 0.3)},
}
_TABLE_53B_PITCHES = [10, 15, 20, 25, 30, 35]
_TABLE_53B_HDS = [0.25, 0.50, 1.00]


def _interp_53b(h_over_d, alpha):
    """Table 5.3(B) lookup with bilinear interpolation.

    Returns (cpe_uplift, cpe_downward) for the upwind slope of a monoslope roof.
    For alpha >= 45 deg, uses Cp,e = 0.8 * sin(alpha).
    """
    if alpha >= 45:
        val = round(0.8 * math.sin(math.radians(alpha)), 3)
        return (val, val)

    # Clamp h/d
    hd = max(0.25, min(1.0, h_over_d))
    alpha = max(10.0, min(35.0, alpha))

    # Find bounding h/d rows
    hds = _TABLE_53B_HDS
    if hd <= hds[0]:
        hd_lo, hd_hi, t_hd = 0, 0, 0.0
    elif hd >= hds[-1]:
        hd_lo, hd_hi, t_hd = len(hds) - 1, len(hds) - 1, 0.0
    else:
        for i in range(len(hds) - 1):
            if hds[i] <= hd <= hds[i + 1]:
                hd_lo, hd_hi = i, i + 1
                t_hd = (hd - hds[i]) / (hds[i + 1] - hds[i])
                break

    # Find bounding pitch columns
    ps = _TABLE_53B_PITCHES
    if alpha <= ps[0]:
        p_lo, p_hi, t_p = 0, 0, 0.0
    elif alpha >= ps[-1]:
        p_lo, p_hi, t_p = len(ps) - 1, len(ps) - 1, 0.0
    else:
        for i in range(len(ps) - 1):
            if ps[i] <= alpha <= ps[i + 1]:
                p_lo, p_hi = i, i + 1
                t_p = (alpha - ps[i]) / (ps[i + 1] - ps[i])
                break

    # Bilinear interpolation for both uplift and downward
    result = []
    for idx in (0, 1):  # 0=uplift, 1=downward
        v00 = _TABLE_53B[hds[hd_lo]][ps[p_lo]][idx]
        v01 = _TABLE_53B[hds[hd_lo]][ps[p_hi]][idx]
        v10 = _TABLE_53B[hds[hd_hi]][ps[p_lo]][idx]
        v11 = _TABLE_53B[hds[hd_hi]][ps[p_hi]][idx]
        v0 = v00 + (v01 - v00) * t_p
        v1 = v10 + (v11 - v10) * t_p
        result.append(round(v0 + (v1 - v0) * t_hd, 3))
    return (result[0], result[1])


# ──────────────────────────────────────────────────────────────────────
# Table 5.3(C) -- Monoslope roof, downwind slope Cp,e (alpha >= 10 deg)
# ──────────────────────────────────────────────────────────────────────

# Format: {h_over_d: {pitch_deg: cpe}}
_TABLE_53C = {
    0.25: {10: -0.3, 15: -0.5, 20: -0.6},
    0.50: {10: -0.5, 15: -0.5, 20: -0.6},
    1.00: {10: -0.7, 15: -0.6, 20: -0.6},
}
_TABLE_53C_PITCHES = [10, 15, 20]
_TABLE_53C_HDS = [0.25, 0.50, 1.00]


def _interp_53c(h_over_d, alpha, b_over_d=None):
    """Table 5.3(C) lookup with bilinear interpolation.

    Returns cpe (single value, always suction) for the downwind slope.
    For alpha >= 25 deg, uses b/d dependent formula.
    """
    if alpha >= 25:
        if b_over_d is None:
            return -0.6
        if b_over_d <= 3:
            return -0.6
        elif b_over_d >= 8:
            return -0.9
        else:
            return round(-0.06 * (7 + b_over_d), 3)

    # Clamp
    hd = max(0.25, min(1.0, h_over_d))
    alpha = max(10.0, min(20.0, alpha))

    hds = _TABLE_53C_HDS
    if hd <= hds[0]:
        hd_lo, hd_hi, t_hd = 0, 0, 0.0
    elif hd >= hds[-1]:
        hd_lo, hd_hi, t_hd = len(hds) - 1, len(hds) - 1, 0.0
    else:
        for i in range(len(hds) - 1):
            if hds[i] <= hd <= hds[i + 1]:
                hd_lo, hd_hi = i, i + 1
                t_hd = (hd - hds[i]) / (hds[i + 1] - hds[i])
                break

    ps = _TABLE_53C_PITCHES
    if alpha <= ps[0]:
        p_lo, p_hi, t_p = 0, 0, 0.0
    elif alpha >= ps[-1]:
        p_lo, p_hi, t_p = len(ps) - 1, len(ps) - 1, 0.0
    else:
        for i in range(len(ps) - 1):
            if ps[i] <= alpha <= ps[i + 1]:
                p_lo, p_hi = i, i + 1
                t_p = (alpha - ps[i]) / (ps[i + 1] - ps[i])
                break

    v00 = _TABLE_53C[hds[hd_lo]][ps[p_lo]]
    v01 = _TABLE_53C[hds[hd_lo]][ps[p_hi]]
    v10 = _TABLE_53C[hds[hd_hi]][ps[p_lo]]
    v11 = _TABLE_53C[hds[hd_hi]][ps[p_hi]]
    v0 = v00 + (v01 - v00) * t_p
    v1 = v10 + (v11 - v10) * t_p
    return round(v0 + (v1 - v0) * t_hd, 3)


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
# Surface coefficient extraction (for GUI surface-based table)
# ──────────────────────────────────────────────────────────────────────

# Side wall Cp,e zones per Table 5.2(C) -- measured from windward edge in multiples of h
SIDE_WALL_CPE_ZONES = [
    (0.0, 1.0, -0.65),
    (1.0, 2.0, -0.5),
    (2.0, 3.0, -0.3),
    (3.0, None, -0.2),
]


def get_surface_coefficients(
    span: float,
    eave_height: float,
    roof_pitch: float,
    building_depth: float,
    windward_wall_cpe: float = 0.7,
    roof_type: str = "gable",
    roof_pitch_2: float | None = None,
):
    """Extract raw Cp,e values per surface for the GUI surface table.

    Returns dict with wall and roof Cp,e data, without applying Kc,e/Kc,i/qu.
    Used by the WindSurfacePanel to populate the editable table.

    Returns:
        {
            "h": float,
            "h_over_d": float,
            "d_over_b": float,
            "walls": {
                "windward_cpe": float,
                "leeward_cpe": float,
                "side_zones": [(start_mult, end_mult, cpe), ...],
            },
            "roof": {
                "type": "zones" | "uniform" | "mixed",
                "zones": [(start_mult, end_mult, cpe_uplift, cpe_downward), ...],
                "left_uniform": (cpe_uplift, cpe_downward) | None,
                "right_uniform": (cpe_uplift, cpe_downward) | None,
            },
        }
    """
    left_pitch = roof_pitch
    right_pitch = roof_pitch_2 if roof_pitch_2 is not None else roof_pitch

    # Frame geometry
    if roof_type == "mono":
        ridge = eave_height + span * math.tan(math.radians(roof_pitch))
    else:
        tan_l = math.tan(math.radians(left_pitch))
        tan_r = math.tan(math.radians(right_pitch))
        if tan_l + tan_r > 0:
            apex_x = span * tan_r / (tan_l + tan_r)
        else:
            apex_x = span * 0.5
        ridge = eave_height + apex_x * tan_l
    h = (eave_height + ridge) / 2.0

    d_over_b = span / building_depth if building_depth > 0 else 1.0
    b_over_d = building_depth / span if span > 0 else 1.0
    h_over_d = h / span if span > 0 else 0.5

    # --- Walls ---
    lw_cpe = leeward_cpe_lookup(d_over_b, roof_pitch)

    # Side wall zones with distance labels
    side_zones = []
    for s_mult, e_mult, cpe in SIDE_WALL_CPE_ZONES:
        start_m = s_mult * h
        if start_m >= building_depth:
            break
        end_m = building_depth if e_mult is None else min(e_mult * h, building_depth)
        side_zones.append((s_mult, e_mult, cpe, round(start_m, 2), round(end_m, 2)))

    # --- Roof ---
    roof_data = {"type": "zones", "zones": [], "left_uniform": None, "right_uniform": None}

    if roof_type == "mono" and roof_pitch >= 10.0:
        # Uniform: Table 5.3(B) for upwind, 5.3(C) for downwind
        cpe_up_uplift, cpe_up_downward = _interp_53b(h_over_d, roof_pitch)
        cpe_down = _interp_53c(h_over_d, roof_pitch, b_over_d)
        roof_data["type"] = "uniform"
        roof_data["left_uniform"] = (cpe_up_uplift, cpe_up_downward)
        roof_data["right_uniform"] = (cpe_down, cpe_down)  # downwind same for both envelopes
    elif roof_type == "gable":
        # Zone-based from Table 5.3(A), but override per-rafter if pitch >= 10
        zone_table = roof_cpe_zones(h_over_d)
        zones_with_dist = []
        for s_mult, e_mult, cpe_up, cpe_dn in zone_table:
            start_m = s_mult * h
            if start_m >= span:
                break
            end_m = span if e_mult is None else min(e_mult * h, span)
            zones_with_dist.append((s_mult, e_mult, cpe_up, cpe_dn,
                                    round(start_m, 2), round(end_m, 2)))
        roof_data["zones"] = zones_with_dist

        if left_pitch >= 10.0:
            cpe_up, cpe_dn = _interp_53b(h_over_d, left_pitch)
            cpe_down = _interp_53c(h_over_d, left_pitch, b_over_d)
            roof_data["left_uniform"] = (cpe_up, cpe_dn, cpe_down)
        if right_pitch >= 10.0:
            cpe_up, cpe_dn = _interp_53b(h_over_d, right_pitch)
            cpe_down = _interp_53c(h_over_d, right_pitch, b_over_d)
            roof_data["right_uniform"] = (cpe_up, cpe_dn, cpe_down)

        if roof_data["left_uniform"] or roof_data["right_uniform"]:
            roof_data["type"] = "mixed"
    else:
        # Mono < 10 or gable < 10: pure zone-based
        zone_table = roof_cpe_zones(h_over_d)
        zones_with_dist = []
        for s_mult, e_mult, cpe_up, cpe_dn in zone_table:
            start_m = s_mult * h
            if start_m >= span:
                break
            end_m = span if e_mult is None else min(e_mult * h, span)
            zones_with_dist.append((s_mult, e_mult, cpe_up, cpe_dn,
                                    round(start_m, 2), round(end_m, 2)))
        roof_data["zones"] = zones_with_dist

    return {
        "h": round(h, 3),
        "h_over_d": round(h_over_d, 4),
        "d_over_b": round(d_over_b, 4),
        "b_over_d": round(b_over_d, 4),
        "building_depth": building_depth,
        "walls": {
            "windward_cpe": windward_wall_cpe,
            "leeward_cpe": lw_cpe,
            "side_zones": side_zones,
        },
        "roof": roof_data,
    }


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
    roof_type: str = "gable",
    roof_pitch_2: float | None = None,
) -> list[WindCase]:
    """Generate 8 standard wind cases per NZS 1170.2:2021.

    Each rafter is classified independently as upwind or downwind.
    Per-rafter table selection:
        pitch < 10 deg  → Table 5.3(A) zone-based
        pitch >= 10 deg, upwind  → Table 5.3(B) uniform
        pitch >= 10 deg, downwind → Table 5.3(C) uniform

    Args:
        roof_pitch: Left rafter pitch (alpha1) in degrees.
        roof_pitch_2: Right rafter pitch (alpha2). None = same as roof_pitch.

    All pressures are Wu (ULS). SLS uses qs/qu scaling in combinations.
    """
    qu = cp.qu
    kc_e = cp.kc_e
    kc_i = cp.kc_i
    left_pitch = roof_pitch
    right_pitch = roof_pitch_2 if roof_pitch_2 is not None else roof_pitch

    # Frame geometry
    if roof_type == "mono":
        ridge = eave_height + span * math.tan(math.radians(roof_pitch))
    else:
        apex_x = span * split_pct / 100.0
        ridge = eave_height + apex_x * math.tan(math.radians(roof_pitch))
    h = (eave_height + ridge) / 2.0

    # Ratios
    d_over_b_cross = span / building_depth if building_depth > 0 else 1.0
    b_over_d = building_depth / span if span > 0 else 1.0
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
    if roof_type == "mono" and roof_pitch >= 10.0:
        # Mono roof >= 10 deg: Tables 5.3(B) upwind and 5.3(C) downwind
        cpe_up_uplift, cpe_up_downward = _interp_53b(h_over_d, roof_pitch)
        cpe_down = _interp_53c(h_over_d, roof_pitch, b_over_d)

        for case_num, is_upslope, cpi_val, envelope, desc_env in [
            (1, True,  cp.cpi_uplift,   "max_uplift",   "max uplift"),
            (2, True,  cp.cpi_downward, "max_downward", "max downward"),
            (3, False, cp.cpi_uplift,   "max_uplift",   "max uplift"),
            (4, False, cp.cpi_downward, "max_downward", "max downward"),
        ]:
            ww_p = wu(cp.windward_wall_cpe, cpi_val)
            lw_p = wu(lw_cpe, cpi_val)

            if is_upslope:
                dir_label = "Upslope"
                direction = "crosswind_LR"
                left_wall, right_wall = ww_p, lw_p
                use_uplift = (envelope == "max_uplift")
                roof_cpe = cpe_up_uplift if use_uplift else cpe_up_downward
            else:
                dir_label = "Downslope"
                direction = "crosswind_RL"
                left_wall, right_wall = lw_p, ww_p
                roof_cpe = cpe_down

            roof_p = wu(roof_cpe, cpi_val)
            cases.append(WindCase(
                name=f"W{case_num}",
                description=f"{dir_label} - {desc_env}",
                direction=direction, envelope=envelope,
                is_crosswind=False,
                left_wall=left_wall, right_wall=right_wall,
                left_rafter=roof_p, right_rafter=0.0,
            ))

    elif roof_type == "mono":
        # Mono < 10 deg: Table 5.3(A) zone-based, single rafter (no split)
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
            rafter_zones = full_zones if is_LR else _mirror_zones(full_zones)
            if is_LR:
                left_wall, right_wall = ww_p, lw_p
            else:
                left_wall, right_wall = lw_p, ww_p
            cases.append(WindCase(
                name=f"W{case_num}",
                description=f"Crosswind {dir_label} - {desc_env}",
                direction=direction, envelope=envelope,
                is_crosswind=True,
                left_wall=left_wall, right_wall=right_wall,
                left_rafter_zones=rafter_zones, right_rafter_zones=[],
            ))

    else:
        # Gable: compute zones first (correct for wind direction),
        # then override individual rafters with uniform if pitch >= 10 deg
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

            # Step 1: Compute zone-based loads for the full span
            # Zones are measured from the windward edge in multiples of h.
            # For L-R: windward = left edge, split directly.
            # For R-L: windward = right edge, mirror full zones first then split.
            full_zones = _compute_zone_loads(
                span, h, h_over_d, cpi_val, kc_e, kc_i, qu, use_uplift
            )
            if is_LR:
                l_zones, r_zones = _split_zones_to_rafters(full_zones, split_pct)
            else:
                mirrored_full = _mirror_zones(full_zones)
                l_zones, r_zones = _split_zones_to_rafters(mirrored_full, split_pct)

            # Step 3: Override with uniform if pitch >= 10 deg
            l_uniform = 0.0
            r_uniform = 0.0
            if is_LR:
                left_role, right_role = "upwind", "downwind"
            else:
                left_role, right_role = "downwind", "upwind"

            if left_pitch >= 10.0:
                if left_role == "upwind":
                    cpe_up, cpe_dn = _interp_53b(h_over_d, left_pitch)
                    cpe = cpe_up if use_uplift else cpe_dn
                else:
                    cpe = _interp_53c(h_over_d, left_pitch, b_over_d)
                l_uniform = wu(cpe, cpi_val)
                l_zones = []  # uniform replaces zones

            if right_pitch >= 10.0:
                if right_role == "upwind":
                    cpe_up, cpe_dn = _interp_53b(h_over_d, right_pitch)
                    cpe = cpe_up if use_uplift else cpe_dn
                else:
                    cpe = _interp_53c(h_over_d, right_pitch, b_over_d)
                r_uniform = wu(cpe, cpi_val)
                r_zones = []  # uniform replaces zones

            if is_LR:
                left_wall, right_wall = ww_p, lw_p
            else:
                left_wall, right_wall = lw_p, ww_p

            has_zones = bool(l_zones or r_zones)
            cases.append(WindCase(
                name=f"W{case_num}",
                description=f"Crosswind {dir_label} - {desc_env}",
                direction=direction, envelope=envelope,
                is_crosswind=has_zones,
                left_wall=left_wall, right_wall=right_wall,
                left_rafter_zones=l_zones, right_rafter_zones=r_zones,
                left_rafter=l_uniform, right_rafter=r_uniform,
            ))

    # ================================================================
    # TRANSVERSE CASES (W5-W8): wind along ridge
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
