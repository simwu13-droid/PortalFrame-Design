"""Tests for PyNite solver integration."""

import pytest
from portal_frame.analysis.results import (
    MemberStationResult, MemberResult, NodeResult,
    ReactionResult, CaseResult, EnvelopeEntry, AnalysisOutput,
)


def test_member_station_result_stores_forces():
    st = MemberStationResult(position=2.5, position_pct=50.0,
                             axial=10.0, shear=-5.0, moment=25.0)
    assert st.position == 2.5
    assert st.axial == 10.0
    assert st.moment == 25.0


def test_member_result_computes_extremes():
    stations = [
        MemberStationResult(0.0, 0, 5.0, -10.0, 0.0),
        MemberStationResult(2.5, 50, -3.0, 2.0, 50.0),
        MemberStationResult(5.0, 100, 5.0, 8.0, 0.0),
    ]
    mr = MemberResult(member_id=1, stations=stations)
    mr.compute_extremes()
    assert mr.max_moment == 50.0
    assert mr.min_moment == 0.0
    assert mr.max_shear == 10.0
    assert mr.max_axial == 5.0
    assert mr.min_axial == -3.0


def test_case_result_organizes_by_id():
    mr = MemberResult(member_id=1, stations=[])
    nr = NodeResult(node_id=1, dx=1.5, dy=-2.0, rz=0.001)
    rr = ReactionResult(node_id=1, fx=0.0, fy=50.0, mz=0.0)
    cr = CaseResult(case_name="G", members={1: mr},
                    deflections={1: nr}, reactions={1: rr})
    assert cr.case_name == "G"
    assert cr.reactions[1].fy == 50.0


def test_analysis_output_holds_cases_and_combos():
    out = AnalysisOutput(case_results={}, combo_results={})
    assert out.uls_envelope == {}
    assert out.sls_envelope == {}


from portal_frame.analysis.combinations import (
    combine_case_results, compute_envelopes,
)


def _make_case(name, axial, shear, moment, dy_mm=0.0, fy_rxn=0.0):
    """Helper to build a CaseResult with one member (id=1) and one node (id=1)."""
    stations = [
        MemberStationResult(0.0, 0, axial, shear, 0.0),
        MemberStationResult(2.5, 50, axial, 0.0, moment),
        MemberStationResult(5.0, 100, axial, -shear, 0.0),
    ]
    mr = MemberResult(member_id=1, stations=stations)
    nr = NodeResult(node_id=1, dx=0.0, dy=dy_mm, rz=0.0)
    rr = ReactionResult(node_id=1, fx=0.0, fy=fy_rxn, mz=0.0)
    return CaseResult(name, {1: mr}, {1: nr}, {1: rr})


def test_combine_scales_by_factor():
    g_case = _make_case("G", axial=-10.0, shear=20.0, moment=50.0,
                        dy_mm=-5.0, fy_rxn=40.0)
    cases = {"G": g_case}
    combo = combine_case_results(cases, {"G": 1.35}, "ULS-1")
    assert combo.case_name == "ULS-1"
    assert abs(combo.members[1].stations[1].moment - 1.35 * 50.0) < 0.01
    assert abs(combo.deflections[1].dy - 1.35 * -5.0) < 0.01
    assert abs(combo.reactions[1].fy - 1.35 * 40.0) < 0.01


def test_combine_sums_multiple_cases():
    g_case = _make_case("G", axial=-10.0, shear=20.0, moment=50.0)
    q_case = _make_case("Q", axial=-2.0, shear=5.0, moment=12.0)
    cases = {"G": g_case, "Q": q_case}
    combo = combine_case_results(cases, {"G": 1.2, "Q": 1.5}, "ULS-2")
    assert abs(combo.members[1].stations[1].moment - 78.0) < 0.01


def test_combine_ignores_missing_cases():
    g_case = _make_case("G", axial=-10.0, shear=20.0, moment=50.0)
    cases = {"G": g_case}
    combo = combine_case_results(cases, {"G": 1.2, "W1": 1.0}, "ULS-3")
    assert abs(combo.members[1].stations[1].moment - 1.2 * 50.0) < 0.01


def test_compute_envelopes_tracks_controlling_combo():
    c1 = _make_case("ULS-1", axial=-13.5, shear=27.0, moment=67.5, dy_mm=-6.75)
    c2 = _make_case("ULS-2", axial=-15.0, shear=33.5, moment=78.0, dy_mm=-8.50)
    out = AnalysisOutput(
        case_results={},
        combo_results={"ULS-1": c1, "ULS-2": c2},
    )
    compute_envelopes(out)
    assert out.uls_envelope["max_moment"].value == 78.0
    assert out.uls_envelope["max_moment"].combo_name == "ULS-2"
    assert out.uls_envelope["max_shear"].value == pytest.approx(33.5)
