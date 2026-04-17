"""Canvas interaction -- pan, zoom, keyboard, tooltip handlers."""

from portal_frame.gui.theme import COLORS, FONT_SMALL


# Keyboard shortcut -> diagram type for hold-and-scroll scaling.
# Extend this dict to add custom shortcuts in the future.
SCALE_KEYMAP = {
    "m": "M",   # Moment
    "n": "N",   # Axial
    "s": "V",   # Shear
    "d": "D",   # Deflection (delta)
    "f": "F",   # Load display
}


def on_resize(canvas, *args):
    if canvas._geom:
        canvas.update_frame(canvas._geom, canvas._supports, canvas._loads, canvas._diagram)


def show_tooltip(canvas, event, text: str) -> None:
    """Draw a tooltip near the mouse cursor. Cleaned up on leave/redraw."""
    hide_tooltip(canvas)
    pad = 6
    tid = canvas.create_text(
        event.x + 12, event.y + 18,
        text=text, fill=COLORS["fg_bright"],
        font=FONT_SMALL, anchor="nw", tags=("hud_tooltip",))
    bb = canvas.bbox(tid)
    if bb:
        canvas.create_rectangle(
            bb[0] - pad, bb[1] - pad / 2,
            bb[2] + pad, bb[3] + pad / 2,
            fill=COLORS["hud_bg"], outline=COLORS["border"], width=1,
            tags=("hud_tooltip",))
        canvas.tag_raise(tid)


def hide_tooltip(canvas) -> None:
    canvas.delete("hud_tooltip")


def tx(canvas, x, y):
    """World coordinates -> screen coordinates using explicit view state."""
    w = getattr(canvas, '_fake_w', None) or canvas.winfo_width()
    h = getattr(canvas, '_fake_h', None) or canvas.winfo_height()
    cx = w / 2.0
    cy = h / 2.0
    return (cx + (x - canvas._view_cx) * canvas._view_zoom,
            cy - (y - canvas._view_cy) * canvas._view_zoom)


def on_pan_start(canvas, event):
    canvas._pan_start = (event.x, event.y)
    canvas.config(cursor="fleur")


def on_pan_move(canvas, event):
    if canvas._pan_start is None:
        return
    dx_px = event.x - canvas._pan_start[0]
    dy_px = event.y - canvas._pan_start[1]
    # Convert pixel delta to world delta (y is flipped: screen-down = world-up negative)
    if canvas._view_zoom > 0:
        canvas._view_cx -= dx_px / canvas._view_zoom
        canvas._view_cy += dy_px / canvas._view_zoom
    canvas._pan_start = (event.x, event.y)
    if canvas._geom:
        canvas.update_frame(canvas._geom, canvas._supports, canvas._loads, canvas._diagram)


def on_pan_end(canvas, event):
    canvas._pan_start = None
    canvas.config(cursor="")


def on_wheel(canvas, event):
    """Mouse wheel: zoom (no modifier) or scale active diagram (held key)."""
    scroll_up = event.delta > 0

    # Held key -> scale the corresponding diagram type
    if canvas._active_modifier is not None:
        dtype = SCALE_KEYMAP.get(canvas._active_modifier)
        if dtype:
            factor = 1.15 if scroll_up else (1.0 / 1.15)
            canvas._diagram_scales[dtype] = max(0.1, min(10.0,
                canvas._diagram_scales[dtype] * factor))
            if canvas._geom:
                canvas.update_frame(canvas._geom, canvas._supports, canvas._loads, canvas._diagram)
            return

    # No modifier -> zoom toward cursor
    factor = 1.1 if scroll_up else (1.0 / 1.1)
    new_zoom = canvas._view_zoom * factor

    min_zoom = canvas._view_zoom_base * 0.1
    max_zoom = canvas._view_zoom_base * 20.0
    new_zoom = max(min_zoom, min(max_zoom, new_zoom))

    if abs(new_zoom - canvas._view_zoom) < 1e-9:
        return

    # Keep the world point under the cursor fixed during zoom
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    cx, cy = w / 2.0, h / 2.0
    wx = canvas._view_cx + (event.x - cx) / canvas._view_zoom
    wy = canvas._view_cy - (event.y - cy) / canvas._view_zoom
    canvas._view_cx = wx - (event.x - cx) / new_zoom
    canvas._view_cy = wy + (event.y - cy) / new_zoom
    canvas._view_zoom = new_zoom

    if canvas._geom:
        canvas.update_frame(canvas._geom, canvas._supports, canvas._loads, canvas._diagram)


def on_zoom_extents(canvas, event):
    """Double-click middle mouse: refit view to frame (Autodesk-style zoom extents).
    Leaves diagram amplitude scales untouched."""
    canvas._view_dirty = True
    if canvas._geom:
        canvas.update_frame(canvas._geom, canvas._supports, canvas._loads, canvas._diagram)


def on_key_press(canvas, event):
    key = event.keysym.lower()
    if key in SCALE_KEYMAP:
        canvas._active_modifier = key


def on_key_release(canvas, event):
    key = event.keysym.lower()
    if key == canvas._active_modifier:
        canvas._active_modifier = None


def set_diagram_type(canvas, dtype: str):
    """Called by app.py when the diagram type combobox changes.
    Updates the active type so the HUD shows the correct letter."""
    canvas._active_diagram_type = dtype
    if canvas._geom:
        canvas.update_frame(canvas._geom, canvas._supports, canvas._loads, canvas._diagram)
