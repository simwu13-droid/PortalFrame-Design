# Interactive Navigation & Scaling Controls — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pan, zoom, diagram-specific amplitude scaling, and HUD controls to the FramePreview canvas.

**Architecture:** Replace the auto-fit `tx()` closure with an explicit view state (`view_cx, view_cy, view_zoom`). Pan/zoom/scaling events modify this state and trigger redraws. A canvas-drawn HUD in the top-right provides Normalize and `[-] M [+]` controls styled to match the dark theme.

**Tech Stack:** Python 3, tkinter Canvas, existing `portal_frame.gui.preview.FramePreview`

**Spec:** `docs/superpowers/specs/2026-04-10-interactive-navigation-scaling-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `portal_frame/gui/preview.py` | Modify | View state, tx() refactor, pan/zoom, keyboard scaling, HUD, diagram scale integration |
| `portal_frame/gui/theme.py` | Modify | Add `hud_bg`, `hud_bg_hover` colors |
| `portal_frame/gui/app.py` | Modify | Notify preview of diagram type changes |
| `tests/test_preview.py` | Create | Unit tests for view state, fit-to-window, tx(), scale clamping, keymap |

---

## Task 1: Add HUD theme colors

**Files:**
- Modify: `portal_frame/gui/theme.py:3-31`

- [ ] **Step 1: Add the two HUD color entries to COLORS dict**

In `portal_frame/gui/theme.py`, add these two entries inside the `COLORS` dict, after the `"canvas_grid"` line:

```python
    "hud_bg":       "#2d2d30",
    "hud_bg_hover": "#3e3e42",
```

- [ ] **Step 2: Verify theme imports still work**

Run: `python -c "from portal_frame.gui.theme import COLORS; print(COLORS['hud_bg'], COLORS['hud_bg_hover'])"`

Expected: `#2d2d30 #3e3e42`

- [ ] **Step 3: Commit**

```bash
git add portal_frame/gui/theme.py
git commit -m "feat: add HUD background colors to theme"
```

---

## Task 2: Create test file for preview view state

**Files:**
- Create: `tests/test_preview.py`

- [ ] **Step 1: Write failing tests for view state initialization and fit-to-window**

Create `tests/test_preview.py`:

