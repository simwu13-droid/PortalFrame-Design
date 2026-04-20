# Dialogs Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `portal_frame/gui/dialogs.py` (808 lines) into a `gui/dialogs/` package with four focused files, each under 500 lines, without changing any behaviour.

**Architecture:** Convert the single file into a package using the established canvas/ extraction pattern — `_build_*` methods become free functions `fn(panel, ...)` in sub-modules, the class keeps all state/logic/public API, and `__init__.py` re-exports `WindSurfacePanel` so no caller changes. A `helpers.py` holds `styled_entry` to avoid circular imports between the builder modules and the class module.

**Tech Stack:** Python 3, tkinter — no new dependencies.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `portal_frame/gui/dialogs/__init__.py` | Re-export `WindSurfacePanel` — no caller changes needed |
| Create | `portal_frame/gui/dialogs/helpers.py` | `styled_entry()` shared widget factory |
| Create | `portal_frame/gui/dialogs/wall_builders.py` | `build_walls_page`, `add_wall_row` |
| Create | `portal_frame/gui/dialogs/roof_builders.py` | `build_roof_page`, `rebuild_roof_table`, `build_roof_header_row`, `build_roof_crosswind_per_rafter`, `build_roof_transverse` |
| Create | `portal_frame/gui/dialogs/wind_surface_panel.py` | `WindSurfacePanel` class (state, event handlers, recalc, public API) |
| Delete | `portal_frame/gui/dialogs.py` | Replaced by the package |

**Import dependency order (no cycles):**
```
helpers.py
  ↑
wall_builders.py   roof_builders.py
  ↑                    ↑
        wind_surface_panel.py
              ↑
         __init__.py
```

---

## Task 1: Create `helpers.py`

**Files:**
- Create: `portal_frame/gui/dialogs/helpers.py`

- [ ] **Step 1: Create the package directory and helpers module**

Create `portal_frame/gui/dialogs/helpers.py` with this exact content:

```python
"""Shared widget helpers for the dialogs package."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_MONO


def styled_entry(parent, var, width, row, col, padx=1, pady=1):
    """Create a consistently-styled Entry widget and grid it."""
    e = tk.Entry(parent, textvariable=var, font=FONT_MONO, width=width,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"])
    e.grid(row=row, column=col, padx=padx, pady=pady)
    return e
```

Note: `_styled_entry` becomes `styled_entry` (public name) since it now lives in its own module with a clear single purpose.

- [ ] **Step 2: Verify the file exists and has no syntax errors**

Run:
```bash
python -c "import ast; ast.parse(open('portal_frame/gui/dialogs/helpers.py').read()); print('OK')"
```
Expected: `OK`

---

## Task 2: Create `wall_builders.py`

**Files:**
- Create: `portal_frame/gui/dialogs/wall_builders.py`

- [ ] **Step 1: Create the wall builders module**

Create `portal_frame/gui/dialogs/wall_builders.py` with this exact content:

