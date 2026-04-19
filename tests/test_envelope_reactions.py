"""Unit tests for envelope reaction synthesis in diagram_controller."""
from portal_frame.analysis.results import (
    AnalysisOutput, CaseResult, ReactionResult,
)
from portal_frame.gui.diagram_controller import synthesise_envelope_reactions


def _case(name, rx):
    """rx: dict[node_id] -> (fx, fy, mz)."""
    return CaseResult(
        case_name=name, members={}, deflections={},
        reactions={nid: ReactionResult(node_id=nid, fx=v[0], fy=v[1], mz=v[2])
                   for nid, v in rx.items()},
    )


def test_picks_max_abs_across_cases():
    out = AnalysisOutput(
        case_results={},
        combo_results={
            "ULS-1": _case("ULS-1", {1: (5.0, -20.0, 0.0), 5: (-5.0, -20.0, 0.0)}),
            "ULS-2": _case("ULS-2", {1: (-10.0, -10.0, 2.0), 5: (10.0, -10.0, -2.0)}),
            "ULS-3": _case("ULS-3", {1: (3.0, -25.0, 1.0), 5: (-3.0, -25.0, -1.0)}),
        },
    )
    result = synthesise_envelope_reactions(out, ["ULS-1", "ULS-2", "ULS-3"])
    # Node 1: max|fx|=10 from ULS-2 (signed), max|fy|=25 from ULS-3, max|mz|=2 from ULS-2
    assert result[1].fx == -10.0
    assert result[1].fy == -25.0
    assert result[1].mz == 2.0
    # Node 5: max|fx|=10 from ULS-2, max|fy|=25 from ULS-3, max|mz|=2 from ULS-2
    assert result[5].fx == 10.0
    assert result[5].fy == -25.0
    assert result[5].mz == -2.0


def test_missing_combos_skipped():
    out = AnalysisOutput(
        case_results={},
        combo_results={
            "ULS-1": _case("ULS-1", {1: (5.0, -20.0, 0.0)}),
        },
    )
    result = synthesise_envelope_reactions(out, ["ULS-1", "ULS-99-nonexistent"])
    assert set(result.keys()) == {1}
    assert result[1].fx == 5.0


def test_empty_combo_list_returns_empty():
    out = AnalysisOutput(case_results={}, combo_results={})
    result = synthesise_envelope_reactions(out, [])
    assert result == {}
