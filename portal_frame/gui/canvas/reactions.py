"""Reaction arrow/label rendering at support nodes.

Free functions operating on a FramePreview canvas instance (passed as the
first argument). Follows the same pattern as canvas/loads.py and canvas/diagrams.py.
"""

import math

from portal_frame.gui.theme import COLORS, FONT_SMALL
from portal_frame.gui.canvas.interaction import tx as _tx
from portal_frame.gui.canvas.labels import create_boxed_draggable_label


ARROW_MAX_PX = 60       # cap on arrow length (pixels)
MZ_SCALE_FACTOR = 0.1   # MZ drawn 10x larger than proportional, since kNm is
                        # typically smaller magnitude than kN forces
MZ_ARC_RADIUS = 18      # px — curved-arrow radius for moment glyph
MZ_THRESHOLD = 0.01     # kNm below which MZ is treated as zero (pinned base)

REACTION_COLOR = "#98c379"  # soft green, visually distinct from M/V/N/delta


def draw_reactions(canvas, payload):
    """Draw reaction arrows + labels at each support node in the payload.

    payload = {
        "type": "R",
        "reactions": dict[int, ReactionResult],
        "topology_nodes": dict[int, (x_world, y_world)],
    }
    """
    reactions = payload.get("reactions") or {}
    nodes = payload.get("topology_nodes") or {}
    if not reactions or not nodes:
        return

    amp = canvas._diagram_scales.get("R", 1.0)

    max_fx = max((abs(r.fx) for r in reactions.values()), default=0.0)
    max_fy = max((abs(r.fy) for r in reactions.values()), default=0.0)
    max_mz = max((abs(r.mz) for r in reactions.values()), default=0.0)

    for nid, r in reactions.items():
        world = nodes.get(nid)
        if world is None:
            continue
        sx, sy = _tx(canvas, world[0], world[1])

        _draw_fx(canvas, sx, sy, r.fx, max_fx, amp)
        _draw_fy(canvas, sx, sy, r.fy, max_fy, amp)
        if abs(r.mz) >= MZ_THRESHOLD:
            _draw_mz(canvas, sx, sy, r.mz, max_mz, amp)

        label_text = (f"FX={r.fx:.1f} kN\n"
                      f"FY={r.fy:.1f} kN\n"
                      f"MZ={r.mz:.1f} kNm")
        create_boxed_draggable_label(
            canvas, sx + 20, sy + 30, label_text,
            label_key=f"reaction_label_{nid}",
            fg=REACTION_COLOR,
        )


def _draw_fx(canvas, sx, sy, fx, max_fx, amp):
    if max_fx <= 1e-9 or abs(fx) < 1e-9:
        return
    length = amp * ARROW_MAX_PX * (fx / max_fx)
    canvas.create_line(
        sx, sy, sx + length, sy,
        fill=REACTION_COLOR, width=2, arrow="last",
        tags=("diagram", "reaction_arrow"),
    )


def _draw_fy(canvas, sx, sy, fy, max_fy, amp):
    if max_fy <= 1e-9 or abs(fy) < 1e-9:
        return
    length = amp * ARROW_MAX_PX * (fy / max_fy)
    canvas.create_line(
        sx, sy, sx, sy - length,
        fill=REACTION_COLOR, width=2, arrow="last",
        tags=("diagram", "reaction_arrow"),
    )


def _draw_mz(canvas, sx, sy, mz, max_mz, amp):
    if max_mz <= 1e-9:
        return
    r = MZ_ARC_RADIUS * amp * min(1.0, abs(mz) / max_mz * MZ_SCALE_FACTOR * 10)
    r = max(r, 6)
    start = 30 if mz > 0 else 210
    extent = 270 if mz > 0 else -270
    canvas.create_arc(
        sx - r, sy - r, sx + r, sy + r,
        start=start, extent=extent, style="arc",
        outline=REACTION_COLOR, width=2,
        tags=("diagram", "reaction_moment"),
    )
    end_angle_rad = math.radians(start + extent)
    ax = sx + r * math.cos(end_angle_rad)
    ay = sy - r * math.sin(end_angle_rad)
    tangent = end_angle_rad + (math.pi / 2 if mz > 0 else -math.pi / 2)
    ex = ax + 4 * math.cos(tangent)
    ey = ay - 4 * math.sin(tangent)
    canvas.create_line(
        ax, ay, ex, ey,
        fill=REACTION_COLOR, width=2, arrow="last",
        tags=("diagram", "reaction_moment"),
    )
