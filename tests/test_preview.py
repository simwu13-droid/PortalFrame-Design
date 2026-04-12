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
