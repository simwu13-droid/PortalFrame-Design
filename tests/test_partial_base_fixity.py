"""Tests for partial base fixity feature."""

import pytest

from portal_frame.models.supports import SupportCondition


def test_support_condition_defaults_unchanged():
    s = SupportCondition()
    assert s.left_base == "pinned"
    assert s.right_base == "pinned"
    assert s.fixity_percent == 0.0


def test_support_condition_accepts_partial():
    s = SupportCondition(left_base="partial", right_base="pinned",
                         fixity_percent=25.0)
    assert s.left_base == "partial"
    assert s.right_base == "pinned"
    assert s.fixity_percent == 25.0


from portal_frame.solvers.pynite_solver import PyNiteSolver


class _StubSection:
    def __init__(self, Iz_m):
        self.Ax_m = 1e-3
        self.Iy_m = 1e-6
        self.Iz_m = Iz_m
        self.J_m = 1e-6


class _StubNode:
    def __init__(self, nid, x, y):
        self.id = nid
        self.x = x
        self.y = y


class _StubTopology:
    def __init__(self, base_y, knee_y):
        self.nodes = {
            1: _StubNode(1, 0.0, base_y),
            2: _StubNode(2, 0.0, knee_y),
        }


class _StubRequest:
    def __init__(self, Iz_m, L, alpha_pct):
        self.column_section = _StubSection(Iz_m)
        self.topology = _StubTopology(base_y=0.0, knee_y=L)

        class S:
            pass
        self.supports = S()
        self.supports.fixity_percent = alpha_pct


def test_compute_partial_ktheta_linear_formula():
    # E = 200e6 kN/m^2, Iz = 1e-6 m^4, L = 6.0 m, alpha = 50%
    # k = 0.50 * 4 * 200e6 * 1e-6 / 6.0 = 66.666... kN·m/rad
    solver = PyNiteSolver()
    solver._request = _StubRequest(Iz_m=1e-6, L=6.0, alpha_pct=50.0)
    base_node = solver._request.topology.nodes[1]
    k = solver._compute_partial_ktheta(base_node)
    assert k == pytest.approx(400.0 / 6.0, rel=1e-9)


def test_compute_partial_ktheta_alpha_zero_returns_zero():
    solver = PyNiteSolver()
    solver._request = _StubRequest(Iz_m=1e-6, L=6.0, alpha_pct=0.0)
    base_node = solver._request.topology.nodes[1]
    assert solver._compute_partial_ktheta(base_node) == 0.0


def test_compute_partial_ktheta_alpha_clamped_to_100():
    # alpha > 100 clamps to 100
    solver = PyNiteSolver()
    solver._request = _StubRequest(Iz_m=1e-6, L=6.0, alpha_pct=150.0)
    base_node = solver._request.topology.nodes[1]
    k_150 = solver._compute_partial_ktheta(base_node)
    solver._request.supports.fixity_percent = 100.0
    k_100 = solver._compute_partial_ktheta(base_node)
    assert k_150 == pytest.approx(k_100)


from portal_frame.solvers.base import AnalysisRequest
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import LoadInput, RafterZoneLoad, WindCase
from portal_frame.io.section_library import load_all_sections


def _base_request(supports: SupportCondition) -> AnalysisRequest:
    sections = load_all_sections()
    col = sections["63020S2"]
    raf = sections["63020S2"]
    geom = PortalFrameGeometry(
        span=10.0, eave_height=4.0, roof_pitch=10.0, roof_pitch_2=10.0,
        bay_spacing=6.0,
    )
    topo = geom.to_topology()
    wind = WindCase(
        name="W1",
        description="Crosswind max uplift",
        left_wall=0.5, right_wall=-0.3,
        left_rafter_zones=[RafterZoneLoad(0.0, 100.0, -0.5)],
        right_rafter_zones=[RafterZoneLoad(0.0, 100.0, -0.5)],
    )
    loads = LoadInput(
        dead_load_roof=0.15, dead_load_wall=0.10, live_load_roof=0.25,
        wind_cases=[wind],
    )
    return AnalysisRequest(
        span=10.0, eave_height=4.0, roof_pitch=10.0, bay_spacing=6.0,
        topology=topo, column_section=col, rafter_section=raf,
        supports=supports, load_input=loads,
    )


def _apex_dy(case_results):
    out = case_results["G"]
    worst = 0.0
    for m in out.members.values():
        for s in m.stations:
            if abs(s.dy_local) > abs(worst):
                worst = s.dy_local
    return worst


def test_partial_alpha_zero_matches_pinned():
    req_pinned = _base_request(SupportCondition(left_base="pinned",
                                                right_base="pinned"))
    req_zero = _base_request(SupportCondition(left_base="partial",
                                              right_base="partial",
                                              fixity_percent=0.0,
                                              sls_partial_only=False))
    s1 = PyNiteSolver(); s1.build_model(req_pinned); s1.solve()
    s2 = PyNiteSolver(); s2.build_model(req_zero); s2.solve()
    dy_pinned = _apex_dy(s1.output.case_results)
    dy_zero = _apex_dy(s2.output.case_results)
    assert dy_pinned == pytest.approx(dy_zero, rel=1e-6, abs=1e-9)


def test_partial_reduces_apex_deflection_monotonically():
    reqs = [
        _base_request(SupportCondition(left_base="partial",
                                       right_base="partial",
                                       fixity_percent=p,
                                       sls_partial_only=False))
        for p in (0.0, 25.0, 50.0, 75.0, 99.0)
    ]
    dys = []
    for req in reqs:
        s = PyNiteSolver(); s.build_model(req); s.solve()
        dys.append(abs(_apex_dy(s.output.case_results)))
    for a, b in zip(dys, dys[1:]):
        assert b <= a + 1e-9, f"non-monotonic: {dys}"
    assert dys[-1] < dys[0]


