# PyNite Solver — Deflection + Envelope Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three issues found by user testing: deflection diagram draws in wrong direction under gravity, δ rendering is visually cluttered against the structural members, and there's no ULS/SLS envelope diagram option.

**Architecture:** Four small independent tasks. Task 1 is a one-line sign flip in the solver. Task 2 enhances `draw_force_diagram()` and `update_frame()` to give δ its own visual treatment (no hatch, thicker line, dimmed members). Task 3 computes per-station max/min envelope curves across ULS and SLS combo sets in `combinations.py`, stored as two `CaseResult` objects each on `AnalysisOutput`. Task 4 wires the envelope into the dropdown and preview canvas, including dual-curve rendering with shared shrink factor.

**Tech Stack:** Python 3.10+, tkinter, PyNite FEModel3D

**Branch:** `pynite-solver-integration` (continuing work)

---

## Context

After the previous round of fixes (state invalidation, bounds clamping, combo descriptions, δ diagram type), the user tested the GUI and found:

1. **Deflection diagram (δ) draws upward under gravity on the rafters.** PyNite's local-y for a rafter going eave→ridge points outward from the roof (toward the sky). A downward gravity deflection is stored as positive local-y, and the renderer draws positive on the local-y+ side — which visually appears upward. The fix is to negate `dy_local` at extraction time, matching the existing negation of `axial` and `moment` (which also flip PyNite's conventions to engineering convention).

2. **δ rendering is cluttered.** The stippled fill and the structural member color compete visually with the deflection curve, making the deformed shape hard to read.

3. **No envelope diagram.** Engineers want to see the max/min envelope across all ULS combinations (for design) and all SLS combinations (for serviceability). Standard practice is two bounding curves per member — max-positive and max-negative at each station — showing the envelope band the member must survive.

---

## Ordering Rationale

1. **Task 1** first — trivial one-line fix that also affects Task 2/4 visuals. Independent.
2. **Task 2** — visual cleanup of δ, unlocks a clean view for testing Task 1.
3. **Task 3** — envelope computation (no UI yet, just data model + tests). Independent.
4. **Task 4** — wires envelope into dropdown and renderer. Depends on Task 3's data model.

---

## Task 1: Fix Deflection Sign Convention

**Goal:** Gravity loads should produce visually downward deflection on rafters/beams in the δ diagram.

**Critical files:**
- [portal_frame/solvers/pynite_solver.py](portal_frame/solvers/pynite_solver.py)

### Step 1.1: Negate `dy_local` at extraction time

Find this line in `_extract_results()` (around line 370 of `portal_frame/solvers/pynite_solver.py`):

```python
dy_local = model.members[name].deflection('dy', x, "LC") * 1000
```

Change to:

```python
# Negate local-y deflection so positive = sagging (into frame interior),
# matching the convention already used for axial and moment extraction.
dy_local = -model.members[name].deflection('dy', x, "LC") * 1000
```

### Step 1.2: Verify tests still pass

Run: `python -m pytest tests/ -v`
Expected: 137/137 pass.

**Note:** The test `test_beam_gravity_midspan_deflection` uses `abs(abs(...))` so it's sign-insensitive. The test `test_combine_propagates_dy_local` builds synthetic stations and never touches PyNite, so it's unaffected.

### Step 1.3: Commit