```python
"""Tests for FramePreview view state, transform, and scaling."""

import math
import pytest

from portal_frame.gui.preview import FramePreview, DIAGRAM_MAX_PX


# ── Helpers ──

class FakeCanvas:
    """Minimal stand-in so we can test view-state logic without a live Tk root.
    We test the pure math methods directly — _fit_to_window, tx, scale clamping —
    by calling them on a FramePreview whose canvas size we fake."""

    def __init__(self, w=800, h=600):
        self.w = w
        self.h = h


def _make_preview(w=800, h=600):
    """Create a FramePreview without a Tk root by skipping __init__'s
    super().__init__ and manually setting the attributes we need."""
    obj = object.__new__(FramePreview)
    # Fake canvas size
    obj._fake_w = w
    obj._fake_h = h
    # View state (mirrors real __init__)
    obj._view_cx = 0.0
    obj._view_cy = 0.0
    obj._view_zoom = 1.0
    obj._view_zoom_base = 1.0
    obj._view_dirty = True
    obj._diagram_scales = {"M": 1.0, "V": 1.0, "N": 1.0, "D": 1.0, "F": 1.0}
    obj._active_modifier = None
    obj._active_diagram_type = "M"
    return obj


# ── View state init ──

class TestViewStateInit:
    def test_default_view_dirty(self):
        p = _make_preview()
        assert p._view_dirty is True

    def test_default_diagram_scales(self):
        p = _make_preview()
        assert p._diagram_scales == {"M": 1.0, "V": 1.0, "N": 1.0, "D": 1.0, "F": 1.0}

    def test_default_modifier_none(self):
        p = _make_preview()
        assert p._active_modifier is None


# ── tx() transform ──

class TestTxTransform:
    def test_origin_maps_to_center_offset(self):
        """tx(view_cx, view_cy) should map to canvas center."""
        p = _make_preview(800, 600)
        p._view_cx = 6.0
        p._view_cy = 3.0
        p._view_zoom = 50.0
        sx, sy = p.tx(6.0, 3.0)
        assert abs(sx - 400.0) < 0.01
        assert abs(sy - 300.0) < 0.01

    def test_zoom_scales_distance(self):
        """A 1m horizontal offset at zoom=100 should be 100px on screen."""
        p = _make_preview(800, 600)
        p._view_cx = 0.0
        p._view_cy = 0.0
        p._view_zoom = 100.0
        x0, _ = p.tx(0.0, 0.0)
        x1, _ = p.tx(1.0, 0.0)
        assert abs((x1 - x0) - 100.0) < 0.01

    def test_y_flipped(self):
        """World +Y should go screen-up (smaller screen y)."""
        p = _make_preview(800, 600)
        p._view_cx = 0.0
        p._view_cy = 0.0
        p._view_zoom = 100.0
        _, y0 = p.tx(0.0, 0.0)
        _, y1 = p.tx(0.0, 1.0)
        assert y1 < y0  # +Y world = up = smaller screen y


# ── Diagram scale clamping ──

class TestDiagramScaleClamping:
    def test_scale_clamp_max(self):
        p = _make_preview()
        p._diagram_scales["M"] = 10.0
        # Scaling up from 10.0 should stay at 10.0
        new_val = min(p._diagram_scales["M"] * 1.15, 10.0)
        assert abs(new_val - 10.0) < 0.01

    def test_scale_clamp_min(self):
        p = _make_preview()
        p._diagram_scales["M"] = 0.1
        # Scaling down from 0.1 should stay at 0.1
        new_val = max(p._diagram_scales["M"] / 1.15, 0.1)
        assert abs(new_val - 0.1) < 0.05


# ── Keymap ──

class TestScaleKeymap:
    def test_keymap_entries(self):
        from portal_frame.gui.preview import _SCALE_KEYMAP
        assert _SCALE_KEYMAP["m"] == "M"
        assert _SCALE_KEYMAP["n"] == "N"
        assert _SCALE_KEYMAP["s"] == "V"
        assert _SCALE_KEYMAP["d"] == "D"
        assert _SCALE_KEYMAP["f"] == "F"

    def test_keymap_has_five_entries(self):
        from portal_frame.gui.preview import _SCALE_KEYMAP
        assert len(_SCALE_KEYMAP) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preview.py -v`

Expected: FAIL — `_SCALE_KEYMAP` doesn't exist, `tx` is not a method, `_make_preview` attributes don't exist on the class.

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_preview.py
git commit -m "test: add failing tests for preview view state and transforms"
```

---

## Task 3: Add view state, keymap, and tx() method to FramePreview

**Files:**
- Modify: `portal_frame/gui/preview.py:1-60`

- [ ] **Step 1: Add _SCALE_KEYMAP module-level constant**

After line 19 (`_DIAGRAM_LABEL_EXTRA = 12`), add:

```python
# Keyboard shortcut -> diagram type for hold-and-scroll scaling.
# Extend this dict to add custom shortcuts in the future.
_SCALE_KEYMAP = {
    "m": "M",   # Moment
    "n": "N",   # Axial
    "s": "V",   # Shear
    "d": "D",   # Deflection (delta)
    "f": "F",   # Load display
}

# HUD display letter for each diagram type (user-facing, matches keyboard shortcut)
_HUD_DISPLAY_LETTER = {"M": "M", "V": "S", "N": "N", "D": "D", "F": "F"}
```

- [ ] **Step 2: Add view state attributes to __init__**

In `__init__` (currently lines 43-55), after the existing `self._label_offsets = {}` line, add:

```python
        # ── View state (explicit, replaces auto-fit closure) ──
        self._view_cx = 0.0       # World X at canvas center
        self._view_cy = 0.0       # World Y at canvas center
        self._view_zoom = 1.0     # Pixels per meter
        self._view_zoom_base = 1.0  # Fit-to-window zoom (for clamping)
        self._view_dirty = True   # When True, next draw recomputes fit

        # Diagram amplitude scales — independent per type, persist across switches
        self._diagram_scales = {"M": 1.0, "V": 1.0, "N": 1.0, "D": 1.0, "F": 1.0}

        # Keyboard modifier tracking for hold-and-scroll scaling
        self._active_modifier = None  # Current held key from _SCALE_KEYMAP
        self._active_diagram_type = "M"  # Synced from app.py combobox

        # Pan state
        self._pan_start = None
