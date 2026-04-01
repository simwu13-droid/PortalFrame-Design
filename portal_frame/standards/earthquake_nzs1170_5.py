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
    # Site Subsoil Class B — Rock
    "B": [
        (0.0,  1.00),
        (0.1,  1.30),
        (0.2,  1.60),
        (0.25, 2.36),
        (0.3,  2.36),
        (0.4,  2.36),
        (0.5,  2.00),
        (0.6,  1.67),
        (0.7,  1.43),
        (0.8,  1.25),
        (0.9,  1.11),
        (1.0,  1.00),
        (1.5,  0.67),
        (2.0,  0.50),
        (2.5,  0.40),
        (3.0,  0.33),
        (3.5,  0.27),
        (4.0,  0.23),
        (4.5,  0.22),
    ],
    # Site Subsoil Class C — Shallow Soil
    "C": [
        (0.0,  1.33),
        (0.1,  1.60),
        (0.2,  2.36),
        (0.3,  2.36),
        (0.4,  2.36),
        (0.5,  2.36),
        (0.6,  2.00),
        (0.7,  1.71),
        (0.8,  1.50),
        (0.9,  1.33),
        (1.0,  1.20),
        (1.5,  0.80),
        (2.0,  0.60),
        (2.5,  0.48),
        (3.0,  0.40),
        (3.5,  0.33),
        (4.0,  0.29),
        (4.5,  0.27),
    ],
    # Site Subsoil Class D — Deep or Soft Soil
    "D": [
        (0.0,  1.12),
        (0.1,  1.50),
        (0.2,  2.00),
        (0.3,  2.50),
        (0.4,  2.84),
        (0.5,  2.99),
        (0.6,  3.00),
        (0.7,  3.00),
        (0.8,  3.00),
        (0.9,  3.00),
        (1.0,  3.00),
        (1.5,  2.67),
        (2.0,  2.00),
        (2.5,  1.60),
        (3.0,  1.33),
        (3.5,  1.07),
        (4.0,  0.80),
        (4.5,  0.67),
    ],
    # Site Subsoil Class E — Very Soft Soil
    "E": [
        (0.0,  1.12),
        (0.1,  1.50),
        (0.2,  2.00),
        (0.3,  2.50),
        (0.4,  2.84),
        (0.5,  2.99),
        (0.6,  3.00),
        (0.7,  3.00),
        (0.8,  3.00),
        (0.9,  3.00),
        (1.0,  3.00),
        (1.5,  3.00),
        (2.0,  2.67),
        (2.5,  2.14),
        (3.0,  1.78),
        (3.5,  1.56),
        (4.0,  1.43),
        (4.5,  1.33),
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
) -> dict:
    """Calculate NZS 1170.5:2004 earthquake forces for a portal frame.

    Args:
        geom: PortalFrameGeometry with .span, .eave_height, .ridge_height, .bay_spacing
        dead_load_roof: Superimposed dead load on roof (kPa)
        dead_load_wall: Cladding dead load on walls (kPa)
        eq: EarthquakeInputs dataclass

    Returns:
        Dict with keys: T1, Ch, k_mu, Cd_uls, Cd_sls, Wt, V_uls, V_sls, F_node, F_node_sls
        All values rounded to 4 decimal places.
    """
    # --- Building height for period calculation ---
    h_n = geom.ridge_height  # Total height to highest point (Clause 4.1.2.1)

    # --- Fundamental period (Clause 4.1.2.1(b) — steel moment-resisting frame) ---
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

    # --- SLS design coefficient (Clause 5.2.1, no Sp or k_mu reduction) ---
    Cd_sls = Ch * eq.Z * eq.R_sls * eq.near_fault

    # --- Seismic weight (kN) ---
    # Roof tributary: dead_load_roof * span * bay_spacing
    # Wall tributary: dead_load_wall * 2 * eave_height * bay_spacing (both walls)
    Wt = (
        dead_load_roof * geom.span
        + dead_load_wall * 2.0 * geom.eave_height
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