```bash
git add portal_frame/solvers/pynite_solver.py
git commit -m "fix: negate dy_local to match engineering sign convention

PyNite's local-y for a rafter eave→ridge points outward from the roof,
so gravity deflection comes back as positive local-y. The diagram
renderer draws positive values on the local-y+ side, which visually
appears upward for rafters under gravity — structurally nonsensical.

Negate dy_local at extraction time so positive = sagging (into frame
interior), matching the convention already used for axial and moment.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: δ Rendering Cleanup

**Goal:** For the δ diagram type, remove the hatched fill, thicken the curve line, and dim the structural member colors so the deflection curve stands out.

**Critical files:**
- [portal_frame/gui/theme.py](portal_frame/gui/theme.py)
- [portal_frame/gui/preview.py](portal_frame/gui/preview.py)

### Step 2.1: Add dimmed member colors to theme

In `portal_frame/gui/theme.py`, add two new entries to the COLORS dict immediately after the existing `frame_col` and `frame_raf` entries:

```python
"frame_col":        "#4ec9b0",
"frame_col_dim":    "#2a5c54",  # Dimmed teal for deflection overlay
"frame_raf":        "#569cd6",
"frame_raf_dim":    "#2c4e6a",  # Dimmed blue for deflection overlay
```

(Leave other `frame_*` entries exactly as they are.)

### Step 2.2: Dim member colors in `update_frame()` when δ is active

In `portal_frame/gui/preview.py` in `update_frame()`, find the Members block around line 260:

```python
        # Members
        if roof_type == "mono":
            self.create_line(*ns[1], *ns[2], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[2], *ns[3], fill=COLORS["frame_raf"], width=3)
            self.create_line(*ns[3], *ns[4], fill=COLORS["frame_col"], width=3)
        else:
            self.create_line(*ns[1], *ns[2], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[5], *ns[4], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[2], *ns[3], fill=COLORS["frame_raf"], width=3)
            self.create_line(*ns[3], *ns[4], fill=COLORS["frame_raf"], width=3)
```

Replace with:

```python
        # Members — use dimmed colors when δ diagram is active so the
        # deflection curve stands out against the structure.
        is_deflection = bool(diagram and diagram.get("type") == "δ")
        col_color = COLORS["frame_col_dim"] if is_deflection else COLORS["frame_col"]
        raf_color = COLORS["frame_raf_dim"] if is_deflection else COLORS["frame_raf"]

        if roof_type == "mono":
            self.create_line(*ns[1], *ns[2], fill=col_color, width=3)
            self.create_line(*ns[2], *ns[3], fill=raf_color, width=3)
            self.create_line(*ns[3], *ns[4], fill=col_color, width=3)
        else:
            self.create_line(*ns[1], *ns[2], fill=col_color, width=3)
            self.create_line(*ns[5], *ns[4], fill=col_color, width=3)
            self.create_line(*ns[2], *ns[3], fill=raf_color, width=3)
            self.create_line(*ns[3], *ns[4], fill=raf_color, width=3)
```

### Step 2.3: Skip hatched fill and thicken curve for δ in `draw_force_diagram()`

In `portal_frame/gui/preview.py` inside `draw_force_diagram()`, find the draw pass around lines 550-565. The current code unconditionally draws a stippled filled polygon then a curve line. Modify to skip the filled polygon when `dtype == "δ"` and use a thicker line:

Current code (approximately):

```python
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
```

Replace with:

```python
        # For δ, skip the hatched fill — draw only the deflection curve.
        # For M/V/N, draw the filled polygon as before.
        is_deflection = (dtype == "δ")

        if not is_deflection and len(poly_pts) >= 6:
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
            curve_width = 3 if is_deflection else 2
            self.create_line(*curve_coords, fill=color, width=curve_width,
                             tags=("diagram",))
```

### Step 2.4: Verification

Run: `python -m pytest tests/ -v`
Expected: 137/137 pass (no test impact — purely visual changes).

Syntax check: `python -c "from portal_frame.gui import preview, theme; print('OK')"`

### Step 2.5: Commit

```bash
git add portal_frame/gui/theme.py portal_frame/gui/preview.py
git commit -m "fix: clean δ rendering — no hatch, thicker line, dimmed members

Deflection curves were visually cluttered against the stippled fill
and full-brightness structural members. For δ diagrams:
- Skip the filled polygon (no hatch)
- Thicken the curve line from 2 to 3 pixels
- Dim frame member colors to new _dim variants in theme.py

M/V/N diagrams unchanged.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: ULS/SLS Envelope Computation

**Goal:** Compute per-station max/min envelope curves across all ULS combos and all SLS combos. Two `CaseResult` objects per envelope set (max and min), each containing per-station max/min values for moment, shear, axial, and dy_local independently.

