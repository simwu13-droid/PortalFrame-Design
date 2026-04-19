"""Frame rendering — fit-to-window, main frame draw, and load arrows.

Free functions that operate on a FramePreview canvas instance (passed as the
first argument ``canvas``). Extracted from preview.py to keep file sizes
within the project's 500–800 line target.
"""

import math

from portal_frame.gui.theme import COLORS, FONT_SMALL
from portal_frame.gui.canvas.labels import _envelope_label_parts
from portal_frame.gui.canvas.hud import draw_axis_indicator, draw_hud
from portal_frame.gui.canvas.loads import draw_loads as _draw_loads
from portal_frame.gui.canvas.reactions import draw_reactions as _draw_reactions


DIAGRAM_COLORS = {
    "M": "#e06c75",   # Red-pink for moment
    "V": "#c678dd",   # Purple for shear
    "N": "#e5c07b",   # Gold for axial
    "δ": "#61afef",   # Blue for deflection
}


# ---------------------------------------------------------------------------
# fit_to_window
# ---------------------------------------------------------------------------

def fit_to_window(canvas, geom, loads=None):
    """Compute view_cx, view_cy, view_zoom to fit the frame in the canvas.

    Replaces the old inline scale/ox/oy computation in update_frame().
    Stores result in _view_cx/cy/zoom so that tx() uses it.
    """
    w = canvas.winfo_width()
    h = canvas.winfo_height()
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
    else:
        if apex_x is None:
            p1 = math.tan(math.radians(pitch))
            p2 = math.tan(math.radians(pitch2))
            apex_x = span * p2 / (p1 + p2) if (p1 + p2) > 0 else span / 2.0
        if ridge is None:
            ridge = eave + apex_x * math.tan(math.radians(pitch))

    has_loads = bool(loads and loads.get("members"))
    pad_side = 100 if has_loads else 55
    pad_top = 80
    pad_bot = 55
    total_h = ridge if ridge > 0 else 1.0

    scale_x = (w - 2 * pad_side) / span if span > 0 else 1
    scale_y = (h - pad_top - pad_bot) / total_h if total_h > 0 else 1
    zoom = min(scale_x, scale_y)

    # Match the old ox/oy-based transform:
    # Old: screen_x = ox + x*zoom, screen_y = oy - y*zoom
    #   where ox = pad_side + (w - 2*pad_side - span*zoom)/2
    #         oy = h - pad_bot
    # New: screen_x = w/2 + (x - view_cx)*zoom
    #      screen_y = h/2 - (y - view_cy)*zoom
    # Solving for view_cx/cy that produce identical output:
    ox = pad_side + (w - 2 * pad_side - span * zoom) / 2
    oy = h - pad_bot
    canvas._view_cx = (w / 2.0 - ox) / zoom
    canvas._view_cy = (oy - h / 2.0) / zoom

    canvas._view_zoom = zoom
    canvas._view_zoom_base = zoom
    canvas._view_dirty = False


# ---------------------------------------------------------------------------
# update_frame
# ---------------------------------------------------------------------------

