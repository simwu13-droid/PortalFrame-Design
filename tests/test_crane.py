"""Tests for gantry crane module."""
from portal_frame.models.crane import CraneTransverseCombo, CraneInputs


def test_crane_transverse_combo():
    c = CraneTransverseCombo(name="Hc-U1", left=5.0, right=5.0)
    assert c.left == 5.0
    assert c.name == "Hc-U1"


def test_crane_transverse_defaults():
    c = CraneTransverseCombo(name="Hc-U1")
    assert c.left == 0.0
    assert c.right == 0.0


def test_crane_inputs():
    ci = CraneInputs(
        rail_height=3.0,
        dead_left=20.0, dead_right=20.0,
        live_left=30.0, live_right=30.0,
        transverse_uls=[CraneTransverseCombo("Hc-U1", 5.0, 5.0)],
        transverse_sls=[CraneTransverseCombo("Hc-S1", 2.7, 2.7)],
    )
    assert ci.rail_height == 3.0
    assert ci.dead_left == 20.0
    assert ci.live_left == 30.0
    assert len(ci.transverse_uls) == 1
    assert len(ci.transverse_sls) == 1


def test_crane_inputs_defaults():
    ci = CraneInputs()
    assert ci.rail_height == 3.0
    assert ci.dead_left == 0.0
    assert ci.transverse_uls == []


# --- Crane bracket topology tests ---

from portal_frame.models.geometry import PortalFrameGeometry


class TestCraneTopology:
    def test_gable_with_crane_brackets(self):
        geom = PortalFrameGeometry(span=12, eave_height=4.5, roof_pitch=5,
                                   bay_spacing=6, crane_rail_height=3.0)
        topo = geom.to_topology()
        assert len(topo.nodes) == 7   # 5 original + 2 brackets
        assert len(topo.members) == 6  # 2 columns split = 4 col segments + 2 rafters
        # Bracket nodes at correct positions
        bracket_nodes = [n for n in topo.nodes.values()
                         if abs(n.y - 3.0) < 0.01 and n.y > 0]
        assert len(bracket_nodes) == 2
        xs = sorted(n.x for n in bracket_nodes)
        assert xs == [0.0, 12.0]

    def test_mono_with_crane_brackets(self):
        geom = PortalFrameGeometry(span=12, eave_height=4.5, roof_pitch=5,
                                   bay_spacing=6, roof_type="mono",
                                   crane_rail_height=2.5)
        topo = geom.to_topology()
        assert len(topo.nodes) == 6   # 4 + 2 brackets
        assert len(topo.members) == 5  # 2 cols split = 4 + 1 rafter

    def test_without_crane_unchanged(self):
        geom = PortalFrameGeometry(span=12, eave_height=4.5, roof_pitch=5,
                                   bay_spacing=6)
        topo = geom.to_topology()
        assert len(topo.nodes) == 5
        assert len(topo.members) == 4

    def test_crane_bracket_above_eave_ignored(self):
        geom = PortalFrameGeometry(span=12, eave_height=4.5, roof_pitch=5,
                                   bay_spacing=6, crane_rail_height=5.0)
        topo = geom.to_topology()
        assert len(topo.nodes) == 5  # no brackets inserted
        assert len(topo.members) == 4

    def test_column_members_all_section_id_1(self):
        geom = PortalFrameGeometry(span=12, eave_height=4.5, roof_pitch=5,
                                   bay_spacing=6, crane_rail_height=3.0)
        topo = geom.to_topology()
        col_members = [m for m in topo.members.values() if m.section_id == 1]
        assert len(col_members) == 4  # 2 columns split into 4 segments


# --- Crane load combination tests ---

from portal_frame.standards.combinations_nzs1170_0 import build_combinations