**Critical files:**
- [portal_frame/analysis/results.py](portal_frame/analysis/results.py)
- [portal_frame/analysis/combinations.py](portal_frame/analysis/combinations.py)
- [portal_frame/solvers/pynite_solver.py](portal_frame/solvers/pynite_solver.py)
- [tests/test_pynite_solver.py](tests/test_pynite_solver.py)

### Step 3.1: Add envelope-curve fields to `AnalysisOutput`

In `portal_frame/analysis/results.py`, modify the `AnalysisOutput` dataclass. Add two new fields at the end (after `combo_descriptions`):

```python
@dataclass
class AnalysisOutput:
    """Complete analysis output: per-case + combination results + envelopes."""
    case_results: dict[str, CaseResult]
    combo_results: dict[str, CaseResult]
    uls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    sls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    combo_descriptions: dict[str, str] = field(default_factory=dict)
    # Envelope curves: (max, min) CaseResult pair per combo set, or None
    uls_envelope_curves: tuple | None = None   # (max CaseResult, min CaseResult)
    sls_envelope_curves: tuple | None = None
```

### Step 3.2: Add `compute_envelope_curves()` in `combinations.py`

In `portal_frame/analysis/combinations.py`, add a new function after the existing `compute_envelopes()`:

```python
def compute_envelope_curves(output: AnalysisOutput) -> None:
    """Compute per-station envelope curves for ULS and SLS combo sets.

    For each combo set (ULS, SLS), produces two synthetic CaseResult objects:
    - envelope_max: max of each attribute at each station across all combos
    - envelope_min: min of each attribute at each station across all combos

    Note: envelope max moment at station j is taken over all ULS combos
    independently of max shear at station j. The resulting CaseResult is
    a display-only construct — it does not represent any single physical
    state — but shows the bounding curves that the member must survive.

    Mutates output in place by setting output.uls_envelope_curves and
    output.sls_envelope_curves.
    """
    output.uls_envelope_curves = _build_envelope_pair(
        output.combo_results, prefix="ULS")
    output.sls_envelope_curves = _build_envelope_pair(
        output.combo_results, prefix="SLS")


def _build_envelope_pair(
    combo_results: dict[str, CaseResult],
    prefix: str,
) -> tuple | None:
    """Build (max, min) CaseResult pair from all combos matching the prefix.

    Returns None if no combos match the prefix.
    """
    matching = {name: cr for name, cr in combo_results.items()
                if name.startswith(prefix)}
    if not matching:
        return None

    # Use the first combo as a structural template for members/nodes
    ref_cr = next(iter(matching.values()))

    # Build max and min CaseResults by walking every station of every combo
    max_members = {}
    min_members = {}
    for mid, ref_mr in ref_cr.members.items():
        n_stations = len(ref_mr.stations)
        max_stations = [
            MemberStationResult(
                position=ref_mr.stations[j].position,
                position_pct=ref_mr.stations[j].position_pct,
                axial=float("-inf"),
                shear=float("-inf"),
                moment=float("-inf"),
                dy_local=float("-inf"),
            )
            for j in range(n_stations)
        ]
        min_stations = [
            MemberStationResult(
                position=ref_mr.stations[j].position,
                position_pct=ref_mr.stations[j].position_pct,
                axial=float("inf"),
                shear=float("inf"),
                moment=float("inf"),
                dy_local=float("inf"),
            )
            for j in range(n_stations)
        ]
        for cr in matching.values():
            if mid not in cr.members:
                continue
            for j, st in enumerate(cr.members[mid].stations):
                if j >= n_stations:
                    break
                ms = max_stations[j]
                if st.axial > ms.axial:
                    ms.axial = st.axial
                if st.shear > ms.shear:
                    ms.shear = st.shear
                if st.moment > ms.moment:
                    ms.moment = st.moment
                if st.dy_local > ms.dy_local:
                    ms.dy_local = st.dy_local
                mn = min_stations[j]
                if st.axial < mn.axial:
                    mn.axial = st.axial
                if st.shear < mn.shear:
                    mn.shear = st.shear
                if st.moment < mn.moment:
                    mn.moment = st.moment
                if st.dy_local < mn.dy_local:
                    mn.dy_local = st.dy_local

        max_mr = MemberResult(member_id=mid, stations=max_stations)
        max_mr.compute_extremes()
        max_members[mid] = max_mr
        min_mr = MemberResult(member_id=mid, stations=min_stations)
        min_mr.compute_extremes()
        min_members[mid] = min_mr

    # Envelope CaseResults don't carry meaningful deflections/reactions at
    # the node level — those would need separate per-node envelopes. Leave
    # them empty; the renderer only uses members[].stations[] for curves.
    max_cr = CaseResult(
        case_name=f"{prefix} Envelope Max",
        members=max_members,
        deflections={},
        reactions={},
    )
    min_cr = CaseResult(
        case_name=f"{prefix} Envelope Min",
        members=min_members,
        deflections={},
        reactions={},
    )
    return (max_cr, min_cr)
```