```python
"""Wall table builder functions for WindSurfacePanel."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.standards.wind_nzs1170_2 import SIDE_WALL_CPE_ZONES
from portal_frame.gui.dialogs.helpers import styled_entry


def build_walls_page(panel, parent):
    """Build the Walls sub-tab page on *parent*, registering vars on *panel*."""
    tk.Label(parent, text="EXTERNAL", font=FONT_BOLD,
             fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
             anchor="w").pack(fill="x", padx=4, pady=(4, 0))

    tbl = tk.Frame(parent, bg=COLORS["bg_panel"])
    tbl.pack(fill="x", padx=2, pady=2)

    headers_row0 = [
        ("Surface", 10, 1), ("Distance", 12, 1), ("Ka", 5, 1),
        ("Cp,e", 6, 1), ("pe", 12, 2), ("pnet", 12, 2),
    ]
    col = 0
    for text, w, span in headers_row0:
        lbl = tk.Label(tbl, text=text, font=FONT_BOLD, fg=COLORS["fg_dim"],
                       bg=COLORS["bg"], width=w, anchor="center")
        lbl.grid(row=0, column=col, columnspan=span, padx=1, pady=(2, 0),
                 sticky="ew")
        col += span

    sub_cols = [(4, "uplift", 6), (5, "downward", 6),
                (6, "uplift", 6), (7, "downward", 6)]
    for c, text, w in sub_cols:
        tk.Label(tbl, text=text, font=FONT_SMALL, fg=COLORS["fg_dim"],
                 bg=COLORS["bg"], width=w, anchor="center"
                 ).grid(row=1, column=c, padx=1, pady=(0, 2), sticky="ew")

    row = 2
    wall_rows = [
        ("windward", "Windward", "All"),
        ("leeward", "Leeward", ""),
    ]
    for key, surface, dist_text in wall_rows:
        add_wall_row(panel, tbl, row, key, surface, dist_text)
        row += 1

    tk.Label(tbl, text="Side", font=FONT_BOLD, fg=COLORS["fg"],
             bg=COLORS["bg_panel"], width=10, anchor="w"
             ).grid(row=row, column=0, padx=1, pady=(4, 0), sticky="w")
    row += 1

    for i, (s_mult, e_mult, cpe) in enumerate(SIDE_WALL_CPE_ZONES):
        zone_label = f"{s_mult:.0f}h" + (
            "-end" if e_mult is None else f"-{e_mult:.0f}h")
        add_wall_row(panel, tbl, row, f"side_{i}", "", zone_label,
                     default_cpe=cpe, is_side=True)
        row += 1

    panel._walls_table = tbl


def add_wall_row(panel, tbl, row, key, surface, dist_text,
                 default_cpe=0.0, is_side=False):
    """Add one wall data row to *tbl*, registering StringVars on *panel*."""
    if surface:
        tk.Label(tbl, text=surface, font=FONT_MONO, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"], width=10, anchor="w"
                 ).grid(row=row, column=0, padx=1, sticky="w")

    dist_lbl = tk.Label(tbl, text=dist_text, font=FONT_MONO,
                        fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                        width=12, anchor="w")
    dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
    panel._dist_labels[f"wall_{key}_dist"] = dist_lbl

    ka_var = tk.StringVar(value="1.0")
    styled_entry(tbl, ka_var, 5, row, 2)
    panel._wall_vars[f"{key}_ka"] = ka_var

    cpe_var = tk.StringVar(value=str(default_cpe))
    styled_entry(tbl, cpe_var, 6, row, 3)
    panel._wall_vars[f"{key}_cpe"] = cpe_var

    for j, env in enumerate(("uplift", "downward")):
        lbl = tk.Label(tbl, text="\u2014", font=FONT_MONO, fg=COLORS["warning"],
                       bg=COLORS["bg_panel"], width=6, anchor="e")
        lbl.grid(row=row, column=4 + j, padx=1, sticky="e")
        panel._pe_labels[f"wall_{key}_{env}"] = lbl

    for j, env in enumerate(("uplift", "downward")):
        lbl = tk.Label(tbl, text="\u2014", font=FONT_MONO, fg=COLORS["success"],
                       bg=COLORS["bg_panel"], width=6, anchor="e")
        lbl.grid(row=row, column=6 + j, padx=1, sticky="e")
        panel._pnet_labels[f"wall_{key}_{env}"] = lbl

    ka_var.trace_add("write", panel._schedule_recalc)
    cpe_var.trace_add("write", panel._schedule_recalc)
```

- [ ] **Step 2: Verify no syntax errors**

Run:
```bash
python -c "import ast; ast.parse(open('portal_frame/gui/dialogs/wall_builders.py').read()); print('OK')"
```
Expected: `OK`

---

## Task 3: Create `roof_builders.py`

**Files:**
- Create: `portal_frame/gui/dialogs/roof_builders.py`

- [ ] **Step 1: Create the roof builders module**

Create `portal_frame/gui/dialogs/roof_builders.py` with this exact content:

