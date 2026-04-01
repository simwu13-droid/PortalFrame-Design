"""Unit tests for model classes."""

import pytest

from portal_frame.models.geometry import Node, Member, FrameTopology, PortalFrameGeometry
from portal_frame.models.supports import SupportCondition


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