### Step 3.3: Call `compute_envelope_curves()` from the solver

In `portal_frame/solvers/pynite_solver.py`, find where `solve()` calls `compute_envelopes(self._output)`. Immediately after that line, add:

```python
        compute_envelope_curves(self._output)
```

Also add the import at the top of the file (near the existing `from portal_frame.analysis.combinations import combine_case_results, compute_envelopes`):

```python
from portal_frame.analysis.combinations import (
    combine_case_results, compute_envelopes, compute_envelope_curves,
)
```

### Step 3.4: Write tests for envelope curves

Append to `tests/test_pynite_solver.py`:

```python
def test_envelope_curves_computed_on_solve():
    """After solve(), uls_envelope_curves and sls_envelope_curves are populated."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    assert out.uls_envelope_curves is not None
    assert out.sls_envelope_curves is not None
    uls_max, uls_min = out.uls_envelope_curves
    sls_max, sls_min = out.sls_envelope_curves
    # Each envelope has the same members as the combos
    assert set(uls_max.members.keys()) == set(out.combo_results["ULS-1"].members.keys())
    assert set(sls_max.members.keys()) == set(out.combo_results["SLS-1"].members.keys())


def test_envelope_max_bounds_all_combos():
    """Envelope max at each station ≥ value at that station in every combo."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    uls_max, uls_min = out.uls_envelope_curves
    uls_combos = [cr for name, cr in out.combo_results.items()
                  if name.startswith("ULS")]

    for mid, env_mr in uls_max.members.items():
        for j, env_st in enumerate(env_mr.stations):
            for combo_cr in uls_combos:
                combo_st = combo_cr.members[mid].stations[j]
                assert env_st.moment >= combo_st.moment - 1e-9
                assert env_st.shear >= combo_st.shear - 1e-9
                assert env_st.axial >= combo_st.axial - 1e-9
                assert env_st.dy_local >= combo_st.dy_local - 1e-9


def test_envelope_min_bounds_all_combos():
    """Envelope min at each station ≤ value at that station in every combo."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    uls_max, uls_min = out.uls_envelope_curves
    uls_combos = [cr for name, cr in out.combo_results.items()
                  if name.startswith("ULS")]

    for mid, env_mr in uls_min.members.items():
        for j, env_st in enumerate(env_mr.stations):
            for combo_cr in uls_combos:
                combo_st = combo_cr.members[mid].stations[j]
                assert env_st.moment <= combo_st.moment + 1e-9
                assert env_st.shear <= combo_st.shear + 1e-9
                assert env_st.axial <= combo_st.axial + 1e-9
                assert env_st.dy_local <= combo_st.dy_local + 1e-9
```

### Step 3.5: Verification

Run: `python -m pytest tests/ -v`
Expected: 140/140 pass (137 previous + 3 new envelope tests).

### Step 3.6: Commit

