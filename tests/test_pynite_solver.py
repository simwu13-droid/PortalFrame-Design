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


import math
from portal_frame.models.geometry import Node, Member, FrameTopology
from portal_frame.models.sections import CFS_Section
from portal_frame.models.loads import LoadInput
from portal_frame.models.supports import SupportCondition
from portal_frame.solvers.base import AnalysisRequest
from portal_frame.solvers.pynite_solver import PyNiteSolver


def _make_beam_request(span=10.0, w_dead=2.0, bay=5.0):
    """Simple beam: 2 nodes, 1 rafter member, pinned-roller supports."""
    nodes = {
        1: Node(1, 0.0, 0.0),
        2: Node(2, span, 0.0),
    }
    members = {1: Member(1, 1, 2, section_id=2)}  # rafter
    topo = FrameTopology(nodes=nodes, members=members)

    sec = CFS_Section(
        name="Test", library="test", library_name="T", group="G",
        Ax=500.0, J=1000.0, Iy=5e6, Iz=5e6,
    )
    supports = SupportCondition(left_base="pinned", right_base="pinned")
    loads = LoadInput(
        dead_load_roof=w_dead, dead_load_wall=0.0, live_load_roof=0.0,
        wind_cases=[], include_self_weight=False,
    )
    return AnalysisRequest(
        topology=topo, column_section=sec, rafter_section=sec,
        supports=supports, load_input=loads,
        span=span, eave_height=0.0, roof_pitch=0.0, bay_spacing=bay,
    )


def test_beam_gravity_reactions():
    """Simply supported beam: reactions = wL/2."""
    req = _make_beam_request(span=10.0, w_dead=2.0, bay=5.0)
    solver = PyNiteSolver()
    solver.build_model(req)
    result = solver.solve()
    assert result.solved is True

    out = solver.output
    g_case = out.case_results["G"]

    # Total applied load = 2.0 kPa * 5.0 m bay * 10.0 m span = 100 kN
    # Each reaction = 50 kN (downward load -> positive upward reaction)
    assert abs(g_case.reactions[1].fy - 50.0) < 0.5
    assert abs(g_case.reactions[2].fy - 50.0) < 0.5


def test_beam_gravity_midspan_moment():
    """Simply supported beam: M_max = wL^2/8 at midspan."""
    req = _make_beam_request(span=10.0, w_dead=2.0, bay=5.0)
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    g_case = out.case_results["G"]
    mr = g_case.members[1]

    # w = 2.0 * 5.0 = 10 kN/m, L = 10m -> M_max = 10*100/8 = 125 kNm
    # Find midspan station (50%)
    mid_station = next(s for s in mr.stations if abs(s.position_pct - 50) < 3)
    assert abs(mid_station.moment - 125.0) < 1.0


def test_local_axis_conventions():
    """Verify PyNite local axis directions match our documented conventions."""
    from Pynite import FEModel3D
    import numpy as np

    m = FEModel3D()
    m.add_material('Steel', 200e6, 80e6, 0.3, 7850)
    m.add_section('S', 0.005, 5e-5, 5e-5, 5e-5)

    m.add_node('N1', 0, 0, 0)
    m.add_node('N2', 0, 4, 0)
    m.add_node('N3', 6, 5, 0)

    m.add_member('Col', 'N1', 'N2', 'Steel', 'S')
    m.add_member('Raf', 'N2', 'N3', 'Steel', 'S')

    T_col = np.array(m.members['Col'].T())
    local_x_col = T_col[0, :3]
    assert abs(local_x_col[1] - 1.0) < 0.01, f"Column local x should be upward, got {local_x_col}"

    T_raf = np.array(m.members['Raf'].T())
    local_x_raf = T_raf[0, :3]
    dx, dy = 6, 1
    L = (dx**2 + dy**2)**0.5
    expected_x = [dx/L, dy/L, 0]
    for i in range(3):
        assert abs(local_x_raf[i] - expected_x[i]) < 0.01, \
            f"Rafter local x mismatch: got {local_x_raf}, expected {expected_x}"

    local_y_raf = T_raf[1, :3]
    expected_y = [-dy/L, dx/L, 0]
    for i in range(3):
        assert abs(local_y_raf[i] - expected_y[i]) < 0.01, \
            f"Rafter local y mismatch: got {local_y_raf}, expected {expected_y}"