def test_partial_asymmetric_fixity_produces_unequal_base_moments():
    req = _base_request(SupportCondition(left_base="partial",
                                         right_base="pinned",
                                         fixity_percent=50.0,
                                         sls_partial_only=False))
    s = PyNiteSolver(); s.build_model(req); s.solve()
    reactions = s.output.case_results["G"].reactions
    base_nodes = sorted(reactions.keys())
    mz_left = reactions[base_nodes[0]].mz
    mz_right = reactions[base_nodes[-1]].mz
    # Pinned side must carry ~zero MZ; partial side must not
    assert abs(mz_right) < 1e-3
    assert abs(mz_left) > 1e-2


def _make_writer(supports: SupportCondition):
    from portal_frame.io.spacegass_writer import SpaceGassWriter
    req = _base_request(supports)
    return SpaceGassWriter(
        topology=req.topology,
        column_section=req.column_section,
        rafter_section=req.rafter_section,
        supports=req.supports,
        loads=req.load_input,
        span=req.span,
        eave_height=req.eave_height,
        roof_pitch=req.roof_pitch,
        bay_spacing=req.bay_spacing,
    )


def test_sg_writer_emits_partial_fixity_comment(tmp_path):
    writer = _make_writer(SupportCondition(left_base="partial",
                                           right_base="pinned",
                                           fixity_percent=35.0))
    text = writer.write()
    assert "partial base fixity" in text
    assert "alpha = 35" in text


def test_sg_writer_no_partial_comment_when_all_pinned(tmp_path):
    writer = _make_writer(SupportCondition(left_base="pinned",
                                           right_base="pinned"))
    text = writer.write()
    assert "partial base fixity" not in text


def test_support_condition_roundtrip_via_dict():
    original = SupportCondition(left_base="partial", right_base="pinned",
                                fixity_percent=42.5)
    d = {
        "left_base": original.left_base,
        "right_base": original.right_base,
        "fixity_percent": original.fixity_percent,
    }
    restored = SupportCondition(
        left_base=d["left_base"], right_base=d["right_base"],
        fixity_percent=d["fixity_percent"],
    )
    assert restored == original


def test_sls_only_toggle_uls_matches_pinned_case_results():
    # When sls_partial_only=True, the case_results on AnalysisOutput are
    # the pinned (ULS) version — should match a pure pinned run.
    req_pinned = _base_request(SupportCondition(
        left_base="pinned", right_base="pinned"))
    req_sls_only = _base_request(SupportCondition(
        left_base="partial", right_base="partial",
        fixity_percent=50.0, sls_partial_only=True))

    s1 = PyNiteSolver(); s1.build_model(req_pinned); s1.solve()
    s2 = PyNiteSolver(); s2.build_model(req_sls_only); s2.solve()

    dy_pinned = _apex_dy(s1.output.case_results)
    dy_sls_only = _apex_dy(s2.output.case_results)
    assert dy_pinned == pytest.approx(dy_sls_only, rel=1e-6, abs=1e-9)


def test_sls_only_toggle_uls_combos_match_pinned():
    # ULS-1 (1.35G) under sls_partial_only should equal ULS-1 under all-pinned.
    req_pinned = _base_request(SupportCondition(
        left_base="pinned", right_base="pinned"))
    req_sls_only = _base_request(SupportCondition(
        left_base="partial", right_base="partial",
        fixity_percent=50.0, sls_partial_only=True))

    s1 = PyNiteSolver(); s1.build_model(req_pinned); s1.solve()
    s2 = PyNiteSolver(); s2.build_model(req_sls_only); s2.solve()

    def _worst_combo_dy(output, prefix):
        worst = 0.0
        for name, cr in output.combo_results.items():
            if not name.startswith(prefix):
                continue
            for m in cr.members.values():
                for s in m.stations:
                    if abs(s.dy_local) > abs(worst):
                        worst = s.dy_local
        return worst

    uls_pinned = _worst_combo_dy(s1.output, "ULS-")
    uls_sls_only = _worst_combo_dy(s2.output, "ULS-")
    assert uls_pinned == pytest.approx(uls_sls_only, rel=1e-6, abs=1e-9)


def test_sls_only_toggle_sls_combos_differ_from_pinned():
    # SLS combos under sls_partial_only should differ from a pure pinned run,
    # because the SLS combos used partial-fixity stiffness.
    req_pinned = _base_request(SupportCondition(
        left_base="pinned", right_base="pinned"))
    req_sls_only = _base_request(SupportCondition(
        left_base="partial", right_base="partial",
        fixity_percent=50.0, sls_partial_only=True))

    s1 = PyNiteSolver(); s1.build_model(req_pinned); s1.solve()
    s2 = PyNiteSolver(); s2.build_model(req_sls_only); s2.solve()

    def _worst_sls_dy(output):
        worst = 0.0
        for name, cr in output.combo_results.items():
            if not name.startswith("SLS-"):
                continue
            for m in cr.members.values():
                for s in m.stations:
                    if abs(s.dy_local) > abs(worst):
                        worst = s.dy_local
        return worst

    sls_pinned = _worst_sls_dy(s1.output)
    sls_sls_only = _worst_sls_dy(s2.output)
    # Partial-fixity reduces SLS δ versus pinned — they must differ
    assert abs(sls_sls_only) < abs(sls_pinned)
