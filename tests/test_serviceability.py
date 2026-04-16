"""Unit tests for SLS deflection checks (apex dy and eave drift)."""

import pytest

from portal_frame.analysis.results import CaseResult, NodeResult
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.standards.serviceability import (
    _actual_ratio, _apex_node_id, _classify, _eave_node_ids,
    _topology_span_m, check_apex_deflection, check_eave_drift,
)


# ─── Helpers ─────────────────────────────────────────────────────────

def _make_combo(
    name: str,
    apex_dy_mm: float = 0.0,
    eave_dx_left: float = 0.0,
    eave_dx_right: float = 0.0,
    apex_node_id: int = 3,
    left_eave_id: int = 2,
    right_eave_id: int = 4,
) -> CaseResult:
    """Build a CaseResult with apex dy + optional eave dx populated."""
    return CaseResult(
        case_name=name,
        members={},
        deflections={
            apex_node_id: NodeResult(apex_node_id, dx=0.0, dy=apex_dy_mm),
            left_eave_id: NodeResult(left_eave_id, dx=eave_dx_left, dy=0.0),
            right_eave_id: NodeResult(right_eave_id, dx=eave_dx_right, dy=0.0),
        },
        reactions={},
    )


def _default_topology():
    return PortalFrameGeometry(
        span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
    ).to_topology()


# ─── Apex node + eave node detection ─────────────────────────────────

def test_apex_detection_gable():
    topo = _default_topology()
    assert _apex_node_id(topo) == 3


def test_apex_detection_mono():
    geom = PortalFrameGeometry(
        span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0, roof_type="mono")
    topo = geom.to_topology()
    assert _apex_node_id(topo) == 3


def test_apex_detection_crane():
    geom = PortalFrameGeometry(
        span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=6.0,
        crane_rail_height=3.0)
    topo = geom.to_topology()
    assert _apex_node_id(topo) == 3


def test_topology_span_derived():
    geom = PortalFrameGeometry(span=18.5, eave_height=5.0, roof_pitch=5.0, bay_spacing=6.0)
    topo = geom.to_topology()
    assert _topology_span_m(topo) == pytest.approx(18.5)


def test_topology_span_unaffected_by_crane():
    geom = PortalFrameGeometry(
        span=15.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=6.0,
        crane_rail_height=3.0)
    topo = geom.to_topology()
    assert _topology_span_m(topo) == pytest.approx(15.0)


def test_eave_node_detection_gable():
    topo = _default_topology()
    # Gable: nodes 2 and 4 are the left/right eaves
    assert sorted(_eave_node_ids(topo)) == [2, 4]


def test_eave_node_detection_mono():
    geom = PortalFrameGeometry(
        span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0, roof_type="mono")
    topo = geom.to_topology()
    # Mono: node 2 is the left eave; node 3 is the ridge+right top
    # (column-to-rafter junction). get_eave_nodes returns nodes
    # connected to both a column and a rafter, so both 2 and 3 qualify.
    eaves = _eave_node_ids(topo)
    assert 2 in eaves
    assert 3 in eaves


# ─── Combo classification ────────────────────────────────────────────

def test_classify_wind_variants():
    assert _classify("G + 0.7Q") == "wind"
    assert _classify("G") == "wind"
    assert _classify("G + W1(s)") == "wind"
    assert _classify("W2(s) wind only") == "wind"


def test_classify_earthquake():
    assert _classify("G + E+(s)") == "eq"
    assert _classify("G + E-(s)") == "eq"


def test_classify_default_wind():
    assert _classify("") == "wind"
    assert _classify("some random thing") == "wind"


# ─── Actual-ratio helper ─────────────────────────────────────────────

def test_actual_ratio_basic():
    # 12000 / 40 = 300 -> L/300
    assert _actual_ratio(12000.0, 40.0) == 300
    # sign doesn't matter (abs)
    assert _actual_ratio(12000.0, -40.0) == 300


def test_actual_ratio_zero_deflection_capped():
    assert _actual_ratio(12000.0, 0.0) == 9999
    assert _actual_ratio(12000.0, 0.00001) == 9999


def test_actual_ratio_rounding():
    # 30000 / 166 = 180.72 -> 181
    assert _actual_ratio(30000.0, 166.0) == 181


# ─── check_apex_deflection ───────────────────────────────────────────