def _make_portal_request(span=12.0, eave=4.5, pitch=5.0, bay=7.2,
                         w_dead=0.15, w_live=0.25, supports="pinned"):
    """Standard gable portal frame request."""
    from portal_frame.models.geometry import PortalFrameGeometry
    geom = PortalFrameGeometry(
        span=span, eave_height=eave, roof_pitch=pitch,
        roof_type="gable", bay_spacing=bay,
    )
    topology = geom.to_topology()
    sec = CFS_Section(
        name="63020S2", library="test", library_name="FS", group="C",
        Ax=689.0, J=518.0, Iy=4.36e6, Iz=0.627e6,
    )
    return AnalysisRequest(
        topology=topology, column_section=sec, rafter_section=sec,
        supports=SupportCondition(left_base=supports, right_base=supports),
        load_input=LoadInput(
            dead_load_roof=w_dead, dead_load_wall=0.0,
            live_load_roof=w_live, wind_cases=[],
            include_self_weight=False,
        ),
        span=span, eave_height=eave, roof_pitch=pitch, bay_spacing=bay,
    )


def test_portal_gravity_equilibrium():
    """Vertical reactions must equal total applied vertical load."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    g_case = solver.output.case_results["G"]
    total_fy = sum(r.fy for r in g_case.reactions.values())
    expected = 0.15 * 7.2 * 12.0
    assert abs(total_fy - expected) < 0.5, f"Total Fy={total_fy}, expected={expected}"


def test_portal_symmetric_reactions():
    """Symmetric gable under gravity: left and right reactions should be equal."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    g_case = solver.output.case_results["G"]
    rxns = sorted(g_case.reactions.values(), key=lambda r: r.node_id)
    assert abs(rxns[0].fy - rxns[-1].fy) < 0.1


def test_portal_combinations_count():
    """Portal with gravity only: should have ULS-1, ULS-2, SLS-1."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    assert "ULS-1" in out.combo_results
    assert "ULS-2" in out.combo_results
    assert "SLS-1" in out.combo_results


def test_portal_uls1_is_135_times_dead():
    """ULS-1 = 1.35G: combo moment should be 1.35x dead-only moment."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    g_moment = out.case_results["G"].members[3].max_moment
    uls1_moment = out.combo_results["ULS-1"].members[3].max_moment
    assert abs(uls1_moment - 1.35 * g_moment) < 0.01


def test_portal_asymmetric_wind_equilibrium():
    """Asymmetric wind: reactions should be non-zero under wind loading."""
    from portal_frame.models.loads import WindCase
    req = _make_portal_request(span=12.0, eave=4.5, pitch=5.0, bay=7.2)
    req.load_input.wind_cases = [
        WindCase(
            name="W1", description="Test wind",
            left_wall=0.8, right_wall=-0.5,
            left_rafter=-0.9, right_rafter=-0.7,
            left_rafter_zones=[], right_rafter_zones=[],
            is_crosswind=False, direction="transverse", envelope="uplift",
        ),
    ]
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    w1_case = solver.output.case_results["W1"]
    total_rxn_fx = sum(r.fx for r in w1_case.reactions.values())
    assert abs(total_rxn_fx) > 0.1, "Should have non-zero horizontal reactions under wind"

    total_rxn_fy = sum(r.fy for r in w1_case.reactions.values())
    assert abs(total_rxn_fy) > 0.1, "Should have vertical reactions from rafter wind"