```python
"""Roof table builder functions for WindSurfacePanel."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.standards.wind_nzs1170_2 import TABLE_5_3A_ZONES
from portal_frame.gui.dialogs.helpers import styled_entry


def build_roof_page(panel, parent):
    """Build the Roof sub-tab page on *parent*, registering state on *panel*."""
    panel._roof_header_lbl = tk.Label(
        parent, text="EXTERNAL \u2014 Crosswind Slope (Table 5.3A)",
        font=FONT_BOLD, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
        anchor="w")
    panel._roof_header_lbl.pack(fill="x", padx=4, pady=(4, 0))

    panel._roof_container = tk.Frame(parent, bg=COLORS["bg_panel"])
    panel._roof_container.pack(fill="x", padx=2, pady=2)
    panel._roof_direction = "crosswind"

    # Initial build — panel._rebuild_roof_table is defined on WindSurfacePanel
    panel._rebuild_roof_table("crosswind")


def rebuild_roof_table(panel, direction, case_name=None):
    """Rebuild the roof Cp,e table based on wind direction and selected case.

    Clears existing roof vars/labels, destroys old widgets, then rebuilds.
    Called both on initial page build (nothing to clear) and on case change.
    """
    for key in list(panel._roof_vars.keys()):
        del panel._roof_vars[key]
    for key in list(panel._pe_labels.keys()):
        if key.startswith("roof_"):
            del panel._pe_labels[key]
    for key in list(panel._pnet_labels.keys()):
        if key.startswith("roof_"):
            del panel._pnet_labels[key]
    for key in list(panel._dist_labels.keys()):
        if key.startswith("roof_"):
            del panel._dist_labels[key]

    for child in panel._roof_container.winfo_children():
        child.destroy()

    panel._roof_direction = direction
    tbl = tk.Frame(panel._roof_container, bg=COLORS["bg_panel"])
    tbl.pack(fill="x")

    if direction == "crosswind":
        is_LR = case_name not in ("W3", "W4")
        build_roof_crosswind_per_rafter(panel, tbl, is_LR)
    else:
        panel._roof_header_lbl.config(
            text="EXTERNAL \u2014 Transverse (Tables 5.3B / 5.3C)")
        build_roof_transverse(panel, tbl)

    panel._roof_table = tbl
    panel._recalc_pressures()


def build_roof_header_row(tbl):
    """Build the standard multi-level header for roof tables."""
    headers_row0 = [
        ("Surface", 10, 1), ("Distance", 12, 1), ("Ka", 5, 1),
        ("Cp,e", 12, 2), ("pe", 12, 2), ("pnet", 12, 2),
    ]
    col = 0
    for text, w, span in headers_row0:
        tk.Label(tbl, text=text, font=FONT_BOLD, fg=COLORS["fg_dim"],
                 bg=COLORS["bg"], width=w, anchor="center"
                 ).grid(row=0, column=col, columnspan=span, padx=1,
                        pady=(2, 0), sticky="ew")
        col += span
    sub_cols = [(3, "uplift", 6), (4, "downward", 6),
                (5, "uplift", 6), (6, "downward", 6),
                (7, "uplift", 6), (8, "downward", 6)]
    for c, text, w in sub_cols:
        tk.Label(tbl, text=text, font=FONT_SMALL, fg=COLORS["fg_dim"],
                 bg=COLORS["bg"], width=w, anchor="center"
                 ).grid(row=1, column=c, padx=1, pady=(0, 2), sticky="ew")


def build_roof_crosswind_per_rafter(panel, tbl, is_LR=True):
    """Build crosswind roof rows per-rafter based on pitch and wind direction.

    Each rafter independently uses the correct table:
    - pitch < 10 deg: Table 5.3(A) zone-based
    - pitch >= 10 deg, upwind: Table 5.3(B) uniform
    - pitch >= 10 deg, downwind: Table 5.3(C) uniform
    """
    build_roof_header_row(tbl)
    row = 2

    left_uni = panel._roof_uniform.get("left_uniform")
    right_uni = panel._roof_uniform.get("right_uniform")

    if is_LR:
        left_role, right_role = "upwind", "downwind"
        dir_desc = "L\u2192R"
    else:
        left_role, right_role = "downwind", "upwind"
        dir_desc = "R\u2192L"

    panel._roof_header_lbl.config(
        text=f"EXTERNAL \u2014 Crosswind ({dir_desc})")

    rafter_configs = []
    for side, role, uni_data in [
        ("Left", left_role, left_uni),
        ("Right", right_role, right_uni),
    ]:
        has_uniform = uni_data is not None
        if has_uniform and role == "upwind":
            cpe_up_val = uni_data[0] if len(uni_data) >= 1 else -0.9
            cpe_dn_val = uni_data[1] if len(uni_data) >= 2 else -0.4
            rafter_configs.append((side, role, "uniform", "5.3(B)",
                                   cpe_up_val, cpe_dn_val))
        elif has_uniform and role == "downwind":
            cpe_val = uni_data[2] if len(uni_data) >= 3 else uni_data[0]
            rafter_configs.append((side, role, "uniform", "5.3(C)",
                                   cpe_val, cpe_val))
        else:
            rafter_configs.append((side, role, "zones", "5.3(A)",
                                   None, None))

    for side, role, mode, table_ref, cpe_up_val, cpe_dn_val in rafter_configs:
        surface_label = f"{side} ({role})"
        table_label = f"Tbl {table_ref}"

        if mode == "uniform":
            key = f"roof_{side.lower()}_{role}"
            tk.Label(tbl, text=surface_label, font=FONT_MONO,
                     fg=COLORS["fg"], bg=COLORS["bg_panel"],
                     width=14, anchor="w"
                     ).grid(row=row, column=0, padx=1, sticky="w")
            tk.Label(tbl, text=table_label, font=FONT_MONO,
                     fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                     width=12, anchor="w"
                     ).grid(row=row, column=1, padx=1, sticky="w")

            ka_var = tk.StringVar(value="1.0")
            styled_entry(tbl, ka_var, 5, row, 2)
            panel._roof_vars[f"{key}_ka"] = ka_var

            cpe_up_var = tk.StringVar(value=str(cpe_up_val))
            styled_entry(tbl, cpe_up_var, 6, row, 3)
            panel._roof_vars[f"{key}_cpe_up"] = cpe_up_var

            cpe_dn_var = tk.StringVar(value=str(cpe_dn_val))
            styled_entry(tbl, cpe_dn_var, 6, row, 4)
            panel._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

            for j, env in enumerate(("uplift", "downward")):
                lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                               fg=COLORS["warning"], bg=COLORS["bg_panel"],
                               width=6, anchor="e")
                lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
                panel._pe_labels[f"roof_{key}_{env}"] = lbl
            for j, env in enumerate(("uplift", "downward")):
                lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                               fg=COLORS["success"], bg=COLORS["bg_panel"],
                               width=6, anchor="e")
                lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
                panel._pnet_labels[f"roof_{key}_{env}"] = lbl

            ka_var.trace_add("write", panel._schedule_recalc)
            cpe_up_var.trace_add("write", panel._schedule_recalc)
            cpe_dn_var.trace_add("write", panel._schedule_recalc)
            row += 1

        else:
            side_lower = side.lower()
            for i, (s_mult, e_mult, cpe_up, cpe_dn) in enumerate(TABLE_5_3A_ZONES):
                zone_label = f"{s_mult:.0f}h" + (
                    "-end" if e_mult is None else f"-{e_mult:.0f}h")
                key = f"roof_{side_lower}_{i}"

                if i == 0:
                    tk.Label(tbl, text=surface_label, font=FONT_MONO,
                             fg=COLORS["fg"], bg=COLORS["bg_panel"],
                             width=14, anchor="w"
                             ).grid(row=row, column=0, padx=1, sticky="w")

                dist_lbl = tk.Label(tbl, text=zone_label, font=FONT_MONO,
                                    fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                                    width=12, anchor="w")
                dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
                panel._dist_labels[f"roof_{key}_dist"] = dist_lbl

                ka_var = tk.StringVar(value="1.0")
                styled_entry(tbl, ka_var, 5, row, 2)
                panel._roof_vars[f"{key}_ka"] = ka_var

                cpe_up_var = tk.StringVar(value=str(cpe_up))
                styled_entry(tbl, cpe_up_var, 6, row, 3)
                panel._roof_vars[f"{key}_cpe_up"] = cpe_up_var

                cpe_dn_var = tk.StringVar(value=str(cpe_dn))
                styled_entry(tbl, cpe_dn_var, 6, row, 4)
                panel._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

                for j, env in enumerate(("uplift", "downward")):
                    lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                   fg=COLORS["warning"], bg=COLORS["bg_panel"],
                                   width=6, anchor="e")
                    lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
                    panel._pe_labels[f"roof_{key}_{env}"] = lbl
                for j, env in enumerate(("uplift", "downward")):
                    lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                   fg=COLORS["success"], bg=COLORS["bg_panel"],
                                   width=6, anchor="e")
                    lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
                    panel._pnet_labels[f"roof_{key}_{env}"] = lbl

                ka_var.trace_add("write", panel._schedule_recalc)
                cpe_up_var.trace_add("write", panel._schedule_recalc)
                cpe_dn_var.trace_add("write", panel._schedule_recalc)
                row += 1


def build_roof_transverse(panel, tbl):
    """Build Table 5.3B/C uniform roof rows for transverse wind."""
    build_roof_header_row(tbl)
    row = 2

    left_uni = panel._roof_uniform.get("left_uniform")
    right_uni = panel._roof_uniform.get("right_uniform")

    upwind_up = left_uni[0] if left_uni and len(left_uni) >= 1 else -0.9
    upwind_dn = left_uni[1] if left_uni and len(left_uni) >= 2 else -0.4
    downwind_cpe = right_uni[0] if right_uni else -0.5

    surfaces = [
        ("roof_upwind", "Upwind (5.3B)", "0-span", upwind_up, upwind_dn),
        ("roof_downwind", "Downwind (5.3C)", "0-span", downwind_cpe, downwind_cpe),
    ]

    for key, surface_name, dist_text, cpe_up_val, cpe_dn_val in surfaces:
        tk.Label(tbl, text=surface_name, font=FONT_MONO,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"],
                 width=14, anchor="w"
                 ).grid(row=row, column=0, padx=1, sticky="w")

        dist_lbl = tk.Label(tbl, text=dist_text, font=FONT_MONO,
                            fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                            width=12, anchor="w")
        dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
        panel._dist_labels[f"roof_{key}_dist"] = dist_lbl

        ka_var = tk.StringVar(value="1.0")
        styled_entry(tbl, ka_var, 5, row, 2)
        panel._roof_vars[f"{key}_ka"] = ka_var

        cpe_up_var = tk.StringVar(value=str(cpe_up_val))
        styled_entry(tbl, cpe_up_var, 6, row, 3)
        panel._roof_vars[f"{key}_cpe_up"] = cpe_up_var

        cpe_dn_var = tk.StringVar(value=str(cpe_dn_val))
        styled_entry(tbl, cpe_dn_var, 6, row, 4)
        panel._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

        for j, env in enumerate(("uplift", "downward")):
            lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                           fg=COLORS["warning"], bg=COLORS["bg_panel"],
                           width=6, anchor="e")
            lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
            panel._pe_labels[f"roof_{key}_{env}"] = lbl

        for j, env in enumerate(("uplift", "downward")):
            lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                           fg=COLORS["success"], bg=COLORS["bg_panel"],
                           width=6, anchor="e")
            lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
            panel._pnet_labels[f"roof_{key}_{env}"] = lbl

        ka_var.trace_add("write", panel._schedule_recalc)
        cpe_up_var.trace_add("write", panel._schedule_recalc)
        cpe_dn_var.trace_add("write", panel._schedule_recalc)
        row += 1
```

