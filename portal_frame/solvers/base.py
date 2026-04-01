"""Analysis solver abstraction — engine-agnostic interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from portal_frame.models.geometry import FrameTopology
from portal_frame.models.sections import CFS_Section
from portal_frame.models.loads import LoadInput
from portal_frame.models.supports import SupportCondition
from portal_frame.standards.combinations_nzs1170_0 import LoadCombination


@dataclass
class AnalysisRequest:
    """Single input object bundling everything a solver needs."""
    topology: FrameTopology
    column_section: CFS_Section
    rafter_section: CFS_Section
    supports: SupportCondition
    load_input: LoadInput
    # Additional geometry context needed by writers
    span: float = 0.0
    eave_height: float = 0.0
    roof_pitch: float = 0.0
    bay_spacing: float = 0.0


@dataclass
class AnalysisResults:
    """Results from structural analysis. Empty for export-only solvers."""
    reactions: dict = field(default_factory=dict)
    member_forces: dict = field(default_factory=dict)
    deflections: dict = field(default_factory=dict)
    solved: bool = False


class AnalysisSolver(ABC):
    """Abstract base class for structural analysis solvers.

    Implementations:
    - SpaceGassSolver: export-only (SpaceGass does the actual analysis externally)
    - Future: PyNiteSolver, OpenSeesSolver, etc.
    """

    @abstractmethod
    def build_model(self, request: AnalysisRequest) -> None:
        """Prepare the analysis model from a request."""

    @abstractmethod
    def solve(self) -> AnalysisResults:
        """Run analysis. Returns results (or empty results for export-only solvers)."""

    @abstractmethod
    def export(self, path: str) -> None:
        """Export model to file."""
