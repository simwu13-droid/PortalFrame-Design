"""Frame topology abstraction — nodes, members, and geometry builders."""

import math
from dataclasses import dataclass, field


@dataclass
class Node:
    """A point in the structural model."""
    id: int
    x: float
    y: float
    z: float = 0.0  # 3D-ready, defaults to 0 for 2D


@dataclass
class Member:
    """A structural member connecting two nodes."""
    id: int
    node_start: int  # Node ID
    node_end: int    # Node ID
    section_id: int  # Maps to section assignment (1=column, 2=rafter)


@dataclass
class FrameTopology:
    """Universal intermediate representation of a structural frame.

    Everything downstream (writers, solvers, preview) consumes FrameTopology.
    Different geometry builders produce FrameTopology instances.
    """
    nodes: dict[int, Node]
    members: dict[int, Member]

    def get_node(self, node_id: int) -> Node:
        return self.nodes[node_id]

    def get_members_at_node(self, node_id: int) -> list[Member]:
        return [m for m in self.members.values()
                if m.node_start == node_id or m.node_end == node_id]

    def get_base_nodes(self) -> list[Node]:
        """Nodes at y=0 (ground level)."""
        return [n for n in self.nodes.values() if n.y == 0.0]

    def get_eave_nodes(self) -> list[Node]:
        """Nodes at eave height (connected to both a column and a rafter)."""
        eave = []
        for n in self.nodes.values():
            members = self.get_members_at_node(n.id)
            section_ids = {m.section_id for m in members}
            if 1 in section_ids and 2 in section_ids:
                eave.append(n)
        return sorted(eave, key=lambda n: n.x)