```

- [ ] **Step 3: Add tx() as a method**

Add this method to `FramePreview`, after `_on_resize`:

```python
    def tx(self, x, y):
        """World coordinates -> screen coordinates using explicit view state."""
        w = getattr(self, '_fake_w', None) or self.winfo_width()
        h = getattr(self, '_fake_h', None) or self.winfo_height()
        cx = w / 2.0
        cy = h / 2.0
        return (cx + (x - self._view_cx) * self._view_zoom,
                cy - (y - self._view_cy) * self._view_zoom)
```

- [ ] **Step 4: Run tests to verify keymap and tx tests pass**

Run: `python -m pytest tests/test_preview.py -v`

Expected: All `TestScaleKeymap`, `TestTxTransform`, and `TestViewStateInit` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add portal_frame/gui/preview.py tests/test_preview.py
git commit -m "feat: add view state, keymap, and tx() method to FramePreview"
```

---

## Task 4: Extract _fit_to_window() and refactor update_frame() to use view state

**Files:**
- Modify: `portal_frame/gui/preview.py:191-260`

This is the most critical task — it replaces the `tx()` closure with the view-state-driven method.

- [ ] **Step 1: Add _fit_to_window() method**

Add this method to `FramePreview`, after `tx()`:

```python
    def _fit_to_window(self, geom, loads=None):
        """Compute view_cx, view_cy, view_zoom to fit the frame in the canvas.

        This replaces the old inline scale/ox/oy computation. The result is
        stored in _view_cx/cy/zoom so that tx() can use it.
        """
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

        # World center of the frame bounding box
        world_cx = span / 2.0
        world_cy = ridge / 2.0

        # Screen center point that the old code targeted:
        # ox = pad_side + (w - 2*pad_side - span*zoom) / 2  (left edge of frame in screen)
        # oy = h - pad_bot  (ground line in screen)
        # The old tx: screen_x = ox + x*zoom, screen_y = oy - y*zoom
        # Our new tx: screen_x = w/2 + (x - view_cx)*zoom, screen_y = h/2 - (y - view_cy)*zoom
        # Matching at the old frame center (span/2, ridge/2):
        #   old_screen_x = ox + (span/2)*zoom
        #   new_screen_x = w/2 + (span/2 - view_cx)*zoom
        # Setting equal: view_cx = span/2 - (ox - w/2)/zoom
        ox = pad_side + (w - 2 * pad_side - span * zoom) / 2
        oy = h - pad_bot
        self._view_cx = span / 2.0 - (ox + span / 2.0 * zoom - w / 2.0) / zoom
        self._view_cy = (oy - h / 2.0) / zoom

        self._view_zoom = zoom
        self._view_zoom_base = zoom
        self._view_dirty = False
```

- [ ] **Step 2: Refactor update_frame() to use _fit_to_window() and self.tx()**

Replace the current `update_frame()` method. The key changes are:
1. Call `_fit_to_window()` when `_view_dirty` is True
2. Remove the inline scale/ox/oy computation (lines 245-256)
3. Remove the `def tx(x, y):` closure (lines 258-259)
4. Replace all `tx(` calls with `self.tx(`
5. Draw HUD last (placeholder call for now)

In `update_frame()`, replace lines 196-268 (from `self.delete("all")` through `ns = {k: tx(*v) ...}`) with:

```python
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

        # Refit view if dirty (first draw, geometry change, normalize)
        if self._view_dirty:
            self._fit_to_window(geom, loads)

        # Draw grid
        for i in range(0, w, 30):
            self.create_line(i, 0, i, h, fill=COLORS["canvas_grid"], dash=(1, 4))
        for i in range(0, h, 30):
            self.create_line(0, i, w, i, fill=COLORS["canvas_grid"], dash=(1, 4))

        # Transform nodes using view-state tx()
        ns = {k: self.tx(*v) for k, v in nodes.items()}
```

