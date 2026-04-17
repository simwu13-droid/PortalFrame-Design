"""Force and deflection diagram drawing for the FramePreview canvas.

Free functions that operate on a FramePreview canvas instance (passed as the
first argument ``canvas``). Extracted from preview.py to keep file sizes
within the project's 500–800 line target.
"""

import math

from portal_frame.gui.theme import COLORS
from portal_frame.gui.canvas.frame_render import DIAGRAM_COLORS
from portal_frame.gui.canvas.labels import _envelope_label_parts


DIAGRAM_UNITS = {"M": "kNm", "V": "kN", "N": "kN", "δ": "mm"}
DIAGRAM_MAX_PX = 60
# Fixed padding (px) reserved for peak-label positioning around diagram bounds.
_DIAGRAM_PAD = 20
_DIAGRAM_LABEL_EXTRA = 12


# ---------------------------------------------------------------------------
# _diagram_bounds
# ---------------------------------------------------------------------------

def _diagram_bounds(canvas):
    """Return effective (x_min, x_max, y_min, y_max) canvas bounds for
    diagram rendering, with padding and peak-label reservation applied."""
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    reserved = _DIAGRAM_PAD + _DIAGRAM_LABEL_EXTRA
    return reserved, w - reserved, reserved, h - reserved


# ---------------------------------------------------------------------------
# draw_force_diagram
# ---------------------------------------------------------------------------

def draw_force_diagram(canvas, diagram, ns):
    """Draw force diagram overlaid on frame members.

    Computes a global shrink factor so all diagrams (including peak value
    labels) stay within the canvas bounds, preserving proportionality
    across all members.
    """
    data = diagram["data"]
    dtype = diagram["type"]
    members_map = diagram.get("members", {})
    color = DIAGRAM_COLORS.get(dtype, "#e06c75")

    # δ diagrams use a different algorithm (rotation-based deformed
    # shape) so that curves meet at shared nodes. M/V/N keep using
    # the perpendicular-projection algorithm below.
    if dtype == "δ":
        _draw_deflection_diagram(canvas, diagram, ns)
        return

    # Find max absolute value across all members for normalisation.
    # For envelopes, scan both data (max curve) and data_min (min curve).
    data_min = diagram.get("data_min")
    is_envelope = data_min is not None
    data_sources = [data] + ([data_min] if is_envelope else [])

    max_val = max(
        (abs(val)
         for source in data_sources
         for stations in source.values()
         for _, val in stations),
        default=0.0,
    )
    if max_val < 1e-6:
        return

    # Canvas bounds with a small safety pad. Reserve space for the fixed
    # +12 peak-label offset; applied to ALL stations (not just the peak)
    # for simplicity — conservative but visually safe.
    x_min, x_max, y_min, y_max = _diagram_bounds(canvas)

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
    dtype_scale = canvas._diagram_scales.get(dtype, 1.0)
    effective_max_px = DIAGRAM_MAX_PX * shrink * dtype_scale

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

            # For δ, skip the filled polygon — draw only the curve line.
            draw_fill = not is_deflection
            if draw_fill and len(poly_pts) >= 6:
                canvas.create_polygon(
                    *poly_pts, fill="", outline=color, width=2,
                    tags=("diagram",))
                canvas.create_polygon(
                    *poly_pts, fill=color, outline="", stipple="gray25",
                    tags=("diagram",))

            curve_coords = []
            for pt in diagram_pts:
                curve_coords.extend(pt)
            if len(curve_coords) >= 4:
                curve_width = 3 if is_deflection else 2
                # Dashed for envelope min curve to distinguish from max
                if is_min:
                    canvas.create_line(*curve_coords, fill=color,
                                     width=curve_width, dash=(4, 3),
                                     tags=("diagram",))
                else:
                    canvas.create_line(*curve_coords, fill=color,
                                     width=curve_width, tags=("diagram",))

            # Peak label — show for both max and min curves when envelope
            # so the user can read both extremes directly. Prefix with
            # "max:" / "min:" to disambiguate.
            peak = max(stations, key=lambda s: abs(s[1]))
            if abs(peak[1]) > 1e-6:
                t = peak[0] / 100.0
                px = sx + mdx * t
                py = sy + mdy * t
                offset = (peak[1] / max_val) * effective_max_px
                nudged = offset + (12 if offset >= 0 else -12)
                lx = px + nx * nudged
                ly = py + ny * nudged
                prefix, key_suffix = _envelope_label_parts(is_envelope, is_min)
                canvas._create_label(
                    lx, ly,
                    f"{prefix}{peak[1]:.1f} {DIAGRAM_UNITS[dtype]}",
                    f"diag_{mid}_{dtype}{key_suffix}", fill=color)

    _draw_curves(data, is_min=False)
    if is_envelope:
        _draw_curves(data_min, is_min=True)


