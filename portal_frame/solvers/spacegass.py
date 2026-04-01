"""SpaceGass solver — export-only (analysis done externally in SpaceGass v14)."""

from portal_frame.solvers.base import AnalysisSolver, AnalysisRequest, AnalysisResults
from portal_frame.io.spacegass_writer import SpaceGassWriter


class SpaceGassSolver(AnalysisSolver):
    """Wraps SpaceGass export as a solver interface.

    solve() is a no-op — SpaceGass does actual analysis externally.
    export() writes the SpaceGass v14 text file.
    """

    def __init__(self):
        self._request = None

    def build_model(self, request: AnalysisRequest) -> None:
        self._request = request

    def solve(self) -> AnalysisResults:
        return AnalysisResults(solved=False)  # External solver

    def export(self, path: str) -> None:
        r = self._request
        writer = SpaceGassWriter(
            topology=r.topology,
            column_section=r.column_section,
            rafter_section=r.rafter_section,
            supports=r.supports,
            loads=r.load_input,
            span=r.span,
            eave_height=r.eave_height,
            roof_pitch=r.roof_pitch,
            bay_spacing=r.bay_spacing,
        )
        content = writer.write()
        with open(path, "w") as f:
            f.write(content)

    def generate_text(self) -> str:
        """Generate SpaceGass text without writing to file."""
        r = self._request
        writer = SpaceGassWriter(
            topology=r.topology,
            column_section=r.column_section,
            rafter_section=r.rafter_section,
            supports=r.supports,
            loads=r.load_input,
            span=r.span,
            eave_height=r.eave_height,
            roof_pitch=r.roof_pitch,
            bay_spacing=r.bay_spacing,
        )
        return writer.write()
