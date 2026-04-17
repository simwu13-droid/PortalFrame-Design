# GUI File Split — Design

**Date:** 2026-04-17
**Status:** Approved — ready for implementation planning
**Scope:** `portal_frame/gui/app.py` (2,566 lines) and `portal_frame/gui/preview.py` (1,640 lines)
**Branch:** `refactor/split-large-gui-files`

## Problem

Two GUI modules have grown far beyond the target size:

| File | Current lines | Responsibilities it has absorbed |
|---|---|---|
| `gui/app.py` | 2,566 | Window + tab orchestration + every tab's UI + wind-case synthesis + persistence + analysis orchestration + results panel + diagram controller |
| `gui/preview.py` | 1,640 | Canvas + pan/zoom + drag + label layout + HUD + frame rendering + load drawing + diagram rendering |

This makes the files hard to navigate, risky to edit, and consumes excessive context when working on them. New feature additions tend to land in these files, which causes them to grow further.

## Goals

1. No single module exceeds ~600 lines post-refactor.
2. Each module has one clear responsibility (SRP).
3. **Zero behaviour change.** Same GUI, same buttons, same numeric output, same saved-config format.
4. All 223 existing tests continue to pass unchanged.
5. Opportunistic simplification (option B) — rename confusing internals, collapse duplicated UI builders, remove dead branches — **only in code being touched**, no drive-by refactoring.

## Non-goals

- Widget library changes (no new widget classes).
- Behavioural changes to the GUI (no new features, no moved buttons).
- Changes to `standards/`, `io/`, `models/`, `analysis/`, `solvers/`, or `tests/`.
- Dialogs split (`gui/dialogs.py` at 808 lines is borderline; left alone this pass).
- Test expansion (out-of-scope; manual smoke test is the verification step).

## Target structure

### `portal_frame/gui/` after refactor

```
gui/
  app.py                   (~250 lines)  Window, tab bar, orchestration
  preview.py               (~250 lines)  FramePreview shell; composes canvas/*
  theme.py                               (unchanged)
  widgets.py                             (unchanged)
  dialogs.py                             (unchanged — deferred)
  wind_generator.py        (~320 lines)  _auto_generate_wind_cases, _synthesize_wind_cases
  persistence.py           (~330 lines)  _collect_config, _apply_config, recent files, auto-restore, _on_close
  analysis_runner.py       (~350 lines)  _generate, _analyse, _run_design_checks, _bucket_*, _update_results_panel
  diagram_controller.py    (~550 lines)  _update_preview, _draw_preview, _build_preview_loads, _build_diagram_data, _update_diagram_dropdowns, refresh_load_case_list
  tabs/
    __init__.py
    frame_tab.py           (~250 lines)  _build_frame_tab + on_frame_change handlers + _build_geometry
    wind_tab.py            (~150 lines)  _build_wind_tab + wind-case select + table change
    earthquake_tab.py      (~270 lines)  _build_earthquake_tab + eq handlers + _update_eq_results + _estimate_member_self_weight
    crane_tab.py           (~160 lines)  _build_crane_tab + crane handlers + add/remove Hc rows
    combos_tab.py          (~30 lines)   _build_combos_tab
  canvas/
    __init__.py
    interaction.py         (~200 lines)  pan, wheel zoom, zoom-extents, key press/release, tooltip show/hide
    labels.py              (~280 lines)  _make_draggable, _drag_*, _create_label, _create_boxed_draggable_label, _resolve_overlaps
    hud.py                 (~200 lines)  _draw_hud, _draw_axis_indicator
    frame_render.py        (~500 lines)  update_frame, _fit_to_window, _draw_loads, _draw_udl_segment
    diagrams.py            (~450 lines)  draw_force_diagram, _draw_deflection_diagram, _diagram_bounds
```

### Extraction technique

**Module-level functions that take `app` (or `canvas`) as first argument.** No mixins, no multiple inheritance, no new abstract classes.

**Example — tab builder:**

Before (inside `app.py`):
```python
class PortalFrameApp(tk.Tk):
    def _build_frame_tab(self, parent):
        self.span_var = tk.StringVar(value="18.0")
        LabeledEntry(parent, "Span (m)", self.span_var).pack(...)
        ...
```

After:
```python
# gui/tabs/frame_tab.py
def build_frame_tab(app, parent):
    app.span_var = tk.StringVar(value="18.0")
    LabeledEntry(parent, "Span (m)", app.span_var).pack(...)
    ...
```

```python
# gui/app.py
from portal_frame.gui.tabs.frame_tab import build_frame_tab

class PortalFrameApp(tk.Tk):
    def _build_ui(self):
        ...
        build_frame_tab(self, self._tab_pages["Frame"])
```

All tkinter state (StringVars, widgets, callbacks) continues to live on `self`. The extractions are purely textual — method body moves, receiver becomes a parameter named `app`.

**Example — canvas helper:**

```python
# gui/canvas/hud.py
def draw_hud(canvas):
    # uses canvas.winfo_width(), canvas._overlay_mode, canvas._diagram_scale, etc.
    ...
```

```python
# gui/preview.py
from portal_frame.gui.canvas.hud import draw_hud

class FramePreview(tk.Canvas):
    def _draw_hud(self):
        draw_hud(self)
```

For methods called externally (e.g. `update_frame`, `set_design_checks`) we keep a thin pass-through on `FramePreview` to preserve the public API.

### Why this technique

- **Minimal behaviour risk:** every `self.X` reference becomes `app.X` — mechanical edit, no semantic change.
- **Preserves public API:** external callers of `FramePreview` and `PortalFrameApp` are unchanged.
- **Works with tkinter's event system:** callbacks bound to widgets continue to reference bound methods or closures on `app`.
- **Readable later:** a grep for `app.span_var` reaches every use, same as today.

## Simplification targets (option B)

Applied only in files being moved, not in unrelated code:

1. **Duplicated labelled-row builders.** Several tabs open-code `tk.Label(...) + tk.Entry(...)` where `LabeledEntry` would serve. Replace where the behaviour matches exactly.
2. **`_bucket_design_checks` → `_group_design_checks_by_member`** — renames internal helper to match what it actually does.
3. **Dead branches / commented-out blocks.** Remove if present and obviously dead (git history preserves the original).
4. **`_get_h_and_depth` / `_get_wind_params`** — inline if each has a single caller post-split, else keep.
5. **Repeated HUD colour-state logic.** Consolidate the "bright when on, dim when off" pattern into a single helper in `canvas/hud.py`.

These simplifications are judgement calls made during extraction. If any simplification changes behaviour (even subtly), it is deferred to a follow-up and flagged to the user.

## Verification plan

Every extraction step ends with:

1. **Import sanity:** `python -c "from portal_frame.gui.app import PortalFrameApp"` with no errors.
2. **Test suite:** `python -m pytest tests/ -v` — must stay at 223/223 passing.
3. **GUI launch smoke test:** `python -m portal_frame.run_gui` — window opens, every tab renders, no console errors.

After the full refactor:

4. **Manual click-through:** open each tab, change a value, toggle overlays (DIM/SLS/ULS), drag a label, pan/zoom the canvas, switch diagram types. All visible behaviour matches pre-refactor.
5. **Output byte-identical:** generate a SpaceGass `.txt` with the default config on `main` and on the refactor branch; `diff` must show no differences.
6. **Save/load roundtrip:** save a config, close the app, reopen → auto-restore brings back the exact same state.

Any failure aborts and rolls back the last extraction.

## Rollback

Branch-based. If the refactor goes wrong at any stage the user deletes the branch and returns to `main` untouched.

## Open questions

None — plan approved by user on 2026-04-17.
