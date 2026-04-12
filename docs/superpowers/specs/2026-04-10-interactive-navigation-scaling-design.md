# Interactive Navigation & Scaling Controls — Design Spec

**Date:** 2026-04-10
**Status:** Approved

## Overview

Add pan, zoom, diagram-specific amplitude scaling, and HUD controls to the `FramePreview` canvas. Designed to feel like SpaceGass/Autodesk-style interactive diagram navigation.

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| View transform model | Explicit view state (B) | Future 3D camera generalization |
| Geometry change behavior | Auto-refit (B1) | Simple, predictable, matches SpaceGass |
| Diagram scale persistence | Per-type, persist across switches (A1) | User intent sticks |
| Scale on recompute | Keep user multiplier (B1) | User intent sticks; Normalize resets |
| Scale reset triggers | Roof type flip, new model load | Major topology = new context |
| Keyboard scaling | Hold-and-scroll (Variant 1) | Matches spec, no hidden modes |
| HUD controls | Canvas-drawn items (B) | Matches dark theme, no widget mismatch |
| Zoom extents shortcut | Double-click middle mouse | Autodesk convention |

## Section 1: View State Model

Replace the auto-fit `tx()` closure in `update_frame()` with explicit view state on `FramePreview`:

```python
self._view_cx = 0.0      # World X at canvas center
self._view_cy = 0.0      # World Y at canvas center
self._view_zoom = 1.0    # Pixels per meter (computed on fit)
self._view_dirty = True   # When True, next draw recomputes fit

self._diagram_scales = {"M": 1.0, "V": 1.0, "N": 1.0, "D": 1.0, "F": 1.0}
```

**`tx(x, y)` becomes a method:**
```
screen_x = canvas_center_x + (x - view_cx) * view_zoom
screen_y = canvas_center_y - (y - view_cy) * view_zoom
```

**Auto-refit triggers** (set `_view_dirty = True`):
- Geometry change (span, pitch, roof type, eave height)
- Roof type switch (gable <-> mono) — also resets `_diagram_scales`
- First draw

**`_fit_to_window()`** — new method extracted from current `update_frame()` lines 246-258. Computes `view_cx, view_cy, view_zoom` from geometry + canvas size with padding. Called when `_view_dirty` is True.

## Section 2: Pan, Zoom, and Keyboard-Modified Scaling

### Pan (middle mouse drag)
- `<ButtonPress-2>` -> record `_pan_start = (event.x, event.y)`
- `<B2-Motion>` -> compute pixel delta, convert to world delta via `/ view_zoom`, update `view_cx, view_cy`, redraw
- Cursor changes to `fleur` during pan

### Zoom (mouse wheel, no modifier)
- Zoom toward cursor position (not canvas center) — standard CAD behavior
- `view_zoom *= 1.1` (scroll up) or `view_zoom /= 1.1` (scroll down)
- Adjust `view_cx, view_cy` so world point under cursor stays under cursor
- Clamp zoom to `[0.1x, 20x]` of initial fit zoom

### Zoom Extents (double-click middle mouse)
- `<Double-Button-2>` -> set `_view_dirty = True`, redraw
- Leaves diagram amplitude scales untouched

### Keyboard-modified scaling (hold key + wheel)

Key tracking on the canvas:
```python
self._active_modifier = None

_SCALE_KEYMAP = {
    "m": "M",   # Moment
    "n": "N",   # Axial
    "s": "V",   # Shear (S for Shear -> diagram type "V")
    "d": "D",   # Deflection
    "f": "F",   # Load display
}
```

- Canvas binds `<KeyPress>` and `<KeyRelease>`
- On `<KeyPress>`: if `event.keysym.lower()` in keymap, set `_active_modifier`
- On `<KeyRelease>`: clear `_active_modifier`
- Canvas gets focus on `<Enter>` via `self.focus_set()`

When `_active_modifier` is set and wheel fires:
- Multiply `_diagram_scales[type]` by `1.15` (up) or `/ 1.15` (down)
- Clamp to `[0.1, 10.0]`
- Redraw (no view change)

**Extensibility:** future custom shortcuts just add/modify `_SCALE_KEYMAP` entries.

## Section 3: Canvas-Drawn HUD Controls (Top-Right)

Layout (top-right corner, 8px margin):
```
[Normalize]  [-] M [+]
```

### Visual treatment
- Rounded rectangles with thin `border` stroke (`#3e3e42`)
- Background fill: `hud_bg` (`#2d2d30`), hover: `hud_bg_hover` (`#3e3e42`)
- Text fill: `fg_dim` (`#808080`), hover: `fg_bright` (`#ffffff`)
- The `M` label between `-` and `+` uses the diagram color for that type
- Tag: `"hud"` for clean delete/redraw per frame

### Behavior
- `[-]` click -> divide `_diagram_scales[active_type]` by `1.15`
- `[+]` click -> multiply by `1.15`
- `M` label -> informational, updates when diagram type changes
- Display letter mapping: `{"M": "M", "V": "S", "N": "N", "D": "D", "F": "F"}`
- `[Normalize]` click -> reset `_view_dirty = True` + reset ALL `_diagram_scales` to 1.0 + redraw

### Hover states (via `tag_bind`)
- `<Enter>` -> brighten fill + text, cursor `hand2`
- `<Leave>` -> restore dim, restore cursor

### Z-order
Drawn last in `update_frame()`, on top of everything.

## Section 4: Integration

### File changes

| File | Change |
|------|--------|
| `preview.py` | All view state, pan/zoom, HUD, keyboard tracking, `tx()` refactor |
| `theme.py` | Add `hud_bg`, `hud_bg_hover` color entries |
| `app.py` | Call `preview.set_diagram_type()` on combobox change |

### preview.py changes (summary)
1. `__init__` — add view state, diagram scales, keymap, bind events
2. `_fit_to_window()` — new, extracted from `update_frame()` scale computation
3. `tx(x, y)` — promoted from closure to method
4. `update_frame()` — call `_fit_to_window()` if dirty, draw with `self.tx()`, draw HUD last
5. `_draw_hud()` — new, draws Normalize + `[-] M [+]`
6. `_on_pan_start/move/end()` — new, middle mouse handlers
7. `_on_wheel()` — new, dispatches to zoom or diagram scale
8. `_on_key_press/release()` — new, sets/clears `_active_modifier`
9. `set_diagram_type(dtype)` — new public method for app.py
10. `draw_force_diagram()` / `_draw_deflection_diagram()` — multiply `DIAGRAM_MAX_PX` by `_diagram_scales[dtype]`
11. `_draw_loads()` — multiply `ARROW_MAX_LEN` by `_diagram_scales["F"]`

### app.py changes (minimal)
- Combobox `<<ComboboxSelected>>` handler: add `self.preview.set_diagram_type(dtype)`

### theme.py changes
- Add `"hud_bg": "#2d2d30"`, `"hud_bg_hover": "#3e3e42"` to `COLORS`

### Untouched
- All standards code, models, solvers, analysis, IO
- Diagram data computation in app.py
- Label dragging system (works in screen space)