```bash
git add portal_frame/analysis/results.py portal_frame/analysis/combinations.py portal_frame/solvers/pynite_solver.py tests/test_pynite_solver.py
git commit -m "feat: compute per-station ULS/SLS envelope curves

Adds compute_envelope_curves() in combinations.py that produces two
synthetic CaseResult objects per combo set (max and min), each with
per-station max/min of moment, shear, axial, and dy_local taken
independently across all combos with matching ULS/SLS prefix.

- New AnalysisOutput.uls_envelope_curves and .sls_envelope_curves
  fields (tuples of max, min CaseResults or None)
- PyNiteSolver.solve() populates them after compute_envelopes()
- 3 new tests verify curves are built and correctly bound all combos

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Envelope UI Integration

**Goal:** Add "ULS Envelope" and "SLS Envelope" entries to the diagram case dropdown. When selected, `draw_force_diagram()` draws two bounding curves per member (max solid, min dashed) sharing the same shrink factor.

**Critical files:**
- [portal_frame/gui/app.py](portal_frame/gui/app.py)
- [portal_frame/gui/preview.py](portal_frame/gui/preview.py)

### Step 4.1: Add envelope entries to `_update_diagram_dropdowns()`

In `portal_frame/gui/app.py`, find `_update_diagram_dropdowns()`. After the existing loop that adds combos with descriptions, add envelope entries before setting `self.diagram_case_combo["values"] = values`:

```python
    for name in sorted(out.combo_results.keys(), key=_combo_sort_key):
        desc = out.combo_descriptions.get(name, "")
        display = f"{name}: {desc}" if desc else name
        values.append(display)
        self._diagram_display_to_name[display] = name

    # Envelope entries (last in the dropdown)
    if out.uls_envelope_curves is not None:
        values.append("ULS Envelope")
        self._diagram_display_to_name["ULS Envelope"] = "ULS Envelope"
    if out.sls_envelope_curves is not None:
        values.append("SLS Envelope")
        self._diagram_display_to_name["SLS Envelope"] = "SLS Envelope"

    self.diagram_case_combo["values"] = values
```

### Step 4.2: Handle envelope selection in `_build_diagram_data()`

In `portal_frame/gui/app.py`, find `_build_diagram_data()`. Replace the body with a version that handles envelope cases:

```python
def _build_diagram_data(self):
    """Build diagram data dict for the preview canvas.

    For normal cases/combos, returns {'data': {mid: [(pct, val), ...]},
    'type': dtype, 'members': {mid: (n1, n2)}}.

    For envelopes, also includes 'data_min' with the min curve. The
    renderer draws both curves with a shared shrink factor.
    """
    display = self.diagram_case_var.get()
    dtype = self.diagram_type_var.get()
    out = self._analysis_output

    # Translate display string back to actual case/combo name
    name = self._diagram_display_to_name.get(display) if hasattr(
        self, '_diagram_display_to_name') else display
    if name is None:
        return None

    attr = {"M": "moment", "V": "shear", "N": "axial", "δ": "dy_local"}[dtype]

    # Envelope selections return both max and min curves
    if name == "ULS Envelope" and out.uls_envelope_curves is not None:
        env_max, env_min = out.uls_envelope_curves
    elif name == "SLS Envelope" and out.sls_envelope_curves is not None:
        env_max, env_min = out.sls_envelope_curves
    else:
        env_max = env_min = None

    def _extract(cr):
        return {
            mid: [(s.position_pct, getattr(s, attr)) for s in mr.stations]
            for mid, mr in cr.members.items()
        }

    members_map = {}
    if self._analysis_topology:
        for mid, mem in self._analysis_topology.members.items():
            members_map[mid] = (mem.node_start, mem.node_end)

    if env_max is not None:
        return {
            "data": _extract(env_max),
            "data_min": _extract(env_min),
            "type": dtype,
            "members": members_map,
            "is_envelope": True,
        }

    # Normal case/combo lookup
    if name in out.case_results:
        cr = out.case_results[name]
    elif name in out.combo_results:
        cr = out.combo_results[name]
    else:
        return None

    return {
        "data": _extract(cr),
        "type": dtype,
        "members": members_map,
    }
```

### Step 4.3: Draw two curves in `draw_force_diagram()` when envelope is active

In `portal_frame/gui/preview.py`, modify `draw_force_diagram()` to handle an optional `data_min` key.

**Modification 1: Include data_min in the max_val scan**

Find the max_val scan (near the top of the method):

```python
    # Find max absolute value across all members for normalisation
    max_val = 0
    for stations in data.values():
        for _, val in stations:
            max_val = max(max_val, abs(val))
    if max_val < 1e-6:
        return