Then replace every remaining `tx(` with `self.tx(` in `update_frame()`. Specifically, these locations:
- Line ~302: `bracket_left = tx(0, crane_h)` -> `bracket_left = self.tx(0, crane_h)`
- Line ~303: `bracket_right = tx(span, crane_h)` -> `bracket_right = self.tx(span, crane_h)`

And the ground line calculation — replace:
```python
        oy = h - pad_bot  # This no longer exists
```
The ground line `gy` must now use `self.tx`:
```python
        # Ground line
        gx1, gy = self.tx(0, 0)
        gx2, _ = self.tx(span, 0)
        gx1 -= 20
        gx2 += 20
        self.create_line(gx1, gy, gx2, gy, fill=COLORS["fg_dim"], width=1, dash=(4, 2))
```

At the end of `update_frame()`, after `self._resolve_overlaps()`, add:

```python
        # HUD controls (drawn last, on top of everything)
        self._draw_hud()
```

- [ ] **Step 3: Run existing tests to check nothing is broken**

Run: `python -m pytest tests/ -v`

Expected: All 144 existing tests PASS (none depend on preview internals).

- [ ] **Step 4: Launch GUI and visually verify frame renders correctly**

Run: `python -m portal_frame.run_gui`

Expected: Frame renders as before — same positions, same padding, same look. The only difference is the transform is now view-state-driven. No HUD visible yet (drawn in Task 7).

- [ ] **Step 5: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "refactor: replace tx() closure with explicit view state and _fit_to_window()"
```

---

## Task 5: Add pan and zoom event handlers

**Files:**
- Modify: `portal_frame/gui/preview.py` (__init__ bindings + new methods)

- [ ] **Step 1: Bind mouse events in __init__**

In `__init__`, after the `self._pan_start = None` line added in Task 3, add:

```python
        # ── Event bindings for pan/zoom/keyboard ──
        self.bind("<ButtonPress-2>", self._on_pan_start)
        self.bind("<B2-Motion>", self._on_pan_move)
        self.bind("<ButtonRelease-2>", self._on_pan_end)
        self.bind("<Double-Button-2>", self._on_zoom_extents)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.bind("<Enter>", lambda e: self.focus_set())
```

- [ ] **Step 2: Add pan handlers**

Add these methods after `tx()`:

```python
    # ── Pan handlers ──

    def _on_pan_start(self, event):
        self._pan_start = (event.x, event.y)
        self.config(cursor="fleur")

    def _on_pan_move(self, event):
        if self._pan_start is None:
            return
        dx_px = event.x - self._pan_start[0]
        dy_px = event.y - self._pan_start[1]
        # Convert pixel delta to world delta (y is flipped)
        if self._view_zoom > 0:
            self._view_cx -= dx_px / self._view_zoom
            self._view_cy += dy_px / self._view_zoom
        self._pan_start = (event.x, event.y)
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)

    def _on_pan_end(self, event):
        self._pan_start = None
        self.config(cursor="")
```

- [ ] **Step 3: Add zoom handler**

```python
    # ── Zoom handler ──

    def _on_wheel(self, event):
        # On Windows, event.delta is typically +/-120
        scroll_up = event.delta > 0

        # Check for keyboard modifier -> diagram scaling
        if self._active_modifier is not None:
            dtype = _SCALE_KEYMAP.get(self._active_modifier)
            if dtype:
                factor = 1.15 if scroll_up else (1.0 / 1.15)
                self._diagram_scales[dtype] = max(0.1, min(10.0,
                    self._diagram_scales[dtype] * factor))
                if self._geom:
                    self.update_frame(self._geom, self._supports, self._loads, self._diagram)
                return

        # No modifier -> zoom toward cursor
        factor = 1.1 if scroll_up else (1.0 / 1.1)
        new_zoom = self._view_zoom * factor

        # Clamp to [0.1x, 20x] of base fit zoom
        min_zoom = self._view_zoom_base * 0.1
        max_zoom = self._view_zoom_base * 20.0
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))

        if abs(new_zoom - self._view_zoom) < 1e-9:
            return

        # Zoom toward cursor: keep the world point under the cursor fixed
        w = self.winfo_width()
        h = self.winfo_height()
        cx, cy = w / 2.0, h / 2.0
        # World point under cursor before zoom
        wx = self._view_cx + (event.x - cx) / self._view_zoom
        wy = self._view_cy - (event.y - cy) / self._view_zoom
        # After zoom, we want the same world point under the cursor:
        # event.x = cx + (wx - new_view_cx) * new_zoom
        # => new_view_cx = wx - (event.x - cx) / new_zoom
        self._view_cx = wx - (event.x - cx) / new_zoom
        self._view_cy = wy + (event.y - cy) / new_zoom
        self._view_zoom = new_zoom

        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)
