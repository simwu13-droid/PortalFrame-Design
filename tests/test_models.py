"""Unit tests for model classes."""

import math
import pytest

from portal_frame.models.geometry import Node, Member, FrameTopology, PortalFrameGeometry
from portal_frame.models.supports import SupportCondition
from portal_frame.models.validation import validate_roof_pitch, validate_geometry_pitch


class TestPortalFrameGeometry:
    def test_to_topology_node_count(self):
        geom = PortalFrameGeometry(span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0)
        topo = geom.to_topology()
        assert len(topo.nodes) == 5

    def test_to_topology_member_count(self):
        geom = PortalFrameGeometry(span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0)
        topo = geom.to_topology()
        assert len(topo.members) == 4

    def test_base_nodes(self):
        geom = PortalFrameGeometry(span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0)
        topo = geom.to_topology()
        base = topo.get_base_nodes()
        assert len(base) == 2
        assert all(n.y == 0.0 for n in base)

    def test_eave_nodes(self):
        geom = PortalFrameGeometry(span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0)
        topo = geom.to_topology()
        eave = topo.get_eave_nodes()
        assert len(eave) == 2
        assert all(n.y == 4.5 for n in eave)

    def test_ridge_height(self):
        geom = PortalFrameGeometry(span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0)
        assert geom.ridge_height == pytest.approx(5.0249, rel=1e-3)

    def test_node_coordinates(self):
        geom = PortalFrameGeometry(span=12.0, eave_height=4.5, roof_pitch=0.0, bay_spacing=6.0)
        topo = geom.to_topology()
        # With 0 pitch, ridge == eave
        assert topo.nodes[3].y == pytest.approx(4.5)
        assert topo.nodes[3].x == pytest.approx(6.0)  # span/2


class TestFrameTopology:
    def test_get_members_at_node(self):
        geom = PortalFrameGeometry(span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0)
        topo = geom.to_topology()
        # Node 2 (left eave) should have 2 members: column 1 and rafter 2
        members = topo.get_members_at_node(2)
        assert len(members) == 2
        member_ids = {m.id for m in members}
        assert member_ids == {1, 2}


class TestVariableApexGable:
    """Tests for gable frames with non-default (off-centre) apex positions."""

    def _geom(self, apex_pct=50.0, span=12.0, eave=4.5, pitch=5.0):
        return PortalFrameGeometry(
            span=span, eave_height=eave, roof_pitch=pitch,
            bay_spacing=6.0, roof_type="gable", apex_position_pct=apex_pct,
        )

    def test_apex_at_midspan_default(self):
        """apex_position_pct=50 produces 5 nodes with ridge at span/2."""
        topo = self._geom(apex_pct=50.0).to_topology()
        assert len(topo.nodes) == 5
        assert topo.nodes[3].x == pytest.approx(6.0)

    def test_apex_at_one_third(self):
        """Apex at 33.333% of 12 m span -> x = 4.0 m."""
        geom = self._geom(apex_pct=100.0 / 3.0, span=12.0)
        topo = geom.to_topology()
        assert topo.nodes[3].x == pytest.approx(4.0, abs=1e-6)

    def test_apex_at_two_thirds(self):
        """Apex at 66.667% of 12 m span -> x = 8.0 m."""
        geom = self._geom(apex_pct=200.0 / 3.0, span=12.0)
        topo = geom.to_topology()
        assert topo.nodes[3].x == pytest.approx(8.0, abs=1e-6)

    def test_ridge_height_uses_apex_distance(self):
        """ridge = eave + apex_x * tan(pitch), not span/2 * tan(pitch)."""
        span, eave, pitch, pct = 12.0, 4.5, 10.0, 33.333
        geom = self._geom(apex_pct=pct, span=span, eave=eave, pitch=pitch)
        apex_x = span * pct / 100.0
        expected = eave + apex_x * math.tan(math.radians(pitch))
        assert geom.ridge_height == pytest.approx(expected, rel=1e-6)

    def test_left_rafter_pitch_differs_from_right(self):
        """Off-centre apex means left_pitch != right_pitch."""
        geom = self._geom(apex_pct=33.333, span=12.0, pitch=10.0)
        # Left pitch always equals roof_pitch
        assert geom.left_pitch == pytest.approx(10.0)
        # Right pitch must be different when apex is off-centre
        assert geom.right_pitch != pytest.approx(10.0, abs=0.1)
        # Right rafter is longer (8 m run) so shallower
        assert geom.right_pitch < geom.left_pitch