```

Replace with:

```python
    # Find max absolute value across all members for normalisation.
    # For envelopes, scan both data (max curve) and data_min (min curve).
    data_min = diagram.get("data_min")
    is_envelope = data_min is not None

    max_val = 0
    for stations in data.values():
        for _, val in stations:
            max_val = max(max_val, abs(val))
    if is_envelope:
        for stations in data_min.values():
            for _, val in stations:
                max_val = max(max_val, abs(val))
    if max_val < 1e-6:
        return
```

**Modification 2: Include data_min in the pre-pass shrink calculation**

Find the pre-pass loop that computes `shrink`. It currently iterates over `data.items()`. Wrap the body into a helper and call it for both data and data_min:

Current:

```python
    # Pre-pass: find global shrink factor by checking every station's
    # proposed diagram point against the effective bounds.
    shrink = 1.0
    for mid, stations in data.items():
        if mid not in member_geom:
            continue
        sx, sy, ex, ey, mdx, mdy, nx, ny = member_geom[mid]
        for pct, val in stations:
            # ... existing body ...
```

Change the outer loop to iterate over both dicts when envelope:

```python
    # Pre-pass: find global shrink factor by checking every station's
    # proposed diagram point against the effective bounds. For envelopes,
    # both the max and min curves must fit.
    shrink = 1.0
    data_sources = [data]
    if is_envelope:
        data_sources.append(data_min)

    for data_source in data_sources:
        for mid, stations in data_source.items():
            if mid not in member_geom:
                continue
            sx, sy, ex, ey, mdx, mdy, nx, ny = member_geom[mid]
            for pct, val in stations:
                # ... existing body of the station loop stays exactly the same ...
```

(Indent the existing station-loop body one level deeper to sit inside the new `for data_source in data_sources:` loop. No other changes to the body.)

**Modification 3: Draw both curves in the draw pass**

Find the draw pass. Refactor it into a helper that takes a data dict and a line style:

Current draw pass:

```python
    # Draw pass
    for mid, stations in data.items():
        if mid not in member_geom:
            continue
        sx, sy, ex, ey, mdx, mdy, nx, ny = member_geom[mid]

        baseline_pts = []
        diagram_pts = []
        for pct, val in stations:
            t = pct / 100.0
            px = sx + mdx * t
            py = sy + mdy * t
            baseline_pts.append((px, py))
            offset = (val / max_val) * effective_max_px
            diagram_pts.append((px + nx * offset, py + ny * offset))

        # ... polygon/curve/label drawing ...
```

Wrap the per-data-source drawing into an inner function and call it for max and (optionally) min. For envelopes, skip the filled polygon entirely (always, even for M/V/N envelopes — two overlapping polygons would be unreadable) and skip the peak label on the min curve (keep the max-curve label only):

Replace the entire draw pass with:

```python
    # Draw pass
    def _draw_curves(data_source, is_min=False):
        for mid, stations in data_source.items():
            if mid not in member_geom:
                continue
            sx, sy, ex, ey, mdx, mdy, nx, ny = member_geom[mid]

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

            # For δ and for envelopes, skip the filled polygon —
            # draw only the curve line for clarity.
            draw_fill = not is_deflection and not is_envelope
            if draw_fill and len(poly_pts) >= 6:
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
                curve_width = 3 if is_deflection else 2
                # Dashed for envelope min curve to distinguish from max
                dash = (4, 3) if is_min else None
                if dash:
                    self.create_line(*curve_coords, fill=color,
                                     width=curve_width, dash=dash,
                                     tags=("diagram",))
                else:
                    self.create_line(*curve_coords, fill=color,
                                     width=curve_width, tags=("diagram",))

            # Peak label — skip on the min curve when envelope so we
            # only see one label per member per station.
            if is_min:
                continue
            peak = max(stations, key=lambda s: abs(s[1]))
            if abs(peak[1]) > 1e-6:
                t = peak[0] / 100.0
                px = sx + mdx * t
                py = sy + mdy * t
                offset = (peak[1] / max_val) * effective_max_px
                lx = px + nx * (offset + 12 * (1 if offset >= 0 else -1))
                ly = py + ny * (offset + 12 * (1 if offset >= 0 else -1))
                unit = {"M": "kNm", "V": "kN", "N": "kN", "δ": "mm"}[dtype]
                self._create_label(
                    lx, ly, f"{peak[1]:.1f} {unit}",
                    f"diag_{mid}_{dtype}", fill=color)

    is_deflection = (dtype == "δ")
    _draw_curves(data, is_min=False)
    if is_envelope:
        _draw_curves(data_min, is_min=True)
