# Deflection Diagram Continuity Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two graphical defects in the δ (deflection) diagram: the curve is discontinuous at the apex (ridge) where left and right rafters meet, and the column deflection is not connected to the rafter deflection at the knee.

**Architecture:** The current δ renderer projects each member's `dy_local` perpendicular to that member's own axis. At shared nodes, different members project in different directions, so the curves don't meet. The fix extracts both `dx_local` AND `dy_local` from PyNite and rotates them into global coordinates using the member's world angle. Since global displacement at a shared node is physically unique, both members will converge to the same point at the node. This is a δ-only change — M/V/N diagrams continue to use the existing perpendicular-projection.

**Tech Stack:** Python 3.10+, tkinter, PyNite FEModel3D

**Branch:** `pynite-solver-integration` (continuing work)

---

## Context

### Current behavior (broken)

In `portal_frame/gui/preview.py` `draw_force_diagram()`, the δ diagram uses the same code path as M/V/N:
```python
nx = -mdy / length  # screen-space perpendicular (90° CCW from member direction)
ny = mdx / length
offset = (val / max_val) * effective_max_px  # val is dy_local
diagram_pts.append((px + nx * offset, py + ny * offset))
```

This projects `dy_local` along each member's own perpendicular direction. At the apex (ridge), the left rafter's perpendicular points one way and the right rafter's perpendicular points a different way, so their diagram endpoints land at different screen positions. Same problem at the knee (column perpendicular is horizontal, rafter perpendicular is inclined).

### Why this works for M/V/N but not δ

Moment/shear/axial diagrams conventionally draw perpendicular to each member independently. Moment doesn't have to be continuous at a rigid joint in the visualization (even if it's physically continuous). So the perpendicular-projection is the engineering convention.

Deflection is different. It's a **geometric** quantity — the actual deformed position of the structure. At a shared node, all members connected to it move together. The visualization must reflect this or it misleads the viewer.

### The correct approach for δ

At each station on a member, the global deformation vector is:
- `Δworld_x = dx_local * cos θ + dy_local * sin θ`
- `Δworld_y = dx_local * sin θ − dy_local * cos θ`

where θ is the member's angle in world coordinates. The signs above assume our convention: PyNite raw `dx_local` stored as-is, and `dy_local` already negated (from Task 1 of the previous plan, so positive `dy_local` = sagging).

At any node shared between two members, both members' local `(dx, dy)` vectors are different, but when rotated back to global coordinates they give the **same** global displacement vector (because PyNite's solver enforces node displacement continuity). So both members' diagrams will converge at the node.

We can avoid computing θ explicitly by using screen-space direction components. Given screen member direction `(mdx, mdy)` and screen length `L`:
- `cos θ_world = mdx / L`
- `sin θ_world = −mdy / L` (because screen Y is flipped relative to world Y)

Substituting and transforming to screen (with another Y flip for the output), the per-station screen offset is:
- `Δscreen_x = α × (dx_local × mdx − dy_local × mdy) / L`
- `Δscreen_y = α × (dx_local × mdy + dy_local × mdx) / L`

where `α` is a pixels-per-mm scale factor chosen so the max deformation magnitude `max(√(dx² + dy²))` maps to `DIAGRAM_MAX_PX`.

### Verification of the formula

For a horizontal beam (mdx > 0, mdy = 0) with gravity sagging (`dy_local` > 0, `dx_local` ≈ 0):
- `Δscreen_x = α × (0 − positive × 0) / L = 0` (no horizontal motion)
- `Δscreen_y = α × (0 + positive × mdx) / L = α × positive` (downward in screen ✓)

For a vertical column (mdx = 0, mdy < 0) pushed right (`dx_local` ≈ 0, `dy_local` > 0 after negation):
- `Δscreen_x = α × (0 − positive × mdy) / L = α × positive` (rightward ✓)
- `Δscreen_y = α × (0 + positive × 0) / L = 0` (no vertical motion ✓)

For the left rafter (mdx > 0, mdy < 0) at the apex under gravity, both rafters' local (dx, dy) differ, but both compute the same global (Δxw, Δyw) via the rotation, so the apex point coincides.

### M/V/N diagrams stay unchanged

The perpendicular-projection algorithm for force diagrams is preserved. Only δ gets the new deformed-shape algorithm.

