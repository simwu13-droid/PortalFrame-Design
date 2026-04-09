# PyNite Solver Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four issues found in user testing of the PyNite solver integration: diagrams overflow canvas, no deflection diagram, stale results after input changes, and bare combo names in dropdown.

**Architecture:** Four independent fixes applied in safety-first order. Task 1 (state invalidation) splits `_update_preview()` into invalidating and non-invalidating variants. Task 2 (bounds clamping) adds a pre-pass shrink calculation to `draw_force_diagram()`. Task 3 (combo descriptions) plumbs `LoadCombination.description` through `AnalysisOutput` to the GUI dropdown. Task 4 (deflection diagrams) extends `MemberStationResult` with `dy_local` and adds a `δ` type to the diagram dropdown.

**Tech Stack:** Python 3.10+, tkinter, PyNite FEModel3D, existing NZS 1170.0 combination logic

**Branch:** `pynite-solver-integration` (continuing work from the initial integration)

---

## Context

The PyNite solver integration is complete and working (135 tests pass), but user testing surfaced 4 issues:

1. **Diagrams overflow the canvas** — 30m span × 118.8 kNm moment at knees pushes the diagram above the canvas top.
2. **No deflection diagram** — only M/V/N diagram types are available; user wants a δ (deflection) option.
3. **Stale results stay visible after input changes** — user could mistakenly apply outdated results to design. This is a safety issue and must be fixed first.
4. **Dropdown shows only combo names** — "ULS-1", "ULS-2". User wants descriptive text like "ULS-1: 1.35G", "ULS-2: 1.2G + 1.5Q".

The intended outcome is a safer, more informative analysis workflow where results are always trustworthy (invalidated on any input change), diagrams are always visible (clamped to canvas), deflection shapes can be visualized, and combinations are self-describing in the UI.

---

## Ordering Rationale

Implement in this order:
1. **Task 1 (Fix A):** State invalidation — safety-critical, do first.
2. **Task 2 (Fix B):** Diagram bounds clamping — visual correctness.
3. **Task 3 (Fix C):** Combo descriptions in dropdown — small UX win.
4. **Task 4 (Fix D):** Deflection diagrams — new feature, depends on clamping in place.

---

## Task 1: State Invalidation (Safety)

**Goal:** When the user changes any input after running analysis, clear all analysis state (results panel, diagram dropdowns, diagram overlay, green "Analysis complete" status) so outdated results cannot be mistaken for current.

**Critical files:**
- [portal_frame/gui/app.py](portal_frame/gui/app.py)

**Key existing methods and line numbers:**
- `_invalidate_analysis()` at line 1772 — exists but never called (this plan wires it up)
- `_update_preview()` at line 1351 — called from input change callbacks AND display-only callbacks (we will split these)
- `_analyse()` at line ~1740 — calls `_update_preview()` at line 1761 after populating results
- `_update_eq_results()` at line 788 — called by all EQ param `bind_change` handlers

### Step 1.1: Enhance `_invalidate_analysis()`

Replace the current method body (lines 1772-1780) with an expanded version:

```python
def _invalidate_analysis(self):
    """Clear stale analysis results when inputs change.

    Called from input change callbacks to prevent the user from mistakenly
    applying outdated analysis results to design.
    """
    self._analysis_output = None
    self._analysis_topology = None
    if hasattr(self, '_results_text'):
        self._results_text.config(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.config(state="disabled")
    if hasattr(self, 'diagram_case_var'):
        self.diagram_case_var.set("(none)")
    if hasattr(self, 'diagram_case_combo'):
        self.diagram_case_combo["values"] = ["(none)"]
    # Clear the green "Analysis complete" status message
    if hasattr(self, 'status_label'):
        self.status_label.config(text="", fg=COLORS["fg_dim"])
```

### Step 1.2: Split `_update_preview()` into two methods

Rename the current body to `_draw_preview()` and create a new thin `_update_preview()` that invalidates first:

