"""Frame topology abstraction — nodes, members, and geometry builders."""

import math
from dataclasses import dataclass


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
    """Portal frame parameters — generates a 5-node/4-member 2D topology."""
    span: float           # Clear span (m)
    eave_height: float    # Eave height (m)
    roof_pitch: float     # Roof pitch (degrees)
    bay_spacing: float    # Bay spacing / tributary width (m) — for load calc

    @property
    def ridge_height(self) -> float:
        return self.eave_height + (self.span / 2.0) * math.tan(math.radians(self.roof_pitch))

    def to_topology(self) -> FrameTopology:
        """Build the standard 2D portal frame.

        Node 1 (0,0) -> Node 2 (0,eave) -> Node 3 (span/2,ridge)
        -> Node 4 (span,eave) -> Node 5 (span,0)

        Members: 1(col-L), 2(raft-L), 3(raft-R), 4(col-R)
        Section IDs: 1=column, 2=rafter
        """
        ridge = self.ridge_height
        nodes = {
            1: Node(1, 0.0, 0.0),
            2: Node(2, 0.0, self.eave_height),
            3: Node(3, self.span / 2.0, ridge),
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
