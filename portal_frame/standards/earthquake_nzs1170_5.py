"""NZS 1170.5:2004 Earthquake Loading calculations.

Implements:
- NZ_HAZARD_FACTORS: 19 NZ locations -> Z values (Appendix A)
- _CH_TABLE: spectral shape factor table (Table 3.1, 5 soil classes)
- spectral_shape_factor(T, soil_class): interpolates Ch(T) from table
- calculate_earthquake_forces(geom, dead_load_roof, dead_load_wall, eq): full calculation

Key formulas (NZS 1170.5:2004):
    T1 = 1.25 * 0.085 * h_n^0.75  (steel MRF, Clause 4.1.2.1(b))
    k_mu: if T1 >= 0.7s -> k_mu = mu; if T1 < 0.7s -> k_mu = (mu-1)*T1/0.7 + 1
    Cd(T1) = Ch(T1) * Z * R * N(T,D) * Sp / k_mu
    Floor: Cd(T1) >= max(0.03, Z*R*0.02)
    V = Cd(T1) * Wt
    Cd_sls = Ch(T1) * Z * R_sls * N  (no Sp or k_mu reduction)
"""

from portal_frame.standards.utils import lerp

# ---------------------------------------------------------------------------
# NZ Hazard Factors — Appendix A, NZS 1170.5:2004
# ---------------------------------------------------------------------------

NZ_HAZARD_FACTORS: dict[str, float] = {
    "Auckland": 0.13,
    "Blenheim": 0.33,
    "Christchurch": 0.30,
    "Dunedin": 0.13,
    "Gisborne": 0.36,
    "Greymouth": 0.30,
    "Hamilton": 0.13,
    "Hastings": 0.39,
    "Invercargill": 0.18,
    "Napier": 0.39,
    "Nelson": 0.27,
    "New Plymouth": 0.18,
    "Palmerston North": 0.38,
    "Queenstown": 0.20,
    "Rotorua": 0.20,
    "Tauranga": 0.20,
    "Timaru": 0.20,
    "Wellington": 0.40,
    "Whangarei": 0.10,
}

# ---------------------------------------------------------------------------
# Spectral Shape Factor table — Table 3.1, NZS 1170.5:2004
# Each class is a list of (T, Ch) tuples, sorted ascending by T.
# ---------------------------------------------------------------------------

_CH_TABLE: dict[str, list[tuple[float, float]]] = {
    # Site Subsoil Class A — Strong Rock
    "A": [
        (0.0,  1.89),
        (0.1,  1.89),
        (0.2,  1.89),
        (0.3,  1.89),
        (0.4,  1.89),
        (0.5,  1.60),
        (0.6,  1.35),
        (0.7,  1.15),
        (0.8,  1.01),
        (0.9,  0.90),
        (1.0,  0.81),
        (1.5,  0.54),
        (2.0,  0.40),
        (2.5,  0.31),
        (3.0,  0.25),
        (3.5,  0.21),
        (4.0,  0.18),
        (4.5,  0.18),
    ],
    # Site Subsoil Class B — Rock (same column as A in Table 3.1)
    "B": [
        (0.0,  1.89),
        (0.1,  1.89),
        (0.2,  1.89),
        (0.3,  1.89),
        (0.4,  1.89),
        (0.5,  1.60),
        (0.6,  1.40),
        (0.7,  1.24),
        (0.8,  1.12),
        (0.9,  1.03),
        (1.0,  0.95),
        (1.5,  0.70),
        (2.0,  0.53),
        (2.5,  0.42),
        (3.0,  0.35),
        (3.5,  0.26),
        (4.0,  0.20),
        (4.5,  0.16),
    ],
    # Site Subsoil Class C — Shallow Soil
    # Non-bracketed values from Table 3.1 (equivalent static method)
    "C": [
        (0.0,  2.36),
        (0.1,  2.36),
        (0.2,  2.36),
        (0.3,  2.36),
        (0.4,  2.36),
        (0.5,  2.00),
        (0.6,  1.74),
        (0.7,  1.55),
        (0.8,  1.41),
        (0.9,  1.29),
        (1.0,  1.19),
        (1.5,  0.88),
        (2.0,  0.66),
        (2.5,  0.53),
        (3.0,  0.44),
        (3.5,  0.32),
        (4.0,  0.25),
        (4.5,  0.20),
    ],
    # Site Subsoil Class D — Deep or Soft Soil
    # Non-bracketed values from Table 3.1 (equivalent static method)
    "D": [
        (0.0,  3.00),
        (0.1,  3.00),
        (0.2,  3.00),
        (0.3,  3.00),
        (0.4,  3.00),
        (0.5,  3.00),
        (0.6,  2.84),
        (0.7,  2.53),
        (0.8,  2.29),
        (0.9,  2.09),
        (1.0,  1.93),
        (1.5,  1.43),
        (2.0,  1.07),
        (2.5,  0.86),
        (3.0,  0.71),
        (3.5,  0.52),
        (4.0,  0.40),
        (4.5,  0.32),
    ],
    # Site Subsoil Class E — Very Soft Soil
    # Non-bracketed values from Table 3.1 (equivalent static method)
    "E": [
        (0.0,  3.00),
        (0.1,  3.00),
        (0.2,  3.00),
        (0.3,  3.00),
        (0.4,  3.00),
        (0.5,  3.00),
        (0.6,  3.00),
        (0.7,  3.00),
        (0.8,  3.00),
        (0.9,  3.00),
        (1.0,  3.00),
        (1.5,  2.21),
        (2.0,  1.66),
        (2.5,  1.33),
        (3.0,  1.11),
        (3.5,  0.81),
        (4.0,  0.62),
        (4.5,  0.49),
    ],
}