```python
def _update_preview(self, *_):
    """Called when inputs change — invalidates stale analysis and redraws.

    Use this from input-change callbacks only. For display-only refresh
    (load case dropdown, diagram selection), call _draw_preview() directly.
    """
    self._invalidate_analysis()
    self._draw_preview()

def _draw_preview(self, *_):
    """Redraw the preview canvas without touching analysis state.

    Use this for display-only refresh (combo selection). Does not invalidate.
    """
    geom_obj = self._build_geometry()
    geom = {
        "span": geom_obj.span,
        "eave_height": geom_obj.eave_height,
        "roof_pitch": geom_obj.roof_pitch,
        "roof_pitch_2": geom_obj.right_pitch,
        "roof_type": geom_obj.roof_type,
        "apex_x": geom_obj.apex_x,
        "ridge_height": geom_obj.ridge_height,
    }
    if geom_obj.crane_rail_height is not None:
        geom["crane_rail_height"] = geom_obj.crane_rail_height
    supports = (self.left_support.get(), self.right_support.get())
    loads = self._build_preview_loads()

    diagram = None
    if (self._analysis_output is not None and
            hasattr(self, 'diagram_case_var') and
            self.diagram_case_var.get() != "(none)"):
        diagram = self._build_diagram_data()

    self.preview.update_frame(geom, supports, loads, diagram)
    self._update_summary()
```

### Step 1.3: Change display-only call sites to use `_draw_preview()`

These are the call sites that only change which thing is *displayed* and must NOT invalidate analysis:

| Line | Context | Current call | New call |
|------|---------|--------------|----------|
| 141 | `load_case_combo.bind("<<ComboboxSelected>>", lambda _: self._update_preview())` | `_update_preview()` | `_draw_preview()` |
| 153 | `diagram_case_combo.bind("<<ComboboxSelected>>", lambda _: self._update_preview())` | `_update_preview()` | `_draw_preview()` |
| 161 | `diagram_type_combo.bind("<<ComboboxSelected>>", lambda _: self._update_preview())` | `_update_preview()` | `_draw_preview()` |
| 1076 | `_on_wind_case_select()` — wind tab click changes which case is displayed | `self._update_preview()` | `self._draw_preview()` |
| 1761 | Inside `_analyse()` after populating results | `self._update_preview()` | `self._draw_preview()` |

**Do not change** lines 56, 459, 476, 481, 956, 961, 1060, 1114, or 2028 — those are input changes or initialization.

### Step 1.4: Add proactive invalidation at start of `_analyse()`

At the very top of `_analyse()` (around line 1742, inside the `try:` block before `request = self._build_analysis_request()`), add:

```python
# Clear any stale results first — if solve fails mid-way, we won't
# leave old results visible.
self._invalidate_analysis()
```

### Step 1.5: Add invalidation to `_update_eq_results()`

This method is called by all the EQ param `bind_change` handlers (eq_Z, eq_soil, eq_mu, eq_Sp, eq_Sp_sls, eq_R_uls, eq_R_sls, eq_near_fault, eq_extra_mass, eq_T1_override), plus `_on_eq_location_change()` and `_on_ductility_change()`. Adding invalidation here covers all of them in one place.

At the top of `_update_eq_results()` (line 788), add:

```python
def _update_eq_results(self, *_):
    self._invalidate_analysis()
    # ... existing body ...
```

### Step 1.6: Add invalidation to `_on_section_change()`

Line 462 — section changes must invalidate:

```python
def _on_section_change(self, *_):
    """Section selection changed — update info display and EQ results."""
    self._invalidate_analysis()
    self._update_section_info()
    self._update_eq_results()  # already invalidates, but harmless
```

### Step 1.7: Wire live_roof to trigger invalidation (latent bug fix)

The `live_roof` LabeledEntry at line 444 has no `bind_change` call. Add one immediately after line 445:

```python
self.live_roof.bind_change(self._on_frame_change)
```

### Step 1.8: Wire self_weight_var to trigger invalidation (latent bug fix)

The self-weight Checkbutton at line 448 has no `command=`. Modify it to add `command=self._on_frame_change`:

```python
tk.Checkbutton(
    parent, text="Include self-weight in Dead Load case",
    variable=self.self_weight_var, font=FONT,
    fg=COLORS["fg"], bg=COLORS["bg_panel"],
    selectcolor=COLORS["bg_input"],
    activebackground=COLORS["bg_panel"],
    activeforeground=COLORS["fg"],
    command=self._on_frame_change
).pack(fill="x", padx=10, pady=(0, 4))
```

### Step 1.9: Verification

Run: `python -m pytest tests/ -v`
Expected: All 135 tests still pass (no regressions).

Launch GUI: `python -m portal_frame.run_gui`
Manual test:
1. Set geometry, click "ANALYSE (PyNite)" — results + green status appear
2. Change span value → results clear, diagram disappears, green status gone ✓
3. Re-analyse → results appear
4. Change column section → results clear ✓
5. Re-analyse → results appear
6. Switch between M/V/N in the Diagram dropdown → results do NOT clear ✓
7. Re-analyse, then toggle "Show Load Case" dropdown → results do NOT clear ✓
8. Re-analyse, then click between Wind tabs (W1/W2/...) in wind panel → results do NOT clear ✓