- [ ] **Step 2: Verify no syntax errors**

Run:
```bash
python -c "import ast; ast.parse(open('portal_frame/gui/dialogs/roof_builders.py').read()); print('OK')"
```
Expected: `OK`

---

## Task 4: Create `wind_surface_panel.py`

**Files:**
- Create: `portal_frame/gui/dialogs/wind_surface_panel.py`

- [ ] **Step 1: Create the refactored WindSurfacePanel module**

Create `portal_frame/gui/dialogs/wind_surface_panel.py` with this exact content:

```python
"""WindSurfacePanel -- surface-based wind coefficient table with Walls/Roof tabs."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL
from portal_frame.gui.dialogs.wall_builders import build_walls_page
from portal_frame.gui.dialogs.roof_builders import build_roof_page, rebuild_roof_table


class WindSurfacePanel(tk.Frame):
    """Surface-based wind coefficient table with Walls/Roof sub-tabs.

    Displays Cp,e and Ka per surface with auto-calculated pe and pnet columns.
    Includes wind case tabs (W1-W8) for preview selection.
    """

    _CASE_INFO = [
        ("W1", "L-R", "uplift",   "crosswind"),
        ("W2", "L-R", "downward", "crosswind"),
        ("W3", "R-L", "uplift",   "crosswind"),
        ("W4", "R-L", "downward", "crosswind"),
        ("W5", "90",  "uplift",   "transverse"),
        ("W6", "90",  "downward", "transverse"),
        ("W7", "270", "uplift",   "transverse"),
        ("W8", "270", "downward", "transverse"),
    ]

    def __init__(self, parent, get_geometry_fn=None, get_wind_params_fn=None,
                 on_change_fn=None, on_case_select_fn=None):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.get_geometry_fn = get_geometry_fn
        self.get_wind_params_fn = get_wind_params_fn
        self.on_change_fn = on_change_fn
        self.on_case_select_fn = on_case_select_fn

        # Data storage — StringVars for editable cells
        self._wall_vars = {}
        self._roof_vars = {}
        self._pe_labels = {}
        self._pnet_labels = {}
        self._dist_labels = {}
        self._recalc_scheduled = False
        # Uniform roof overrides for steep pitch (set by populate, not editable)
        self._roof_uniform = {
            "type": "zones",
            "left_uniform": None,
            "right_uniform": None,
        }

        self._active_case = None
        self._case_btns = {}

        case_strip = tk.Frame(self, bg=COLORS["bg_panel"])
        case_strip.pack(fill="x", padx=2, pady=(4, 0))

        cw_frame = tk.Frame(case_strip, bg=COLORS["bg_panel"])
        cw_frame.pack(side="left", padx=(0, 6))
        tk.Label(cw_frame, text="CROSSWIND", font=("Segoe UI", 7),
                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"]
                 ).pack(side="left", padx=(0, 3))
        for name, direction, envelope, group in self._CASE_INFO[:4]:
            self._build_case_tab(cw_frame, name, direction, envelope)

        sep = tk.Frame(case_strip, bg=COLORS["border"], width=1)
        sep.pack(side="left", fill="y", padx=4, pady=2)

        tr_frame = tk.Frame(case_strip, bg=COLORS["bg_panel"])
        tr_frame.pack(side="left", padx=(0, 4))
        tk.Label(tr_frame, text="TRANSVERSE", font=("Segoe UI", 7),
                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"]
                 ).pack(side="left", padx=(0, 3))
        for name, direction, envelope, group in self._CASE_INFO[4:]:
            self._build_case_tab(tr_frame, name, direction, envelope)

        self._case_desc = tk.Label(
            self, text="", font=FONT_SMALL,
            fg=COLORS["fg_dim"], bg=COLORS["bg_panel"], anchor="w")
        self._case_desc.pack(fill="x", padx=4, pady=(0, 2))

        tab_bar = tk.Frame(self, bg=COLORS["bg"])
        tab_bar.pack(fill="x")

        self._sub_tabs = {}
        self._sub_tab_btns = {}
        self._active_sub = None

        for name in ("Walls", "Roof"):
            btn = tk.Label(tab_bar, text=f"  {name}  ", font=FONT_BOLD,
                           fg=COLORS["fg_dim"], bg=COLORS["bg"],
                           cursor="hand2", padx=8, pady=4)
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, n=name: self._select_sub(n))
            self._sub_tab_btns[name] = btn

            page = tk.Frame(self, bg=COLORS["bg_panel"])
            self._sub_tabs[name] = page

        build_walls_page(self, self._sub_tabs["Walls"])
        build_roof_page(self, self._sub_tabs["Roof"])
        self._select_sub("Walls")

    def _build_case_tab(self, parent, name, direction, envelope):
        """Build a single wind case tab button.

        Stays on the class because its lambda closures reference self._active_case
        and self._case_btns directly — extracting would give no size benefit.
        """
        if envelope == "uplift":
            active_bg = "#1b5e7a"
            active_fg = "#7fdbff"
        else:
            active_bg = "#5e3a1b"
            active_fg = "#ffbd7f"

        if direction == "L-R":
            arrow = "\u2192"
        elif direction == "R-L":
            arrow = "\u2190"
        elif direction == "90":
            arrow = "\u2191"
        else:
            arrow = "\u2193"

        btn = tk.Label(
            parent, text=f"{name}", font=("Consolas", 8, "bold"),
            fg=COLORS["fg_dim"], bg=COLORS["bg"],
            cursor="hand2", padx=4, pady=2,
            relief="flat", borderwidth=0,
        )
        btn.pack(side="left", padx=1)
        btn.bind("<Button-1>", lambda e, n=name: self._select_case(n))
        btn.bind("<Enter>", lambda e, b=btn, n=name:
                 b.config(bg=COLORS["bg_input"]) if n != self._active_case else None)
        btn.bind("<Leave>", lambda e, b=btn, n=name:
                 b.config(bg=COLORS["bg"] if n != self._active_case
                          else self._case_btns[n]["active_bg"]))

        self._case_btns[name] = {
            "widget": btn,
            "direction": direction,
            "envelope": envelope,
            "arrow": arrow,
            "active_bg": active_bg,
            "active_fg": active_fg,
        }

    def _select_case(self, name):
        """Select a wind case tab and notify the app for preview."""
        if self._active_case and self._active_case in self._case_btns:
            prev = self._case_btns[self._active_case]
            prev["widget"].config(bg=COLORS["bg"], fg=COLORS["fg_dim"])

        if self._active_case == name:
            self._active_case = None
            self._case_desc.config(text="")
            if self.on_case_select_fn:
                self.on_case_select_fn(None)
            return

        self._active_case = name
        info = self._case_btns[name]
        info["widget"].config(bg=info["active_bg"], fg=info["active_fg"])

        direction = info["direction"]
        envelope = info["envelope"]
        arrow = info["arrow"]
        if direction in ("L-R", "R-L"):
            desc = f"{arrow}  {name}: Crosswind {direction} - max {envelope}"
        else:
            desc = f"{arrow}  {name}: Transverse {direction}\u00b0 - max {envelope}"
        self._case_desc.config(text=desc)

        case_group = next(
            (g for n, d, e, g in self._CASE_INFO if n == name), "crosswind")
        self._rebuild_roof_table(case_group, case_name=name)

        if self.on_case_select_fn:
            self.on_case_select_fn(name)

    def _select_sub(self, name):
        if self._active_sub == name:
            return
        for n, page in self._sub_tabs.items():
            page.pack_forget()
            self._sub_tab_btns[n].config(
                bg=COLORS["bg"], fg=COLORS["fg_dim"])
        self._sub_tabs[name].pack(fill="x", expand=False)
        self._sub_tab_btns[name].config(
            bg=COLORS["accent"], fg=COLORS["fg_bright"])
        self._active_sub = name

    def _rebuild_roof_table(self, direction, case_name=None):
        rebuild_roof_table(self, direction, case_name=case_name)

    def _schedule_recalc(self, *_):
        if not self._recalc_scheduled:
            self._recalc_scheduled = True
            self.after_idle(self._recalc_pressures)

    def _recalc_pressures(self):
        self._recalc_scheduled = False
        if not self.get_wind_params_fn:
            return
        try:
            p = self.get_wind_params_fn()
        except Exception:
            return

        qu = p.get("qu", 0)
        kc_i = p.get("kc_i", 1.0)
        cpi_up = p.get("cpi_uplift", 0.2)
        cpi_dn = p.get("cpi_downward", -0.3)

        def _fmt(val):
            return f"{val:+.2f}" if val != 0 else "0.00"

        wall_keys = ["windward", "leeward"] + [f"side_{i}" for i in range(4)]
        for key in wall_keys:
            ka_var = self._wall_vars.get(f"{key}_ka")
            cpe_var = self._wall_vars.get(f"{key}_cpe")
            if not ka_var or not cpe_var:
                continue
            try:
                ka = float(ka_var.get())
                cpe = float(cpe_var.get())
            except ValueError:
                continue

            for env, cpi in [("uplift", cpi_up), ("downward", cpi_dn)]:
                pe = round(cpe * ka * qu, 4)
                pnet = round((cpe * ka - cpi * kc_i) * qu, 4)

                pe_lbl = self._pe_labels.get(f"wall_{key}_{env}")
                pnet_lbl = self._pnet_labels.get(f"wall_{key}_{env}")
                if pe_lbl:
                    pe_lbl.config(text=_fmt(pe))
                if pnet_lbl:
                    pnet_lbl.config(text=_fmt(pnet))

        roof_keys = set()
        for var_key in self._roof_vars:
            if var_key.endswith("_ka"):
                roof_keys.add(var_key[:-3])
        for key in sorted(roof_keys):
            ka_var = self._roof_vars.get(f"{key}_ka")
            cpe_up_var = self._roof_vars.get(f"{key}_cpe_up")
            cpe_dn_var = self._roof_vars.get(f"{key}_cpe_dn")
            if not ka_var or not cpe_up_var or not cpe_dn_var:
                continue
            try:
                ka = float(ka_var.get())
                cpe_uplift = float(cpe_up_var.get())
                cpe_downward = float(cpe_dn_var.get())
            except ValueError:
                continue

            for env, cpi, cpe in [("uplift", cpi_up, cpe_uplift),
                                   ("downward", cpi_dn, cpe_downward)]:
                pe = round(cpe * ka * qu, 4)
                pnet = round((cpe * ka - cpi * kc_i) * qu, 4)

                pe_lbl = self._pe_labels.get(f"roof_{key}_{env}")
                pnet_lbl = self._pnet_labels.get(f"roof_{key}_{env}")
                if pe_lbl:
                    pe_lbl.config(text=_fmt(pe))
                if pnet_lbl:
                    pnet_lbl.config(text=_fmt(pnet))

        if self.on_change_fn:
            self.on_change_fn()

    def populate(self, surface_data):
        """Fill the table from get_surface_coefficients() output."""
        walls = surface_data.get("walls", {})
        roof = surface_data.get("roof", {})

        self._roof_uniform = {
            "type": roof.get("type", "zones"),
            "left_uniform": roof.get("left_uniform"),
            "right_uniform": roof.get("right_uniform"),
        }

        ww_var = self._wall_vars.get("windward_cpe")
        if ww_var:
            ww_var.set(str(walls.get("windward_cpe", 0.7)))
        lw_var = self._wall_vars.get("leeward_cpe")
        if lw_var:
            lw_var.set(str(walls.get("leeward_cpe", -0.5)))

        depth = surface_data.get("building_depth", 0)
        lw_dist = self._dist_labels.get("wall_leeward_dist")
        if lw_dist and depth:
            lw_dist.config(text=f"{depth:.1f} m")

        for i, zone_data in enumerate(walls.get("side_zones", [])):
            s_mult, e_mult, cpe, start_m, end_m = zone_data
            cpe_var = self._wall_vars.get(f"side_{i}_cpe")
            if cpe_var:
                cpe_var.set(str(cpe))
            dist_lbl = self._dist_labels.get(f"wall_side_{i}_dist")
            if dist_lbl:
                zone_text = f"{start_m:.1f}-{end_m:.1f} m"
                dist_lbl.config(text=zone_text)

        if self._active_case:
            case_group = next(
                (g for n, d, e, g in self._CASE_INFO if n == self._active_case),
                "crosswind")
            self._rebuild_roof_table(case_group, case_name=self._active_case)
        else:
            self._rebuild_roof_table("crosswind")

        self._recalc_pressures()

    def _get_var_float(self, var_dict, key, default=0.0):
        var = var_dict.get(key)
        if not var:
            return default
        try:
            return float(var.get())
        except ValueError:
            return default

    def get_surface_data(self) -> dict:
        """Return raw surface Cp,e data for case synthesis by the app."""
        ww_cpe = (self._get_var_float(self._wall_vars, "windward_cpe")
                  * self._get_var_float(self._wall_vars, "windward_ka", 1.0))
        lw_cpe = (self._get_var_float(self._wall_vars, "leeward_cpe")
                  * self._get_var_float(self._wall_vars, "leeward_ka", 1.0))

        side_cpes = []
        for i in range(4):
            cpe = self._get_var_float(self._wall_vars, f"side_{i}_cpe")
            ka = self._get_var_float(self._wall_vars, f"side_{i}_ka", 1.0)
            side_cpes.append(cpe * ka)

        roof_zones_up = []
        roof_zones_dn = []
        roof_keys = sorted(
            k[:-3] for k in self._roof_vars if k.endswith("_ka"))
        for key in roof_keys:
            ka = self._get_var_float(self._roof_vars, f"{key}_ka", 1.0)
            cpe_up = self._get_var_float(self._roof_vars, f"{key}_cpe_up") * ka
            cpe_dn = self._get_var_float(self._roof_vars, f"{key}_cpe_dn") * ka
            roof_zones_up.append(cpe_up)
            roof_zones_dn.append(cpe_dn)

        return {
            "windward_cpe": ww_cpe,
            "leeward_cpe": lw_cpe,
            "side_cpes": side_cpes,
            "roof_zones_up": roof_zones_up,
            "roof_zones_dn": roof_zones_dn,
            "roof_uniform": self._roof_uniform,
        }
```