```

- [ ] **Step 4: Add zoom extents handler**

```python
    def _on_zoom_extents(self, event):
        """Double-click middle mouse: refit view to frame (like Autodesk zoom extents).
        Leaves diagram amplitude scales untouched."""
        self._view_dirty = True
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)
```

- [ ] **Step 5: Add keyboard modifier handlers**

```python
    # ── Keyboard modifier tracking ──

    def _on_key_press(self, event):
        key = event.keysym.lower()
        if key in _SCALE_KEYMAP:
            self._active_modifier = key

    def _on_key_release(self, event):
        key = event.keysym.lower()
        if key == self._active_modifier:
            self._active_modifier = None
```

- [ ] **Step 6: Add set_diagram_type() public method**

```python
    def set_diagram_type(self, dtype: str):
        """Called by app.py when the diagram type combobox changes.
        Updates the HUD label to reflect the active type."""
        self._active_diagram_type = dtype
        # Redraw HUD only if we have a frame
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)
```

- [ ] **Step 7: Launch GUI and test pan/zoom interactively**

Run: `python -m portal_frame.run_gui`

Test:
1. Mouse wheel over the canvas -> frame zooms in/out toward cursor
2. Middle-click drag -> frame pans smoothly
3. Double-click middle mouse -> frame snaps back to fit
4. Hold `M` + scroll -> nothing visible yet (diagram scaling wired in Task 6)

- [ ] **Step 8: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "feat: add pan, zoom, zoom-extents, and keyboard modifier handlers"
```

---

## Task 6: Wire diagram amplitude scales into drawing code

**Files:**
- Modify: `portal_frame/gui/preview.py` (draw_force_diagram, _draw_deflection_diagram, _draw_loads)

- [ ] **Step 1: Apply diagram scale in draw_force_diagram()**

In `draw_force_diagram()`, the max pixel height is set at line ~572:

```python
        effective_max_px = DIAGRAM_MAX_PX * shrink
```

Replace with:

```python
        dtype_scale = self._diagram_scales.get(dtype, 1.0)
        effective_max_px = DIAGRAM_MAX_PX * shrink * dtype_scale
```

- [ ] **Step 2: Apply diagram scale in _draw_deflection_diagram()**

In `_draw_deflection_diagram()`, the initial alpha is set at line ~713:

```python
        alpha_0 = DIAGRAM_MAX_PX / max_disp
```

Replace with:

```python
        dtype_scale = self._diagram_scales.get("D", 1.0)
        alpha_0 = DIAGRAM_MAX_PX * dtype_scale / max_disp
```

- [ ] **Step 3: Apply load display scale in _draw_loads()**

In `_draw_loads()` (line ~845), the arrow length is computed in `_draw_udl_segment()` at line ~928:

```python
        arrow_len = (abs(w_kn) / max_w) * self.ARROW_MAX_LEN
```

Replace with:

```python
        load_scale = self._diagram_scales.get("F", 1.0)
        arrow_len = (abs(w_kn) / max_w) * self.ARROW_MAX_LEN * load_scale
```

- [ ] **Step 4: Launch GUI and test diagram scaling**

Run: `python -m portal_frame.run_gui`