```

**Important:** `is_deflection` must be defined before `_draw_curves` uses it. The refactor above defines it right before the calls. Also, the existing `is_deflection` computation (from Task 2) must be removed from its current location so it isn't duplicated.

### Step 4.4: Verification

Run: `python -m pytest tests/ -v`
Expected: 140/140 pass.

Syntax check:
```bash
python -c "from portal_frame.gui import preview, app; print('OK')"
```

Launch GUI: `python -m portal_frame.run_gui &` (wait 3 seconds, then `tasklist | grep python` to verify running, then kill).

Manual test after you take it from here:
1. Set geometry (12m span, 4.5m eave, 5°), click ANALYSE
2. Verify δ diagram now shows downward (sagging) rafter deflection — not upward
3. Verify δ rendering has no hatch fill and members appear dimmed
4. Open Diagram dropdown — "ULS Envelope" and "SLS Envelope" appear at the end
5. Select "ULS Envelope" + type "M" — two curves (solid max, dashed min) per member
6. Switch type to δ — envelope works for deflection too
7. Select "SLS Envelope" + type "δ" — SLS deflection envelope visible

### Step 4.5: Commit

```bash
git add portal_frame/gui/app.py portal_frame/gui/preview.py
git commit -m "feat: add ULS/SLS envelope diagram selection

Two new dropdown entries ('ULS Envelope', 'SLS Envelope') appear at
the bottom of the Diagram dropdown once analysis has run. When
selected, draw_force_diagram() draws two bounding curves per member:
solid for max, dashed for min. Both curves share a single shrink
factor so they always fit inside the canvas together.

Envelope curves use no hatch fill (clarity with dashed line) and
show a single peak value label per member (from the max curve).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Overall Verification

After all 4 tasks complete:

1. **Tests:** `python -m pytest tests/ -v` — all 140 tests pass (137 previous + 3 envelope).

2. **Full manual workflow:**
   - Launch `python -m portal_frame.run_gui`
   - Set 12m span, 4.5m eave, 5° pitch, click ANALYSE
   - Select SLS-1 + δ — rafter deflection now shows downward (sagging) ✓
   - Verify δ rendering is clean: no hatch, thicker curve, dimmed members ✓
   - Open Diagram dropdown — "ULS Envelope" and "SLS Envelope" appear at end ✓
   - Select "ULS Envelope" + M — two bounding moment curves per member ✓
   - Switch to V, N, δ — envelope works for all diagram types ✓
   - Switch to "SLS Envelope" — SLS envelope curves render ✓
   - Change any input → results clear (state invalidation still works from previous fixes) ✓

3. **SpaceGass export still works unchanged:**
   - Click GENERATE SPACEGASS FILE — output matches pre-existing behavior.

---

## Summary of File Changes

| File | Tasks |
|------|-------|
| `portal_frame/solvers/pynite_solver.py` | 1 (sign flip), 3 (call compute_envelope_curves + import) |
| `portal_frame/gui/theme.py` | 2 (dim color entries) |
| `portal_frame/gui/preview.py` | 2 (dim members, skip hatch for δ, thicker line), 4 (envelope dual curves) |
| `portal_frame/analysis/results.py` | 3 (envelope_curves fields) |
| `portal_frame/analysis/combinations.py` | 3 (compute_envelope_curves + helper) |
| `portal_frame/gui/app.py` | 4 (dropdown entries, envelope data extraction) |
| `tests/test_pynite_solver.py` | 3 (3 new envelope tests) |