---

## File Structure

| File | Responsibility | Changes |
|------|----------------|---------|
| `portal_frame/analysis/results.py` | `MemberStationResult` dataclass | Add `dx_local: float = 0.0` field |
| `portal_frame/solvers/pynite_solver.py` | PyNite extraction | Extract `dx_local` (raw, not negated) in `_extract_results()` |
| `portal_frame/analysis/combinations.py` | Linear combination + envelope | Aggregate `dx_local` alongside `dy_local` |
| `portal_frame/gui/app.py` | Build diagram payload | Add `data_dx` / `data_min_dx` keys when δ selected |
| `portal_frame/gui/preview.py` | Diagram rendering | Detect δ type; use new deformed-shape algorithm; keep old path for M/V/N |
| `tests/test_pynite_solver.py` | Tests | Add tests for `dx_local` extraction + combination + continuity |

---

## Task 1: Add `dx_local` to `MemberStationResult`

**Files:**
- Modify: `portal_frame/analysis/results.py`

- [ ] **Step 1: Add the field**

In `portal_frame/analysis/results.py`, find the `MemberStationResult` dataclass (currently has `position`, `position_pct`, `axial`, `shear`, `moment`, `dy_local`). Add a new `dx_local` field at the end with a default value:

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
    dx_local: float = 0.0 # mm, member-local x deflection (along member axis)
```

The default value keeps all existing positional constructors in `combinations.py` and `tests/test_pynite_solver.py` working without modification (since `dx_local` is appended after existing fields).

- [ ] **Step 2: Verify existing tests still pass**

Run: `python -m pytest tests/ -v`
Expected: 140/140 pass.

- [ ] **Step 3: Commit**

```bash
git add portal_frame/analysis/results.py
git commit -m "feat: add dx_local field to MemberStationResult

Needed for deflection diagram continuity fix — the renderer needs
both dx_local and dy_local to compute the global deformation vector
at each station, which guarantees curves meet at shared nodes.

Default 0.0 preserves backward compatibility with existing positional
constructors.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Extract `dx_local` in PyNite solver

**Files:**
- Modify: `portal_frame/solvers/pynite_solver.py`
- Test: `tests/test_pynite_solver.py`

- [ ] **Step 1: Write test for dx_local extraction**

Append to `tests/test_pynite_solver.py`:

```python
def test_dx_local_extracted_for_column():
    """Vertical column pushed horizontally at top — dy_local (after Task 1
    negation) should be nonzero; dx_local (axial) should be ~0."""
    from portal_frame.models.geometry import Node, Member, FrameTopology
    nodes = {
        1: Node(1, 0.0, 0.0),
        2: Node(2, 0.0, 4.0),
    }
    members = {1: Member(1, 1, 2, section_id=1)}  # column
    topo = FrameTopology(nodes=nodes, members=members)
    sec = CFS_Section(
        name="Test", library="test", library_name="T", group="G",
        Ax=500.0, J=1000.0, Iy=5e6, Iz=5e6,
    )
    supports = SupportCondition(left_base="fixed", right_base="fixed")
    loads = LoadInput(
        dead_load_roof=0.0, dead_load_wall=0.0, live_load_roof=0.0,
        wind_cases=[], include_self_weight=False,
    )
    req = AnalysisRequest(
        topology=topo, column_section=sec, rafter_section=sec,
        supports=supports, load_input=loads,
        span=0.0, eave_height=4.0, roof_pitch=0.0, bay_spacing=5.0,
    )
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    # Under dead load only (zero here) nothing should happen — but the
    # point is that dx_local is a field on the station now and solver
    # populates it (even if 0).
    g_case = solver.output.case_results["G"]
    mr = g_case.members[1]
    assert all(hasattr(s, "dx_local") for s in mr.stations)
    # Magnitude checks: in a zero-load test, both should be ~0
    for s in mr.stations:
        assert abs(s.dx_local) < 0.01
        assert abs(s.dy_local) < 0.01
```

- [ ] **Step 2: Run the test — expect failure**

Run: `python -m pytest tests/test_pynite_solver.py::test_dx_local_extracted_for_column -v`
Expected: Passes if the default 0.0 from Task 1 is in place. (The field exists but is currently not populated by the solver — default 0.0 is returned.) If it passes, move on. If it fails, diagnose.

