"""Result dataclasses for structural analysis output."""

from dataclasses import dataclass, field


@dataclass
class MemberStationResult:
    """Forces and deflections at a single station along a member."""
    position: float       # Distance from member start (m)
    position_pct: float   # 0-100%
    axial: float          # kN, +ve = tension
    shear: float          # kN
    moment: float         # kNm
    dy_local: float = 0.0 # mm, member-local y deflection (perpendicular to member)
    dx_local: float = 0.0 # mm, member-local x deflection (along member axis)


@dataclass
class MemberResult:
    """Complete results for one member in one load case/combo.

    Max/min fields are derived from stations. Always recompute after
    modifying stations to keep them consistent.
    """
    member_id: int
    stations: list[MemberStationResult]
    max_moment: float = 0.0
    min_moment: float = 0.0
    max_shear: float = 0.0
    max_axial: float = 0.0
    min_axial: float = 0.0

    def compute_extremes(self):
        """Recompute max/min from stations. Call after building stations list."""
        if not self.stations:
            return
        self.max_moment = max(s.moment for s in self.stations)
        self.min_moment = min(s.moment for s in self.stations)
        self.max_shear = max(abs(s.shear) for s in self.stations)
        self.max_axial = max(s.axial for s in self.stations)
        self.min_axial = min(s.axial for s in self.stations)


@dataclass
class NodeResult:
    """Displacement at a single node."""
    node_id: int
    dx: float = 0.0   # mm (horizontal)
    dy: float = 0.0   # mm (vertical)
    rz: float = 0.0   # rad


@dataclass
class ReactionResult:
    """Reaction at a support node."""
    node_id: int
    fx: float = 0.0   # kN
    fy: float = 0.0   # kN
    mz: float = 0.0   # kNm


@dataclass
class CaseResult:
    """All results for a single load case or combination."""
    case_name: str
    members: dict[int, MemberResult]
    deflections: dict[int, NodeResult]
    reactions: dict[int, ReactionResult]


@dataclass
class EnvelopeEntry:
    """Max/min value with the controlling combination name."""
    value: float
    combo_name: str
    member_id: int = 0
    position_pct: float = 0.0


@dataclass
class MemberDesignCheck:
    """AS/NZS 4600 member capacity check result for one member.

    Forces are envelope extremes from the ULS envelope curves; checks use
    pre-computed φN_c / φM_bx / φV_y from the Formsteel span table.
    """
    member_id: int
    member_role: str             # "col" | "raf"
    section_name: str            # SpaceGass library name
    L_eff: float                 # m
    phi_Nc: float | None         # kN, None if no span table data
    phi_Nt: float                # kN, always computed (0.85 * Ag * fu)
    phi_Mbx: float | None        # kNm, None if no span table data
    phi_Vy: float | None = None  # kN, None if no span table data
    N_compression: float = 0.0   # kN, abs of most -ve axial (>=0)
    N_tension: float = 0.0       # kN, most +ve axial (>=0)
    M_max: float = 0.0           # kNm, max |moment|
    V_max: float = 0.0           # kN, max |shear|
    util_axial: float = 0.0      # max(N*c/φNc, N*t/φNt)
    util_bending: float = 0.0    # M*/φMbx
    util_shear: float = 0.0      # V*/φVy
    util_combined: float = 0.0   # linear interaction (axial + bending)
    status: str = "PASS"         # "PASS" | "FAIL" | "NO_DATA"
    controlling_combo_n: str = ""
    controlling_combo_m: str = ""
    controlling_combo_v: str = ""


@dataclass
class SLSCheck:
    """Serviceability deflection check result.

    One instance per (metric, category) pair. Two metrics are supported:
      - "apex_dy" : vertical deflection at the ridge, limit = span / ratio
      - "drift"   : horizontal deflection at an eave node, limit = h / ratio

    `actual_ratio` is the X that would make `ref_length / X == deflection`
    — i.e. what the frame ACTUALLY deformed by. `ratio` is the user's
    design limit. These are usually different and both are informative.
    """
    metric: str                  # "apex_dy" | "drift"
    category: str                # "wind" | "eq"
    deflection_mm: float         # signed deflection at the measured point
    limit_mm: float              # absolute limit = ref_length * 1000 / ratio
    ratio: int                   # the X in the user's L/X or h/X input
    actual_ratio: int            # ref_length / |deflection|, 9999 if ~0
    util: float                  # |deflection| / limit
    status: str                  # "PASS" | "FAIL"
    controlling_combo: str = ""
    reference_length_m: float = 0.0   # span (apex) or eave_height (drift)
    reference_symbol: str = "L"       # "L" for span, "h" for column height


@dataclass
class AnalysisOutput:
    """Complete analysis output: per-case + combination results + envelopes."""
    case_results: dict[str, CaseResult]
    combo_results: dict[str, CaseResult]
    uls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    sls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    combo_descriptions: dict[str, str] = field(default_factory=dict)
    # Envelope curves: (max, min) CaseResult pair per combo set, or None
    uls_envelope_curves: tuple | None = None   # (max CaseResult, min CaseResult)
    sls_envelope_curves: tuple | None = None
    sls_wind_only_envelope_curves: tuple | None = None
    design_checks: list[MemberDesignCheck] = field(default_factory=list)
    sls_checks: list[SLSCheck] = field(default_factory=list)