- [ ] **Step 2: Verify no syntax errors**

Run:
```bash
python -c "import ast; ast.parse(open('portal_frame/gui/dialogs/wind_surface_panel.py').read()); print('OK')"
```
Expected: `OK`

---

## Task 5: Create `__init__.py`, delete old `dialogs.py`, verify, commit

**Files:**
- Create: `portal_frame/gui/dialogs/__init__.py`
- Delete: `portal_frame/gui/dialogs.py`

- [ ] **Step 1: Create `__init__.py`**

Create `portal_frame/gui/dialogs/__init__.py` with this exact content:

```python
from portal_frame.gui.dialogs.wind_surface_panel import WindSurfacePanel

__all__ = ["WindSurfacePanel"]
```

- [ ] **Step 2: Delete the old `dialogs.py`**

```bash
rm portal_frame/gui/dialogs.py
```

Python now resolves `portal_frame.gui.dialogs` to the package directory instead of the old file.

- [ ] **Step 3: Verify the import resolves correctly**

Run:
```bash
python -c "from portal_frame.gui.dialogs import WindSurfacePanel; print(WindSurfacePanel)"
```
Expected output (no error):
```
<class 'portal_frame.gui.dialogs.wind_surface_panel.WindSurfacePanel'>
```

- [ ] **Step 4: Verify all existing tests still pass**

