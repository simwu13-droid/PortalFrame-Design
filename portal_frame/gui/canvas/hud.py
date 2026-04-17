"""Canvas HUD -- heads-up display buttons + axis indicator."""

from portal_frame.gui.theme import COLORS, FONT_SMALL


# HUD display letter for each diagram type (user-facing, matches keyboard shortcut)
_HUD_DISPLAY_LETTER = {"M": "M", "V": "S", "N": "N", "D": "D", "F": "F"}


def draw_axis_indicator(canvas):
    """Draw X/Y axis indicator in bottom-left corner."""
    h = canvas.winfo_height()
    ox, oy = 35, h - 35  # Origin point
    length = 25
    arrow_col = COLORS["fg_dim"]
    label_col = COLORS["fg_bright"]

    # X axis (rightward)
    canvas.create_line(ox, oy, ox + length, oy,
                     fill=arrow_col, width=2, arrow="last")
    canvas.create_text(ox + length + 8, oy, text="X",
                     fill=label_col, font=FONT_SMALL, anchor="w")

    # Y axis (upward)
    canvas.create_line(ox, oy, ox, oy - length,
                     fill=arrow_col, width=2, arrow="last")
    canvas.create_text(ox, oy - length - 8, text="Y",
                     fill=label_col, font=FONT_SMALL, anchor="s")


def draw_hud(canvas, diagram_colors):
    """Draw HUD controls in top-right corner: [DIM] [SLS] [ULS] [Normalize]  [-] M [+]

    Controls are drawn as canvas items (not tk widgets) so they blend
    with the dark canvas theme. All items tagged "hud" for clean redraw.

    diagram_colors: dict mapping diagram type key to hex colour string
                    (e.g. {"M": "#e06c75", ...}). Passed in to avoid a
                    circular import with preview.py.
    """
    w = canvas.winfo_width()
    if w < 200:
        return

    margin = 8
    btn_h = 22
    btn_pad_x = 8
    gap = 6

    bg = COLORS["hud_bg"]
    bg_hover = COLORS["hud_bg_hover"]
    border_col = COLORS["border"]
    fg = COLORS["fg_dim"]
    fg_hover = COLORS["fg_bright"]

    def draw_button(cx, top_y, text, click_handler, text_color=None, tooltip=None):
        """Draw a rect+text button centered at cx. Returns (x1, x2).

        `tooltip`, when set, renders a small label near the cursor on
        hover. The extra <Enter>/<Leave> bindings use add="+" to chain
        onto the existing fill/colour hover handlers.
        """
        if text_color is None:
            text_color = fg
        text_w = len(text) * 7 + 2 * btn_pad_x
        x1 = cx - text_w / 2
        x2 = cx + text_w / 2
        y1 = top_y
        y2 = top_y + btn_h

        rect = canvas.create_rectangle(x1, y1, x2, y2,
            fill=bg, outline=border_col, width=1, tags=("hud",))
        txt = canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2,
            text=text, fill=text_color, font=FONT_SMALL, tags=("hud",))

        for item in (rect, txt):
            canvas.tag_bind(item, "<Enter>",
                lambda e, r=rect, t=txt: (
                    canvas.itemconfig(r, fill=bg_hover),
                    canvas.itemconfig(t, fill=fg_hover),
                    canvas.config(cursor="hand2")))
            canvas.tag_bind(item, "<Leave>",
                lambda e, r=rect, t=txt, tc=text_color: (
                    canvas.itemconfig(r, fill=bg),
                    canvas.itemconfig(t, fill=tc),
                    canvas.config(cursor="")))
            canvas.tag_bind(item, "<ButtonRelease-1>",
                lambda e, h=click_handler: h())
            if tooltip:
                canvas.tag_bind(item, "<Enter>",
                    lambda e, msg=tooltip: canvas._show_tooltip(e, msg),
                    add="+")
                canvas.tag_bind(item, "<Leave>",
                    lambda e: canvas._hide_tooltip(),
                    add="+")

        return x1, x2

    # Active diagram type and color for the middle label
    dtype = canvas._active_diagram_type
    display_letter = _HUD_DISPLAY_LETTER.get(dtype, dtype)
    dtype_color = diagram_colors.get(
        {"D": "\u03b4"}.get(dtype, dtype),
        COLORS["fg_bright"])

    top_y = margin

    # Layout right-to-left: [+] ... letter ... [-] ... [Normalize]
    # [+] button (rightmost)
    plus_cx = w - margin - 16
    def on_plus():
        key = canvas._active_diagram_type
        canvas._diagram_scales[key] = min(10.0,
            canvas._diagram_scales.get(key, 1.0) * 1.15)
        if canvas._geom:
            canvas.update_frame(canvas._geom, canvas._supports,
                              canvas._loads, canvas._diagram)
    x1_plus, _ = draw_button(plus_cx, top_y, "+", on_plus)

    # Type label between [-] and [+]
    label_cx = x1_plus - gap - 7
    canvas.create_text(label_cx, top_y + btn_h / 2,
        text=display_letter, fill=dtype_color,
        font=FONT_SMALL, tags=("hud",))

    # [-] button
    minus_cx = label_cx - gap - 16
    def on_minus():
        key = canvas._active_diagram_type
        canvas._diagram_scales[key] = max(0.1,
            canvas._diagram_scales.get(key, 1.0) / 1.15)
        if canvas._geom:
            canvas.update_frame(canvas._geom, canvas._supports,
                              canvas._loads, canvas._diagram)
    x1_minus, _ = draw_button(minus_cx, top_y, "-", on_minus)

    # [Normalize] button
    norm_cx = x1_minus - gap - 35
    def on_normalize():
        canvas._diagram_scales = {k: 1.0 for k in canvas._diagram_scales}
        canvas._view_dirty = True
        if canvas._geom:
            canvas.update_frame(canvas._geom, canvas._supports,
                              canvas._loads, canvas._diagram)
    x1_norm, _ = draw_button(norm_cx, top_y, "Normalize", on_normalize)

    # [ULS] toggle button -- member capacity check overlay
    uls_cx = x1_norm - gap - 16
    uls_color = COLORS["dc_pass"] if canvas._overlay_mode == "uls" else fg
    x1_uls, _ = draw_button(
        uls_cx, top_y, "ULS", canvas.toggle_uls_overlay,
        text_color=uls_color,
        tooltip="Enable Member Capacity Check (ULS) -- bending, axial, combined per AS/NZS 4600")

    # [SLS] toggle button -- serviceability overlay (left of ULS)
    sls_cx = x1_uls - gap - 16
    sls_color = COLORS["dc_pass"] if canvas._overlay_mode == "sls" else fg
    x1_sls, _ = draw_button(
        sls_cx, top_y, "SLS", canvas.toggle_sls_overlay,
        text_color=sls_color,
        tooltip="Enable Serviceability Check (SLS) -- apex deflection vs span/X limit")

    # [DIM] toggle button -- dimension annotations (left of SLS)
    dim_cx = x1_sls - gap - 16
    dim_color = COLORS["fg_bright"] if canvas._show_dimensions else fg
    draw_button(
        dim_cx, top_y, "DIM", canvas.toggle_dimensions,
        text_color=dim_color,
        tooltip="Toggle dimensions (span, eave, ridge, pitches)")