Test: Analyse a frame, select Moment diagram, hold `M` + scroll up/down -> moment diagram amplitude changes. Switch to Shear (`V`), hold `S` + scroll -> shear scales independently. Switch back to Moment -> previous scale preserved. Hold `F` + scroll on load display -> arrow lengths change.

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "feat: wire diagram amplitude scales into force/deflection/load drawing"
```

---

## Task 7: Draw HUD controls on canvas

**Files:**
- Modify: `portal_frame/gui/preview.py`

- [ ] **Step 1: Add the _draw_hud() method**

Add this method to `FramePreview`:

```python
    # ── HUD controls (canvas-drawn, top-right corner) ──

    def _draw_hud(self):
        """Draw Normalize button and [-] M [+] scaling control in top-right."""
        w = self.winfo_width()
        if w < 200:
            return  # Canvas too small for HUD

        margin = 8
        btn_h = 22
        btn_pad_x = 8
        btn_pad_y = 3
        gap = 6  # gap between controls

        bg = COLORS["hud_bg"]
        border = COLORS["border"]
        fg = COLORS["fg_dim"]
        fg_hover = COLORS["fg_bright"]
        bg_hover = COLORS["hud_bg_hover"]

        # ── Helper to draw a rounded-rect button ──
        def draw_button(x, y, text, tag, text_color=None):
            """Draw a rect with centered text. Returns (x_left, x_right) for layout."""
            if text_color is None:
                text_color = fg
            # Measure text width (approximate: 7px per char for FONT_SMALL)
            text_w = len(text) * 7 + 2 * btn_pad_x
            x1 = x - text_w / 2
            y1 = y
            x2 = x + text_w / 2
            y2 = y + btn_h

            rect = self.create_rectangle(
                x1, y1, x2, y2, fill=bg, outline=border, width=1,
                tags=("hud", tag))
            txt = self.create_text(
                (x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=text_color,
                font=FONT_SMALL, tags=("hud", tag))

            # Hover effects
            for item in (rect, txt):
                self.tag_bind(item, "<Enter>",
                    lambda e, r=rect, t=txt: (
                        self.itemconfig(r, fill=bg_hover),
                        self.itemconfig(t, fill=fg_hover),
                        self.config(cursor="hand2")))
                self.tag_bind(item, "<Leave>",
                    lambda e, r=rect, t=txt, tc=text_color: (
                        self.itemconfig(r, fill=bg),
                        self.itemconfig(t, fill=tc),
                        self.config(cursor="")))

            return x1, x2, rect, txt

        # Layout: right-to-left from the margin
        # [Normalize]  [-] M [+]

        # Active diagram type display letter and color
        dtype = self._active_diagram_type
        display_letter = _HUD_DISPLAY_LETTER.get(dtype, dtype)
        dtype_color = DIAGRAM_COLORS.get(
            {"D": "δ"}.get(dtype, dtype), COLORS["fg_bright"])

        top_y = margin

        # [+] button (rightmost)
        plus_cx = w - margin - 16
        x1_plus, x2_plus, rect_plus, txt_plus = draw_button(
            plus_cx, top_y, "+", "hud_plus")

        # Type label (between - and +)
        label_cx = x1_plus - gap - 7
        type_label = self.create_text(
            label_cx, top_y + btn_h / 2, text=display_letter,
            fill=dtype_color, font=FONT_SMALL, tags=("hud",))

        # [-] button
        minus_cx = label_cx - gap - 16
        x1_minus, x2_minus, rect_minus, txt_minus = draw_button(
            minus_cx, top_y, "-", "hud_minus")

        # [Normalize] button
        norm_cx = x1_minus - gap - 35
        x1_norm, x2_norm, rect_norm, txt_norm = draw_button(
            norm_cx, top_y, "Normalize", "hud_normalize")

        # ── Click handlers ──
        def on_plus(e):
            dtype = self._active_diagram_type
            key = {"D": "D"}.get(dtype, dtype)
            self._diagram_scales[key] = min(10.0,
                self._diagram_scales.get(key, 1.0) * 1.15)
            if self._geom:
                self.update_frame(self._geom, self._supports, self._loads, self._diagram)

        def on_minus(e):
            dtype = self._active_diagram_type
            key = {"D": "D"}.get(dtype, dtype)
            self._diagram_scales[key] = max(0.1,
                self._diagram_scales.get(key, 1.0) / 1.15)
            if self._geom:
                self.update_frame(self._geom, self._supports, self._loads, self._diagram)

        def on_normalize(e):
            self._diagram_scales = {k: 1.0 for k in self._diagram_scales}
            self._view_dirty = True
            if self._geom:
                self.update_frame(self._geom, self._supports, self._loads, self._diagram)

        for item in (rect_plus, txt_plus):
            self.tag_bind(item, "<ButtonRelease-1>", on_plus)
        for item in (rect_minus, txt_minus):
            self.tag_bind(item, "<ButtonRelease-1>", on_minus)
        for item in (rect_norm, txt_norm):
            self.tag_bind(item, "<ButtonRelease-1>", on_normalize)
```

- [ ] **Step 2: Verify _draw_hud() is called in update_frame()**

This was added at the end of Task 4 Step 2. Confirm the line `self._draw_hud()` exists at the end of `update_frame()`, after `self._resolve_overlaps()`.

- [ ] **Step 3: Launch GUI and test HUD**

Run: `python -m portal_frame.run_gui`

Test:
1. Top-right shows `[Normalize]  [-] M [+]`
2. Hover over buttons -> highlight effect
3. Click `[+]` -> active diagram amplitude increases
4. Click `[-]` -> decreases
5. Click `[Normalize]` -> view refits and all scales reset to 1.0
6. Switch diagram type in combobox -> letter between `[-]` and `[+]` updates

- [ ] **Step 4: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "feat: add canvas-drawn HUD with Normalize and diagram scale controls"
```

---

## Task 8: Wire app.py to notify preview of diagram type changes

**Files:**
- Modify: `portal_frame/gui/app.py:161-162`

- [ ] **Step 1: Add set_diagram_type call in combobox handler**

In `app.py`, the diagram type combobox binding is at line 161-162:

```python
        self.diagram_type_combo.bind("<<ComboboxSelected>>",
                                      lambda _: self._draw_preview())
```

Replace with:

```python
        self.diagram_type_combo.bind("<<ComboboxSelected>>",
                                      lambda _: self._on_diagram_type_changed())
```

- [ ] **Step 2: Add the _on_diagram_type_changed method**

Add this method to `PortalFrameApp` (near the other event handler methods):

```python
    def _on_diagram_type_changed(self):
        """Handle diagram type combobox change — notify preview and redraw."""
        dtype = self.diagram_type_var.get()
        # Map combobox values to scale keys: "M", "V", "N", "delta" -> "D"
        scale_key = {"M": "M", "V": "V", "N": "N", "\u03b4": "D"}.get(dtype, dtype)
        self.preview.set_diagram_type(scale_key)
        self._draw_preview()
```

- [ ] **Step 3: Launch GUI and test end-to-end**

Run: `python -m portal_frame.run_gui`

Test:
1. Change diagram type from M to V -> HUD shows `[-] S [+]`
2. Change to delta -> HUD shows `[-] D [+]`
3. Scale moment with `M + scroll`, switch to shear, switch back -> moment scale preserved
4. Click Normalize -> all scales reset, view refits

- [ ] **Step 4: Commit**

```bash
git add portal_frame/gui/app.py
git commit -m "feat: notify preview of diagram type changes from combobox"
```

---

## Task 9: Mark view dirty on geometry changes

**Files:**
- Modify: `portal_frame/gui/preview.py:191-195`

- [ ] **Step 1: Detect geometry and roof-type changes in update_frame()**

At the top of `update_frame()`, after storing the new values, add change detection:

```python
    def update_frame(self, geom: dict, supports: tuple, loads: dict = None, diagram: dict = None):
        # Detect geometry change -> mark view dirty for auto-refit
        old_geom = self._geom
        if old_geom is not None and geom is not None:
            # Check key geometry fields that affect frame shape
            for key in ("span", "eave_height", "roof_pitch", "roof_pitch_2",
                        "roof_type", "apex_x", "ridge_height", "crane_rail_height"):
                if geom.get(key) != old_geom.get(key):
                    self._view_dirty = True
                    # Roof type change is major topology change -> reset scales
                    if key == "roof_type":
                        self._diagram_scales = {k: 1.0 for k in self._diagram_scales}
                    break

        self._geom = geom
        self._supports = supports
        self._loads = loads
        self._diagram = diagram
```

- [ ] **Step 2: Launch GUI and test auto-refit**

Run: `python -m portal_frame.run_gui`

Test:
1. Zoom into a corner of the frame
2. Change span in the Geometry tab -> view auto-refits to show full frame
3. Change roof pitch -> auto-refits
4. Switch gable to mono -> auto-refits AND scales reset to 1.0
5. Pan the view, then change eave height -> auto-refits

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "feat: auto-refit view on geometry changes, reset scales on roof type flip"
```

---

## Task 10: Final integration test and cleanup

**Files:**
- Modify: `tests/test_preview.py` (add integration-level tests)

- [ ] **Step 1: Add tests for diagram scale integration**

Append to `tests/test_preview.py`:

```python
# ── Diagram scale application ──

class TestDiagramScaleApplication:
    def test_scale_multiplies_max_px(self):
        """When diagram scale is 2.0, effective_max_px should double."""
        p = _make_preview()
        p._diagram_scales["M"] = 2.0
        # The drawing code computes: DIAGRAM_MAX_PX * shrink * dtype_scale
        # With shrink=1.0 and scale=2.0:
        effective = DIAGRAM_MAX_PX * 1.0 * p._diagram_scales["M"]
        assert abs(effective - 120.0) < 0.01

    def test_normalize_resets_all_scales(self):
        p = _make_preview()
        p._diagram_scales["M"] = 3.0
        p._diagram_scales["V"] = 0.5
        p._diagram_scales["N"] = 2.0
        # Simulate normalize
        p._diagram_scales = {k: 1.0 for k in p._diagram_scales}
        for v in p._diagram_scales.values():
            assert abs(v - 1.0) < 0.01

    def test_scale_persists_across_type_switch(self):
        p = _make_preview()
        p._diagram_scales["M"] = 2.5
        p._active_diagram_type = "V"
        # Switch back to M
        p._active_diagram_type = "M"
        assert abs(p._diagram_scales["M"] - 2.5) < 0.01


class TestViewDirtyOnGeometryChange:
    def test_span_change_marks_dirty(self):
        p = _make_preview()
        p._view_dirty = False
        p._geom = {"span": 12, "roof_type": "gable"}
        new_geom = {"span": 15, "roof_type": "gable"}
        # Simulate the detection logic
        old_geom = p._geom
        for key in ("span", "eave_height", "roof_pitch", "roof_pitch_2",
                     "roof_type"):
            if new_geom.get(key) != old_geom.get(key):
                p._view_dirty = True
                break
        assert p._view_dirty is True

    def test_roof_type_change_resets_scales(self):
        p = _make_preview()
        p._diagram_scales["M"] = 3.0
        p._geom = {"span": 12, "roof_type": "gable"}
        new_geom = {"span": 12, "roof_type": "mono"}
        old_geom = p._geom
        for key in ("span", "eave_height", "roof_pitch", "roof_pitch_2",
                     "roof_type"):
            if new_geom.get(key) != old_geom.get(key):
                p._view_dirty = True
                if key == "roof_type":
                    p._diagram_scales = {k: 1.0 for k in p._diagram_scales}
                break
        assert p._diagram_scales["M"] == 1.0
```

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS (existing 144 + new preview tests).

- [ ] **Step 3: Full interactive smoke test**

Run: `python -m portal_frame.run_gui`

Complete checklist:
- [ ] Mouse wheel alone -> zoom in/out toward cursor
- [ ] Middle mouse drag -> pan view
- [ ] Double-click middle mouse -> zoom extents (refit)
- [ ] Hold M + scroll -> moment diagram scales
- [ ] Hold S + scroll -> shear diagram scales
- [ ] Hold N + scroll -> axial diagram scales
- [ ] Hold D + scroll -> deflection diagram scales
- [ ] Hold F + scroll -> load arrows scale
- [ ] HUD `[-] M [+]` visible in top-right, updates with diagram type
- [ ] `[+]` click -> increases current diagram scale
- [ ] `[-]` click -> decreases current diagram scale
- [ ] `[Normalize]` click -> resets view and all scales
- [ ] Change geometry -> view auto-refits
- [ ] Switch gable/mono -> scales reset
- [ ] All existing label dragging still works
- [ ] Diagrams render with envelopes, peak labels, etc.

- [ ] **Step 4: Commit**

```bash
git add tests/test_preview.py
git commit -m "test: add preview view state and scaling integration tests"
```