def update_frame(canvas, geom: dict, supports: tuple, loads: dict = None, diagram: dict = None):
    """Main frame draw — clears canvas and redraws everything.

    This is the free-function body extracted from FramePreview.update_frame().
    The class keeps a thin delegate stub that calls this function.
    """
    # Detect geometry change -> mark view dirty for auto-refit
    old_geom = canvas._geom
    if old_geom is not None and geom is not None:
        for key in ("span", "eave_height", "roof_pitch", "roof_pitch_2",
                    "roof_type", "apex_x", "ridge_height", "crane_rail_height"):
            if geom.get(key) != old_geom.get(key):
                canvas._view_dirty = True
                # Roof type change is major topology change -> reset scales
                if key == "roof_type":
                    canvas._diagram_scales = {k: 1.0 for k in canvas._diagram_scales}
                break

    canvas._geom = geom
    canvas._supports = supports
    canvas._loads = loads
    canvas._diagram = diagram
    # Explicit tooltip cleanup before the global delete("all") — makes
    # intent clear and avoids surprising future readers who don't
    # realise delete("all") also clears tagged canvas items.
    canvas._hide_tooltip()
    canvas.delete("all")
    canvas._label_items = []
    canvas._label_positions = {}
    canvas._item_to_key = {}
    canvas._label_partners = {}

    w = canvas.winfo_width()
    h = canvas.winfo_height()
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
        canvas.create_line(i, 0, i, h, fill=COLORS["canvas_grid"], dash=(1, 4))
    for i in range(0, h, 30):
        canvas.create_line(0, i, w, i, fill=COLORS["canvas_grid"], dash=(1, 4))

    # Refit view if dirty (first draw, geometry change, normalize)
    if canvas._view_dirty:
        fit_to_window(canvas, geom, loads)

    # Ground line — use tx(0,0) and tx(span,0) for endpoints
    gx1, ground_sy = canvas.tx(0, 0)  # ground_sy = screen Y of world Y=0
    gx2 = canvas.tx(span, 0)[0]
    gx1 -= 20
    gx2 += 20
    canvas.create_line(gx1, ground_sy, gx2, ground_sy, fill=COLORS["fg_dim"], width=1, dash=(4, 2))

    # Transform nodes
    ns = {k: canvas.tx(*v) for k, v in nodes.items()}

    # Merge any extra topology nodes supplied by the diagram payload
    # (e.g. crane bracket nodes with IDs outside the hardcoded 1-5 range).
    # Without this, draw_force_diagram skips members whose endpoints
    # aren't in ns — making column sub-members invisible on crane frames.
    if diagram and "topology_nodes" in diagram:
        for nid, (wx, wy) in diagram["topology_nodes"].items():
            if nid not in ns:
                ns[nid] = canvas.tx(wx, wy)

    # Members — when δ diagram is active, draw the undeformed frame as
    # thin dimmed outline so small column deflections (only a few pixels
    # wide) aren't hidden behind a thick structural member line.
    is_deflection = bool(diagram and diagram.get("type") == "δ")
    col_color = COLORS["frame_col_dim"] if is_deflection else COLORS["frame_col"]
    raf_color = COLORS["frame_raf_dim"] if is_deflection else COLORS["frame_raf"]
    member_width = 1 if is_deflection else 3

    # Overlay state — single-slot, mutually exclusive.
    uls_on = canvas._overlay_mode == "uls" and bool(canvas._dc_groups)
    sls_on = canvas._overlay_mode == "sls" and bool(canvas._sls_checks)

    sls_color = None
    if sls_on:
        worst_util, worst_status = canvas._sls_worst_util()
        sls_color = canvas._dc_color_for(worst_status, worst_util)

    def _line(pt_a, pt_b, base_color, role, dc_key, mid=None):
        if uls_on and dc_key in canvas._dc_groups and canvas._dc_groups[dc_key] is not None:
            chk = canvas._dc_groups[dc_key]
            # Use the worst of (combined, shear) for colouring so the
            # member turns red if either check fails.
            worst_util = max(chk.util_combined, chk.util_shear)
            color = canvas._dc_color_for(chk.status, worst_util)
            width = 4
        elif sls_on and role == "raf":
            color = sls_color
            width = 4
        else:
            color = base_color
            width = member_width
        tags = ("member", f"member_{mid}") if mid is not None else ()
        canvas.create_line(*pt_a, *pt_b, fill=color, width=width, tags=tags)

    if roof_type == "mono":
        # Mono topology: 1=left col, 2=rafter, 3=right col
        _line(ns[1], ns[2], col_color, "col", "col_L", mid=1)
        _line(ns[2], ns[3], raf_color, "raf", "raf_L", mid=2)
        _line(ns[3], ns[4], col_color, "col", "col_R", mid=3)
    else:
        # Gable topology: 1=left col, 2=left rafter, 3=right rafter, 4=right col
        _line(ns[1], ns[2], col_color, "col", "col_L", mid=1)
        _line(ns[5], ns[4], col_color, "col", "col_R", mid=4)
        _line(ns[2], ns[3], raf_color, "raf", "raf_L", mid=2)
        _line(ns[3], ns[4], raf_color, "raf", "raf_R", mid=3)

    # ULS midpoint utilisation labels — two lines: util ratio on top,
    # dominant combo name on the bottom so the user can see which
    # load case is driving the critical capacity check. Each label
    # is draggable (text + background rect move together).
    if uls_on:
        def _dominant(chk) -> tuple[float, str, str]:
            """Return (max_util, display_util_label, combo_name).

            Picks the governing check — whichever of:
            - combined bending+axial (the usual driver),
            - pure shear (rare but possible for deep beams)
            has the highest utilisation. Label shows that value and its
            controlling combo.
            """
            sigma = chk.util_combined
            v = chk.util_shear
            if v > sigma:
                return (v, f"V/\u03c6V={v:.2f}", chk.controlling_combo_v)
            # Combined governs — pick the sub-combo for display
            if chk.util_bending >= chk.util_axial:
                combo = chk.controlling_combo_m or chk.controlling_combo_n
            else:
                combo = chk.controlling_combo_n or chk.controlling_combo_m
            return (sigma, f"\u03a3={sigma:.2f}", combo)

        def _dc_label(pt_a, pt_b, dc_key):
            if dc_key not in canvas._dc_groups or canvas._dc_groups[dc_key] is None:
                return
            chk = canvas._dc_groups[dc_key]
            mx = (pt_a[0] + pt_b[0]) / 2
            my = (pt_a[1] + pt_b[1]) / 2
            if chk.status == "NO_DATA":
                text = "n/d"
                color_util = 0.0
                color_status = "NO_DATA"
            else:
                util, label, combo = _dominant(chk)
                text = f"{label}\n{combo}" if combo else label
                color_util = util
                color_status = chk.status
            color = canvas._dc_color_for(color_status, color_util)
            canvas._create_boxed_draggable_label(
                mx, my, text, f"uls_{dc_key}",
                fg=color, outline=color,
                anchor="center", bbox_pad=3)

        if roof_type == "mono":
            _dc_label(ns[1], ns[2], "col_L")
            _dc_label(ns[2], ns[3], "raf_L")
            _dc_label(ns[3], ns[4], "col_R")
        else:
            _dc_label(ns[1], ns[2], "col_L")
            _dc_label(ns[5], ns[4], "col_R")
            _dc_label(ns[2], ns[3], "raf_L")
            _dc_label(ns[3], ns[4], "raf_R")

    # SLS badges — one per metric (apex_dy, drift). Each badge shows
    # EVERY category for that metric (so the user sees both wind and
    # eq numbers, not just the one with the highest utilisation).
    # Colour is driven by the worst util across categories. Each
    # row shows the ACTUAL L/X or h/X deformation ratio the frame
    # reached (not the design limit — that's in the results panel).
    if sls_on and canvas._sls_checks:
        def _format_metric_badge(checks: list) -> str:
            """Build a multi-line badge text with one row per category.

            Rows are ordered wind-first-then-eq for consistency.
            Each row: '  CAT  delta=+X mm / L/Y  COMBO'
            """
            order = {"wind": 0, "eq": 1}
            rows_sorted = sorted(checks, key=lambda c: order.get(c.category, 2))
            lines = []
            for c in rows_sorted:
                combo = f" {c.controlling_combo}" if c.controlling_combo else ""
                lines.append(
                    f"{c.category.upper():4s} "
                    f"\u03b4={c.deflection_mm:>6.1f}mm / "
                    f"{c.reference_symbol}/{c.actual_ratio}"
                    f"{combo}"
                )
            return "\n".join(lines)

        apex_checks = [c for c in canvas._sls_checks if c.metric == "apex_dy"]
        drift_checks = [c for c in canvas._sls_checks if c.metric == "drift"]

        # Apex badge at the ridge node
        if apex_checks:
            worst_apex = max(apex_checks, key=lambda c: c.util)
            apex_node_id = 3   # node 3 = apex/ridge for gable and mono
            if apex_node_id in ns:
                ax, ay = ns[apex_node_id]
                color = canvas._dc_color_for(worst_apex.status, worst_apex.util)
                # Mono puts the ridge at the top-right column — offset
                # the badge left/up so it clears the a1 pitch label.
                if roof_type == "mono":
                    bx, by, banchor = ax - 20, ay - 28, "se"
                else:
                    bx, by, banchor = ax, ay - 20, "s"
                canvas._create_boxed_draggable_label(
                    bx, by, _format_metric_badge(apex_checks),
                    "sls_apex_badge",
                    fg=color, outline=color,
                    anchor=banchor, bbox_pad=4)

        # Drift badge next to the eave with the larger worst-case |dx|.
        if drift_checks:
            worst_drift = max(drift_checks, key=lambda c: c.util)
            eave_left = ns.get(2)
            eave_right = ns.get(4) if roof_type != "mono" else ns.get(3)
            if eave_left and eave_right:
                if worst_drift.deflection_mm >= 0:
                    bx, by, banchor = (eave_right[0] + 15, eave_right[1] - 8, "w")
                else:
                    bx, by, banchor = (eave_left[0] - 15, eave_left[1] - 8, "e")
                color = canvas._dc_color_for(worst_drift.status, worst_drift.util)
                canvas._create_boxed_draggable_label(
                    bx, by, _format_metric_badge(drift_checks),
                    "sls_drift_badge",
                    fg=color, outline=color,
                    anchor=banchor, bbox_pad=4)

    # Crane bracket nodes (if crane_rail_height is set)
    crane_h = geom.get("crane_rail_height")
    if crane_h is not None and 0 < crane_h < eave:
        # Draw bracket markers on each column
        bracket_left = canvas.tx(0, crane_h)
        bracket_right = canvas.tx(span, crane_h)
        ns["bracket_left"] = bracket_left
        ns["bracket_right"] = bracket_right
        br = 5
        for bpt in [bracket_left, bracket_right]:
            canvas.create_rectangle(
                bpt[0] - br, bpt[1] - br, bpt[0] + br, bpt[1] + br,
                fill=COLORS["warning"], outline=COLORS["fg_bright"], width=1)

    # Nodes
    r = 4
    for key, pt in ns.items():
        if isinstance(key, str) and key.startswith("bracket"):
            continue  # bracket nodes already drawn as squares
        canvas.create_oval(pt[0]-r, pt[1]-r, pt[0]+r, pt[1]+r,
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
            canvas.create_polygon(
                bx, by, bx - sz, by + sz, bx + sz, by + sz,
                outline=COLORS["frame_support"], fill="", width=2
            )
            for j in range(-1, 2):
                hx = bx + j * 8
                canvas.create_line(hx - 4, by + sz + 2, hx + 4, by + sz + 8,
                                 fill=COLORS["frame_support"], width=1)
        else:
            sz = 10
            canvas.create_rectangle(
                bx - sz, by, bx + sz, by + sz * 1.5,
                outline=COLORS["frame_support"], fill=COLORS["frame_support"],
                stipple="gray50", width=2
            )

    # UDL load arrows
    if loads:
        _draw_loads(canvas, loads, ns, canvas._view_zoom)

    # Dimension annotations (all as draggable labels)
    # Toggled via the HUD DIM button — hides arrows, dimension
    # labels, and pitch annotations as a group.
    if canvas._show_dimensions:
        dim_col = COLORS["fg_dim"]

        # Span
        left_base_sx = ns[base_node_ids[0]][0] if base_node_ids else canvas.tx(0, 0)[0]
        right_base_sx = ns[base_node_ids[-1]][0] if len(base_node_ids) >= 2 else canvas.tx(span, 0)[0]
        dim_y = min(ground_sy + 28, h - 20)
        canvas.create_line(left_base_sx, dim_y, right_base_sx, dim_y,
                         fill=dim_col, width=1, arrow="both")
        canvas._create_label(
            (left_base_sx + right_base_sx) / 2, dim_y + 12,
            f"{span:.1f} m", "dim_span", fill=dim_col)

        # Eave height
        dx = max(40, ns[1][0] - 30)
        canvas.create_line(dx, ns[1][1], dx, ns[2][1], fill=dim_col, width=1, arrow="both")
        canvas._create_label(
            dx - 8, (ns[1][1] + ns[2][1]) / 2,
            f"{eave:.1f} m", "dim_eave", fill=dim_col, anchor="e")

        if roof_type == "gable":
            # Ridge height
            dx2 = ns[3][0] + 20
            canvas.create_line(dx2, ground_sy, dx2, ns[3][1], fill=dim_col, width=1, arrow="both")
            canvas._create_label(
                dx2 + 8, (ground_sy + ns[3][1]) / 2,
                f"{ridge:.2f} m", "dim_ridge", fill=dim_col, anchor="w")

            # Apex horizontal distance
            apex_dim_y = ns[2][1] - 15
            canvas.create_line(ns[2][0], apex_dim_y, ns[3][0], apex_dim_y,
                             fill=dim_col, width=1, arrow="both")
            canvas._create_label(
                (ns[2][0] + ns[3][0]) / 2, apex_dim_y - 10,
                f"{apex_x:.2f} m", "dim_apex_x", fill=dim_col)

            # Left rafter pitch
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            canvas._create_label(
                mx, my - 15,
                f"a1={pitch:.1f}", "pitch_left",
                fill=COLORS["frame_raf"], anchor="s")

            # Right rafter pitch
            mx2 = (ns[3][0] + ns[4][0]) / 2
            my2 = (ns[3][1] + ns[4][1]) / 2
            canvas._create_label(
                mx2, my2 - 15,
                f"a2={pitch2:.1f}", "pitch_right",
                fill=COLORS["frame_raf"], anchor="s")
        else:
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            canvas._create_label(
                mx, my - 15,
                f"{pitch:.1f} deg", "pitch_mono",
                fill=COLORS["frame_raf"], anchor="s")

    # Legend
    ly = 15
    lx = 10
    canvas.create_line(lx, ly, lx + 20, ly, fill=COLORS["frame_col"], width=2)
    canvas.create_text(lx + 25, ly, text="Column", fill=COLORS["fg_dim"],
                     font=FONT_SMALL, anchor="w")
    ly += 16
    canvas.create_line(lx, ly, lx + 20, ly, fill=COLORS["frame_raf"], width=2)
    canvas.create_text(lx + 25, ly, text="Rafter", fill=COLORS["fg_dim"],
                     font=FONT_SMALL, anchor="w")
    if loads:
        ly += 16
        canvas.create_line(lx, ly, lx + 20, ly, fill=canvas.ARROW_COLOR, width=2)
        canvas.create_text(lx + 25, ly, text="Load", fill=COLORS["fg_dim"],
                         font=FONT_SMALL, anchor="w")

    # Diagram overlay — dispatch by type
    if diagram is not None:
        dtype = diagram.get("type")
        if dtype == "R":
            _draw_reactions(canvas, diagram)
        elif diagram.get("data"):
            canvas.draw_force_diagram(diagram, ns)
            dcolor = DIAGRAM_COLORS.get(dtype, "#e06c75")
            ly += 16
            canvas.create_line(lx, ly, lx + 20, ly, fill=dcolor, width=2)
            label_map = {"M": "Moment", "V": "Shear", "N": "Axial", "δ": "Deflection"}
            canvas.create_text(lx + 25, ly, text=label_map.get(dtype, dtype),
                             fill=COLORS["fg_dim"], font=FONT_SMALL, anchor="w")

    # Drag offsets are intentionally NOT pruned here. Keeping the
    # offset for keys that aren't in the current redraw lets overlays
    # (ULS, SLS) and dimensions preserve user-set positions across
    # toggle cycles, and roof-type-specific labels (pitch_right,
    # dim_ridge, ...) keep their positions when the user switches
    # back to the matching roof type. The dict only grows with
    # active user drags, so there's no unbounded accumulation.

    # Resolve label overlaps
    canvas._resolve_overlaps()

    # Axis indicator (bottom-left corner)
    draw_axis_indicator(canvas)

    draw_hud(canvas, DIAGRAM_COLORS)