### Step 1.10: Commit

```bash
git add portal_frame/gui/app.py
git commit -m "fix: invalidate analysis state on any input change

Previously, stale PyNite analysis results and force diagrams remained
visible after the user changed any input, risking use of outdated
results for design decisions.

- Split _update_preview into _update_preview (invalidates) and
  _draw_preview (display-only, preserves state)
- Display-only callers (diagram dropdowns, load case selector, wind
  case tabs, _analyse completion) now call _draw_preview
- _invalidate_analysis now also clears diagram_case_combo values and
  the 'Analysis complete' status label
- Added invalidation to _update_eq_results and _on_section_change
- Wired missing bind_change on live_roof and command on self_weight_var

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Diagram Bounds Clamping

**Goal:** Force diagrams must stay within the canvas. Currently with a 30m frame, a 118.8 kNm moment at knee corners pushes the diagram above the top edge.

**Critical files:**
- [portal_frame/gui/preview.py](portal_frame/gui/preview.py)

**Key existing code:**
- `DIAGRAM_MAX_PX = 60` constant at module level (line 14)
- `draw_force_diagram()` method at line 426
- `update_frame()` uses pad_side=55 or 100, pad_top=80, pad_bot=55 — these define the "safe" drawing area within the canvas bounds

### Step 2.1: Modify `draw_force_diagram()` to compute a global shrink factor

Replace the current `draw_force_diagram()` method in `portal_frame/gui/preview.py` with this version that clamps to canvas bounds. The change computes the required shrink in a pre-pass, then draws with the shrunk effective max offset.

```python
def draw_force_diagram(self, diagram, ns):
    """Draw force diagram overlaid on frame members.

    Computes a global shrink factor so all diagrams (including peak value
    labels) stay within the canvas bounds, preserving proportionality.
    """
    data = diagram["data"]
    dtype = diagram["type"]
    members_map = diagram.get("members", {})
    color = DIAGRAM_COLORS.get(dtype, "#e06c75")

    # Find max absolute value across all members for normalisation
    max_val = 0
    for stations in data.values():
        for _, val in stations:
            max_val = max(max_val, abs(val))
    if max_val < 1e-6:
        return

    # Canvas bounds (with small pad for safety)
    w = self.winfo_width()
    h = self.winfo_height()
    pad = 20
    x_min = pad
    x_max = w - pad
    y_min = pad
    y_max = h - pad

    # Label extension: the peak value label draws at offset + 12*sign(offset)
    LABEL_EXTRA = 12

    # Pre-compute member geometry and find global shrink factor
    member_geom = {}  # mid -> (sx, sy, ex, ey, dx, dy, nx, ny, length)
    for mid, stations in data.items():
        if mid not in members_map:
            continue
        n_start, n_end = members_map[mid]
        if n_start not in ns or n_end not in ns:
            continue
        sx, sy = ns[n_start]
        ex, ey = ns[n_end]
        mdx = ex - sx
        mdy = ey - sy
        length = math.hypot(mdx, mdy)
        if length < 1:
            continue
        nx = -mdy / length
        ny = mdx / length
        member_geom[mid] = (sx, sy, ex, ey, mdx, mdy, nx, ny, length)

    # Pre-pass: find minimum shrink factor so all extremes stay in bounds.
    # For each station, the proposed offset is k = (val/max_val) * DIAGRAM_MAX_PX.
    # Additionally the peak label extends by (k + 12*sign(k)). We clamp against
    # the effective label position since that's the true visible extent.
    shrink = 1.0
    for mid, stations in data.items():
        if mid not in member_geom:
            continue
        sx, sy, ex, ey, mdx, mdy, nx, ny, _ = member_geom[mid]
        # Identify peak station for label-extent consideration
        peak_pct, peak_val = max(stations, key=lambda s: abs(s[1]))
        for pct, val in stations:
            t = pct / 100.0
            base_x = sx + mdx * t
            base_y = sy + mdy * t
            k = (val / max_val) * DIAGRAM_MAX_PX
            # Peak station includes the label offset
            if pct == peak_pct and abs(val) > 1e-6:
                k_extended = k + LABEL_EXTRA * (1 if k >= 0 else -1)
            else:
                k_extended = k
            # Proposed outermost point on this station
            px = base_x + nx * k_extended
            py = base_y + ny * k_extended

            # Per-component shrink if outside bounds.
            # Only adjust for the *offset* component (nx*k, ny*k); we cannot
            # shrink the baseline position. If baseline is already outside,
            # skip (should not happen given existing frame padding).
            if base_x < x_min or base_x > x_max or base_y < y_min or base_y > y_max:
                continue

            # Compute the max allowed k that keeps px, py within bounds
            if abs(nx) > 1e-9:
                if nx > 0:
                    k_allow_x = (x_max - base_x) / nx
                else:
                    k_allow_x = (x_min - base_x) / nx
            else:
                k_allow_x = float('inf')
            if abs(ny) > 1e-9:
                if ny > 0:
                    k_allow_y = (y_max - base_y) / ny
                else:
                    k_allow_y = (y_min - base_y) / ny
            else:
                k_allow_y = float('inf')

            k_allow = min(k_allow_x, k_allow_y)
            # k_extended is signed; compare absolute values
            if abs(k_extended) > 1e-9 and k_allow > 0:
                s_needed = abs(k_allow) / abs(k_extended)
                if s_needed < shrink:
                    shrink = s_needed

    # Floor the shrink so tiny diagrams remain legible
    shrink = max(shrink, 0.25)
    effective_max_px = DIAGRAM_MAX_PX * shrink

    # Draw pass
    for mid, stations in data.items():
        if mid not in member_geom:
            continue
        sx, sy, ex, ey, mdx, mdy, nx, ny, _ = member_geom[mid]

        baseline_pts = []
        diagram_pts = []
        for pct, val in stations:
            t = pct / 100.0
            px = sx + mdx * t
            py = sy + mdy * t
            baseline_pts.append((px, py))
            offset = (val / max_val) * effective_max_px
            diagram_pts.append((px + nx * offset, py + ny * offset))

        poly_pts = []
        for pt in baseline_pts:
            poly_pts.extend(pt)
        for pt in reversed(diagram_pts):
            poly_pts.extend(pt)

        if len(poly_pts) >= 6:
            self.create_polygon(
                *poly_pts, fill="", outline=color, width=2,
                tags=("diagram",))
            self.create_polygon(
                *poly_pts, fill=color, outline="", stipple="gray25",
                tags=("diagram",))

        curve_coords = []
        for pt in diagram_pts:
            curve_coords.extend(pt)
        if len(curve_coords) >= 4:
            self.create_line(*curve_coords, fill=color, width=2,
                             tags=("diagram",))

        # Peak label
        peak = max(stations, key=lambda s: abs(s[1]))
        if abs(peak[1]) > 1e-6:
            t = peak[0] / 100.0
            px = sx + mdx * t
            py = sy + mdy * t
            offset = (peak[1] / max_val) * effective_max_px
            lx = px + nx * (offset + 12 * (1 if offset >= 0 else -1))
            ly = py + ny * (offset + 12 * (1 if offset >= 0 else -1))
            unit = {"M": "kNm", "V": "kN", "N": "kN"}[dtype]
            self._create_label(
                lx, ly, f"{peak[1]:.1f} {unit}",
                f"diag_{mid}_{dtype}", fill=color)