@dataclass
class PortalFrameGeometry:
    """Portal frame parameters — generates a 2D topology.

    Supports two roof types:
      - "gable": symmetric or asymmetric pitched roof. Apex position is
                 derived from roof_pitch (left) and roof_pitch_2 (right).
                 Produces 5 nodes, 4 members.
      - "mono":  monopitch (lean-to) roof sloping from left eave up to right
                 ridge. Produces 4 nodes, 3 members.

    Defaults produce the same 5-node/4-member symmetric gable as the original
    implementation, preserving full backward compatibility.
    """
    span: float           # Clear span (m)
    eave_height: float    # Eave height (m)
    roof_pitch: float     # Roof pitch (degrees) — left rafter (alpha1)
    bay_spacing: float    # Bay spacing / tributary width (m) — for load calc
    roof_type: str = "gable"          # "gable" or "mono"
    roof_pitch_2: float | None = None  # Right rafter pitch (alpha2), None = same as roof_pitch
    # Legacy field — ignored if roof_pitch_2 is set
    apex_position_pct: float = 50.0
    crane_rail_height: float | None = None  # Height of crane bracket nodes (m)

    # ------------------------------------------------------------------
    # Derived geometry properties
    # ------------------------------------------------------------------

    @property
    def _effective_pitch_2(self) -> float:
        """Resolved right-side pitch in degrees."""
        if self.roof_pitch_2 is not None:
            return self.roof_pitch_2
        # Legacy: derive from apex_position_pct if pitch_2 not set
        if self.apex_position_pct == 50.0:
            return self.roof_pitch
        # Backward compat: compute pitch2 from apex_position_pct
        apex_x = self.span * self.apex_position_pct / 100.0
        rise = apex_x * math.tan(math.radians(self.roof_pitch))
        run = self.span - apex_x
        if run <= 0:
            return 90.0
        return math.degrees(math.atan2(rise, run))

    @property
    def apex_x(self) -> float:
        """X coordinate of the apex/ridge node.

        For gable: derived from the two pitches so both slopes meet.
            apex_x = span * tan(pitch2) / (tan(pitch1) + tan(pitch2))
        For mono:  ridge is at the far (right) end = span.
        """
        if self.roof_type == "mono":
            return self.span
        p1 = math.tan(math.radians(self.roof_pitch))
        p2 = math.tan(math.radians(self._effective_pitch_2))
        if p1 + p2 == 0:
            return self.span / 2.0
        return self.span * p2 / (p1 + p2)

    @property
    def ridge_height(self) -> float:
        """Height of the apex/ridge above ground."""
        if self.roof_type == "mono":
            return self.eave_height + self.span * math.tan(math.radians(self.roof_pitch))
        return self.eave_height + self.apex_x * math.tan(math.radians(self.roof_pitch))

    @property
    def left_pitch(self) -> float:
        """Left rafter pitch in degrees (alpha1)."""
        return self.roof_pitch

    @property
    def right_pitch(self) -> float:
        """Right rafter pitch in degrees (alpha2)."""
        if self.roof_type == "mono":
            return self.roof_pitch
        return self._effective_pitch_2

    # ------------------------------------------------------------------
    # Topology builders
    # ------------------------------------------------------------------

    def to_topology(self) -> FrameTopology:
        """Dispatch to the appropriate topology builder."""
        if self.roof_type == "mono":
            topo = self._build_mono_topology()
        else:
            topo = self._build_gable_topology()
        return self._insert_crane_brackets(topo)

    def _insert_crane_brackets(self, topo: FrameTopology) -> FrameTopology:
        """Insert crane bracket nodes into columns, splitting each column at the bracket height.

        Returns topo unchanged if crane_rail_height is None, <= 0, or >= eave_height.
        """
        h = self.crane_rail_height
        if h is None or h <= 0 or h >= self.eave_height:
            return topo

        next_node_id = max(topo.nodes) + 1
        next_member_id = max(topo.members) + 1

        # Find column members that span the bracket height
        columns_to_split = []
        for m in list(topo.members.values()):
            if m.section_id != 1:
                continue
            n_start = topo.nodes[m.node_start]
            n_end = topo.nodes[m.node_end]
            y_lo = min(n_start.y, n_end.y)
            y_hi = max(n_start.y, n_end.y)
            if y_lo < h < y_hi:
                columns_to_split.append(m)

        for m in columns_to_split:
            n_start = topo.nodes[m.node_start]
            n_end = topo.nodes[m.node_end]

            # Bracket node at same x as the column, at crane_rail_height
            bracket_node = Node(next_node_id, n_start.x, h)
            topo.nodes[next_node_id] = bracket_node

            # Determine which end is bottom and which is top
            if n_start.y < n_end.y:
                bot_id, top_id = m.node_start, m.node_end
            else:
                bot_id, top_id = m.node_end, m.node_start

            # Remove original column member
            del topo.members[m.id]

            # Add two new segments: base-to-bracket and bracket-to-top
            topo.members[next_member_id] = Member(next_member_id, bot_id, next_node_id, 1)
            next_member_id += 1
            topo.members[next_member_id] = Member(next_member_id, next_node_id, top_id, 1)
            next_member_id += 1
            next_node_id += 1

        return topo

    def _build_gable_topology(self) -> FrameTopology:
        """Build a gable (pitched) 2D portal frame.

        Node 1 (0,0) -> Node 2 (0,eave) -> Node 3 (apex_x,ridge)
        -> Node 4 (span,eave) -> Node 5 (span,0)

        Members: 1(col-L), 2(raft-L), 3(raft-R), 4(col-R)
        Section IDs: 1=column, 2=rafter
        """
        ridge = self.ridge_height
        nodes = {
            1: Node(1, 0.0, 0.0),
            2: Node(2, 0.0, self.eave_height),
            3: Node(3, self.apex_x, ridge),
            4: Node(4, self.span, self.eave_height),
            5: Node(5, self.span, 0.0),
        }
        members = {
            1: Member(1, 1, 2, 1),  # Left column
            2: Member(2, 2, 3, 2),  # Left rafter
            3: Member(3, 3, 4, 2),  # Right rafter
            4: Member(4, 4, 5, 1),  # Right column
        }
        return FrameTopology(nodes=nodes, members=members)

    def _build_mono_topology(self) -> FrameTopology:
        """Build a monopitch (lean-to) 2D portal frame.

        Node 1 (0,0) -> Node 2 (0,eave) -> Node 3 (span,ridge) -> Node 4 (span,0)

        Members: 1(col-L), 2(rafter), 3(col-R)
        Section IDs: 1=column, 2=rafter
        """
        ridge = self.ridge_height
        nodes = {
            1: Node(1, 0.0, 0.0),
            2: Node(2, 0.0, self.eave_height),
            3: Node(3, self.span, ridge),
            4: Node(4, self.span, 0.0),
        }
        members = {
            1: Member(1, 1, 2, 1),  # Left column
            2: Member(2, 2, 3, 2),  # Rafter (full span)
            3: Member(3, 3, 4, 1),  # Right column
        }
        return FrameTopology(nodes=nodes, members=members)
