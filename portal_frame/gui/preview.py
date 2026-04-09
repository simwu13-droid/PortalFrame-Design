"""Frame preview canvas — 2D rendering of portal frame with loads."""

import tkinter as tk
import math

from portal_frame.gui.theme import COLORS, FONT_SMALL


DIAGRAM_COLORS = {
    "M": "#e06c75",   # Red-pink for moment
    "V": "#c678dd",   # Purple for shear
    "N": "#e5c07b",   # Gold for axial
    "δ": "#61afef",   # Blue for deflection
}
DIAGRAM_MAX_PX = 60


class FramePreview(tk.Canvas):
    """Live 2D sketch of the portal frame with optional UDL arrows.

    All text labels are draggable — click and drag to reposition.
    Labels auto-nudge to avoid overlap on each redraw.
    """

    ARROW_COLOR = COLORS["frame_load"]
    ARROW_SPACING = 22
    ARROW_MAX_LEN = 40
    LABEL_PAD = 4        # padding around label bboxes for collision
    NUDGE_STEP = 14       # pixels to nudge on each collision pass
    NUDGE_MAX_PASSES = 8  # maximum collision resolution iterations

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=COLORS["canvas_bg"], highlightthickness=0, **kw)
        self.bind("<Configure>", lambda e: self.after_idle(self._on_resize))
        self._geom = None
        self._supports = ("pinned", "pinned")
        self._loads = None
        self._diagram = None
        # Drag state
        self._drag_item = None
        self._drag_label_key = None
        self._drag_offset = (0, 0)
        # User-adjusted label offsets: key -> (dx, dy) from original position
        self._label_offsets = {}

    def _on_resize(self, *_):
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)

    # ── Draggable label infrastructure ──

    def _make_draggable(self, item_id, label_key):
        """Bind drag events to a canvas text item."""
        self.tag_bind(item_id, "<ButtonPress-1>", lambda e: self._drag_start(e, item_id, label_key))
        self.tag_bind(item_id, "<B1-Motion>", self._drag_move)
        self.tag_bind(item_id, "<ButtonRelease-1>", self._drag_end)
        self.tag_bind(item_id, "<Enter>", lambda e: self.config(cursor="fleur"))
        self.tag_bind(item_id, "<Leave>", lambda e: self.config(cursor=""))

    def _drag_start(self, event, item_id, label_key):
        self._drag_item = item_id
        self._drag_label_key = label_key
        ix, iy = self.coords(item_id)
        self._drag_offset = (event.x - ix, event.y - iy)

    def _drag_move(self, event):
        if self._drag_item is None:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        # Clamp within canvas
        nx = max(5, min(event.x - self._drag_offset[0], w - 5))
        ny = max(5, min(event.y - self._drag_offset[1], h - 5))
        self.coords(self._drag_item, nx, ny)

    def _drag_end(self, event):
        if self._drag_item is None:
            return
        # Store the user offset so it persists across redraws
        cx, cy = self.coords(self._drag_item)
        key = self._drag_label_key
        if key and key in self._label_positions:
            ox, oy = self._label_positions[key]
            self._label_offsets[key] = (cx - ox, cy - oy)
        self._drag_item = None

    def _create_label(self, x, y, text, label_key, fill=None, font=None, anchor="center"):
        """Create a text label that is draggable and tracked for collision."""
        if fill is None:
            fill = COLORS["fg_dim"]
        if font is None:
            font = FONT_SMALL

        # Apply user offset if they previously dragged this label
        ux, uy = self._label_offsets.get(label_key, (0, 0))
        fx, fy = x + ux, y + uy

        # Clamp within canvas
        w = self.winfo_width()
        h = self.winfo_height()
        fx = max(5, min(fx, w - 5))
        fy = max(8, min(fy, h - 8))

        item = self.create_text(fx, fy, text=text, fill=fill, font=font,
                                anchor=anchor, tags=("label",))
        self._make_draggable(item, label_key)
        # Store original (un-offset) position for drag delta calculation
        self._label_positions[label_key] = (x, y)
        self._label_items.append(item)
        self._item_to_key[item] = label_key
        return item

    def _resolve_overlaps(self):
        """Nudge auto-placed labels that overlap. User-dragged labels are not moved."""
        self.update_idletasks()  # ensure bbox() returns valid geometry
        for _ in range(self.NUDGE_MAX_PASSES):
            moved = False
            items = list(self._label_items)
            bboxes = {}
            for item in items:
                bb = self.bbox(item)
                if bb:
                    bboxes[item] = bb

            for i, a in enumerate(items):
                if a not in bboxes:
                    continue
                ax1, ay1, ax2, ay2 = bboxes[a]
                p = self.LABEL_PAD
                for b in items[i+1:]:
                    if b not in bboxes:
                        continue
                    # Skip nudging labels the user has manually dragged
                    b_key = self._item_to_key.get(b)
                    if b_key and b_key in self._label_offsets:
                        continue
                    bx1, by1, bx2, by2 = bboxes[b]
                    if (ax1 - p < bx2 + p and ax2 + p > bx1 - p and
                            ay1 - p < by2 + p and ay2 + p > by1 - p):
                        cx_a = (ax1 + ax2) / 2
                        cy_a = (ay1 + ay2) / 2
                        cx_b = (bx1 + bx2) / 2
                        cy_b = (by1 + by2) / 2
                        dx = cx_b - cx_a
                        dy = cy_b - cy_a
                        dist = math.hypot(dx, dy)
                        if dist < 1:
                            dx, dy = 0, 1
                            dist = 1
                        nx = dx / dist * self.NUDGE_STEP
                        ny = dy / dist * self.NUDGE_STEP
                        self.move(b, nx, ny)
                        bboxes[b] = self.bbox(b)
                        moved = True
            if not moved:
                break
        # Final clamp: ensure all labels stay within canvas
        w = self.winfo_width()
        h = self.winfo_height()
        for item in self._label_items:
            bb = self.bbox(item)
            if not bb:
                continue
            x1, y1, x2, y2 = bb
            shift_x = 0
            shift_y = 0
            if x1 < 2:
                shift_x = 2 - x1
            elif x2 > w - 2:
                shift_x = (w - 2) - x2
            if y1 < 2:
                shift_y = 2 - y1
            elif y2 > h - 2:
                shift_y = (h - 2) - y2
            if shift_x or shift_y:
                self.move(item, shift_x, shift_y)

    # ── Main draw ──

    def update_frame(self, geom: dict, supports: tuple, loads: dict = None, diagram: dict = None):
        self._geom = geom
        self._supports = supports
        self._loads = loads
        self._diagram = diagram
        self.delete("all")
        self._label_items = []
        self._label_positions = {}
        self._item_to_key = {}

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 50 or h < 50:
            return

        span = geom.get("span", 12)
        eave = geom.get("eave_height", 4.5)
        pitch = geom.get("roof_pitch", 5)
        pitch2 = geom.get("roof_pitch_2", pitch)
        roof_type = geom.get("roof_type", "gable")

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

        # Scale to fit — generous padding for loads + annotations
        has_loads = bool(loads and loads.get("members"))
        pad_side = 100 if has_loads else 55
        pad_top = 80
        pad_bot = 55
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

        # Transform nodes
        ns = {k: tx(*v) for k, v in nodes.items()}

        # Members — use dimmed colors when δ diagram is active so the
        # deflection curve stands out against the structure.
        is_deflection = bool(diagram and diagram.get("type") == "δ")
        col_color = COLORS["frame_col_dim"] if is_deflection else COLORS["frame_col"]
        raf_color = COLORS["frame_raf_dim"] if is_deflection else COLORS["frame_raf"]

        if roof_type == "mono":
            self.create_line(*ns[1], *ns[2], fill=col_color, width=3)
            self.create_line(*ns[2], *ns[3], fill=raf_color, width=3)
            self.create_line(*ns[3], *ns[4], fill=col_color, width=3)
        else:
            self.create_line(*ns[1], *ns[2], fill=col_color, width=3)
            self.create_line(*ns[5], *ns[4], fill=col_color, width=3)
            self.create_line(*ns[2], *ns[3], fill=raf_color, width=3)
            self.create_line(*ns[3], *ns[4], fill=raf_color, width=3)

        # Crane bracket nodes (if crane_rail_height is set)
        crane_h = geom.get("crane_rail_height")
        if crane_h is not None and 0 < crane_h < eave:
            # Draw bracket markers on each column
            bracket_left = tx(0, crane_h)
            bracket_right = tx(span, crane_h)
            ns["bracket_left"] = bracket_left
            ns["bracket_right"] = bracket_right
            br = 5
            for bpt in [bracket_left, bracket_right]:
                self.create_rectangle(
                    bpt[0] - br, bpt[1] - br, bpt[0] + br, bpt[1] + br,
                    fill=COLORS["warning"], outline=COLORS["fg_bright"], width=1)

        # Nodes
        r = 4
        for key, pt in ns.items():
            if isinstance(key, str) and key.startswith("bracket"):
                continue  # bracket nodes already drawn as squares
            self.create_oval(pt[0]-r, pt[1]-r, pt[0]+r, pt[1]+r,
                             fill=COLORS["frame_node"], outline="")

        # Supports
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

        # ── Dimension annotations (all as draggable labels) ──
        dim_col = COLORS["fg_dim"]

        # Span
        left_base_sx = ns[base_node_ids[0]][0] if base_node_ids else ox
        right_base_sx = ns[base_node_ids[-1]][0] if len(base_node_ids) >= 2 else ox + span * scale
        dim_y = min(oy + 28, h - 20)
        self.create_line(left_base_sx, dim_y, right_base_sx, dim_y,
                         fill=dim_col, width=1, arrow="both")
        self._create_label(
            (left_base_sx + right_base_sx) / 2, dim_y + 12,
            f"{span:.1f} m", "dim_span", fill=dim_col)

        # Eave height
        dx = max(40, ns[1][0] - 30)
        self.create_line(dx, ns[1][1], dx, ns[2][1], fill=dim_col, width=1, arrow="both")
        self._create_label(
            dx - 8, (ns[1][1] + ns[2][1]) / 2,
            f"{eave:.1f} m", "dim_eave", fill=dim_col, anchor="e")

        if roof_type == "gable":
            # Ridge height
            dx2 = ns[3][0] + 20
            self.create_line(dx2, oy, dx2, ns[3][1], fill=dim_col, width=1, arrow="both")
            self._create_label(
                dx2 + 8, (oy + ns[3][1]) / 2,
                f"{ridge:.2f} m", "dim_ridge", fill=dim_col, anchor="w")

            # Apex horizontal distance
            apex_dim_y = ns[2][1] - 15
            self.create_line(ns[2][0], apex_dim_y, ns[3][0], apex_dim_y,
                             fill=dim_col, width=1, arrow="both")
            self._create_label(
                (ns[2][0] + ns[3][0]) / 2, apex_dim_y - 10,
                f"{apex_x:.2f} m", "dim_apex_x", fill=dim_col)

            # Left rafter pitch
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            self._create_label(
                mx, my - 15,
                f"a1={pitch:.1f}", "pitch_left",
                fill=COLORS["frame_raf"], anchor="s")

            # Right rafter pitch
            mx2 = (ns[3][0] + ns[4][0]) / 2
            my2 = (ns[3][1] + ns[4][1]) / 2
            self._create_label(
                mx2, my2 - 15,
                f"a2={pitch2:.1f}", "pitch_right",
                fill=COLORS["frame_raf"], anchor="s")
        else:
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            self._create_label(
                mx, my - 15,
                f"{pitch:.1f} deg", "pitch_mono",
                fill=COLORS["frame_raf"], anchor="s")

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

        # Force diagram overlay
        if diagram and diagram.get("data"):
            self.draw_force_diagram(diagram, ns)

        if diagram and diagram.get("data"):
            dtype = diagram.get("type", "M")
            dcolor = DIAGRAM_COLORS.get(dtype, "#e06c75")
            ly += 16
            self.create_line(lx, ly, lx + 20, ly, fill=dcolor, width=2)
            label_map = {"M": "Moment", "V": "Shear", "N": "Axial", "δ": "Deflection"}
            self.create_text(lx + 25, ly, text=label_map.get(dtype, dtype),
                             fill=COLORS["fg_dim"], font=FONT_SMALL, anchor="w")

        # Prune stale drag offsets for labels no longer present
        stale = [k for k in self._label_offsets if k not in self._label_positions]
        for k in stale:
            del self._label_offsets[k]

        # Resolve label overlaps
        self._resolve_overlaps()

    # ── Force diagram drawing ──

    def draw_force_diagram(self, diagram, ns):
        """Draw force diagram overlaid on frame members.

        Computes a global shrink factor so all diagrams (including peak value
        labels) stay within the canvas bounds, preserving proportionality
        across all members.
        """
        data = diagram["data"]
        dtype = diagram["type"]
        members_map = diagram.get("members", {})
        color = DIAGRAM_COLORS.get(dtype, "#e06c75")

        # Find max absolute value across all members for normalisation.
        # For envelopes, scan both data (max curve) and data_min (min curve).
        data_min = diagram.get("data_min")
        is_envelope = data_min is not None

        max_val = 0
        for stations in data.values():
            for _, val in stations:
                max_val = max(max_val, abs(val))
        if is_envelope:
            for stations in data_min.values():
                for _, val in stations:
                    max_val = max(max_val, abs(val))
        if max_val < 1e-6:
            return

        # Canvas bounds with a small safety pad
        w = self.winfo_width()
        h = self.winfo_height()
        pad = 20
        # Reserve additional space for the fixed +12 peak-label offset. We apply
        # this reservation to ALL stations (not just the peak) — it's conservative
        # but eliminates sign-tracking complexity and is visually safe.
        LABEL_EXTRA = 12
        x_min = pad + LABEL_EXTRA
        x_max = w - pad - LABEL_EXTRA
        y_min = pad + LABEL_EXTRA
        y_max = h - pad - LABEL_EXTRA

        # Pre-compute member geometry
        member_geom = {}  # mid -> (sx, sy, ex, ey, mdx, mdy, nx, ny)
        for mid, stations in data.items():
            if mid not in members_map:
                continue
            n_start, n_end = members_map[mid]
            if n_start not in ns or n_end not in ns:
                continue
            sx, sy = ns[n_start]
            ex, ey = ns[n_end]
            mdx = ex - sx
            mdy = ey - sy
            length = math.hypot(mdx, mdy)
            if length < 1:
                continue
            nx = -mdy / length
            ny = mdx / length
            member_geom[mid] = (sx, sy, ex, ey, mdx, mdy, nx, ny)

        # Pre-pass: find global shrink factor by checking every station's
        # proposed diagram point against the effective bounds. For envelopes,
        # both the max and min curves must fit.
        shrink = 1.0
        data_sources = [data]
        if is_envelope:
            data_sources.append(data_min)

        for data_source in data_sources:
            for mid, stations in data_source.items():
                if mid not in member_geom:
                    continue
                sx, sy, ex, ey, mdx, mdy, nx, ny = member_geom[mid]
                for pct, val in stations:
                    t = pct / 100.0
                    base_x = sx + mdx * t
                    base_y = sy + mdy * t

                    # Skip if baseline is outside effective bounds (shouldn't happen
                    # given existing frame padding, but defensive).
                    if (base_x < x_min or base_x > x_max or
                            base_y < y_min or base_y > y_max):
                        continue

                    # Unshrunken diagram offset at this station
                    k = (val / max_val) * DIAGRAM_MAX_PX
                    px_proposed = base_x + nx * k
                    py_proposed = base_y + ny * k

                    s_point = 1.0

                    # x-axis: if proposed point is outside, compute shrink to the
                    # violated wall. Formula: we want base_x + nx*k*s ∈ [x_min, x_max],
                    # so s = (boundary - base_x) / (nx*k) when the point is out on
                    # that side. Both numerator and denominator have the same sign
                    # in the out-of-bounds case, so s is positive.
                    nxk = nx * k
                    if abs(nxk) > 1e-9:
                        if px_proposed > x_max:
                            s_point = min(s_point, (x_max - base_x) / nxk)
                        elif px_proposed < x_min:
                            s_point = min(s_point, (x_min - base_x) / nxk)

                    nyk = ny * k
                    if abs(nyk) > 1e-9:
                        if py_proposed > y_max:
                            s_point = min(s_point, (y_max - base_y) / nyk)
                        elif py_proposed < y_min:
                            s_point = min(s_point, (y_min - base_y) / nyk)

                    if s_point < shrink:
                        shrink = s_point

        # Floor the shrink so tiny diagrams remain legible
        shrink = max(shrink, 0.25)
        effective_max_px = DIAGRAM_MAX_PX * shrink

        # Draw pass
        is_deflection = (dtype == "δ")

        def _draw_curves(data_source, is_min=False):
            for mid, stations in data_source.items():
                if mid not in member_geom:
                    continue
                sx, sy, ex, ey, mdx, mdy, nx, ny = member_geom[mid]

                baseline_pts = []
                diagram_pts = []
                for pct, val in stations:
                    t = pct / 100.0
                    px = sx + mdx * t
                    py = sy + mdy * t
                    baseline_pts.append((px, py))
                    offset = (val / max_val) * effective_max_px
                    diagram_pts.append((px + nx * offset, py + ny * offset))

                poly_pts = []
                for pt in baseline_pts:
                    poly_pts.extend(pt)
                for pt in reversed(diagram_pts):
                    poly_pts.extend(pt)

                # For δ and for envelopes, skip the filled polygon —
                # draw only the curve line for clarity.
                draw_fill = not is_deflection and not is_envelope
                if draw_fill and len(poly_pts) >= 6:
                    self.create_polygon(
                        *poly_pts, fill="", outline=color, width=2,
                        tags=("diagram",))
                    self.create_polygon(
                        *poly_pts, fill=color, outline="", stipple="gray25",
                        tags=("diagram",))

                curve_coords = []
                for pt in diagram_pts:
                    curve_coords.extend(pt)
                if len(curve_coords) >= 4:
                    curve_width = 3 if is_deflection else 2
                    # Dashed for envelope min curve to distinguish from max
                    if is_min:
                        self.create_line(*curve_coords, fill=color,
                                         width=curve_width, dash=(4, 3),
                                         tags=("diagram",))
                    else:
                        self.create_line(*curve_coords, fill=color,
                                         width=curve_width, tags=("diagram",))

                # Peak label — skip on the min curve when envelope so we
                # only see one label per member per station.
                if is_min:
                    continue
                peak = max(stations, key=lambda s: abs(s[1]))
                if abs(peak[1]) > 1e-6:
                    t = peak[0] / 100.0
                    px = sx + mdx * t
                    py = sy + mdy * t
                    offset = (peak[1] / max_val) * effective_max_px
                    lx = px + nx * (offset + 12 * (1 if offset >= 0 else -1))
                    ly = py + ny * (offset + 12 * (1 if offset >= 0 else -1))
                    unit = {"M": "kNm", "V": "kN", "N": "kN", "δ": "mm"}[dtype]
                    self._create_label(
                        lx, ly, f"{peak[1]:.1f} {unit}",
                        f"diag_{mid}_{dtype}", fill=color)

        _draw_curves(data, is_min=False)
        if is_envelope:
            _draw_curves(data_min, is_min=True)

    # ── Load drawing ──

    def _draw_loads(self, loads, ns, scale):
        members = loads.get("members", [])
        point_loads = loads.get("point_loads", [])

        if members:
            max_w = 0
            for mem in members:
                for seg in mem.get("segments", []):
                    max_w = max(max_w, abs(seg.get("w_kn", 0)))
            if max_w > 0:
                for mem_idx, mem in enumerate(members):
                    n_from = ns[mem["from"]]
                    n_to = ns[mem["to"]]
                    for seg_idx, seg in enumerate(mem.get("segments", [])):
                        label_key = f"load_m{mem_idx}_s{seg_idx}"
                        self._draw_udl_segment(n_from, n_to, seg, max_w, scale,
                                               label_key)

        cw = self.winfo_width()
        ch = self.winfo_height()
        for pl_idx, pl in enumerate(point_loads):
            nid = pl["node"]
            if nid not in ns:
                continue
            px, py = ns[nid]
            fx = pl.get("fx", 0)
            fy = pl.get("fy", 0)
            arrow_len = 50
            if fx != 0:
                dx = arrow_len if fx > 0 else -arrow_len
                self.create_line(px - dx, py, px, py,
                                 fill=self.ARROW_COLOR, width=2,
                                 arrow="last", arrowshape=(10, 12, 5))
                self._create_label(
                    px - dx / 2, py - 14,
                    f"{abs(fx):.2f} kN", f"ptload_{pl_idx}_fx",
                    fill=self.ARROW_COLOR)
            if fy != 0:
                dy = arrow_len if fy > 0 else -arrow_len
                self.create_line(px, py + dy, px, py,
                                 fill=self.ARROW_COLOR, width=2,
                                 arrow="last", arrowshape=(10, 12, 5))
                self._create_label(
                    px + 20, py + dy / 2,
                    f"{abs(fy):.2f} kN", f"ptload_{pl_idx}_fy",
                    fill=self.ARROW_COLOR)

    def _draw_udl_segment(self, n_from, n_to, seg, max_w, scale, label_key):
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

        # Label at midpoint of the baseline (outside the arrows)
        mid_x = (sx + ex) / 2 - ax * (arrow_len + 12)
        mid_y = (sy + ey) / 2 - ay * (arrow_len + 12)
        self._create_label(mid_x, mid_y, f"{abs(w_kn):.2f} kN/m",
                           label_key, fill=self.ARROW_COLOR)