class TestCraneCombinations:
    def test_without_crane_unchanged(self):
        uls, sls, _ = build_combinations(wind_case_names=["W1"])
        descs = [c[1] for c in uls]
        assert "1.35G" in descs
        assert not any("Gc" in d for d in descs)

    def test_with_crane_has_both_sets(self):
        uls, sls, _ = build_combinations(
            wind_case_names=["W1"],
            crane_gc_name="Gc", crane_qc_name="Qc",
            crane_hc_uls_names=["Hc-U1"],
            crane_hc_sls_names=["Hc-S1"],
        )
        descs = [c[1] for c in uls]
        # Without crane combos still present
        assert "1.35G" in descs
        assert "1.2G + 1.5Q" in descs
        # With crane combos added
        assert "1.35(G+Gc)" in descs
        assert "1.2(G+Gc) + 1.5Q" in descs

    def test_crane_live_combos(self):
        uls, sls, _ = build_combinations(
            wind_case_names=[],
            crane_gc_name="Gc", crane_qc_name="Qc",
            crane_hc_uls_names=["Hc-U1"],
        )
        descs = [c[1] for c in uls]
        assert "1.2(G+Gc) + 1.5Qc" in descs
        assert "1.2(G+Gc) + 1.5Qc + Hc-U1" in descs
        assert "0.9(G+Gc) + Hc-U1" in descs

    def test_crane_wind_combos(self):
        uls, sls, _ = build_combinations(
            wind_case_names=["W1"],
            crane_gc_name="Gc", crane_qc_name="Qc",
        )
        descs = [c[1] for c in uls]
        assert "1.2(G+Gc) + W1" in descs
        assert "0.9(G+Gc) + W1" in descs

    def test_crane_eq_combos(self):
        uls, sls, _ = build_combinations(
            wind_case_names=[],
            eq_case_names=["E+"],
            crane_gc_name="Gc", crane_qc_name="Qc",
        )
        descs = [c[1] for c in uls]
        assert "1.0(G+Gc) + E+" in descs

    def test_crane_sls_combos(self):
        uls, sls, _ = build_combinations(
            wind_case_names=["W1"],
            crane_gc_name="Gc", crane_qc_name="Qc",
            crane_hc_sls_names=["Hc-S1"],
        )
        sls_descs = [c[1] for c in sls]
        assert "(G+Gc) + 0.7Q" in sls_descs
        assert "(G+Gc)" in sls_descs
        assert "(G+Gc) + W1(s)" in sls_descs
        assert "(G+Gc) + Qc(s)" in sls_descs
        assert "(G+Gc) + Hc-S1" in sls_descs

    def test_crane_combo_factors(self):
        uls, sls, _ = build_combinations(
            wind_case_names=[],
            crane_gc_name="Gc", crane_qc_name="Qc",
            crane_hc_uls_names=["Hc-U1"],
        )
        # Find 1.2(G+Gc) + 1.5Qc + Hc-U1
        combo = next(c for c in uls if "1.5Qc + Hc-U1" in c[1])
        assert combo[2]["G"] == 1.2
        assert combo[2]["Gc"] == 1.2
        assert combo[2]["Qc"] == 1.5
        assert combo[2]["Hc-U1"] == 1.0


# --- Crane SpaceGass output tests ---


class TestCraneSpaceGassOutput:
    def _make_writer_with_crane(self):
        from portal_frame.models.geometry import PortalFrameGeometry
        from portal_frame.models.loads import LoadInput
        from portal_frame.models.crane import CraneTransverseCombo, CraneInputs
        from portal_frame.models.supports import SupportCondition
        from portal_frame.io.section_library import load_all_sections
        from portal_frame.io.spacegass_writer import SpaceGassWriter

        secs = load_all_sections()
        sec = list(secs.values())[0]
        crane = CraneInputs(
            rail_height=3.0,
            dead_left=20.0, dead_right=20.0,
            live_left=30.0, live_right=30.0,
            transverse_uls=[CraneTransverseCombo("Hc-U1", 5.0, 5.0)],
            transverse_sls=[CraneTransverseCombo("Hc-S1", 2.7, 2.7)],
        )
        geom = PortalFrameGeometry(span=12, eave_height=4.5, roof_pitch=5,
                                   bay_spacing=6, crane_rail_height=3.0)
        topo = geom.to_topology()
        loads = LoadInput(dead_load_roof=0.15, dead_load_wall=0.1, crane=crane)
        supports = SupportCondition()
        return SpaceGassWriter(topo, sec, sec, supports, loads,
                               span=12, bay_spacing=6,
                               eave_height=4.5, roof_pitch=5)

    def test_output_has_nodeloads(self):
        writer = self._make_writer_with_crane()
        output = writer.generate()
        assert "NODELOADS" in output

    def test_crane_node_loads_at_bracket_nodes(self):
        writer = self._make_writer_with_crane()
        output = writer.generate()
        lines = output.split("\n")
        # Find NODELOADS section
        in_nodeloads = False
        nodeload_lines = []
        for line in lines:
            if line.strip() == "NODELOADS":
                in_nodeloads = True
                continue
            if in_nodeloads:
                if line.strip() == "" or line.strip().startswith(("COMBINATIONS", "TITLES", "END")):
                    break
                nodeload_lines.append(line.strip())
        # Should have crane loads (Gc, Qc, Hc at 2 bracket nodes each)
        assert len(nodeload_lines) >= 6  # 3 cases x 2 nodes minimum

    def test_output_without_crane_unchanged(self):
        """Non-crane output must have no NODELOADS for crane."""
        from portal_frame.models.geometry import PortalFrameGeometry
        from portal_frame.models.loads import LoadInput
        from portal_frame.models.supports import SupportCondition
        from portal_frame.io.section_library import load_all_sections
        from portal_frame.io.spacegass_writer import SpaceGassWriter

        secs = load_all_sections()
        sec = list(secs.values())[0]
        geom = PortalFrameGeometry(span=12, eave_height=4.5, roof_pitch=5,
                                   bay_spacing=6)
        topo = geom.to_topology()
        loads = LoadInput(dead_load_roof=0.15)
        supports = SupportCondition()
        writer = SpaceGassWriter(topo, sec, sec, supports, loads,
                                 span=12, bay_spacing=6,
                                 eave_height=4.5, roof_pitch=5)
        output = writer.generate()
        # No Gc/Qc/Hc in output
        assert "Gc" not in output or "Crane" not in output

    def test_crane_titles_present(self):
        writer = self._make_writer_with_crane()
        output = writer.generate()
        assert "Crane Dead" in output
        assert "Crane Live" in output
        assert "Crane Transverse" in output

    def test_crane_combinations_present(self):
        writer = self._make_writer_with_crane()
        output = writer.generate()
        assert "1.35(G+Gc)" in output or "(G+Gc)" in output
