"""Frame preview canvas — 2D rendering of portal frame with loads."""

import tkinter as tk
import math

from portal_frame.gui.theme import COLORS, FONT_SMALL


class FramePreview(tk.Canvas):
    """Live 2D sketch of the portal frame with optional UDL arrows."""

    ARROW_COLOR = COLORS["frame_load"]
    ARROW_SPACING = 22
    ARROW_MAX_LEN = 40

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=COLORS["canvas_bg"], highlightthickness=0, **kw)
        self.bind("<Configure>", lambda e: self.after_idle(self._on_resize))
        self._geom = None
        self._supports = ("pinned", "pinned")
        self._loads = None

    def _on_resize(self, *_):
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads)

    def update_frame(self, geom: dict, supports: tuple, loads: dict = None):
        self._geom = geom
        self._supports = supports
        self._loads = loads
        self.delete("all")

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 50 or h < 50:
            return

        span = geom.get("span", 12)
        eave = geom.get("eave_height", 4.5)
        pitch = geom.get("roof_pitch", 5)
        pitch2 = geom.get("roof_pitch_2", pitch)
        roof_type = geom.get("roof_type", "gable")

        # Use pre-computed values from geometry model if available
        ridge = geom.get("ridge_height", None)
        apex_x = geom.get("apex_x", None)

        if roof_type == "mono":
            if ridge is None:
                ridge = eave + span * math.tan(math.radians(pitch))
            nodes = {
                1: (0, 0),
                2: (0, eave),
                3: (span, ridge),
                4: (span, 0),
            }
        else:
            if apex_x is None:
                p1 = math.tan(math.radians(pitch))
                p2 = math.tan(math.radians(pitch2))
                apex_x = span * p2 / (p1 + p2) if (p1 + p2) > 0 else span / 2.0
            if ridge is None:
                ridge = eave + apex_x * math.tan(math.radians(pitch))
            nodes = {
                1: (0, 0),
                2: (0, eave),
                3: (apex_x, ridge),
                4: (span, eave),
                5: (span, 0),
            }

        # Draw grid
        for i in range(0, w, 30):
            self.create_line(i, 0, i, h, fill=COLORS["canvas_grid"], dash=(1, 4))
        for i in range(0, h, 30):
            self.create_line(0, i, w, i, fill=COLORS["canvas_grid"], dash=(1, 4))

        # Scale to fit
        pad_side = 50
        pad_top = 80
        pad_bot = 50
        total_h = ridge * 1.0
        scale_x = (w - 2 * pad_side) / span if span > 0 else 1
        scale_y = (h - pad_top - pad_bot) / total_h if total_h > 0 else 1
        scale = min(scale_x, scale_y)

        ox = pad_side + (w - 2 * pad_side - span * scale) / 2
        oy = h - pad_bot

        def tx(x, y):
            return ox + x * scale, oy - y * scale

        # Ground line
        gx1 = ox - 20
        gx2 = ox + span * scale + 20
        gy = oy
        self.create_line(gx1, gy, gx2, gy, fill=COLORS["fg_dim"], width=1, dash=(4, 2))

        # Transform nodes to screen coords
        ns = {k: tx(*v) for k, v in nodes.items()}

        # Members
        if roof_type == "mono":
            self.create_line(*ns[1], *ns[2], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[2], *ns[3], fill=COLORS["frame_raf"], width=3)
            self.create_line(*ns[3], *ns[4], fill=COLORS["frame_col"], width=3)
        else:
            self.create_line(*ns[1], *ns[2], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[5], *ns[4], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[2], *ns[3], fill=COLORS["frame_raf"], width=3)
            self.create_line(*ns[3], *ns[4], fill=COLORS["frame_raf"], width=3)

        # Nodes
        r = 4
        for pt in ns.values():
            self.create_oval(pt[0]-r, pt[1]-r, pt[0]+r, pt[1]+r,
                             fill=COLORS["frame_node"], outline="")

        # Supports — find base nodes (y==0), sorted by x
        base_nodes = sorted(
            [(nid, coord) for nid, coord in nodes.items() if coord[1] == 0],
            key=lambda item: item[1][0]
        )
        base_node_ids = [nid for nid, _ in base_nodes]
        support_pairs = []
        if len(base_node_ids) >= 2:
            support_pairs = [
                (base_node_ids[0], supports[0]),
                (base_node_ids[-1], supports[1]),
            ]

        for nid, condition in support_pairs:
            bx, by = ns[nid]
            if condition == "pinned":
                sz = 12
                self.create_polygon(
                    bx, by, bx - sz, by + sz, bx + sz, by + sz,
                    outline=COLORS["frame_support"], fill="", width=2
                )
                for j in range(-1, 2):
                    hx = bx + j * 8
                    self.create_line(hx - 4, by + sz + 2, hx + 4, by + sz + 8,
                                     fill=COLORS["frame_support"], width=1)
            else:
                sz = 10
                self.create_rectangle(
                    bx - sz, by, bx + sz, by + sz * 1.5,
                    outline=COLORS["frame_support"], fill=COLORS["frame_support"],
                    stipple="gray50", width=2
                )

        # UDL load arrows
        if loads:
            self._draw_loads(loads, ns, scale)

        # Dimension annotations
        dim_col = COLORS["fg_dim"]

        # Span annotation using actual base node screen positions
        left_base_sx = ns[base_node_ids[0]][0] if base_node_ids else ox
        right_base_sx = ns[base_node_ids[-1]][0] if len(base_node_ids) >= 2 else ox + span * scale

        dy = oy + 30
        self.create_line(left_base_sx, dy, right_base_sx, dy,
                         fill=dim_col, width=1, arrow="both")
        self.create_text((left_base_sx + right_base_sx) / 2, dy + 12,
                         text=f"{span:.1f} m", fill=dim_col, font=FONT_SMALL, anchor="n")

        # Eave height annotation
        dx = ns[1][0] - 25
        self.create_line(dx, ns[1][1], dx, ns[2][1], fill=dim_col, width=1, arrow="both")
        self.create_text(dx - 5, (ns[1][1] + ns[2][1]) / 2, text=f"{eave:.1f} m",
                         fill=dim_col, font=FONT_SMALL, anchor="e")

        if roof_type == "gable":
            # Rise annotation at ridge (node 3)
            dx2 = ns[3][0]
            self.create_line(dx2, ns[2][1], dx2, ns[3][1], fill=dim_col, width=1, arrow="both")
            rise = ridge - eave
            self.create_text(dx2 + 10, (ns[2][1] + ns[3][1]) / 2, text=f"{rise:.2f} m",
                             fill=dim_col, font=FONT_SMALL, anchor="w")
            # Left rafter pitch
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            self.create_text(mx - 15, my - 12, text=f"a1={pitch:.1f}",
                             fill=COLORS["frame_raf"], font=FONT_SMALL, anchor="e")
            # Right rafter pitch
            mx2 = (ns[3][0] + ns[4][0]) / 2
            my2 = (ns[3][1] + ns[4][1]) / 2
            self.create_text(mx2 + 15, my2 - 12, text=f"a2={pitch2:.1f}",
                             fill=COLORS["frame_raf"], font=FONT_SMALL, anchor="w")
        else:
            # Pitch label along the single rafter for mono
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            self.create_text(mx, my - 12, text=f"{pitch:.1f} deg",
                             fill=COLORS["frame_raf"], font=FONT_SMALL, anchor="s")

        # Legend
        ly = 15
        lx = 10
        self.create_line(lx, ly, lx + 20, ly, fill=COLORS["frame_col"], width=2)
        self.create_text(lx + 25, ly, text="Column", fill=COLORS["fg_dim"],
                         font=FONT_SMALL, anchor="w")
        ly += 16
        self.create_line(lx, ly, lx + 20, ly, fill=COLORS["frame_raf"], width=2)
        self.create_text(lx + 25, ly, text="Rafter", fill=COLORS["fg_dim"],
                         font=FONT_SMALL, anchor="w")
        if loads:
            ly += 16
            self.create_line(lx, ly, lx + 20, ly, fill=self.ARROW_COLOR, width=2)
            self.create_text(lx + 25, ly, text="Load", fill=COLORS["fg_dim"],
                             font=FONT_SMALL, anchor="w")

    def _draw_loads(self, loads, ns, scale):
        members = loads.get("members", [])
        point_loads = loads.get("point_loads", [])

        if members:
            max_w = 0
            for mem in members:
                for seg in mem.get("segments", []):
                    max_w = max(max_w, abs(seg.get("w_kn", 0)))
            if max_w > 0:
                for mem in members:
                    n_from = ns[mem["from"]]
                    n_to = ns[mem["to"]]
                    for seg in mem.get("segments", []):
                        self._draw_udl_segment(n_from, n_to, seg, max_w, scale)

        for pl in point_loads:
            nid = pl["node"]
            if nid not in ns:
                continue
            px, py = ns[nid]
            fx = pl.get("fx", 0)
            fy = pl.get("fy", 0)
            label = pl.get("label", "")
            arrow_len = 50
            if fx != 0:
                dx = arrow_len if fx > 0 else -arrow_len
                self.create_line(px - dx, py, px, py,
                                 fill=self.ARROW_COLOR, width=2,
                                 arrow="last", arrowshape=(10, 12, 5))
                self.create_text(px - dx/2, py - 12,
                                 text=f"{abs(fx):.2f} kN",
                                 fill=self.ARROW_COLOR, font=FONT_SMALL)
            if fy != 0:
                dy = arrow_len if fy > 0 else -arrow_len
                self.create_line(px, py + dy, px, py,
                                 fill=self.ARROW_COLOR, width=2,
                                 arrow="last", arrowshape=(10, 12, 5))
                self.create_text(px + 15, py + dy/2,
                                 text=f"{abs(fy):.2f} kN",
                                 fill=self.ARROW_COLOR, font=FONT_SMALL)

    def _draw_udl_segment(self, n_from, n_to, seg, max_w, scale):
        w_kn = seg.get("w_kn", 0)
        if abs(w_kn) < 1e-6:
            return

        s_pct = seg.get("start_pct", 0) / 100.0
        e_pct = seg.get("end_pct", 100) / 100.0
        direction = seg.get("direction", "normal")

        sx = n_from[0] + (n_to[0] - n_from[0]) * s_pct
        sy = n_from[1] + (n_to[1] - n_from[1]) * s_pct
        ex = n_from[0] + (n_to[0] - n_from[0]) * e_pct
        ey = n_from[1] + (n_to[1] - n_from[1]) * e_pct

        mem_dx = n_to[0] - n_from[0]
        mem_dy = n_to[1] - n_from[1]
        mem_len = math.hypot(mem_dx, mem_dy)
        if mem_len < 1:
            return

        if direction == "global_y":
            ax, ay = 0, 1
            if w_kn < 0:
                ax, ay = 0, -1
        elif direction == "global_x":
            ax, ay = 1, 0
            if w_kn < 0:
                ax, ay = -1, 0
        else:
            nx = -mem_dy / mem_len
            ny = mem_dx / mem_len
            if w_kn > 0:
                ax, ay = nx, ny
            else:
                ax, ay = -nx, -ny

        arrow_len = (abs(w_kn) / max_w) * self.ARROW_MAX_LEN

        seg_dx = ex - sx
        seg_dy = ey - sy
        seg_len = math.hypot(seg_dx, seg_dy)
        if seg_len < 5:
            return

        n_arrows = max(2, int(seg_len / self.ARROW_SPACING))

        bx1 = sx - ax * arrow_len
        by1 = sy - ay * arrow_len
        bx2 = ex - ax * arrow_len
        by2 = ey - ay * arrow_len
        self.create_line(bx1, by1, bx2, by2, fill=self.ARROW_COLOR, width=1)

        for i in range(n_arrows + 1):
            t = i / n_arrows
            px = sx + seg_dx * t
            py = sy + seg_dy * t
            tail_x = px - ax * arrow_len
            tail_y = py - ay * arrow_len
            self.create_line(tail_x, tail_y, px, py,
                             fill=self.ARROW_COLOR, width=1,
                             arrow="last", arrowshape=(6, 7, 3))

        mid_x = (sx + ex) / 2 - ax * (arrow_len + 10)
        mid_y = (sy + ey) / 2 - ay * (arrow_len + 10)
        self.create_text(mid_x, mid_y, text=f"{abs(w_kn):.2f} kN/m",
                         fill=self.ARROW_COLOR, font=FONT_SMALL, anchor="center")
