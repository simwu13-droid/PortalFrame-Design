"""Frame preview canvas — 2D rendering of portal frame with loads."""

import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_SMALL
from portal_frame.gui.canvas.interaction import (
    on_resize, on_pan_start, on_pan_move, on_pan_end, on_wheel,
    on_zoom_extents, on_key_press, on_key_release,
    show_tooltip, hide_tooltip,
    tx as _tx_fn,
    set_diagram_type as _set_diagram_type_fn,
    SCALE_KEYMAP as _SCALE_KEYMAP,
)
from portal_frame.gui.canvas.labels import (
    _envelope_label_parts,
    make_draggable, drag_start, drag_move, drag_end,
    create_label, create_boxed_draggable_label, resolve_overlaps,
)
from portal_frame.gui.canvas.hud import draw_hud, draw_axis_indicator
from portal_frame.gui.canvas.frame_render import (
    update_frame as _update_frame_fn,
    fit_to_window as _fit_to_window_fn,
)
from portal_frame.gui.canvas.diagrams import (
    draw_force_diagram as _draw_force_diagram_fn,
    DIAGRAM_MAX_PX,
)



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
        # Label partners: text item id -> [companion canvas items] that
        # should move in lockstep when the text is dragged (e.g. the
        # background rect on ULS capacity labels and the SLS apex badge).
        self._label_partners: dict[int, list[int]] = {}

        # Dimension annotations visibility (toggled from HUD)
        self._show_dimensions: bool = True

        # ── View state (explicit, replaces auto-fit closure) ──
        self._view_cx = 0.0       # World X at canvas center
        self._view_cy = 0.0       # World Y at canvas center
        self._view_zoom = 1.0     # Pixels per meter
        self._view_zoom_base = 1.0  # Fit-to-window zoom (for clamping)
        self._view_dirty = True   # When True, next draw recomputes fit

        # Diagram amplitude scales — independent per type, persist across switches.
        # "F" is the load-arrow display scale, not a force-diagram type (no color/unit).
        self._diagram_scales = {"M": 1.0, "V": 1.0, "N": 1.0, "D": 1.0, "F": 1.0}

        # Keyboard modifier tracking for hold-and-scroll scaling
        self._active_modifier = None  # Current held key from _SCALE_KEYMAP
        self._active_diagram_type = "M"  # Synced from app.py combobox

        # Pan state
        self._pan_start = None

        # Design check overlay state
        # _dc_groups: {"col_L": MemberDesignCheck | None, "col_R": ..., ...}
        # set via set_design_checks() from app.py
        self._dc_groups: dict[str, object] = {}
        # SLS check list (wind/eq rows). Set via set_sls_checks().
        self._sls_checks: list = []
        # Overlay mode is single-slot: "off" | "uls" | "sls". Changing one
        # mode automatically clears the other — mutual exclusion comes
        # free from the single-slot state.
        self._overlay_mode: str = "off"

        # ── Event bindings for pan/zoom/keyboard ──
        self.bind("<ButtonPress-2>", self._on_pan_start)
        self.bind("<B2-Motion>", self._on_pan_move)
        self.bind("<ButtonRelease-2>", self._on_pan_end)
        self.bind("<Double-Button-2>", self._on_zoom_extents)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.bind("<Enter>", lambda e: self.focus_set())

    def _on_resize(self, *args):
        on_resize(self, *args)

    def set_design_checks(self, groups: dict | None) -> None:
        """Receive bucketed ULS design-check results from app.py.

        groups keys: "col_L", "col_R", "raf_L", "raf_R" (mono uses "raf_L"
        for the single rafter line and omits "raf_R"). Values are the
        worst-utilisation MemberDesignCheck for each canvas line, or None
        if no check is available.

        Pass None to clear.
        """
        self._dc_groups = groups or {}

    def set_sls_checks(self, checks: list | None) -> None:
        """Receive SLS apex deflection checks from app.py. Pass None to clear."""
        self._sls_checks = checks or []

    def toggle_uls_overlay(self) -> None:
        """Toggle the ULS member capacity overlay. Mutually exclusive with SLS."""
        self._overlay_mode = "off" if self._overlay_mode == "uls" else "uls"
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)

    def toggle_sls_overlay(self) -> None:
        """Toggle the SLS apex deflection overlay. Mutually exclusive with ULS."""
        self._overlay_mode = "off" if self._overlay_mode == "sls" else "sls"
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)

    def toggle_dimensions(self) -> None:
        """Toggle the dimension annotations (span, eave, ridge, pitches)."""
        self._show_dimensions = not self._show_dimensions
        if self._geom:
            self.update_frame(self._geom, self._supports, self._loads, self._diagram)

    def _dc_color_for(self, status: str, util: float) -> str:
        """Return overlay colour for a member based on status + util."""
        if status == "NO_DATA":
            return COLORS["dc_nodata"]
        if util > 1.0:
            return COLORS["dc_fail"]
        if util > 0.85:
            return COLORS["dc_warn"]
        return COLORS["dc_pass"]

    def _sls_worst_util(self) -> tuple[float, str]:
        """Return (worst_util, worst_status) across both SLS categories.

        When no checks exist, returns (0.0, 'NO_DATA') so callers treat it
        as uninitialised/grey.
        """
        if not self._sls_checks:
            return 0.0, "NO_DATA"
        worst = max(self._sls_checks, key=lambda c: c.util)
        return worst.util, worst.status

    def _show_tooltip(self, event, text: str) -> None:
        show_tooltip(self, event, text)

    def _hide_tooltip(self) -> None:
        hide_tooltip(self)

    def tx(self, x, y):
        return _tx_fn(self, x, y)

    def _on_pan_start(self, event):
        on_pan_start(self, event)

    def _on_pan_move(self, event):
        on_pan_move(self, event)

    def _on_pan_end(self, event):
        on_pan_end(self, event)

    def _on_wheel(self, event):
        on_wheel(self, event)

    def _on_zoom_extents(self, event):
        on_zoom_extents(self, event)

    def _on_key_press(self, event):
        on_key_press(self, event)

    def _on_key_release(self, event):
        on_key_release(self, event)

    def set_diagram_type(self, dtype: str):
        _set_diagram_type_fn(self, dtype)

    def _fit_to_window(self, geom, loads=None):
        _fit_to_window_fn(self, geom, loads)

    # ── Draggable label infrastructure ──

    def _make_draggable(self, item_id, label_key):
        make_draggable(self, item_id, label_key)

    def _drag_start(self, event, item_id, label_key):
        drag_start(self, event, item_id, label_key)

    def _drag_move(self, event):
        drag_move(self, event)

    def _drag_end(self, event):
        drag_end(self, event)

    def _create_label(self, x, y, text, label_key, fill=None, font=None,
                      anchor="center", justify="center"):
        return create_label(self, x, y, text, label_key, fill=fill, font=font,
                            anchor=anchor, justify=justify)

    def _create_boxed_draggable_label(
        self, x: float, y: float, text: str, label_key: str,
        fg: str, outline: str | None = None,
        bg: str | None = None, anchor: str = "center",
        bbox_pad: int = 3,
    ) -> int:
        return create_boxed_draggable_label(self, x, y, text, label_key,
                                            fg=fg, outline=outline, bg=bg,
                                            anchor=anchor, bbox_pad=bbox_pad)

    def _resolve_overlaps(self):
        resolve_overlaps(self)

    # ── Main draw ──

    def update_frame(self, geom: dict, supports: tuple, loads: dict = None, diagram: dict = None):
        _update_frame_fn(self, geom, supports, loads, diagram)

    # ── Force diagram drawing ──

    def draw_force_diagram(self, diagram, ns):
        _draw_force_diagram_fn(self, diagram, ns)