```

### Step 2.2: Verification

Launch GUI: `python -m portal_frame.run_gui`
Manual test:
1. Set span to 30m, run analysis, select ULS-1, diagram type M
2. Diagram should fit entirely within the canvas ✓
3. Peak labels should not be clipped at the edges ✓
4. Use a 6m span — diagram should still look reasonable (not shrunk to nothing)
5. Try switching between M / V / N — each should fit independently ✓

### Step 2.3: Commit

```bash
git add portal_frame/gui/preview.py
git commit -m "fix: clamp force diagrams to canvas bounds

Large frames (e.g., 30m span with 118 kNm peak moment) previously
pushed the diagram and peak labels beyond the canvas top edge.

draw_force_diagram now does a pre-pass to compute the minimum shrink
factor that keeps all member stations (including peak label extents)
within the canvas bounds, preserving proportionality across all
members. A 0.25 floor prevents diagrams from shrinking to unreadable.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Combo Descriptions in Dropdown

**Goal:** Diagram dropdown shows "ULS-1: 1.35G", "ULS-2: 1.2G + 1.5Q", etc. instead of bare "ULS-1", "ULS-2".

**Critical files:**
- [portal_frame/analysis/results.py](portal_frame/analysis/results.py)
- [portal_frame/solvers/pynite_solver.py](portal_frame/solvers/pynite_solver.py)
- [portal_frame/gui/app.py](portal_frame/gui/app.py)

