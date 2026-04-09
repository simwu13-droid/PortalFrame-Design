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
class AnalysisOutput:
    """Complete analysis output: per-case + combination results + envelopes."""
    case_results: dict[str, CaseResult]
    combo_results: dict[str, CaseResult]
    uls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    sls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    combo_descriptions: dict[str, str] = field(default_factory=dict)