Actually, this test only verifies the field exists and is 0 when no load. That passes with just Task 1 + default 0.0. We need a stronger test that validates extraction actually pulls from PyNite. Add this second test:

```python
def test_dx_local_nonzero_for_axially_loaded_column():
    """Column with downward tip load should have negative dx_local
    (axial shortening) at the top after extraction."""
    from portal_frame.models.geometry import Node, Member, FrameTopology
    nodes = {
        1: Node(1, 0.0, 0.0),
        2: Node(2, 0.0, 4.0),
    }
    members = {1: Member(1, 1, 2, section_id=1)}
    topo = FrameTopology(nodes=nodes, members=members)
    sec = CFS_Section(
        name="Test", library="test", library_name="T", group="G",
        Ax=500.0, J=1000.0, Iy=5e6, Iz=5e6,
    )
    supports = SupportCondition(left_base="fixed", right_base="fixed")
    loads = LoadInput(
        dead_load_roof=0.0, dead_load_wall=2.0,  # 2 kPa on wall
        live_load_roof=0.0, wind_cases=[], include_self_weight=False,
    )
    req = AnalysisRequest(
        topology=topo, column_section=sec, rafter_section=sec,
        supports=supports, load_input=loads,
        span=0.0, eave_height=4.0, roof_pitch=0.0, bay_spacing=5.0,
    )
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    g_case = solver.output.case_results["G"]
    mr = g_case.members[1]
    # The wall dead is applied in global -Y, which has an axial component
    # along the vertical column. So dx_local at the top should be nonzero
    # after extraction. We don't assert sign (depends on PyNite local x
    # direction) — just that it's not the default 0.0.
    top_station = mr.stations[-1]
    assert abs(top_station.dx_local) > 1e-6, \
        f"dx_local should be nonzero after load, got {top_station.dx_local}"
```

Run: `python -m pytest tests/test_pynite_solver.py::test_dx_local_nonzero_for_axially_loaded_column -v`
Expected: FAIL — the solver doesn't populate `dx_local` yet; it stays at the default 0.0.

- [ ] **Step 3: Extract dx_local in `_extract_results()`**

In `portal_frame/solvers/pynite_solver.py`, find the station loop in `_extract_results()` (around line 368-374). Currently it looks like:

```python
                # Negate moment and axial to match standard convention:
                # standard: +moment = sagging, +axial = tension
                # PyNite: +moment = hogging, +axial = compression
                axial = -model.members[name].axial(x, "LC")
                shear = model.members[name].shear("Fy", x, "LC")
                moment = -model.members[name].moment("Mz", x, "LC")
                # Local-y deflection in mm (PyNite returns metres).
                # Negate so positive = sagging (into frame interior), matching
                # the convention already used for axial and moment extraction.
                dy_local = -model.members[name].deflection('dy', x, "LC") * 1000
                stations.append(MemberStationResult(
                    position=x, position_pct=pct,
                    axial=axial, shear=shear, moment=moment,
                    dy_local=dy_local,
                ))
```

Add a `dx_local` extraction and pass it to the constructor. `dx_local` is PyNite's raw local x deflection — do NOT negate it, because our rotation formula expects PyNite's raw convention for `dx_local` paired with the negated `dy_local`.

Replace with:

```python
                # Negate moment and axial to match standard convention:
                # standard: +moment = sagging, +axial = tension
                # PyNite: +moment = hogging, +axial = compression
                axial = -model.members[name].axial(x, "LC")
                shear = model.members[name].shear("Fy", x, "LC")
                moment = -model.members[name].moment("Mz", x, "LC")
                # Local-y deflection in mm (PyNite returns metres).
                # Negate so positive = sagging (into frame interior), matching
                # the convention already used for axial and moment extraction.
                dy_local = -model.members[name].deflection('dy', x, "LC") * 1000
                # Local-x deflection in mm (PyNite raw — do NOT negate).
                # Used only by the δ diagram renderer to reconstruct the
                # global deformation vector via member-angle rotation.
                dx_local = model.members[name].deflection('dx', x, "LC") * 1000
                stations.append(MemberStationResult(
                    position=x, position_pct=pct,
                    axial=axial, shear=shear, moment=moment,
                    dy_local=dy_local,
                    dx_local=dx_local,
                ))
```