**Key existing:**
- `LoadCombination.description` field exists at [portal_frame/standards/combinations_nzs1170_0.py:14](portal_frame/standards/combinations_nzs1170_0.py#L14). Example values: `"1.35G"`, `"1.2G + 1.5Q"`, `"1.2G + W1"`, `"G + 0.7Q"`, `"G + W1(s)"`.
- `PyNiteSolver._get_combinations()` at [portal_frame/solvers/pynite_solver.py:437](portal_frame/solvers/pynite_solver.py#L437) builds `LoadCombination(name, desc, factors, 101+i)` — description is already present.

### Step 3.1: Add `combo_descriptions` field to `AnalysisOutput`

In `portal_frame/analysis/results.py`, modify the `AnalysisOutput` dataclass (line 79):

```python
@dataclass
class AnalysisOutput:
    """Complete analysis output: per-case + combination results + envelopes."""
    case_results: dict[str, CaseResult]
    combo_results: dict[str, CaseResult]
    uls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    sls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    combo_descriptions: dict[str, str] = field(default_factory=dict)
```

### Step 3.2: Populate `combo_descriptions` in `PyNiteSolver.solve()`

In `portal_frame/solvers/pynite_solver.py`, find where `self._output = AnalysisOutput(...)` is constructed in `solve()` (around line 70). Modify to pass `combo_descriptions`:

```python
        # Build combinations from NZS 1170.0
        combos = self._get_combinations()
        combo_results = {}
        combo_descriptions = {}
        for combo in combos:
            combo_results[combo.name] = combine_case_results(
                case_results, combo.factors, combo.name
            )
            combo_descriptions[combo.name] = combo.description

        self._output = AnalysisOutput(
            case_results=case_results,
            combo_results=combo_results,
            combo_descriptions=combo_descriptions,
        )
```

### Step 3.3: Update `_update_diagram_dropdowns()` in app.py

Use a parallel mapping dict (display string → actual name) stored on the app instance. This avoids brittle string parsing.

Replace `_update_diagram_dropdowns()` in `portal_frame/gui/app.py` (around line 1790):

```python
def _update_diagram_dropdowns(self):
    """Populate diagram case dropdown with analysis cases and combos.

    Builds human-friendly display strings for combos (e.g., 'ULS-1: 1.35G')
    while maintaining a display_to_name map for reverse lookup.
    """
    out = self._analysis_output
    self._diagram_display_to_name = {"(none)": None}

    if out is None:
        self.diagram_case_combo["values"] = ["(none)"]
        return

    values = ["(none)"]

    # Individual unfactored cases — name only
    for name in sorted(out.case_results.keys()):
        values.append(name)
        self._diagram_display_to_name[name] = name

    # Combinations — "name: description"
    def _combo_sort_key(n):
        # ULS first, then SLS; numeric order within each
        prefix = 0 if n.startswith("ULS") else 1
        try:
            num = int(n.split("-")[1])
        except (IndexError, ValueError):
            num = 0
        return (prefix, num)

    for name in sorted(out.combo_results.keys(), key=_combo_sort_key):
        desc = out.combo_descriptions.get(name, "")
        display = f"{name}: {desc}" if desc else name
        values.append(display)
        self._diagram_display_to_name[display] = name

    self.diagram_case_combo["values"] = values
```

### Step 3.4: Update `_build_diagram_data()` in app.py

Look up the actual name from the display map:

```python
def _build_diagram_data(self):
    """Build diagram data dict for the preview canvas."""
    display = self.diagram_case_var.get()
    dtype = self.diagram_type_var.get()
    out = self._analysis_output

    # Translate display string back to actual case/combo name
    name = self._diagram_display_to_name.get(display) if hasattr(
        self, '_diagram_display_to_name') else display
    if name is None:
        return None

    if name in out.case_results:
        cr = out.case_results[name]
    elif name in out.combo_results:
        cr = out.combo_results[name]
    else:
        return None

    attr = {"M": "moment", "V": "shear", "N": "axial"}[dtype]
    data = {}
    for mid, mr in cr.members.items():
        data[mid] = [(s.position_pct, getattr(s, attr)) for s in mr.stations]

    members_map = {}
    if self._analysis_topology:
        for mid, mem in self._analysis_topology.members.items():
            members_map[mid] = (mem.node_start, mem.node_end)
    return {"data": data, "type": dtype, "members": members_map}
```

### Step 3.5: Initialize `_diagram_display_to_name` in `__init__`

Add to the `__init__` where `_analysis_output` and `_analysis_topology` are initialised:

```python
self._diagram_display_to_name = {"(none)": None}
```

### Step 3.6: Handle display-vs-name in invalidation

In `_invalidate_analysis()`, no change needed — setting `diagram_case_var.set("(none)")` and `diagram_case_combo["values"] = ["(none)"]` still works because `"(none)"` is in the display map.

However, also reset the map:

```python
if hasattr(self, '_diagram_display_to_name'):
    self._diagram_display_to_name = {"(none)": None}
```

Add this line to `_invalidate_analysis()` from Task 1.

### Step 3.7: Verification

Run: `python -m pytest tests/ -v`
Expected: All 135 tests pass.

Launch GUI: `python -m portal_frame.run_gui`
Manual test:
1. Run analysis with gravity only — Diagram dropdown shows "ULS-1: 1.35G", "ULS-2: 1.2G + 1.5Q", "SLS-1: G + 0.7Q", "SLS-2: G" ✓
2. Enable wind — dropdown shows "ULS-3: 1.2G + W1", "ULS-4: 0.9G + W1", etc. ✓
3. Select a combo with description — diagram displays correctly ✓
4. Change inputs — dropdown resets to "(none)" ✓

### Step 3.8: Commit

```bash
git add portal_frame/analysis/results.py portal_frame/solvers/pynite_solver.py portal_frame/gui/app.py
git commit -m "feat: show combo descriptions in diagram dropdown

Diagram dropdown now displays e.g. 'ULS-1: 1.35G' instead of bare
'ULS-1', using the existing LoadCombination.description field.

- Added combo_descriptions dict to AnalysisOutput
- PyNiteSolver.solve() populates descriptions from build_combinations
- GUI uses a display-to-name map for reverse lookup, avoiding
  brittle string parsing

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Deflection Diagrams

**Goal:** Add a new diagram type δ (lowercase Greek delta U+03B4) to the diagram type dropdown that displays the deflected shape of the frame, drawn perpendicular to each undeformed member.

**Critical files:**
- [portal_frame/analysis/results.py](portal_frame/analysis/results.py)
- [portal_frame/solvers/pynite_solver.py](portal_frame/solvers/pynite_solver.py)
- [portal_frame/analysis/combinations.py](portal_frame/analysis/combinations.py)
- [portal_frame/gui/app.py](portal_frame/gui/app.py)
- [portal_frame/gui/preview.py](portal_frame/gui/preview.py)

**Key existing:**
- `MemberStationResult` dataclass at [portal_frame/analysis/results.py:7](portal_frame/analysis/results.py#L7) — currently has position, position_pct, axial, shear, moment
- `PyNiteSolver._extract_results()` at [portal_frame/solvers/pynite_solver.py:355](portal_frame/solvers/pynite_solver.py#L355) — builds station list per member
- `combine_case_results()` at [portal_frame/analysis/combinations.py:9](portal_frame/analysis/combinations.py#L9) — sums stations across cases
- PyNite deflection API (verified): `model.members[name].deflection('dy', x, combo_name)` returns member-local y deflection in metres. Confirmed during planning.

### Step 4.1: Add `dy_local` field to `MemberStationResult`

In `portal_frame/analysis/results.py`, modify the dataclass:

```python
@dataclass
class MemberStationResult:
    """Forces and deflections at a single station along a member."""
    position: float       # Distance from member start (m)
    position_pct: float   # 0-100%
    axial: float          # kN, +ve = tension
    shear: float          # kN
    moment: float         # kNm
    dy_local: float = 0.0 # mm, member-local y deflection (perpendicular to member)
```

**Note:** Adding the new field with a default at the end preserves backward compatibility with all existing positional constructors (in [combinations.py:28](portal_frame/analysis/combinations.py#L28) and test_pynite_solver.py lines 20-22, 57-59).

### Step 4.2: Extract deflection in `PyNiteSolver._extract_results()`

In `portal_frame/solvers/pynite_solver.py`, modify the station loop inside `_extract_results()` (around line 366). The current code reads axial/shear/moment; add a deflection read:

```python
            for i in range(NUM_STATIONS):
                x = i / (NUM_STATIONS - 1) * L
                pct = i / (NUM_STATIONS - 1) * 100
                # Negate moment and axial to match standard convention:
                # standard: +moment = sagging, +axial = tension
                # PyNite: +moment = hogging, +axial = compression
                axial = -model.members[name].axial(x, "LC")
                shear = model.members[name].shear("Fy", x, "LC")
                moment = -model.members[name].moment("Mz", x, "LC")
                # Local-y deflection in mm (PyNite returns metres)
                dy_local = model.members[name].deflection('dy', x, "LC") * 1000
                stations.append(MemberStationResult(
                    position=x, position_pct=pct,
                    axial=axial, shear=shear, moment=moment,
                    dy_local=dy_local,
                ))
```

### Step 4.3: Sum deflection in `combine_case_results()`

In `portal_frame/analysis/combinations.py`, modify the station loop (around line 19) to also combine `dy_local`:

```python
    members = {}
    for mid, ref_mr in ref_case.members.items():
        stations = []
        for j, ref_st in enumerate(ref_mr.stations):
            axial = shear = moment = dy_local = 0.0
            for cname, factor in factors.items():
                if cname in case_results and mid in case_results[cname].members:
                    st = case_results[cname].members[mid].stations[j]
                    axial += factor * st.axial
                    shear += factor * st.shear
                    moment += factor * st.moment
                    dy_local += factor * st.dy_local
            stations.append(MemberStationResult(
                ref_st.position, ref_st.position_pct,
                axial, shear, moment, dy_local,
            ))
        mr = MemberResult(mid, stations)
        mr.compute_extremes()
        members[mid] = mr
```

### Step 4.4: Add δ to diagram type dropdown

In `portal_frame/gui/app.py`, find the diagram_type_combo creation (line 155-161). Change the values list:

```python
self.diagram_type_combo = ttk.Combobox(
    load_bar, textvariable=self.diagram_type_var,
    values=["M", "V", "N", "δ"], state="readonly", font=FONT_MONO, width=4)
```

### Step 4.5: Wire δ in `_build_diagram_data()`

In `portal_frame/gui/app.py`, update the `attr` map in `_build_diagram_data()`:

```python
    attr = {"M": "moment", "V": "shear", "N": "axial", "δ": "dy_local"}[dtype]
```

### Step 4.6: Add δ to DIAGRAM_COLORS and unit map in preview.py

In `portal_frame/gui/preview.py`:

Update DIAGRAM_COLORS at line 9:
```python
DIAGRAM_COLORS = {
    "M": "#e06c75",   # Red-pink for moment
    "V": "#c678dd",   # Purple for shear
    "N": "#e5c07b",   # Gold for axial
    "δ": "#61afef",   # Blue for deflection
}
```

In `draw_force_diagram()`, update the unit map (currently at line ~498 inside the method):
```python
unit = {"M": "kNm", "V": "kN", "N": "kN", "δ": "mm"}[dtype]
```

### Step 4.7: Add δ to diagram legend

In `update_frame()` in `portal_frame/gui/preview.py`, find the diagram legend block added in Task 7 of the original plan. Update `label_map`:

```python
label_map = {"M": "Moment", "V": "Shear", "N": "Axial", "δ": "Deflection"}
```

### Step 4.8: Update tests

Add a test to `tests/test_pynite_solver.py` that verifies deflection extraction:

```python
def test_beam_gravity_midspan_deflection():
    """Simply supported beam: midspan deflection = 5wL^4 / (384 EI)."""
    req = _make_beam_request(span=10.0, w_dead=2.0, bay=5.0)
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    g_case = out.case_results["G"]
    mr = g_case.members[1]

    # w = 2.0 * 5.0 = 10 kN/m, L = 10m
    # E = 200 GPa = 200e6 kN/m^2
    # Iz = 5e6 mm^4 = 5e6 * 1e-12 m^4 = 5e-6 m^4
    # delta_max = 5wL^4 / (384 EI) = 5 * 10 * 10^4 / (384 * 200e6 * 5e-6)
    #           = 500000 / 384000 = 1.302 m = 1302 mm
    # Midspan deflection should be downward (negative), ~1302 mm magnitude
    mid_station = next(s for s in mr.stations if abs(s.position_pct - 50) < 3)
    # The sign of dy_local depends on PyNite's local-y direction for a
    # horizontal member. We assert the magnitude is correct and non-zero.
    assert abs(abs(mid_station.dy_local) - 1302) < 20
```

Also verify the combine function propagates dy_local:

```python
def test_combine_propagates_dy_local():
    """Linear combination should scale dy_local by the factor."""
    stations = [
        MemberStationResult(0.0, 0, 0, 0, 0, dy_local=0.0),
        MemberStationResult(2.5, 50, 0, 0, 0, dy_local=-5.0),
        MemberStationResult(5.0, 100, 0, 0, 0, dy_local=0.0),
    ]
    mr = MemberResult(member_id=1, stations=stations)
    nr = NodeResult(node_id=1)
    rr = ReactionResult(node_id=1)
    g_case = CaseResult("G", {1: mr}, {1: nr}, {1: rr})
    cases = {"G": g_case}
    combo = combine_case_results(cases, {"G": 1.35}, "ULS-1")
    assert abs(combo.members[1].stations[1].dy_local - 1.35 * -5.0) < 0.01
```

### Step 4.9: Verification

Run: `python -m pytest tests/ -v`
Expected: All 137 tests pass (135 existing + 2 new).

Launch GUI: `python -m portal_frame.run_gui`
Manual test:
1. Set span=12m, eave=4.5m, pitch=5°, run analysis
2. Select "SLS-1: G + 0.7Q" from Diagram dropdown, type "δ"
3. Deflection curve should appear in blue, showing the deformed shape of rafters (sagging) and columns (small) ✓
4. Peak label should show value in mm ✓
5. Switch to "M" — moment diagram appears instead
6. Switch back to "δ" — deflection diagram returns
7. Legend at top-left of canvas should show "Deflection" in blue when δ is active

### Step 4.10: Sign-check and Commit

If the deflection curve draws in the wrong direction (e.g., upward for gravity loading on a beam), the fix is to negate in `draw_force_diagram()` only for the δ case. Add this if needed after the sign check:

```python
# In draw_force_diagram(), if deflection direction needs flipping:
# if dtype == "δ":
#     val = -val  # flip sign for visual convention
```

This is a conditional fix — only apply if the manual visual check in Step 4.9 shows inverted deflection.

```bash
git add portal_frame/analysis/results.py portal_frame/solvers/pynite_solver.py portal_frame/analysis/combinations.py portal_frame/gui/app.py portal_frame/gui/preview.py tests/test_pynite_solver.py
git commit -m "feat: add deflection (δ) diagram type

Adds member-local y-deflection extraction from PyNite and a new
δ diagram type that renders the deformed shape as an offset curve
perpendicular to each undeformed member.

- New MemberStationResult.dy_local field (mm, member-local y)
- PyNiteSolver extracts deflection via model.members[name].deflection('dy', x, 'LC')
- combine_case_results aggregates deflections by linear superposition
- Diagram type dropdown gains 'δ' option
- Blue (#61afef) color distinguishes deflection from M/V/N
- 2 new tests verify extraction and combination

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Overall Verification

After all 4 tasks complete:

1. **Tests:** `python -m pytest tests/ -v` — all 137 tests pass.

2. **Full manual workflow:**
   - Launch GUI with `python -m portal_frame.run_gui`
   - Set geometry: 30m span, 4.5m eave, 5° pitch
   - Click "ANALYSE (PyNite)" — green "Analysis complete" shows
   - Results panel shows ULS/SLS envelope
   - Diagram dropdown shows "(none)", "G", "Q", "W1"..., "ULS-1: 1.35G", "ULS-2: 1.2G + 1.5Q", "SLS-1: G + 0.7Q", etc.
   - Select "ULS-1: 1.35G", type "M" — moment diagram fits within canvas
   - Switch type to "V", then "N", then "δ" — all fit within canvas, correct colours
   - Change span value → results clear, diagram clears, green status clears
   - Re-analyse → everything refreshes correctly
   - Toggle EQ → results clear
   - Click between wind case tabs → results persist

3. **SpaceGass export still works unchanged:**
   - Click "GENERATE SPACEGASS FILE" — output matches pre-Task-1 behaviour

---

## Summary of File Changes

| File | Tasks |
|------|-------|
| `portal_frame/gui/app.py` | 1 (state invalidation), 3 (dropdown display), 4 (δ dropdown option, attr map) |
| `portal_frame/gui/preview.py` | 2 (bounds clamping), 4 (δ color + unit + legend) |
| `portal_frame/analysis/results.py` | 3 (combo_descriptions field), 4 (dy_local field) |
| `portal_frame/solvers/pynite_solver.py` | 3 (populate combo_descriptions), 4 (extract dy_local) |
| `portal_frame/analysis/combinations.py` | 4 (sum dy_local) |
| `tests/test_pynite_solver.py` | 4 (new deflection tests) |
