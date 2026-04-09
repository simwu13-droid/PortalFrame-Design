"""Load case data models — input data only (no standards logic)."""

from dataclasses import dataclass, field

from portal_frame.models.crane import CraneInputs


@dataclass
class RafterZoneLoad:
    """A zone of pressure on a rafter, defined by start/end % of member length."""
    start_pct: float    # Start position as % of rafter length (0-100)
    end_pct: float      # End position as % of rafter length (0-100)
    pressure: float     # Net pressure in kPa (+ve = into surface)


@dataclass
class WindCase:
    """A single wind load case with pressures on each surface.

    3D-upgradeable: `direction` and `envelope` metadata allow future
    expansion to longitudinal, diagonal, and multi-surface wind cases.
    """
    name: str
    description: str
    # Surface net pressures (kPa) — +ve = into surface
    left_wall: float = 0.0
    right_wall: float = 0.0
    left_rafter: float = 0.0
    right_rafter: float = 0.0
    left_rafter_zones: list = field(default_factory=list)   # List of RafterZoneLoad
    right_rafter_zones: list = field(default_factory=list)   # List of RafterZoneLoad
    is_crosswind: bool = False
    # 3D-ready metadata
    direction: str = ""      # "crosswind_LR", "crosswind_RL", "transverse", or custom
    envelope: str = ""       # "max_uplift", "max_downward", or custom


@dataclass
class EarthquakeInputs:
    """Placeholder for NZS 1170.5:2004 earthquake loading inputs."""
    Z: float = 0.0
    soil_class: str = "C"
    R_uls: float = 1.0
    R_sls: float = 0.25
    mu: float = 1.0
    Sp: float = 1.0
    near_fault: float = 1.0
    Sp_sls: float = 0.7             # SLS structural performance factor (Cl 4.4.4). Default 0.7.
    extra_seismic_mass: float = 0.0
    T1_override: float = 0.0       # User override period (s). 0 = auto-calculate.


@dataclass
class LoadInput:
    """Load input values (unfactored, in kPa unless noted)."""
    dead_load_roof: float = 0.0     # Superimposed dead on roof (kPa)
    dead_load_wall: float = 0.0     # Cladding on walls (kPa)
    live_load_roof: float = 0.25    # Imposed roof load (kPa) — AS/NZS 1170.1
    wind_cases: list = field(default_factory=list)
    include_self_weight: bool = True
    ws_factor: float = 0.75         # SLS wind scaling: qs/qu ratio (default 0.9/1.2)
    earthquake: EarthquakeInputs | None = None
    crane: CraneInputs | None = None