def spectral_shape_factor(T: float, soil_class: str) -> float:
    """Interpolate Ch(T) from Table 3.1 for the given period and soil class.

    Args:
        T: Structural period in seconds (>= 0).
        soil_class: One of "A", "B", "C", "D", "E".

    Returns:
        Ch(T) — spectral shape factor (dimensionless).
    """
    table = _CH_TABLE[soil_class]

    # Below first entry: return first value
    if T <= table[0][0]:
        return table[0][1]

    # Above last entry: return last value (flat extrapolation)
    if T >= table[-1][0]:
        return table[-1][1]

    # Find surrounding bracket and interpolate
    for i in range(len(table) - 1):
        t0, ch0 = table[i]
        t1, ch1 = table[i + 1]
        if t0 <= T <= t1:
            return lerp(T, t0, t1, ch0, ch1)

    # Fallback (should not reach here)
    return table[-1][1]


def calculate_earthquake_forces(
    geom,
    dead_load_roof: float,
    dead_load_wall: float,
    eq,
    T1_override: float | None = None,
) -> dict:
    """Calculate NZS 1170.5:2004 earthquake forces for a portal frame.

    Args:
        geom: PortalFrameGeometry with .span, .eave_height, .ridge_height, .bay_spacing
        dead_load_roof: Superimposed dead load on roof (kPa)
        dead_load_wall: Cladding dead load on walls (kPa)
        eq: EarthquakeInputs dataclass
        T1_override: If provided, use this period instead of auto-calculating.

    Returns:
        Dict with keys: T1, Ch, k_mu, Cd_uls, Cd_sls, Wt, V_uls, V_sls, F_node, F_node_sls
        All values rounded to 4 decimal places.
    """
    # --- Fundamental period ---
    # Use override from parameter, then from EarthquakeInputs, then auto-calc
    _t1_from_eq = getattr(eq, 'T1_override', 0.0)
    _t1 = T1_override if T1_override is not None and T1_override > 0 else (
        _t1_from_eq if _t1_from_eq > 0 else None)
    if _t1:
        T1 = _t1
    else:
        # Clause 4.1.2.1(b) — steel moment-resisting frame
        h_n = geom.ridge_height
        T1 = 1.25 * 0.085 * (h_n ** 0.75)

    # --- Spectral shape factor ---
    Ch = spectral_shape_factor(T1, eq.soil_class)

    # --- Ductility-related factor (Clause 5.2.1.1) ---
    if T1 >= 0.7:
        k_mu = eq.mu
    else:
        k_mu = (eq.mu - 1) * T1 / 0.7 + 1.0

    # --- ULS design coefficient (Clause 5.2.1) ---
    Cd_uls_raw = Ch * eq.Z * eq.R_uls * eq.near_fault * eq.Sp / k_mu
    Cd_floor = max(0.03, eq.Z * eq.R_uls * 0.02)
    Cd_uls = max(Cd_uls_raw, Cd_floor)

    # --- SLS design coefficient (Clause 5.2.1) ---
    # SLS uses Sp_sls (default 0.7, Cl 4.4.4) and k_mu=1.0 (mu=1 for SLS, Cl 4.4.2)
    Sp_sls = getattr(eq, 'Sp_sls', 0.7)
    k_mu_sls = 1.0
    Cd_sls = Ch * eq.Z * eq.R_sls * eq.near_fault * Sp_sls / k_mu_sls

    # --- Seismic weight (kN) ---
    # Only mass tributary to knee level (top half of building):
    # Roof: full roof dead load
    # Walls: top half of wall cladding on both sides
    Wt = (
        dead_load_roof * geom.span
        + dead_load_wall * 2.0 * geom.eave_height / 2.0
    ) * geom.bay_spacing + eq.extra_seismic_mass

    # --- Base shear ---
    V_uls = Cd_uls * Wt
    V_sls = Cd_sls * Wt

    # --- Node forces (split equally to two eave nodes) ---
    F_node = V_uls / 2.0
    F_node_sls = V_sls / 2.0

    return {
        "T1": round(T1, 4),
        "Ch": round(Ch, 4),
        "k_mu": round(k_mu, 4),
        "Cd_uls": round(Cd_uls, 4),
        "Cd_sls": round(Cd_sls, 4),
        "Wt": round(Wt, 4),
        "V_uls": round(V_uls, 4),
        "V_sls": round(V_sls, 4),
        "F_node": round(F_node, 4),
        "F_node_sls": round(F_node_sls, 4),
    }
