"""Load arrow drawing — UDL segments and point loads on the canvas."""

import math


def draw_loads(canvas, loads, ns, scale):
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
                    _draw_udl_segment(canvas, n_from, n_to, seg, max_w, scale,
                                      label_key)

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
            canvas.create_line(px - dx, py, px, py,
                             fill=canvas.ARROW_COLOR, width=2,
                             arrow="last", arrowshape=(10, 12, 5))
            canvas._create_label(
                px - dx / 2, py - 14,
                f"{abs(fx):.2f} kN", f"ptload_{pl_idx}_fx",
                fill=canvas.ARROW_COLOR)
        if fy != 0:
            dy = arrow_len if fy > 0 else -arrow_len
            canvas.create_line(px, py + dy, px, py,
                             fill=canvas.ARROW_COLOR, width=2,
                             arrow="last", arrowshape=(10, 12, 5))
            canvas._create_label(
                px + 20, py + dy / 2,
                f"{abs(fy):.2f} kN", f"ptload_{pl_idx}_fy",
                fill=canvas.ARROW_COLOR)


def _draw_udl_segment(canvas, n_from, n_to, seg, max_w, scale, label_key):
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

    load_scale = canvas._diagram_scales.get("F", 1.0)
    arrow_len = (abs(w_kn) / max_w) * canvas.ARROW_MAX_LEN * load_scale

    seg_dx = ex - sx
    seg_dy = ey - sy
    seg_len = math.hypot(seg_dx, seg_dy)
    if seg_len < 5:
        return

    n_arrows = max(2, int(seg_len / canvas.ARROW_SPACING))

    bx1 = sx - ax * arrow_len
    by1 = sy - ay * arrow_len
    bx2 = ex - ax * arrow_len
    by2 = ey - ay * arrow_len
    canvas.create_line(bx1, by1, bx2, by2, fill=canvas.ARROW_COLOR, width=1)

    for i in range(n_arrows + 1):
        t = i / n_arrows
        px = sx + seg_dx * t
        py = sy + seg_dy * t
        tail_x = px - ax * arrow_len
        tail_y = py - ay * arrow_len
        canvas.create_line(tail_x, tail_y, px, py,
                         fill=canvas.ARROW_COLOR, width=1,
                         arrow="last", arrowshape=(6, 7, 3))

    mid_x = (sx + ex) / 2 - ax * (arrow_len + 12)
    mid_y = (sy + ey) / 2 - ay * (arrow_len + 12)
    canvas._create_label(mid_x, mid_y, f"{abs(w_kn):.2f} kN/m",
                       label_key, fill=canvas.ARROW_COLOR)