# ---------------------------------------------------------------------------
# _draw_deflection_diagram
# ---------------------------------------------------------------------------

def _draw_deflection_diagram(canvas, diagram, ns):
    """Draw the deflection (δ) diagram as a true deformed shape.

    Unlike M/V/N diagrams which are drawn perpendicular to each member
    independently, the deflection diagram reconstructs the global
    deformation vector at each station from PyNite's member-local
    dx and dy, then plots the deformed position directly. This makes
    the curves meet at shared nodes (apex, knee) because global
    displacement is physically unique at each node.

    Formula (screen coordinates, y-flipped relative to world):
        Δscreen_x = α × (dx_local × mdx − dy_local × mdy) / L
        Δscreen_y = α × (dx_local × mdy + dy_local × mdx) / L
    where (mdx, mdy) is the screen member direction and L is the
    screen member length. α is a uniform scale factor in pixels per
    mm of global deformation magnitude.
    """
    data = diagram["data"]            # {mid: [(pct, dy_local), ...]}
    data_dx = diagram.get("data_dx", {})
    data_min = diagram.get("data_min")
    data_min_dx = diagram.get("data_min_dx", {})
    members_map = diagram.get("members", {})
    color = DIAGRAM_COLORS.get("δ", "#61afef")

    is_envelope = data_min is not None

    # Find max deformation magnitude (in mm) across all stations and
    # both envelope curves (if present). This sets the base scale.
    def _max_mag(data_dy, data_dx_src):
        m = 0.0
        for mid, stations in data_dy.items():
            dx_list = data_dx_src.get(mid, [])
            for i, (_, dy) in enumerate(stations):
                dx = dx_list[i][1] if i < len(dx_list) else 0.0
                mag = math.hypot(dx, dy)
                if mag > m:
                    m = mag
        return m

    max_disp = _max_mag(data, data_dx)
    if is_envelope:
        max_disp = max(max_disp, _max_mag(data_min, data_min_dx))
    if max_disp < 1e-6:
        return

    # Canvas bounds with a small safety pad and reserved label space
    x_min, x_max, y_min, y_max = _diagram_bounds(canvas)

    # Pre-compute member geometry (screen-space direction and length)
    member_geom = {}  # mid -> (sx, sy, mdx, mdy, L)
    for mid, _ in data.items():
        if mid not in members_map:
            continue
        n_start, n_end = members_map[mid]
        if n_start not in ns or n_end not in ns:
            continue
        sx, sy = ns[n_start]
        ex, ey = ns[n_end]
        mdx = ex - sx
        mdy = ey - sy
        L = math.hypot(mdx, mdy)
        if L < 1:
            continue
        member_geom[mid] = (sx, sy, mdx, mdy, L)

    # Initial scale: α0 pixels per mm such that max_disp maps to
    # DIAGRAM_MAX_PX.
    dtype_scale = canvas._diagram_scales.get("D", 1.0)
    alpha_0 = DIAGRAM_MAX_PX * dtype_scale / max_disp

    # Pre-pass: find shrink factor so every station stays inside
    # the effective bounds.
    def _station_screen_delta(dx_local, dy_local, mdx, mdy, L, alpha):
        """Return (Δscreen_x, Δscreen_y) in pixels for a station."""
        dsx = alpha * (dx_local * mdx - dy_local * mdy) / L
        dsy = alpha * (dx_local * mdy + dy_local * mdx) / L
        return dsx, dsy

    dy_dx_sources = [(data, data_dx)]
    if is_envelope:
        dy_dx_sources.append((data_min, data_min_dx))

    shrink = 1.0
    for source_dy, source_dx in dy_dx_sources:
        for mid, stations in source_dy.items():
            if mid not in member_geom:
                continue
            sx, sy, mdx, mdy, L = member_geom[mid]
            dx_list = source_dx.get(mid, [])
            for i, (pct, dy_local) in enumerate(stations):
                dx_local = dx_list[i][1] if i < len(dx_list) else 0.0
                t = pct / 100.0
                base_x = sx + mdx * t
                base_y = sy + mdy * t

                # Skip if baseline is already outside effective bounds
                if (base_x < x_min or base_x > x_max or
                        base_y < y_min or base_y > y_max):
                    continue

                dsx0, dsy0 = _station_screen_delta(
                    dx_local, dy_local, mdx, mdy, L, alpha_0)
                px_proposed = base_x + dsx0
                py_proposed = base_y + dsy0

                s_point = 1.0
                # X bound check
                if abs(dsx0) > 1e-9:
                    if px_proposed > x_max:
                        s_point = min(s_point, (x_max - base_x) / dsx0)
                    elif px_proposed < x_min:
                        s_point = min(s_point, (x_min - base_x) / dsx0)
                # Y bound check
                if abs(dsy0) > 1e-9:
                    if py_proposed > y_max:
                        s_point = min(s_point, (y_max - base_y) / dsy0)
                    elif py_proposed < y_min:
                        s_point = min(s_point, (y_min - base_y) / dsy0)

                if s_point < shrink:
                    shrink = s_point

    # Floor the shrink so the diagram stays legible
    shrink = max(shrink, 0.25)
    alpha = alpha_0 * shrink

    # Draw pass
    def _draw_curves(source_dy, source_dx, is_min=False):
        for mid, stations in source_dy.items():
            if mid not in member_geom:
                continue
            sx, sy, mdx, mdy, L = member_geom[mid]
            dx_list = source_dx.get(mid, [])

            deformed_pts = []
            for i, (pct, dy_local) in enumerate(stations):
                dx_local = dx_list[i][1] if i < len(dx_list) else 0.0
                t = pct / 100.0
                base_x = sx + mdx * t
                base_y = sy + mdy * t
                dsx, dsy = _station_screen_delta(
                    dx_local, dy_local, mdx, mdy, L, alpha)
                deformed_pts.append((base_x + dsx, base_y + dsy))

            # Draw the deformed-shape curve (no polygon fill for δ)
            curve_coords = []
            for pt in deformed_pts:
                curve_coords.extend(pt)
            if len(curve_coords) >= 4:
                # Wider than the 1px undeformed frame so the deformed
                # shape dominates the view, including small column
                # deflections that would otherwise hide behind the frame.
                curve_width = 4
                if is_min:
                    canvas.create_line(*curve_coords, fill=color,
                                     width=curve_width, dash=(4, 3),
                                     tags=("diagram",))
                else:
                    canvas.create_line(*curve_coords, fill=color,
                                     width=curve_width, tags=("diagram",))

            # Peak label: station with largest global deformation
            # magnitude. Show for both max and min curves when envelope.
            peak_idx = 0
            peak_mag = 0.0
            for i, (_, dy_local) in enumerate(stations):
                dx_local = dx_list[i][1] if i < len(dx_list) else 0.0
                mag = math.hypot(dx_local, dy_local)
                if mag > peak_mag:
                    peak_mag = mag
                    peak_idx = i
            if peak_mag > 1e-6:
                pct, dy_local = stations[peak_idx]
                dx_local = (dx_list[peak_idx][1]
                            if peak_idx < len(dx_list) else 0.0)
                t = pct / 100.0
                base_x = sx + mdx * t
                base_y = sy + mdy * t
                dsx, dsy = _station_screen_delta(
                    dx_local, dy_local, mdx, mdy, L, alpha)
                # Extend label slightly beyond the peak
                dmag_screen = math.hypot(dsx, dsy)
                if dmag_screen > 1e-6:
                    nudge = 18.0 / dmag_screen
                    lx = base_x + dsx * (1.0 + nudge)
                    ly = base_y + dsy * (1.0 + nudge)
                else:
                    lx = base_x
                    ly = base_y
                prefix, key_suffix = _envelope_label_parts(is_envelope, is_min)
                # Global displacements from screen delta (Y flipped)
                dx_mm = dsx / alpha
                dy_mm = -dsy / alpha
                canvas._create_label(
                    lx, ly,
                    f"{prefix}x: {dx_mm:.1f}mm\ny: {dy_mm:.1f}mm",
                    f"diag_{mid}_δ{key_suffix}", fill=color)

    _draw_curves(data, data_dx, is_min=False)
    if is_envelope:
        _draw_curves(data_min, data_min_dx, is_min=True)