- [ ] **Step 4: Run the test — expect pass**

Run: `python -m pytest tests/test_pynite_solver.py::test_dx_local_nonzero_for_axially_loaded_column -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: 142/142 pass (140 previous + 2 new dx_local tests).

- [ ] **Step 6: Commit**

```bash
git add portal_frame/solvers/pynite_solver.py tests/test_pynite_solver.py
git commit -m "feat: extract dx_local from PyNite per station

PyNiteSolver._extract_results now reads model.members[name].deflection('dx', x)
at each station in addition to 'dy'. Stored raw (without negation) since
the δ diagram renderer pairs it with the already-negated dy_local to
reconstruct the global deformation vector via member-angle rotation.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Aggregate `dx_local` in combinations

**Files:**
- Modify: `portal_frame/analysis/combinations.py`
- Test: `tests/test_pynite_solver.py`

- [ ] **Step 1: Write tests**

Append to `tests/test_pynite_solver.py`:

```python
def test_combine_propagates_dx_local():
    """Linear combination should scale dx_local by the factor."""
    stations = [
        MemberStationResult(0.0, 0, 0, 0, 0, dy_local=0.0, dx_local=0.0),
        MemberStationResult(2.5, 50, 0, 0, 0, dy_local=0.0, dx_local=-3.0),
        MemberStationResult(5.0, 100, 0, 0, 0, dy_local=0.0, dx_local=0.0),
    ]
    mr = MemberResult(member_id=1, stations=stations)
    nr = NodeResult(node_id=1)
    rr = ReactionResult(node_id=1)
    g_case = CaseResult("G", {1: mr}, {1: nr}, {1: rr})
    cases = {"G": g_case}
    combo = combine_case_results(cases, {"G": 1.35}, "ULS-1")
    assert abs(combo.members[1].stations[1].dx_local - 1.35 * -3.0) < 0.01


def test_envelope_bounds_dx_local():
    """Envelope max/min should also bound dx_local across combos."""
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
                assert env_st.dx_local >= combo_st.dx_local - 1e-9
    for mid, env_mr in uls_min.members.items():
        for j, env_st in enumerate(env_mr.stations):
            for combo_cr in uls_combos:
                combo_st = combo_cr.members[mid].stations[j]
                assert env_st.dx_local <= combo_st.dx_local + 1e-9
```

- [ ] **Step 2: Run tests — expect failure**

Run: `python -m pytest tests/test_pynite_solver.py::test_combine_propagates_dx_local tests/test_pynite_solver.py::test_envelope_bounds_dx_local -v`
Expected: FAIL. `combine_case_results` and `_build_envelope_pair` don't handle `dx_local` yet.

- [ ] **Step 3: Update `combine_case_results()`**

In `portal_frame/analysis/combinations.py`, find `combine_case_results()`. The current station loop looks like:

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

Replace with a version that also combines `dx_local`:

```python
    members = {}
    for mid, ref_mr in ref_case.members.items():
        stations = []
        for j, ref_st in enumerate(ref_mr.stations):
            axial = shear = moment = dy_local = dx_local = 0.0
            for cname, factor in factors.items():
                if cname in case_results and mid in case_results[cname].members:
                    st = case_results[cname].members[mid].stations[j]
                    axial += factor * st.axial
                    shear += factor * st.shear
                    moment += factor * st.moment
                    dy_local += factor * st.dy_local
                    dx_local += factor * st.dx_local
            stations.append(MemberStationResult(
                ref_st.position, ref_st.position_pct,
                axial, shear, moment, dy_local, dx_local,
            ))
        mr = MemberResult(mid, stations)
        mr.compute_extremes()
        members[mid] = mr
```

- [ ] **Step 4: Update `_build_envelope_pair()`**

In `portal_frame/analysis/combinations.py`, find `_build_envelope_pair()`. The current station initialisation looks like:

```python
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
```

Add `dx_local` initialisation and the max/min tracking. Replace with:

```python
        max_stations = [
            MemberStationResult(
                position=ref_mr.stations[j].position,
                position_pct=ref_mr.stations[j].position_pct,
                axial=float("-inf"),
                shear=float("-inf"),
                moment=float("-inf"),
                dy_local=float("-inf"),
                dx_local=float("-inf"),
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
                dx_local=float("inf"),
            )
            for j in range(n_stations)
        ]
```