class TestMonoRoofTopology:
    """Tests for monopitch (lean-to) roof frames."""

    def _geom(self, span=12.0, eave=4.5, pitch=5.0):
        return PortalFrameGeometry(
            span=span, eave_height=eave, roof_pitch=pitch,
            bay_spacing=6.0, roof_type="mono",
        )

    def test_mono_node_count(self):
        topo = self._geom().to_topology()
        assert len(topo.nodes) == 4

    def test_mono_member_count(self):
        topo = self._geom().to_topology()
        assert len(topo.members) == 3

    def test_mono_ridge_height(self):
        """ridge = eave + span * tan(pitch)."""
        span, eave, pitch = 12.0, 4.5, 5.0
        geom = self._geom(span=span, eave=eave, pitch=pitch)
        expected = eave + span * math.tan(math.radians(pitch))
        assert geom.ridge_height == pytest.approx(expected, rel=1e-6)

    def test_mono_base_nodes(self):
        topo = self._geom().to_topology()
        base = topo.get_base_nodes()
        assert len(base) == 2
        assert all(n.y == 0.0 for n in base)

    def test_mono_eave_nodes(self):
        """Both column tops connect to the single rafter -> 2 eave nodes."""
        topo = self._geom().to_topology()
        eave = topo.get_eave_nodes()
        assert len(eave) == 2

    def test_mono_right_column_height(self):
        """Right column top (node 3) should be at ridge height."""
        span, eave, pitch = 12.0, 4.5, 5.0
        geom = self._geom(span=span, eave=eave, pitch=pitch)
        topo = geom.to_topology()
        expected_ridge = eave + span * math.tan(math.radians(pitch))
        # Node 3 is the top of the right column / high end of rafter
        assert topo.nodes[3].y == pytest.approx(expected_ridge, rel=1e-6)
        assert topo.nodes[3].x == pytest.approx(span)

    def test_mono_single_rafter(self):
        """Exactly one member with section_id=2 (rafter)."""
        topo = self._geom().to_topology()
        rafters = [m for m in topo.members.values() if m.section_id == 2]
        assert len(rafters) == 1


class TestPitchValidation:
    def test_normal_pitch_no_warnings(self):
        warnings = validate_roof_pitch(5.0)
        assert warnings == []

    def test_low_pitch_warning(self):
        warnings = validate_roof_pitch(2.0)
        assert len(warnings) == 1
        assert "ponding" in warnings[0].lower()

    def test_exactly_3deg_no_warning(self):
        warnings = validate_roof_pitch(3.0)
        assert warnings == []

    def test_high_pitch_warning(self):
        warnings = validate_roof_pitch(35.0)
        assert len(warnings) == 1
        assert "30" in warnings[0]

    def test_exactly_30deg_no_warning(self):
        warnings = validate_roof_pitch(30.0)
        assert warnings == []

    def test_gable_both_pitches_checked(self):
        """For off-center apex, the shallower side may be below 3 deg."""
        geom = PortalFrameGeometry(
            span=20.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
            roof_type="gable", apex_position_pct=20.0,
        )
        warnings = validate_geometry_pitch(geom)
        # Right side pitch: rise over 80% of span — likely < 3 deg
        assert any("right rafter" in w.lower() or "ponding" in w.lower() for w in warnings)