Run:
```bash
python -m pytest tests/ -v
```
Expected: 232 tests pass, 0 failures.

- [ ] **Step 5: GUI smoke test**

Run:
```bash
python -m portal_frame.run_gui 2>/tmp/gui_stderr.log &
```
Wait 5 seconds, then:
```bash
grep -i traceback /tmp/gui_stderr.log && echo "FAIL" || echo "PASS"
```
Expected: `PASS`

Kill the GUI process:
```bash
taskkill /F /IM python.exe 2>/dev/null || true
```

- [ ] **Step 6: Verify file line counts are all under 500**

Run:
```bash
for f in portal_frame/gui/dialogs/__init__.py portal_frame/gui/dialogs/helpers.py portal_frame/gui/dialogs/wall_builders.py portal_frame/gui/dialogs/roof_builders.py portal_frame/gui/dialogs/wind_surface_panel.py; do echo "$f: $(wc -l < $f) lines"; done
```
Expected: all files report under 500 lines.

- [ ] **Step 7: Commit**

```bash
git add portal_frame/gui/dialogs/
git rm portal_frame/gui/dialogs.py
git commit -m "refactor: split gui/dialogs.py into dialogs/ package (wall/roof builders)"
```

---

## Self-Review

**Spec coverage:**
- `__init__.py` re-export ✓ (Task 5)
- `helpers.py` with `styled_entry` ✓ (Task 1)
- `wall_builders.py` with `build_walls_page`, `add_wall_row` ✓ (Task 2)
- `roof_builders.py` with all 5 roof functions ✓ (Task 3)
- `wind_surface_panel.py` with refactored class ✓ (Task 4)
- Old `dialogs.py` deleted ✓ (Task 5)
- No caller changes needed (`app.py`, `wind_tab.py`) ✓ — `__init__.py` preserves the import path
- All tests pass ✓ (Task 5, Step 4)
- GUI smoke test ✓ (Task 5, Step 5)

**Placeholder scan:** No TBDs or vague steps — every step has exact file content or an exact command.

**Type consistency:** `styled_entry` is used consistently across `wall_builders.py` and `roof_builders.py` (imported from `helpers`). `rebuild_roof_table` is called as `rebuild_roof_table(self, direction, case_name=case_name)` in `_rebuild_roof_table` and identically imported in `wind_surface_panel.py`. `build_walls_page(self, ...)` and `build_roof_page(self, ...)` signatures match their call sites in `__init__`.