def test_apex_single_wind_combo():
    topo = _default_topology()
    combos = {"SLS-1": _make_combo("SLS-1", apex_dy_mm=40.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)

    assert len(result) == 1
    r = result[0]
    assert r.metric == "apex_dy"
    assert r.category == "wind"
    assert r.deflection_mm == 40.0
    assert r.ratio == 180
    assert r.limit_mm == pytest.approx(12000.0 / 180)
    assert r.actual_ratio == 300   # 12000 / 40
    assert r.util == pytest.approx(40.0 / (12000.0 / 180))
    assert r.status == "PASS"
    assert r.controlling_combo == "SLS-1"
    assert r.reference_symbol == "L"


def test_apex_worst_combo_selected():
    topo = _default_topology()
    combos = {
        "SLS-1": _make_combo("SLS-1", apex_dy_mm=40.0),
        "SLS-2": _make_combo("SLS-2", apex_dy_mm=55.0),
        "SLS-3": _make_combo("SLS-3", apex_dy_mm=-62.0),
        "SLS-4": _make_combo("SLS-4", apex_dy_mm=30.0),
    }
    descs = {k: "G + W(s)" for k in combos}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    assert len(result) == 1
    assert result[0].deflection_mm == -62.0
    assert result[0].controlling_combo == "SLS-3"


def test_apex_wind_and_eq_both_present():
    topo = _default_topology()
    combos = {
        "SLS-1": _make_combo("SLS-1", apex_dy_mm=50.0),
        "SLS-2": _make_combo("SLS-2", apex_dy_mm=-25.0),
    }
    descs = {"SLS-1": "G + W1(s)", "SLS-2": "G + E+(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)

    by_cat = {r.category: r for r in result}
    assert by_cat["wind"].deflection_mm == 50.0
    assert by_cat["eq"].deflection_mm == -25.0


def test_apex_empty_eq_omitted():
    topo = _default_topology()
    combos = {"SLS-1": _make_combo("SLS-1", apex_dy_mm=40.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    assert len(result) == 1
    assert result[0].category == "wind"


def test_apex_uls_combos_ignored():
    topo = _default_topology()
    combos = {
        "ULS-1": _make_combo("ULS-1", apex_dy_mm=999.0),
        "SLS-1": _make_combo("SLS-1", apex_dy_mm=10.0),
    }
    descs = {"ULS-1": "1.35G", "SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    assert len(result) == 1
    assert result[0].deflection_mm == 10.0


def test_apex_pass_at_exact_unity():
    topo = _default_topology()
    limit = 12000.0 / 180
    combos = {"SLS-1": _make_combo("SLS-1", apex_dy_mm=limit)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    assert result[0].util == pytest.approx(1.0)
    assert result[0].status == "PASS"


def test_apex_fail_above_unity():
    topo = _default_topology()
    limit = 12000.0 / 180
    combos = {"SLS-1": _make_combo("SLS-1", apex_dy_mm=limit * 1.01)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    assert result[0].util == pytest.approx(1.01)
    assert result[0].status == "FAIL"


def test_apex_zero_ratio_skipped():
    topo = _default_topology()
    combos = {"SLS-1": _make_combo("SLS-1", apex_dy_mm=40.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=0, limit_ratio_eq=360)
    assert result == []


def test_apex_no_deflection_in_combo():
    topo = _default_topology()
    combo_no_apex = CaseResult(
        case_name="SLS-1", members={}, deflections={}, reactions={})
    combos = {"SLS-1": combo_no_apex}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    assert result == []


def test_apex_float_ratio_accepted():
    topo = _default_topology()
    combos = {"SLS-1": _make_combo("SLS-1", apex_dy_mm=40.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180.5, limit_ratio_eq=360.0)
    assert len(result) == 1
    assert result[0].limit_mm == pytest.approx(12000.0 / 180.5)


def test_apex_eq_fails_while_wind_passes():
    topo = _default_topology()
    combos = {
        "SLS-1": _make_combo("SLS-1", apex_dy_mm=20.0),
        "SLS-2": _make_combo("SLS-2", apex_dy_mm=40.0),
    }
    descs = {"SLS-1": "G + W1(s)", "SLS-2": "G + E+(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    by_cat = {r.category: r for r in result}
    assert by_cat["wind"].status == "PASS"
    assert by_cat["eq"].status == "FAIL"


def test_apex_actual_ratio_on_check():
    """The actual_ratio on the SLSCheck matches span/|dy|."""
    topo = _default_topology()   # span = 12m
    combos = {"SLS-1": _make_combo("SLS-1", apex_dy_mm=40.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_apex_deflection(
        topo, combos, descs, limit_ratio_wind=180, limit_ratio_eq=360)
    # 12000 / 40 = 300
    assert result[0].actual_ratio == 300


# ─── check_eave_drift ────────────────────────────────────────────────

def test_drift_single_wind_combo():
    topo = _default_topology()   # eave_height = 4.5m
    combos = {"SLS-1": _make_combo("SLS-1", eave_dx_left=30.0, eave_dx_right=25.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_eave_drift(
        topo, combos, descs, limit_ratio_wind=150, limit_ratio_eq=300)

    assert len(result) == 1
    r = result[0]
    assert r.metric == "drift"
    assert r.category == "wind"
    assert r.deflection_mm == 30.0   # worst of (30, 25)
    assert r.ratio == 150
    assert r.limit_mm == pytest.approx(4500.0 / 150)
    assert r.reference_symbol == "h"
    assert r.reference_length_m == pytest.approx(4.5)
    assert r.actual_ratio == 150   # 4500 / 30


def test_drift_worst_eave_selected():
    """Left eave has the larger |dx| -> that's the reported value."""
    topo = _default_topology()
    combos = {"SLS-1": _make_combo("SLS-1", eave_dx_left=-42.0, eave_dx_right=15.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_eave_drift(
        topo, combos, descs, limit_ratio_wind=150, limit_ratio_eq=300)
    assert result[0].deflection_mm == -42.0


def test_drift_both_categories_present():
    topo = _default_topology()
    combos = {
        "SLS-1": _make_combo("SLS-1", eave_dx_right=20.0),
        "SLS-2": _make_combo("SLS-2", eave_dx_right=-18.0),
    }
    descs = {"SLS-1": "G + W1(s)", "SLS-2": "G + E+(s)"}
    result = check_eave_drift(
        topo, combos, descs, limit_ratio_wind=150, limit_ratio_eq=300)
    by_cat = {r.category: r for r in result}
    assert by_cat["wind"].deflection_mm == 20.0
    assert by_cat["eq"].deflection_mm == -18.0


def test_drift_fail_above_unity():
    topo = _default_topology()
    # limit = 4500 / 150 = 30mm -> 35mm fails
    combos = {"SLS-1": _make_combo("SLS-1", eave_dx_right=35.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_eave_drift(
        topo, combos, descs, limit_ratio_wind=150, limit_ratio_eq=300)
    assert result[0].status == "FAIL"
    assert result[0].util == pytest.approx(35.0 / 30.0)


def test_drift_actual_ratio():
    topo = _default_topology()   # eave_height = 4.5m
    combos = {"SLS-1": _make_combo("SLS-1", eave_dx_right=45.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_eave_drift(
        topo, combos, descs, limit_ratio_wind=150, limit_ratio_eq=300)
    # 4500 / 45 = 100 -> h/100
    assert result[0].actual_ratio == 100


def test_drift_zero_eave_height_returns_empty():
    """A topology with eave at y=0 (degenerate) should skip the drift check."""
    # Build a topology then monkey-patch node y to 0 to simulate degeneracy
    from portal_frame.models.geometry import Node, Member, FrameTopology
    nodes = {
        1: Node(1, 0.0, 0.0),
        2: Node(2, 0.0, 0.0),   # "eave" at y=0 — degenerate
        3: Node(3, 6.0, 1.0),
        4: Node(4, 12.0, 0.0),
        5: Node(5, 12.0, 0.0),
    }
    members = {
        1: Member(1, 1, 2, 1),
        2: Member(2, 2, 3, 2),
        3: Member(3, 3, 4, 2),
        4: Member(4, 4, 5, 1),
    }
    topo = FrameTopology(nodes=nodes, members=members)
    combos = {"SLS-1": _make_combo("SLS-1", eave_dx_right=10.0)}
    descs = {"SLS-1": "G + W1(s)"}
    result = check_eave_drift(
        topo, combos, descs, limit_ratio_wind=150, limit_ratio_eq=300)
    assert result == []
