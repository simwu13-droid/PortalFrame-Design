# Dialogs Split Design

> **Status:** Approved for implementation

## Goal

Split `portal_frame/gui/dialogs.py` (808 lines, one class) into a `gui/dialogs/` package to bring every file under the 600-line target, consistent with the established canvas/ and tabs/ extraction pattern.

## Architecture

Convert `gui/dialogs.py` into a `gui/dialogs/` package. External callers (`app.py`, `wind_tab.py`) both import only `WindSurfacePanel` — the `__init__.py` re-export preserves this without any changes to callers.

The `_build_*` methods are pure widget construction: they write to `panel._wall_vars`, `panel._roof_vars`, `panel._pe_labels`, etc., and return nothing. They are extracted as free functions `fn(panel, parent_widget, ...)` exactly as `gui/canvas/` helpers were extracted with `fn(canvas, ...)`. `WindSurfacePanel` delegates to them in `__init__` and `_rebuild_roof_table`.

State management, event handlers, recalculation logic, and the public API (`populate`, `get_surface_data`) stay on the class — these are tightly coupled to `self` state and not worth extracting.

## File Breakdown

### `gui/dialogs/__init__.py` (~5 lines)
Re-exports `WindSurfacePanel` from `wind_surface_panel`:
```python
from portal_frame.gui.dialogs.wind_surface_panel import WindSurfacePanel
__all__ = ["WindSurfacePanel"]
```

### `gui/dialogs/wind_surface_panel.py` (~370 lines)
The `WindSurfacePanel` class with everything that is not pure widget construction:
- `_styled_entry()` module-level helper (unchanged)
- `_CASE_INFO` class constant
- `__init__` — calls `build_case_tab()`, `build_walls_page()`, `build_roof_page()` from sub-modules
- `_build_case_tab(parent, name, direction, envelope)` — stays on class; only ~42 lines and references `self._active_case` / `self._case_btns` directly in lambda closures (extracting would require passing `panel` into deeply nested lambdas with no size benefit)
- `_select_case`, `_select_sub` — event handlers, heavy `self` access
- `_rebuild_roof_table` — calls `build_roof_crosswind_per_rafter()` and `build_roof_transverse()` from roof_builders
- `_schedule_recalc`, `_recalc_pressures` — recalculation logic
- `populate`, `_get_var_float`, `get_surface_data` — public API

### `gui/dialogs/wall_builders.py` (~100 lines)
Free functions for wall page construction:
- `build_walls_page(panel, parent)` — was `_build_walls_page`
- `add_wall_row(panel, tbl, row, key, surface, dist_text, default_cpe=0.0, is_side=False)` — was `_add_wall_row`

Both write to `panel._wall_vars`, `panel._pe_labels`, `panel._pnet_labels`, `panel._dist_labels`.

### `gui/dialogs/roof_builders.py` (~310 lines)
Free functions for roof page construction:
- `build_roof_page(panel, parent)` — was `_build_roof_page`
- `build_roof_header_row(tbl)` — was `_build_roof_header_row`; takes only `tbl` (no panel state needed)
- `build_roof_crosswind_per_rafter(panel, tbl, is_LR=True)` — was `_build_roof_crosswind_per_rafter`; 159-line method, the main reason for the split
- `build_roof_transverse(panel, tbl)` — was `_build_roof_transverse`

All write to `panel._roof_vars`, `panel._pe_labels`, `panel._pnet_labels`, `panel._dist_labels`, and call `panel._schedule_recalc`.

## Data Flow

No data flow changes. The panel's `_wall_vars`, `_roof_vars`, `_pe_labels`, `_pnet_labels`, `_dist_labels` dicts are populated by the builder free-functions (same as before — builder methods were already mutating `self`). Callers see no difference.

## Import Changes

**Callers (no change needed):**
```python
# gui/app.py and gui/tabs/wind_tab.py — unchanged
from portal_frame.gui.dialogs import WindSurfacePanel
```

**Inside dialogs package:**
```python
# wind_surface_panel.py imports builders
from portal_frame.gui.dialogs.wall_builders import build_walls_page, add_wall_row
from portal_frame.gui.dialogs.roof_builders import (
    build_roof_page, build_roof_crosswind_per_rafter, build_roof_transverse
)
```

## Delegation Pattern in `__init__`

```python
# Before (in class):
self._build_walls_page(self._sub_tabs["Walls"])
self._build_roof_page(self._sub_tabs["Roof"])

# After (delegating to free functions):
build_walls_page(self, self._sub_tabs["Walls"])
build_roof_page(self, self._sub_tabs["Roof"])
```

```python
# Before (in _rebuild_roof_table):
self._build_roof_crosswind_per_rafter(tbl, is_LR)
self._build_roof_transverse(tbl)

# After:
build_roof_crosswind_per_rafter(self, tbl, is_LR)
build_roof_transverse(self, tbl)
```

## Estimated Line Counts After Split

| File | Lines |
|------|-------|
| `gui/dialogs/__init__.py` | ~5 |
| `gui/dialogs/wind_surface_panel.py` | ~370 |
| `gui/dialogs/wall_builders.py` | ~100 |
| `gui/dialogs/roof_builders.py` | ~310 |
| **Total** | **~785** |

All files under 500 lines. Original `dialogs.py` is deleted.

## Testing

- `python -m pytest tests/ -v` — all 232 tests pass (no dialogs unit tests exist; the class is GUI-only)
- GUI smoke test: `python -m portal_frame.run_gui 2>/tmp/gui_stderr.log` — no Traceback in stderr
- Manual: open Wind tab, click Auto-generate, verify W1–W8 case tabs switch correctly, Walls/Roof sub-tabs work, pe/pnet columns update
- `python -m portal_frame.cli` — still runs (no dialogs import in CLI path)

## What Is NOT Changed

- No logic changes inside any method
- No renaming of public methods (`populate`, `get_surface_data`)
- No changes to `_CASE_INFO`, `_styled_entry`, or any recalc logic
- No changes to callers (`app.py`, `wind_tab.py`)
- `gui/dialogs.py` root file is deleted (replaced by package directory)