And in the same function, find the per-station update block:

```python
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
```

Replace with a version that also tracks `dx_local`:

```python
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
                if st.dx_local > ms.dx_local:
                    ms.dx_local = st.dx_local
                mn = min_stations[j]
                if st.axial < mn.axial:
                    mn.axial = st.axial
                if st.shear < mn.shear:
                    mn.shear = st.shear
                if st.moment < mn.moment:
                    mn.moment = st.moment
                if st.dy_local < mn.dy_local:
                    mn.dy_local = st.dy_local
                if st.dx_local < mn.dx_local:
                    mn.dx_local = st.dx_local
```

- [ ] **Step 5: Run tests — expect pass**

Run: `python -m pytest tests/ -v`
Expected: 144/144 pass (142 previous + 2 new).

- [ ] **Step 6: Commit**

```bash
git add portal_frame/analysis/combinations.py tests/test_pynite_solver.py
git commit -m "feat: aggregate dx_local in combinations and envelopes

combine_case_results() now sums dx_local alongside axial/shear/moment/
dy_local, and _build_envelope_pair() tracks per-station max/min for it.
Needed so the δ diagram renderer can reconstruct the global deformation
vector from both local components after combinations and envelopes.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Pass `dx_local` to the renderer for δ diagrams

**Files:**
- Modify: `portal_frame/gui/app.py`

- [ ] **Step 1: Update `_build_diagram_data()` to include `dx_local`**

In `portal_frame/gui/app.py`, find the existing `_build_diagram_data()` method. The current code extracts only one scalar per station (the attribute for the selected diagram type). For δ, we also need `dx_local` so the renderer can compute the global deformation.

Replace the entire method with:

```python
def _build_diagram_data(self):
    """Build diagram data dict for the preview canvas.

    For normal cases/combos, returns {'data': {mid: [(pct, val), ...]},
    'type': dtype, 'members': {mid: (n1, n2)}}.

    For envelopes, also includes 'data_min' with the min curve.

    For the δ diagram type, also includes 'data_dx' (and 'data_min_dx'
    for envelopes) — per-station dx_local values needed by the renderer
    to reconstruct the global deformation vector and guarantee diagram
    continuity at shared nodes.
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

    def _extract_dx(cr):
        """For δ diagrams, extract dx_local values parallel to main attr."""
        return {
            mid: [(s.position_pct, s.dx_local) for s in mr.stations]
            for mid, mr in cr.members.items()
        }

    members_map = {}
    if self._analysis_topology:
        for mid, mem in self._analysis_topology.members.items():
            members_map[mid] = (mem.node_start, mem.node_end)

    if env_max is not None:
        result = {
            "data": _extract(env_max),
            "data_min": _extract(env_min),
            "type": dtype,
            "members": members_map,
            "is_envelope": True,
        }
        if dtype == "δ":
            result["data_dx"] = _extract_dx(env_max)
            result["data_min_dx"] = _extract_dx(env_min)
        return result

    # Normal case/combo lookup
    if name in out.case_results:
        cr = out.case_results[name]
    elif name in out.combo_results:
        cr = out.combo_results[name]
    else:
        return None

    result = {
        "data": _extract(cr),
        "type": dtype,
        "members": members_map,
    }
    if dtype == "δ":
        result["data_dx"] = _extract_dx(cr)
    return result
```

- [ ] **Step 2: Verify tests still pass**

Run: `python -m pytest tests/ -v`
Expected: 144/144 pass (no test impact — this is GUI data assembly).

- [ ] **Step 3: Commit**

```bash
git add portal_frame/gui/app.py
git commit -m "feat: include dx_local in δ diagram payload

_build_diagram_data now adds 'data_dx' (and 'data_min_dx' for envelopes)
when the δ diagram type is selected. The preview renderer will use
these alongside dy_local to reconstruct the global deformation vector
at each station, fixing the diagram discontinuities at shared nodes.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Rewrite δ rendering to use global deformation

**Files:**
- Modify: `portal_frame/gui/preview.py`

This is the largest change. The existing `draw_force_diagram()` uses a single algorithm for all diagram types. We'll split it into a helper that handles M/V/N (unchanged) and a new helper that handles δ using the rotation-based deformed-shape algorithm.

- [ ] **Step 1: Add δ branching in `draw_force_diagram()`**

In `portal_frame/gui/preview.py`, find the top of `draw_force_diagram()`. After reading `data = diagram["data"]` and `dtype = diagram["type"]`, add an early branch that dispatches to a separate δ renderer:

Find this block near the top of the method:

```python
    def draw_force_diagram(self, diagram, ns):
        """Draw force diagram overlaid on frame members.

        Computes a global shrink factor so all diagrams (including peak value
        labels) stay within the canvas bounds, preserving proportionality
        across all members.
        """
        data = diagram["data"]
        dtype = diagram["type"]
        members_map = diagram.get("members", {})
        color = DIAGRAM_COLORS.get(dtype, "#e06c75")
```

Immediately after that block, add:

```python
        # δ diagrams use a different algorithm (rotation-based deformed
        # shape) so that curves meet at shared nodes. M/V/N keep using
        # the perpendicular-projection algorithm below.
        if dtype == "δ":
            self._draw_deflection_diagram(diagram, ns)
            return
```

This keeps the existing code path for M/V/N unchanged.

- [ ] **Step 2: Implement `_draw_deflection_diagram()`**

Still in `portal_frame/gui/preview.py`, add a new method after `draw_force_diagram()`:

```python
    def _draw_deflection_diagram(self, diagram, ns):
        """Draw the deflection (δ) diagram as a true deformed shape.

        Unlike M/V/N diagrams which are drawn perpendicular to each member
        independently, the deflection diagram reconstructs the global
        deformation vector at each station from PyNite's member-local
        dx and dy, then plots the deformed position directly. This makes
        the curves meet at shared nodes (apex, knee) because global
        displacement is physically unique at each node.

        Formula (screen coordinates, y-flipped relative to world):
            Δscreen_x = α × (dx_local × mdx − dy_local × mdy) / L
            Δscreen_y = α × (dx_local × mdy + dy_local × mdx) / L
        where (mdx, mdy) is the screen member direction and L is the
        screen member length. α is a uniform scale factor in pixels per
        mm of global deformation magnitude.
        """
        data = diagram["data"]            # {mid: [(pct, dy_local), ...]}
        data_dx = diagram.get("data_dx", {})
        data_min = diagram.get("data_min")
        data_min_dx = diagram.get("data_min_dx", {})
        members_map = diagram.get("members", {})
        color = DIAGRAM_COLORS.get("δ", "#61afef")

        is_envelope = data_min is not None

        # Find max deformation magnitude (in mm) across all stations and
        # both envelope curves (if present). This sets the base scale.
        def _max_mag(data_dy, data_dx_src):
            m = 0.0
            for mid, stations in data_dy.items():
                dx_list = data_dx_src.get(mid, [])
                for i, (_, dy) in enumerate(stations):
                    dx = dx_list[i][1] if i < len(dx_list) else 0.0
                    mag = math.hypot(dx, dy)
                    if mag > m:
                        m = mag
            return m

        max_disp = _max_mag(data, data_dx)
        if is_envelope:
            max_disp = max(max_disp, _max_mag(data_min, data_min_dx))
        if max_disp < 1e-6:
            return

        # Canvas bounds with a small safety pad and reserved label space
        w = self.winfo_width()
        h = self.winfo_height()
        pad = 20
        LABEL_EXTRA = 12
        x_min = pad + LABEL_EXTRA
        x_max = w - pad - LABEL_EXTRA
        y_min = pad + LABEL_EXTRA
        y_max = h - pad - LABEL_EXTRA

        # Pre-compute member geometry (screen-space direction and length)
        member_geom = {}  # mid -> (sx, sy, mdx, mdy, L)
        for mid, _ in data.items():
            if mid not in members_map:
                continue
            n_start, n_end = members_map[mid]
            if n_start not in ns or n_end not in ns:
                continue
            sx, sy = ns[n_start]
            ex, ey = ns[n_end]
            mdx = ex - sx
            mdy = ey - sy
            L = math.hypot(mdx, mdy)
            if L < 1:
                continue
            member_geom[mid] = (sx, sy, mdx, mdy, L)

        # Initial scale: α0 pixels per mm such that max_disp maps to
        # DIAGRAM_MAX_PX.
        alpha_0 = DIAGRAM_MAX_PX / max_disp

        # Pre-pass: find shrink factor so every station stays inside
        # the effective bounds.
        def _station_screen_delta(dx_local, dy_local, mdx, mdy, L, alpha):
            """Return (Δscreen_x, Δscreen_y) in pixels for a station."""
            dsx = alpha * (dx_local * mdx - dy_local * mdy) / L
            dsy = alpha * (dx_local * mdy + dy_local * mdx) / L
            return dsx, dsy

        def _iter_sources():
            yield data, data_dx
            if is_envelope:
                yield data_min, data_min_dx

        shrink = 1.0
        for source_dy, source_dx in _iter_sources():
            for mid, stations in source_dy.items():
                if mid not in member_geom:
                    continue
                sx, sy, mdx, mdy, L = member_geom[mid]
                dx_list = source_dx.get(mid, [])
                for i, (pct, dy_local) in enumerate(stations):
                    dx_local = dx_list[i][1] if i < len(dx_list) else 0.0
                    t = pct / 100.0
                    base_x = sx + mdx * t
                    base_y = sy + mdy * t

                    # Skip if baseline is already outside effective bounds
                    if (base_x < x_min or base_x > x_max or
                            base_y < y_min or base_y > y_max):
                        continue

                    dsx0, dsy0 = _station_screen_delta(
                        dx_local, dy_local, mdx, mdy, L, alpha_0)
                    px_proposed = base_x + dsx0
                    py_proposed = base_y + dsy0

                    s_point = 1.0
                    # X bound check
                    if abs(dsx0) > 1e-9:
                        if px_proposed > x_max:
                            s_point = min(s_point, (x_max - base_x) / dsx0)
                        elif px_proposed < x_min:
                            s_point = min(s_point, (x_min - base_x) / dsx0)
                    # Y bound check
                    if abs(dsy0) > 1e-9:
                        if py_proposed > y_max:
                            s_point = min(s_point, (y_max - base_y) / dsy0)
                        elif py_proposed < y_min:
                            s_point = min(s_point, (y_min - base_y) / dsy0)

                    if s_point < shrink:
                        shrink = s_point

        # Floor the shrink so the diagram stays legible
        shrink = max(shrink, 0.25)
        alpha = alpha_0 * shrink

        # Draw pass
        def _draw_curves(source_dy, source_dx, is_min=False):
            for mid, stations in source_dy.items():
                if mid not in member_geom:
                    continue
                sx, sy, mdx, mdy, L = member_geom[mid]
                dx_list = source_dx.get(mid, [])

                deformed_pts = []
                for i, (pct, dy_local) in enumerate(stations):
                    dx_local = dx_list[i][1] if i < len(dx_list) else 0.0
                    t = pct / 100.0
                    base_x = sx + mdx * t
                    base_y = sy + mdy * t
                    dsx, dsy = _station_screen_delta(
                        dx_local, dy_local, mdx, mdy, L, alpha)
                    deformed_pts.append((base_x + dsx, base_y + dsy))

                # Draw the deformed-shape curve (no polygon fill for δ)
                curve_coords = []
                for pt in deformed_pts:
                    curve_coords.extend(pt)
                if len(curve_coords) >= 4:
                    curve_width = 3
                    if is_min:
                        self.create_line(*curve_coords, fill=color,
                                         width=curve_width, dash=(4, 3),
                                         tags=("diagram",))
                    else:
                        self.create_line(*curve_coords, fill=color,
                                         width=curve_width, tags=("diagram",))

                # Peak label: station with largest global deformation
                # magnitude. Show for both max and min curves when envelope.
                peak_idx = 0
                peak_mag = 0.0
                for i, (_, dy_local) in enumerate(stations):
                    dx_local = dx_list[i][1] if i < len(dx_list) else 0.0
                    mag = math.hypot(dx_local, dy_local)
                    if mag > peak_mag:
                        peak_mag = mag
                        peak_idx = i
                if peak_mag > 1e-6:
                    pct, dy_local = stations[peak_idx]
                    dx_local = (dx_list[peak_idx][1]
                                if peak_idx < len(dx_list) else 0.0)
                    t = pct / 100.0
                    base_x = sx + mdx * t
                    base_y = sy + mdy * t
                    dsx, dsy = _station_screen_delta(
                        dx_local, dy_local, mdx, mdy, L, alpha)
                    # Extend label slightly beyond the peak
                    dmag_screen = math.hypot(dsx, dsy)
                    if dmag_screen > 1e-6:
                        nudge = 12.0 / dmag_screen
                        lx = base_x + dsx * (1.0 + nudge)
                        ly = base_y + dsy * (1.0 + nudge)
                    else:
                        lx = base_x
                        ly = base_y
                    if is_envelope:
                        prefix = "min: " if is_min else "max: "
                    else:
                        prefix = ""
                    label_key = (f"diag_{mid}_δ_min" if is_min
                                 else f"diag_{mid}_δ")
                    self._create_label(
                        lx, ly, f"{prefix}{dy_local:.1f} mm",
                        label_key, fill=color)

        _draw_curves(data, data_dx, is_min=False)
        if is_envelope:
            _draw_curves(data_min, data_min_dx, is_min=True)
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ -v`
Expected: 144/144 pass (still, no test changes).

Syntax check: `python -c "from portal_frame.gui import preview; print('OK')"`

- [ ] **Step 4: Launch GUI to verify visually**

Run: `python -m portal_frame.run_gui &`
Wait 3 seconds, verify with `tasklist | grep python`, then kill the process with `taskkill //F //PID <pid>`.

The full manual verification is the user's job — they will check:
1. Select SLS-1 + δ → rafter sag meets at the apex without a gap
2. Select ULS Envelope + δ → both max and min curves meet at the apex and knee
3. Column deflection connects smoothly to rafter deflection at the knee

- [ ] **Step 5: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "fix: δ diagram uses global deformation for continuity

The old δ renderer projected dy_local perpendicular to each member's
own axis. At shared nodes (apex, knee) different members project in
different directions, so curves didn't meet — producing visible gaps.

New _draw_deflection_diagram() reconstructs the global deformation
vector at each station from both dx_local and dy_local using the
member-angle rotation:
    Δworld_x = dx_local·cos θ + dy_local·sin θ
    Δworld_y = dx_local·sin θ − dy_local·cos θ
Since PyNite enforces node displacement continuity, global Δ at a
shared node is identical from every member's perspective, so all
curves converge to the same point.

M/V/N diagrams are unchanged — they still use the perpendicular-
projection convention, which is the correct engineering way to
draw force diagrams.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Overall Verification

After all 5 tasks complete:

1. **Tests:** `python -m pytest tests/ -v` — 144/144 pass (140 previous + 4 new: 2 `dx_local` extraction tests, 1 combination test, 1 envelope test).

2. **Manual visual verification:**
   - Launch `python -m portal_frame.run_gui`
   - Set geometry (12m span, 4.5m eave, 5° pitch), click ANALYSE
   - Select "SLS-1: G + 0.7Q" + δ
   - **At apex**: the left rafter's deflection curve should connect to the right rafter's deflection curve at the same point — no gap
   - **At knee**: the column's deflection curve should connect smoothly to the rafter's deflection curve — no jump
   - Switch to "ULS Envelope" + δ — both max (solid) and min (dashed) curves meet at shared nodes
   - Check that member deflection peaks look physically reasonable (rafters sag downward under gravity, columns deflect minimally inward)

3. **No regressions:**
   - M / V / N diagrams still render correctly (perpendicular-projection unchanged)
   - SpaceGass export unaffected
   - State invalidation still works
   - Bounds clamping still works

---

## Summary of File Changes

| File | Task |
|------|------|
| `portal_frame/analysis/results.py` | 1 (add `dx_local` field) |
| `portal_frame/solvers/pynite_solver.py` | 2 (extract `dx_local`) |
| `portal_frame/analysis/combinations.py` | 3 (aggregate `dx_local`) |
| `portal_frame/gui/app.py` | 4 (pass `dx_local` to renderer) |
| `portal_frame/gui/preview.py` | 5 (new `_draw_deflection_diagram`) |
| `tests/test_pynite_solver.py` | 2, 3 (4 new tests) |