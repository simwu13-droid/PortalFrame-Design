# PyNite Solver Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PyNite as an in-app structural analysis solver with force diagram visualization, while keeping SpaceGass export unchanged.

**Architecture:** PyNiteSolver implements the existing AnalysisSolver ABC. Individual unfactored load cases are solved separately, then combined in Python using NZS 1170.0 factors from `build_combinations()`. Results displayed in a summary panel and as M/V/N diagram overlays on the existing FramePreview canvas.

**Tech Stack:** PyNiteFEA 2.4.1, tkinter, existing NZS 1170.0 combination logic

**Spec:** `docs/superpowers/specs/2026-04-09-pynite-solver-integration-design.md`

---

## Verified PyNite API Notes

These were verified against PyNiteFEA 2.4.1 installed locally:

- **Import:** `from Pynite import FEModel3D` (capital P, lowercase ynite — NOT `PyNite`)
- **Sections:** `model.add_section(name, A, Iy, Iz, J)` — separate from `add_member`
- **Members:** `model.add_member(name, i_node, j_node, material_name, section_name)`
- **Loads:** `model.add_member_dist_load(member_name, direction, w1, w2, x1, x2, case=case_name)`
- **Node loads:** `model.add_node_load(node_name, direction, P, case=case_name)`
- **Results:** `model.members[name].moment('Mz', x, combo_name)`, `.shear('Fy', x, combo)`, `.axial(x, combo)`
- **Node results:** `model.nodes[name].DX[combo]`, `.DY[combo]`, `.RZ[combo]` (dict keyed by combo name)
- **Reactions:** `model.nodes[name].RxnFX[combo]`, `.RxnFY[combo]`, `.RxnMZ[combo]`
- **Member length:** `model.members[name].L()`
- **Units:** With coords in metres: E = 200,000,000 kN/m^2, G = 80,000,000 kN/m^2, section props in m^2/m^4
- **Moment sign:** PyNite returns NEGATED moments vs standard convention (wL^2/8 returns as -wL^2/8). Negate when extracting.
- **Axial sign:** PyNite positive = compression (opposite to standard +tension). Negate when extracting.
- **2D constraint:** `def_support(name, False, False, True, True, True, False)` on ALL nodes restrains Dz, Rx, Ry. Override base nodes for pin/fix.
- **Per-case strategy:** Use `add_load_combo('LC', {case_name: 1.0})` per solve, extract with combo `'LC'`

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `portal_frame/analysis/__init__.py` | Package init (empty) |
| `portal_frame/analysis/results.py` | Result dataclasses: MemberStationResult, MemberResult, NodeResult, ReactionResult, CaseResult, EnvelopeEntry, AnalysisOutput |
| `portal_frame/analysis/combinations.py` | `combine_case_results()`, `compute_envelopes()` |
| `portal_frame/solvers/pynite_solver.py` | PyNiteSolver implementing AnalysisSolver ABC |
| `tests/test_pynite_solver.py` | Solver validation tests |

### Modified Files
| File | Changes |
|------|---------|
| `pyproject.toml` | Add PyNiteFEA dependency |
| `portal_frame/gui/app.py` | Analyse button, `_build_analysis_request()` refactor, results panel, diagram dropdowns |
| `portal_frame/gui/preview.py` | `draw_force_diagram()` method |
| `portal_frame/gui/theme.py` | Diagram colors |

---

## Task 1: Add PyNiteFEA Dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency to pyproject.toml**

In `pyproject.toml`, add the dependencies list under `[project]`:

```toml
dependencies = [
    "PyNiteFEA>=2.4.0",
]
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from Pynite import FEModel3D; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add PyNiteFEA dependency"
```

---

## Task 2: Result Dataclasses

**Files:**
- Create: `portal_frame/analysis/__init__.py`
- Create: `portal_frame/analysis/results.py`
- Test: `tests/test_pynite_solver.py`

- [ ] **Step 1: Write test for result dataclasses**

Create `tests/test_pynite_solver.py`:

```python
"""Tests for PyNite solver integration."""

import pytest
from portal_frame.analysis.results import (
    MemberStationResult, MemberResult, NodeResult,
    ReactionResult, CaseResult, EnvelopeEntry, AnalysisOutput,
)


def test_member_station_result_stores_forces():
    st = MemberStationResult(position=2.5, position_pct=50.0,
                             axial=10.0, shear=-5.0, moment=25.0)
    assert st.position == 2.5
    assert st.axial == 10.0
    assert st.moment == 25.0


def test_member_result_computes_extremes():
    stations = [
        MemberStationResult(0.0, 0, 5.0, -10.0, 0.0),
        MemberStationResult(2.5, 50, -3.0, 2.0, 50.0),
        MemberStationResult(5.0, 100, 5.0, 8.0, 0.0),
    ]
    mr = MemberResult(member_id=1, stations=stations)
    mr.max_moment = max(s.moment for s in stations)
    mr.min_moment = min(s.moment for s in stations)
    mr.max_shear = max(abs(s.shear) for s in stations)
    mr.max_axial = max(s.axial for s in stations)
    mr.min_axial = min(s.axial for s in stations)
    assert mr.max_moment == 50.0
    assert mr.min_moment == 0.0
    assert mr.max_shear == 10.0
    assert mr.max_axial == 5.0
    assert mr.min_axial == -3.0


def test_case_result_organizes_by_id():
    mr = MemberResult(member_id=1, stations=[])
    nr = NodeResult(node_id=1, dx=1.5, dy=-2.0, rz=0.001)
    rr = ReactionResult(node_id=1, fx=0.0, fy=50.0, mz=0.0)
    cr = CaseResult(case_name="G", members={1: mr},
                    deflections={1: nr}, reactions={1: rr})
    assert cr.case_name == "G"
    assert cr.reactions[1].fy == 50.0


def test_analysis_output_holds_cases_and_combos():
    out = AnalysisOutput(case_results={}, combo_results={})
    assert out.uls_envelope == {}
    assert out.sls_envelope == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pynite_solver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portal_frame.analysis'`

- [ ] **Step 3: Create the analysis package and results module**

Create `portal_frame/analysis/__init__.py` (empty file).

Create `portal_frame/analysis/results.py`:

```python
"""Result dataclasses for structural analysis output."""

from dataclasses import dataclass, field


@dataclass
class MemberStationResult:
    """Forces at a single station along a member."""
    position: float       # Distance from member start (m)
    position_pct: float   # 0-100%
    axial: float          # kN, +ve = tension
    shear: float          # kN
    moment: float         # kNm


@dataclass
class MemberResult:
    """Complete results for one member in one load case/combo."""
    member_id: int
    stations: list[MemberStationResult]
    max_moment: float = 0.0
    min_moment: float = 0.0
    max_shear: float = 0.0
    max_axial: float = 0.0
    min_axial: float = 0.0


@dataclass
class NodeResult:
    """Displacement at a single node."""
    node_id: int
    dx: float = 0.0   # mm (horizontal)
    dy: float = 0.0   # mm (vertical)
    rz: float = 0.0   # rad


@dataclass
class ReactionResult:
    """Reaction at a support node."""
    node_id: int
    fx: float = 0.0   # kN
    fy: float = 0.0   # kN
    mz: float = 0.0   # kNm


@dataclass
class CaseResult:
    """All results for a single load case or combination."""
    case_name: str
    members: dict[int, MemberResult]
    deflections: dict[int, NodeResult]
    reactions: dict[int, ReactionResult]


@dataclass
class EnvelopeEntry:
    """Max/min value with the controlling combination name."""
    value: float
    combo_name: str
    member_id: int = 0
    position_pct: float = 0.0


@dataclass
class AnalysisOutput:
    """Complete analysis output: per-case + combination results + envelopes."""
    case_results: dict[str, CaseResult]
    combo_results: dict[str, CaseResult]
    uls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    sls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pynite_solver.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add portal_frame/analysis/__init__.py portal_frame/analysis/results.py tests/test_pynite_solver.py
git commit -m "feat: add analysis result dataclasses"
```

---

## Task 3: Combination Post-Processing

**Files:**
- Create: `portal_frame/analysis/combinations.py`
- Test: `tests/test_pynite_solver.py`

- [ ] **Step 1: Write tests for linear combination and envelope**

Append to `tests/test_pynite_solver.py`:

```python
from portal_frame.analysis.combinations import (
    combine_case_results, compute_envelopes,
)


def _make_case(name, axial, shear, moment, dy_mm=0.0, fy_rxn=0.0):
    """Helper to build a CaseResult with one member (id=1) and one node (id=1)."""
    stations = [
        MemberStationResult(0.0, 0, axial, shear, 0.0),
        MemberStationResult(2.5, 50, axial, 0.0, moment),
        MemberStationResult(5.0, 100, axial, -shear, 0.0),
    ]
    mr = MemberResult(member_id=1, stations=stations)
    nr = NodeResult(node_id=1, dx=0.0, dy=dy_mm, rz=0.0)
    rr = ReactionResult(node_id=1, fx=0.0, fy=fy_rxn, mz=0.0)
    return CaseResult(name, {1: mr}, {1: nr}, {1: rr})


def test_combine_scales_by_factor():
    g_case = _make_case("G", axial=-10.0, shear=20.0, moment=50.0,
                        dy_mm=-5.0, fy_rxn=40.0)
    cases = {"G": g_case}
    combo = combine_case_results(cases, {"G": 1.35}, "ULS-1")
    assert combo.case_name == "ULS-1"
    # Midspan moment station (index 1)
    assert abs(combo.members[1].stations[1].moment - 1.35 * 50.0) < 0.01
    assert abs(combo.deflections[1].dy - 1.35 * -5.0) < 0.01
    assert abs(combo.reactions[1].fy - 1.35 * 40.0) < 0.01


def test_combine_sums_multiple_cases():
    g_case = _make_case("G", axial=-10.0, shear=20.0, moment=50.0)
    q_case = _make_case("Q", axial=-2.0, shear=5.0, moment=12.0)
    cases = {"G": g_case, "Q": q_case}
    combo = combine_case_results(cases, {"G": 1.2, "Q": 1.5}, "ULS-2")
    # Midspan moment: 1.2*50 + 1.5*12 = 60 + 18 = 78
    assert abs(combo.members[1].stations[1].moment - 78.0) < 0.01


def test_combine_ignores_missing_cases():
    g_case = _make_case("G", axial=-10.0, shear=20.0, moment=50.0)
    cases = {"G": g_case}
    # Factor references "W1" which doesn't exist in cases
    combo = combine_case_results(cases, {"G": 1.2, "W1": 1.0}, "ULS-3")
    # Only G contributes
    assert abs(combo.members[1].stations[1].moment - 1.2 * 50.0) < 0.01


def test_compute_envelopes_tracks_controlling_combo():
    c1 = _make_case("ULS-1", axial=-13.5, shear=27.0, moment=67.5, dy_mm=-6.75)
    c2 = _make_case("ULS-2", axial=-15.0, shear=33.5, moment=78.0, dy_mm=-8.50)
    out = AnalysisOutput(
        case_results={},
        combo_results={"ULS-1": c1, "ULS-2": c2},
    )
    compute_envelopes(out)
    assert out.uls_envelope["max_moment"].value == 78.0
    assert out.uls_envelope["max_moment"].combo_name == "ULS-2"
    assert out.uls_envelope["max_shear"].value == pytest.approx(33.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pynite_solver.py::test_combine_scales_by_factor -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portal_frame.analysis.combinations'`

- [ ] **Step 3: Implement combinations module**

Create `portal_frame/analysis/combinations.py`:

```python
"""Post-processing: linear combination and envelope computation."""

from portal_frame.analysis.results import (
    CaseResult, MemberResult, MemberStationResult,
    NodeResult, ReactionResult, AnalysisOutput, EnvelopeEntry,
)


def combine_case_results(
    case_results: dict[str, CaseResult],
    factors: dict[str, float],
    combo_name: str,
) -> CaseResult:
    """Linearly combine per-case results: combo = sum(factor_i * case_i)."""
    ref_case = next(iter(case_results.values()))

    members = {}
    for mid, ref_mr in ref_case.members.items():
        stations = []
        for j, ref_st in enumerate(ref_mr.stations):
            axial = shear = moment = 0.0
            for cname, factor in factors.items():
                if cname in case_results and mid in case_results[cname].members:
                    st = case_results[cname].members[mid].stations[j]
                    axial += factor * st.axial
                    shear += factor * st.shear
                    moment += factor * st.moment
            stations.append(MemberStationResult(
                ref_st.position, ref_st.position_pct,
                axial, shear, moment,
            ))
        mr = MemberResult(mid, stations)
        mr.max_moment = max(s.moment for s in stations)
        mr.min_moment = min(s.moment for s in stations)
        mr.max_shear = max(abs(s.shear) for s in stations)
        mr.max_axial = max(s.axial for s in stations)
        mr.min_axial = min(s.axial for s in stations)
        members[mid] = mr

    deflections = {}
    for nid, ref_nd in ref_case.deflections.items():
        dx = dy = rz = 0.0
        for cname, factor in factors.items():
            if cname in case_results and nid in case_results[cname].deflections:
                nd = case_results[cname].deflections[nid]
                dx += factor * nd.dx
                dy += factor * nd.dy
                rz += factor * nd.rz
        deflections[nid] = NodeResult(nid, dx, dy, rz)

    reactions = {}
    for nid, ref_rx in ref_case.reactions.items():
        fx = fy = mz = 0.0
        for cname, factor in factors.items():
            if cname in case_results and nid in case_results[cname].reactions:
                rx = case_results[cname].reactions[nid]
                fx += factor * rx.fx
                fy += factor * rx.fy
                mz += factor * rx.mz
        reactions[nid] = ReactionResult(nid, fx, fy, mz)

    return CaseResult(combo_name, members, deflections, reactions)


def compute_envelopes(output: AnalysisOutput) -> None:
    """Compute ULS and SLS envelopes across all combinations. Mutates output in-place."""
    output.uls_envelope = {}
    output.sls_envelope = {}

    for combo_name, cr in output.combo_results.items():
        is_uls = combo_name.startswith("ULS")
        env = output.uls_envelope if is_uls else output.sls_envelope

        for mid, mr in cr.members.items():
            for st in mr.stations:
                _update_max(env, "max_moment", st.moment, combo_name, mid, st.position_pct)
                _update_min(env, "min_moment", st.moment, combo_name, mid, st.position_pct)
                _update_abs_max(env, "max_shear", st.shear, combo_name, mid, st.position_pct)
                _update_max(env, "max_axial", st.axial, combo_name, mid, st.position_pct)
                _update_min(env, "min_axial", st.axial, combo_name, mid, st.position_pct)

        for nid, nd in cr.deflections.items():
            _update_abs_max(env, "max_dx", nd.dx, combo_name)
            _update_abs_max(env, "max_dy", nd.dy, combo_name)

        for nid, rx in cr.reactions.items():
            _update_abs_max(env, "max_reaction_fy", rx.fy, combo_name)


def _update_max(env, key, value, combo_name, mid=0, pct=0.0):
    if key not in env or value > env[key].value:
        env[key] = EnvelopeEntry(value, combo_name, mid, pct)


def _update_min(env, key, value, combo_name, mid=0, pct=0.0):
    if key not in env or value < env[key].value:
        env[key] = EnvelopeEntry(value, combo_name, mid, pct)


def _update_abs_max(env, key, value, combo_name, mid=0, pct=0.0):
    if key not in env or abs(value) > abs(env[key].value):
        env[key] = EnvelopeEntry(value, combo_name, mid, pct)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pynite_solver.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add portal_frame/analysis/combinations.py tests/test_pynite_solver.py
git commit -m "feat: add combination post-processing and envelope computation"
```

---

## Task 4: PyNiteSolver Core — Model Building

**Files:**
- Create: `portal_frame/solvers/pynite_solver.py`
- Test: `tests/test_pynite_solver.py`

- [ ] **Step 1: Write test for simply-supported beam under UDL**

Append to `tests/test_pynite_solver.py`:

```python
import math
from portal_frame.models.geometry import Node, Member, FrameTopology
from portal_frame.models.sections import CFS_Section
from portal_frame.models.loads import LoadInput
from portal_frame.models.supports import SupportCondition
from portal_frame.solvers.base import AnalysisRequest
from portal_frame.solvers.pynite_solver import PyNiteSolver


def _make_beam_request(span=10.0, w_dead=2.0, bay=5.0):
    """Simple beam: 2 nodes, 1 rafter member, pinned-roller supports."""
    nodes = {
        1: Node(1, 0.0, 0.0),
        2: Node(2, span, 0.0),
    }
    members = {1: Member(1, 1, 2, section_id=2)}  # rafter
    topo = FrameTopology(nodes=nodes, members=members)

    sec = CFS_Section(
        name="Test", library="test", library_name="T", group="G",
        Ax=500.0, J=1000.0, Iy=5e6, Iz=5e6,
    )
    supports = SupportCondition(left_base="pinned", right_base="pinned")
    loads = LoadInput(
        dead_load_roof=w_dead, dead_load_wall=0.0, live_load_roof=0.0,
        wind_cases=[], include_self_weight=False, bay_spacing=bay,
    )
    return AnalysisRequest(
        topology=topo, column_section=sec, rafter_section=sec,
        supports=supports, load_input=loads,
        span=span, eave_height=0.0, roof_pitch=0.0, bay_spacing=bay,
    )


def test_beam_gravity_reactions():
    """Simply supported beam: reactions = wL/2."""
    req = _make_beam_request(span=10.0, w_dead=2.0, bay=5.0)
    solver = PyNiteSolver()
    solver.build_model(req)
    result = solver.solve()
    assert result.solved is True

    out = solver.output
    g_case = out.case_results["G"]

    # Total applied load = 2.0 kPa * 5.0 m bay * 10.0 m span = 100 kN
    # Each reaction = 50 kN (downward load -> positive upward reaction)
    assert abs(g_case.reactions[1].fy - 50.0) < 0.5
    assert abs(g_case.reactions[2].fy - 50.0) < 0.5


def test_beam_gravity_midspan_moment():
    """Simply supported beam: M_max = wL^2/8 at midspan."""
    req = _make_beam_request(span=10.0, w_dead=2.0, bay=5.0)
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    g_case = out.case_results["G"]
    mr = g_case.members[1]

    # w = 2.0 * 5.0 = 10 kN/m, L = 10m -> M_max = 10*100/8 = 125 kNm
    # Find midspan station (50%)
    mid_station = next(s for s in mr.stations if abs(s.position_pct - 50) < 3)
    assert abs(mid_station.moment - 125.0) < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pynite_solver.py::test_beam_gravity_reactions -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portal_frame.solvers.pynite_solver'`

- [ ] **Step 3: Implement PyNiteSolver**

Create `portal_frame/solvers/pynite_solver.py`:

```python
"""PyNite structural analysis solver — in-app FEM analysis."""

import math

from Pynite import FEModel3D

from portal_frame.solvers.base import AnalysisSolver, AnalysisRequest, AnalysisResults
from portal_frame.analysis.results import (
    AnalysisOutput, CaseResult, MemberResult, MemberStationResult,
    NodeResult, ReactionResult,
)
from portal_frame.analysis.combinations import combine_case_results, compute_envelopes
from portal_frame.standards.combinations_nzs1170_0 import build_combinations
from portal_frame.standards.earthquake_nzs1170_5 import calculate_earthquake_forces

NUM_STATIONS = 21


class PyNiteSolver(AnalysisSolver):
    """In-app structural solver using PyNite FEModel3D."""

    def __init__(self):
        self._request: AnalysisRequest | None = None
        self._output: AnalysisOutput | None = None

    @property
    def output(self) -> AnalysisOutput | None:
        return self._output

    def build_model(self, request: AnalysisRequest) -> None:
        self._request = request
        self._output = None

    def solve(self) -> AnalysisResults:
        r = self._request
        case_names = self._build_case_names()

        # Solve each unfactored load case individually
        case_results = {}
        for case_name in case_names:
            model = self._new_model()
            self._apply_loads(model, case_name)
            model.add_load_combo("LC", {case_name: 1.0})
            model.analyze()
            case_results[case_name] = self._extract_results(model, case_name)

        # Build combinations from NZS 1170.0
        combos = self._get_combinations()
        combo_results = {}
        for combo in combos:
            combo_results[combo.name] = combine_case_results(
                case_results, combo.factors, combo.name
            )

        self._output = AnalysisOutput(
            case_results=case_results,
            combo_results=combo_results,
        )
        compute_envelopes(self._output)

        return AnalysisResults(solved=True)

    def export(self, path: str) -> None:
        pass  # PyNite solver does not export files

    # ── Model construction ──

    def _new_model(self) -> FEModel3D:
        """Build a fresh PyNite model with nodes, members, supports (no loads)."""
        r = self._request
        model = FEModel3D()

        # Material: CFS steel (units: kN/m^2 for E and G)
        model.add_material("Steel", 200e6, 80e6, 0.3, 7850)

        # Sections
        col = r.column_section
        raf = r.rafter_section
        model.add_section("Col", col.Ax_m, col.Iy_m, col.Iz_m, col.J_m)
        model.add_section("Raf", raf.Ax_m, raf.Iy_m, raf.Iz_m, raf.J_m)

        # Nodes
        for nid, node in r.topology.nodes.items():
            model.add_node(f"N{nid}", node.x, node.y, 0.0)

        # 2D constraints: restrain out-of-plane DOFs at ALL nodes first
        for nid in r.topology.nodes:
            model.def_support(f"N{nid}", False, False, True, True, True, False)

        # Base supports (override out-of-plane-only with full support)
        base_nodes = sorted(r.topology.get_base_nodes(), key=lambda n: n.x)
        if len(base_nodes) >= 2:
            left_cond = r.supports.left_base
            right_cond = r.supports.right_base
            self._apply_support(model, base_nodes[0], left_cond)
            self._apply_support(model, base_nodes[-1], right_cond)

        # Members
        for mid, mem in r.topology.members.items():
            sec_name = "Col" if mem.section_id == 1 else "Raf"
            model.add_member(f"M{mid}", f"N{mem.node_start}",
                             f"N{mem.node_end}", "Steel", sec_name)

        return model

    def _apply_support(self, model, node, condition):
        name = f"N{node.id}"
        if condition == "fixed":
            model.def_support(name, True, True, True, True, True, True)
        else:  # pinned
            model.def_support(name, True, True, True, True, True, False)

    # ── Case map ──

    def _build_case_names(self) -> list[str]:
        """Build ordered list of unfactored case names matching SpaceGassWriter."""
        r = self._request
        names = ["G", "Q"]
        for wc in r.load_input.wind_cases:
            names.append(wc.name)
        if r.load_input.earthquake is not None:
            names.extend(["E+", "E-"])
        crane = r.load_input.crane
        if crane is not None:
            names.extend(["Gc", "Qc"])
            for tc in crane.transverse_uls:
                names.append(tc.name)
            for tc in crane.transverse_sls:
                names.append(tc.name)
        return names

    # ── Load application ──

    def _apply_loads(self, model: FEModel3D, case_name: str) -> None:
        r = self._request
        bay = r.bay_spacing
        topo = r.topology

        rafter_ids = sorted(m.id for m in topo.members.values() if m.section_id == 2)
        column_ids = sorted(m.id for m in topo.members.values() if m.section_id == 1)

        if case_name == "G":
            self._apply_dead_loads(model, case_name, rafter_ids, column_ids, bay)
        elif case_name == "Q":
            self._apply_live_loads(model, case_name, rafter_ids, bay)
        elif case_name in ("E+", "E-"):
            self._apply_earthquake_loads(model, case_name)
        elif case_name == "Gc":
            self._apply_crane_dead(model, case_name)
        elif case_name == "Qc":
            self._apply_crane_live(model, case_name)
        else:
            # Wind case or crane transverse
            wc_match = next((w for w in r.load_input.wind_cases
                             if w.name == case_name), None)
            if wc_match:
                self._apply_wind_loads(model, case_name, wc_match,
                                       rafter_ids, column_ids, bay)
            else:
                self._apply_crane_transverse(model, case_name)

    def _apply_dead_loads(self, model, case_name, rafter_ids, column_ids, bay):
        r = self._request
        # Roof dead: global -Y on rafters
        if r.load_input.dead_load_roof > 0:
            w = -r.load_input.dead_load_roof * bay
            for mid in rafter_ids:
                model.add_member_dist_load(f"M{mid}", "FY", w, w, case=case_name)
        # Wall dead: global -Y on columns
        if r.load_input.dead_load_wall > 0:
            w = -r.load_input.dead_load_wall * bay
            for mid in column_ids:
                model.add_member_dist_load(f"M{mid}", "FY", w, w, case=case_name)
        # Self-weight
        if r.load_input.include_self_weight:
            for mid, mem in r.topology.members.items():
                sec = r.column_section if mem.section_id == 1 else r.rafter_section
                w_sw = -7850 * 9.81 / 1000 * sec.Ax_m  # kN/m
                model.add_member_dist_load(f"M{mid}", "FY", w_sw, w_sw,
                                           case=case_name)

    def _apply_live_loads(self, model, case_name, rafter_ids, bay):
        r = self._request
        if r.load_input.live_load_roof > 0:
            w = -r.load_input.live_load_roof * bay
            for mid in rafter_ids:
                model.add_member_dist_load(f"M{mid}", "FY", w, w, case=case_name)

    def _apply_wind_loads(self, model, case_name, wc, rafter_ids, column_ids, bay):
        r = self._request
        topo = r.topology

        # Classify left/right columns
        left_col_ids = []
        right_col_ids = []
        for mid in column_ids:
            mem = topo.members[mid]
            n1 = topo.nodes[mem.node_start]
            n2 = topo.nodes[mem.node_end]
            x = min(n1.x, n2.x)
            if x == 0.0:
                left_col_ids.append(mid)
            else:
                right_col_ids.append(mid)

        # Wall loads — global X
        if wc.left_wall != 0:
            w = wc.left_wall * bay  # +ve into surface = +X
            for mid in left_col_ids:
                model.add_member_dist_load(f"M{mid}", "FX", w, w, case=case_name)
        if wc.right_wall != 0:
            w = -wc.right_wall * bay  # +ve into surface = -X for right wall
            for mid in right_col_ids:
                model.add_member_dist_load(f"M{mid}", "FX", w, w, case=case_name)

        # Rafter loads — local y (normal to surface)
        if len(rafter_ids) >= 2:
            rafter_data = [
                (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
                (rafter_ids[1], wc.right_rafter_zones, wc.right_rafter),
            ]
        else:
            rafter_data = [
                (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
            ]

        for mid, zones, uniform in rafter_data:
            mem = topo.members[mid]
            n1 = topo.nodes[mem.node_start]
            n2 = topo.nodes[mem.node_end]
            mem_len = math.hypot(n2.x - n1.x, n2.y - n1.y)

            if wc.is_crosswind and zones:
                for zone in zones:
                    if zone.pressure != 0:
                        w = -zone.pressure * bay  # into surface = -local y
                        x1 = zone.start_pct / 100.0 * mem_len
                        x2 = zone.end_pct / 100.0 * mem_len
                        model.add_member_dist_load(
                            f"M{mid}", "Fy", w, w, x1, x2, case=case_name)
            elif uniform != 0:
                w = -uniform * bay
                model.add_member_dist_load(f"M{mid}", "Fy", w, w, case=case_name)

    def _apply_earthquake_loads(self, model, case_name):
        r = self._request
        from types import SimpleNamespace
        geom_ns = SimpleNamespace(
            span=r.span, eave_height=r.eave_height,
            ridge_height=r.eave_height + (r.span / 2.0) * math.tan(
                math.radians(r.roof_pitch)),
            bay_spacing=r.bay_spacing,
        )
        eq_result = calculate_earthquake_forces(
            geom_ns, r.load_input.dead_load_roof,
            r.load_input.dead_load_wall, r.load_input.earthquake,
        )
        F_uls = eq_result["F_node"]
        sign = 1.0 if case_name == "E+" else -1.0

        eave_nodes = sorted(r.topology.get_eave_nodes(), key=lambda n: n.x)
        for node in eave_nodes:
            model.add_node_load(f"N{node.id}", "FX", sign * F_uls,
                                case=case_name)

        # Crane seismic at bracket nodes
        crane = r.load_input.crane
        if crane is not None:
            gc_total = crane.dead_left + crane.dead_right
            qc_total = crane.live_left + crane.live_right
            crane_wt = gc_total + 0.6 * qc_total
            if crane_wt > 0:
                Cd_uls = eq_result["Cd_uls"]
                F_crane = Cd_uls * crane_wt / 2.0
                bracket_nodes = self._get_bracket_nodes()
                for node in bracket_nodes:
                    model.add_node_load(f"N{node.id}", "FX",
                                        sign * F_crane, case=case_name)

    def _apply_crane_dead(self, model, case_name):
        r = self._request
        crane = r.load_input.crane
        bracket_nodes = self._get_bracket_nodes()
        if len(bracket_nodes) >= 2:
            model.add_node_load(f"N{bracket_nodes[0].id}", "FY",
                                -crane.dead_left, case=case_name)
            model.add_node_load(f"N{bracket_nodes[-1].id}", "FY",
                                -crane.dead_right, case=case_name)

    def _apply_crane_live(self, model, case_name):
        r = self._request
        crane = r.load_input.crane
        bracket_nodes = self._get_bracket_nodes()
        if len(bracket_nodes) >= 2:
            model.add_node_load(f"N{bracket_nodes[0].id}", "FY",
                                -crane.live_left, case=case_name)
            model.add_node_load(f"N{bracket_nodes[-1].id}", "FY",
                                -crane.live_right, case=case_name)

    def _apply_crane_transverse(self, model, case_name):
        r = self._request
        crane = r.load_input.crane
        if crane is None:
            return
        bracket_nodes = self._get_bracket_nodes()
        if len(bracket_nodes) < 2:
            return
        # Find the matching transverse combo
        tc = None
        for t in crane.transverse_uls + crane.transverse_sls:
            if t.name == case_name:
                tc = t
                break
        if tc is None:
            return
        model.add_node_load(f"N{bracket_nodes[0].id}", "FX",
                            tc.left, case=case_name)
        model.add_node_load(f"N{bracket_nodes[-1].id}", "FX",
                            tc.right, case=case_name)

    def _get_bracket_nodes(self):
        """Find crane bracket nodes (same logic as SpaceGassWriter)."""
        r = self._request
        crane = r.load_input.crane
        if crane is None:
            return []
        h = crane.rail_height
        bracket_nodes = [
            n for n in r.topology.nodes.values()
            if abs(n.y - h) < 0.01 and n.y > 0
        ]
        return sorted(bracket_nodes, key=lambda n: n.x)

    # ── Result extraction ──

    def _extract_results(self, model: FEModel3D, case_name: str) -> CaseResult:
        r = self._request
        members = {}
        for mid, mem in r.topology.members.items():
            name = f"M{mid}"
            L = model.members[name].L()

            stations = []
            for i in range(NUM_STATIONS):
                x = i / (NUM_STATIONS - 1) * L
                pct = i / (NUM_STATIONS - 1) * 100
                # Negate moment and axial to match standard convention:
                # standard: +moment = sagging, +axial = tension
                # PyNite: +moment = hogging, +axial = compression
                axial = -model.members[name].axial(x, "LC")
                shear = model.members[name].shear("Fy", x, "LC")
                moment = -model.members[name].moment("Mz", x, "LC")
                stations.append(MemberStationResult(
                    position=x, position_pct=pct,
                    axial=axial, shear=shear, moment=moment,
                ))

            mr = MemberResult(member_id=mid, stations=stations)
            mr.max_moment = max(s.moment for s in stations)
            mr.min_moment = min(s.moment for s in stations)
            mr.max_shear = max(abs(s.shear) for s in stations)
            mr.max_axial = max(s.axial for s in stations)
            mr.min_axial = min(s.axial for s in stations)
            members[mid] = mr

        deflections = {}
        for nid in r.topology.nodes:
            name = f"N{nid}"
            node = model.nodes[name]
            dx = node.DX.get("LC", 0.0) * 1000  # m -> mm
            dy = node.DY.get("LC", 0.0) * 1000
            rz = node.RZ.get("LC", 0.0)
            deflections[nid] = NodeResult(nid, dx, dy, rz)

        reactions = {}
        for base_node in r.topology.get_base_nodes():
            name = f"N{base_node.id}"
            node = model.nodes[name]
            fx = node.RxnFX.get("LC", 0.0)
            fy = node.RxnFY.get("LC", 0.0)
            mz = node.RxnMZ.get("LC", 0.0)
            reactions[base_node.id] = ReactionResult(base_node.id, fx, fy, mz)

        return CaseResult(case_name, members, deflections, reactions)

    # ── Combinations ──

    def _get_combinations(self):
        """Get NZS 1170.0 combinations using existing build_combinations()."""
        r = self._request
        wind_names = [wc.name for wc in r.load_input.wind_cases]
        eq_names = ["E+", "E-"] if r.load_input.earthquake else None

        eq_sls_factor = 1.0
        if r.load_input.earthquake and hasattr(r.load_input.earthquake, 'R_sls'):
            from types import SimpleNamespace
            geom_ns = SimpleNamespace(
                span=r.span, eave_height=r.eave_height,
                ridge_height=r.eave_height + (r.span / 2.0) * math.tan(
                    math.radians(r.roof_pitch)),
                bay_spacing=r.bay_spacing,
            )
            eq_result = calculate_earthquake_forces(
                geom_ns, r.load_input.dead_load_roof,
                r.load_input.dead_load_wall, r.load_input.earthquake,
            )
            # SLS EQ factor = F_node_sls / F_node_uls (scales the ULS case)
            if eq_result["F_node"] > 0:
                eq_sls_factor = eq_result["F_node_sls"] / eq_result["F_node"]

        crane = r.load_input.crane
        crane_gc = "Gc" if crane else None
        crane_qc = "Qc" if crane else None
        crane_hc_uls = [tc.name for tc in crane.transverse_uls] if crane else None
        crane_hc_sls = [tc.name for tc in crane.transverse_sls] if crane else None

        uls, sls, groups = build_combinations(
            wind_case_names=wind_names,
            ws_factor=r.load_input.ws_factor,
            eq_case_names=eq_names,
            eq_sls_factor=eq_sls_factor,
            crane_gc_name=crane_gc,
            crane_qc_name=crane_qc,
            crane_hc_uls_names=crane_hc_uls,
            crane_hc_sls_names=crane_hc_sls,
        )

        from portal_frame.standards.combinations_nzs1170_0 import LoadCombination
        combos = []
        for i, (name, desc, factors) in enumerate(uls):
            combos.append(LoadCombination(name, desc, factors, 101 + i))
        for i, (name, desc, factors) in enumerate(sls):
            combos.append(LoadCombination(name, desc, factors, 201 + i))
        return combos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pynite_solver.py -v`
Expected: All 10 tests PASS (8 previous + 2 new beam tests)

- [ ] **Step 5: Run all existing tests to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All 119+ tests PASS

- [ ] **Step 6: Commit**

```bash
git add portal_frame/solvers/pynite_solver.py tests/test_pynite_solver.py
git commit -m "feat: implement PyNiteSolver with full load case support"
```

---

## Task 5: Portal Frame Validation Tests

**Files:**
- Test: `tests/test_pynite_solver.py`

- [ ] **Step 1: Write portal frame validation tests**

Append to `tests/test_pynite_solver.py`:

```python
def _make_portal_request(span=12.0, eave=4.5, pitch=5.0, bay=7.2,
                         w_dead=0.15, w_live=0.25, supports="pinned"):
    """Standard gable portal frame request."""
    from portal_frame.models.geometry import PortalFrameGeometry
    geom = PortalFrameGeometry(
        span=span, eave_height=eave, roof_pitch=pitch,
        roof_type="gable", bay_spacing=bay,
    )
    topology = geom.to_topology()
    sec = CFS_Section(
        name="63020S2", library="test", library_name="FS", group="C",
        Ax=689.0, J=518.0, Iy=4.36e6, Iz=0.627e6,
    )
    return AnalysisRequest(
        topology=topology, column_section=sec, rafter_section=sec,
        supports=SupportCondition(left_base=supports, right_base=supports),
        load_input=LoadInput(
            dead_load_roof=w_dead, dead_load_wall=0.0,
            live_load_roof=w_live, wind_cases=[],
            include_self_weight=False, bay_spacing=bay,
        ),
        span=span, eave_height=eave, roof_pitch=pitch, bay_spacing=bay,
    )


def test_portal_gravity_equilibrium():
    """Vertical reactions must equal total applied vertical load."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    g_case = solver.output.case_results["G"]
    total_fy = sum(r.fy for r in g_case.reactions.values())
    # Total load = w * bay * span (projected) = 0.15 * 7.2 * 12 = 12.96 kN
    expected = 0.15 * 7.2 * 12.0
    assert abs(total_fy - expected) < 0.5, f"Total Fy={total_fy}, expected={expected}"


def test_portal_symmetric_reactions():
    """Symmetric gable under gravity: left and right reactions should be equal."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    g_case = solver.output.case_results["G"]
    rxns = sorted(g_case.reactions.values(), key=lambda r: r.node_id)
    assert abs(rxns[0].fy - rxns[-1].fy) < 0.1


def test_portal_combinations_count():
    """Portal with gravity only: should have ULS-1 (1.35G) and ULS-2 (1.2G+1.5Q)."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    assert "ULS-1" in out.combo_results
    assert "ULS-2" in out.combo_results
    assert "SLS-1" in out.combo_results


def test_portal_uls1_is_135_times_dead():
    """ULS-1 = 1.35G: combo moment should be 1.35x dead-only moment."""
    req = _make_portal_request()
    solver = PyNiteSolver()
    solver.build_model(req)
    solver.solve()

    out = solver.output
    g_moment = out.case_results["G"].members[3].max_moment  # left rafter
    uls1_moment = out.combo_results["ULS-1"].members[3].max_moment
    assert abs(uls1_moment - 1.35 * g_moment) < 0.01
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_pynite_solver.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_pynite_solver.py
git commit -m "test: add portal frame validation tests for PyNite solver"
```

---

## Task 6: GUI — Refactor _generate() and Add Analyse Button

**Files:**
- Modify: `portal_frame/gui/app.py`
- Modify: `portal_frame/gui/theme.py`

- [ ] **Step 1: Add theme colors**

In `portal_frame/gui/theme.py`, add to the COLORS dict:

```python
"diagram_moment":    "#e06c75",
"diagram_shear":     "#c678dd",
"diagram_axial":     "#e5c07b",
"analyse_btn":       "#2d7d46",
"analyse_btn_hover": "#38a055",
```

- [ ] **Step 2: Extract `_build_analysis_request()` from `_generate()`**

In `portal_frame/gui/app.py`, extract lines 1570-1668 of `_generate()` into a new method `_build_analysis_request()` that returns an `AnalysisRequest`. Then simplify `_generate()` to call it:

```python
def _build_analysis_request(self) -> 'AnalysisRequest':
    """Collect all GUI inputs and build an AnalysisRequest."""
    col_name = self.col_section.get()
    raf_name = self.raf_section.get()

    if not col_name or col_name not in self.section_library:
        raise ValueError("Please select a valid column section.")
    if not raf_name or raf_name not in self.section_library:
        raise ValueError("Please select a valid rafter section.")

    col_sec = self.section_library[col_name]
    raf_sec = self.section_library[raf_name]

    geom = self._build_geometry()

    supports = SupportCondition(
        left_base=self.left_support.get(),
        right_base=self.right_support.get(),
    )

    wind_cases = self._synthesize_wind_cases()

    qu_val = self.qu.get()
    qs_val = self.qs.get()
    ws_factor = qs_val / qu_val if qu_val > 0 else 0.75

    earthquake = None
    if self.eq_enabled_var.get():
        t1_val = self.eq_T1_override.get()
        earthquake = EarthquakeInputs(
            Z=self.eq_Z.get(),
            soil_class=self.eq_soil.get(),
            R_uls=self.eq_R_uls.get(),
            R_sls=self.eq_R_sls.get(),
            mu=self.eq_mu.get(),
            Sp=self.eq_Sp.get(),
            Sp_sls=self.eq_Sp_sls.get(),
            near_fault=self.eq_near_fault.get(),
            extra_seismic_mass=self.eq_extra_mass.get(),
            T1_override=t1_val if t1_val > 0 else 0.0,
        )

    crane_inputs = None
    if self.crane_enabled_var.get():
        from portal_frame.models.crane import CraneTransverseCombo, CraneInputs
        hc_uls = []
        for _, name_var, left_var, right_var in self.crane_hc_uls_rows:
            try:
                hc_uls.append(CraneTransverseCombo(
                    name=name_var.get(),
                    left=float(left_var.get()),
                    right=float(right_var.get()),
                ))
            except ValueError:
                pass
        hc_sls = []
        for _, name_var, left_var, right_var in self.crane_hc_sls_rows:
            try:
                hc_sls.append(CraneTransverseCombo(
                    name=name_var.get(),
                    left=float(left_var.get()),
                    right=float(right_var.get()),
                ))
            except ValueError:
                pass
        crane_inputs = CraneInputs(
            rail_height=self.crane_rail_height.get(),
            dead_left=self.crane_gc_left.get(),
            dead_right=self.crane_gc_right.get(),
            live_left=self.crane_qc_left.get(),
            live_right=self.crane_qc_right.get(),
            transverse_uls=hc_uls,
            transverse_sls=hc_sls,
        )

    loads = LoadInput(
        dead_load_roof=self.dead_roof.get(),
        dead_load_wall=self.dead_wall.get(),
        live_load_roof=self.live_roof.get(),
        wind_cases=wind_cases,
        include_self_weight=self.self_weight_var.get(),
        ws_factor=ws_factor,
        earthquake=earthquake,
        crane=crane_inputs,
    )

    topology = geom.to_topology()

    return AnalysisRequest(
        topology=topology,
        column_section=col_sec,
        rafter_section=raf_sec,
        supports=supports,
        load_input=loads,
        span=geom.span,
        eave_height=geom.eave_height,
        roof_pitch=geom.roof_pitch,
        bay_spacing=geom.bay_spacing,
    )
```

Then `_generate()` becomes:

```python
def _generate(self):
    """Collect all inputs and generate the SpaceGass file via solver interface."""
    try:
        request = self._build_analysis_request()

        solver = SpaceGassSolver()
        solver.build_model(request)
        output = solver.generate_text()

        geom = self._build_geometry()
        default_name = f"portal_{geom.span:.0f}m_{geom.roof_pitch:.0f}deg.txt"
        filepath = filedialog.asksaveasfilename(
            title="Save SpaceGass File",
            defaultextension=".txt",
            filetypes=[("SpaceGass Text", "*.txt"), ("All Files", "*.*")],
            initialfile=default_name,
        )

        if filepath:
            with open(filepath, "w") as f:
                f.write(output)
            self.status_label.config(
                text=f"Saved: {os.path.basename(filepath)}",
                fg=COLORS["success"]
            )

    except Exception as e:
        messagebox.showerror("Generation Error", str(e))
        self.status_label.config(text=f"Error: {e}", fg=COLORS["error"])
```

- [ ] **Step 3: Add Analyse button in `_build_ui()`**

After the Generate button (around line 166), add:

```python
self.analyse_btn = tk.Button(
    btn_row, text="  ANALYSE (PyNite)  ", font=FONT_BOLD,
    fg=COLORS["fg_bright"], bg=COLORS["analyse_btn"],
    activebackground=COLORS["analyse_btn_hover"],
    activeforeground=COLORS["fg_bright"],
    relief="flat", cursor="hand2", padx=16, pady=8,
    command=self._analyse
)
self.analyse_btn.pack(side="left", padx=(8, 0))
```

- [ ] **Step 4: Add `_analyse()` method and state management**

Add to `__init__`:
```python
self._analysis_output = None
```

Add these methods:

```python
def _analyse(self):
    """Run PyNite analysis on current inputs."""
    try:
        request = self._build_analysis_request()

        from portal_frame.solvers.pynite_solver import PyNiteSolver
        solver = PyNiteSolver()
        solver.build_model(request)

        self.status_label.config(text="Analysing...", fg=COLORS["warning"])
        self.update_idletasks()

        solver.solve()

        self._analysis_output = solver.output
        self._update_results_panel()
        self._update_diagram_dropdowns()
        self._update_preview()

        self.status_label.config(
            text="Analysis complete", fg=COLORS["success"]
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        messagebox.showerror("Analysis Error", str(e))
        self.status_label.config(text=f"Analysis error: {e}", fg=COLORS["error"])

def _invalidate_analysis(self):
    """Clear stale analysis results when inputs change."""
    self._analysis_output = None
    if hasattr(self, '_results_text'):
        self._results_text.config(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.config(state="disabled")
    if hasattr(self, 'diagram_case_var'):
        self.diagram_case_var.set("(none)")
```

Call `self._invalidate_analysis()` at the end of every existing `_on_*_change` callback (e.g., `_on_frame_change`, `_update_preview`, etc.). Find all methods that are bound to input widget changes and add the call.

- [ ] **Step 5: Add results summary panel**

In `_build_ui()`, after `self.summary_label.pack(...)` (around line 153), add:

```python
self._results_text = tk.Text(
    bottom, font=FONT_MONO, fg=COLORS["fg"],
    bg=COLORS["bg_input"], height=8, width=60,
    relief="flat", state="disabled", wrap="none",
)
self._results_text.pack(fill="x", padx=8, pady=(0, 4))
```

Add the update method:

```python
def _update_results_panel(self):
    """Display envelope results in the summary text widget."""
    out = self._analysis_output
    if out is None:
        return

    lines = []
    if out.uls_envelope:
        lines.append("ULS Envelope:")
        for key, label in [("max_moment", "Max M+"), ("min_moment", "Max M-"),
                           ("max_shear", "Max V"), ("min_axial", "Max N(c)")]:
            if key in out.uls_envelope:
                e = out.uls_envelope[key]
                unit = "kNm" if "moment" in key else "kN"
                lines.append(f"  {label:8s} = {e.value:>8.1f} {unit}  "
                             f"({e.combo_name})  M{e.member_id} @ {e.position_pct:.0f}%")

    if out.sls_envelope:
        lines.append("SLS Envelope:")
        for key, label in [("max_dy", "Max dy"), ("max_dx", "Max dx")]:
            if key in out.sls_envelope:
                e = out.sls_envelope[key]
                lines.append(f"  {label:8s} = {e.value:>8.1f} mm   "
                             f"({e.combo_name})")

    self._results_text.config(state="normal")
    self._results_text.delete("1.0", "end")
    self._results_text.insert("1.0", "\n".join(lines))
    self._results_text.config(state="disabled")
```

- [ ] **Step 6: Add diagram dropdowns to load_bar**

In `_build_ui()`, after the load_case_combo (around line 138), add:

```python
tk.Label(load_bar, text="  Diagram:", font=FONT, fg=COLORS["fg"],
         bg=COLORS["bg_panel"]).pack(side="left", padx=(16, 4))

self.diagram_case_var = tk.StringVar(value="(none)")
self.diagram_case_combo = ttk.Combobox(
    load_bar, textvariable=self.diagram_case_var,
    values=["(none)"], state="readonly", font=FONT_MONO, width=22)
self.diagram_case_combo.pack(side="left", padx=4)
self.diagram_case_combo.bind("<<ComboboxSelected>>",
                              lambda _: self._update_preview())

self.diagram_type_var = tk.StringVar(value="M")
self.diagram_type_combo = ttk.Combobox(
    load_bar, textvariable=self.diagram_type_var,
    values=["M", "V", "N"], state="readonly", font=FONT_MONO, width=4)
self.diagram_type_combo.pack(side="left", padx=4)
self.diagram_type_combo.bind("<<ComboboxSelected>>",
                              lambda _: self._update_preview())
```

Add the dropdown population method:

```python
def _update_diagram_dropdowns(self):
    """Populate diagram case dropdown with analysis cases and combos."""
    out = self._analysis_output
    if out is None:
        self.diagram_case_combo["values"] = ["(none)"]
        return

    values = ["(none)"]
    values.extend(sorted(out.case_results.keys()))
    values.extend(sorted(out.combo_results.keys(),
                         key=lambda n: (0 if n.startswith("ULS") else 1,
                                        int(n.split("-")[1]) if "-" in n else 0)))
    self.diagram_case_combo["values"] = values
```

- [ ] **Step 7: Wire diagram data into `_update_preview()`**

In the existing `_update_preview()` method, before calling `self.preview.update_frame(...)`, build the diagram data:

```python
diagram = None
if (self._analysis_output is not None and
        hasattr(self, 'diagram_case_var') and
        self.diagram_case_var.get() != "(none)"):
    diagram = self._build_diagram_data()
```

Then pass it to `update_frame`:

```python
self.preview.update_frame(geom, supports, loads, diagram)
```

Add the helper:

```python
def _build_diagram_data(self):
    """Build diagram data dict for the preview canvas."""
    case_or_combo = self.diagram_case_var.get()
    dtype = self.diagram_type_var.get()
    out = self._analysis_output

    if case_or_combo in out.case_results:
        cr = out.case_results[case_or_combo]
    elif case_or_combo in out.combo_results:
        cr = out.combo_results[case_or_combo]
    else:
        return None

    attr = {"M": "moment", "V": "shear", "N": "axial"}[dtype]
    data = {}
    for mid, mr in cr.members.items():
        data[mid] = [(s.position_pct, getattr(s, attr)) for s in mr.stations]

    members_map = {}
    topo = list(out.case_results.values())[0] if out.case_results else None
    # Get topology from the request we built
    # Store topology reference when analyse runs
    return {"data": data, "type": dtype}
```

Note: The preview canvas needs the member-to-node mapping to draw diagrams. Store `self._analysis_topology` in `_analyse()`:

```python
# In _analyse(), after building request:
self._analysis_topology = request.topology
```

Then in `_build_diagram_data()`:

```python
members_map = {}
if self._analysis_topology:
    for mid, mem in self._analysis_topology.members.items():
        members_map[mid] = (mem.node_start, mem.node_end)
return {"data": data, "type": dtype, "members": members_map}
```

- [ ] **Step 8: Test GUI launches without errors**

Run: `python -m portal_frame.run_gui`
Expected: GUI opens with the new "ANALYSE (PyNite)" button visible next to "GENERATE SPACEGASS FILE". Diagram dropdowns visible in the load bar.

- [ ] **Step 9: Commit**

```bash
git add portal_frame/gui/app.py portal_frame/gui/theme.py
git commit -m "feat: add Analyse button, results panel, and diagram dropdowns"
```

---

## Task 7: Force Diagram Drawing on Preview Canvas

**Files:**
- Modify: `portal_frame/gui/preview.py`

- [ ] **Step 1: Add `draw_force_diagram()` to FramePreview**

Add to `portal_frame/gui/preview.py`:

```python
DIAGRAM_COLORS = {
    "M": "#e06c75",   # Red-pink for moment
    "V": "#c678dd",   # Purple for shear
    "N": "#e5c07b",   # Gold for axial
}
DIAGRAM_MAX_PX = 60  # Max diagram offset in pixels
```

Add the drawing method to the `FramePreview` class:

```python
def draw_force_diagram(self, diagram, ns):
    """Draw force diagram overlaid on frame members.

    Args:
        diagram: dict with keys "data", "type", "members"
            data: {member_id: [(position_pct, value), ...]}
            type: "M", "V", or "N"
            members: {member_id: (node_start, node_end)}
        ns: dict of node_id -> (screen_x, screen_y)
    """
    data = diagram["data"]
    dtype = diagram["type"]
    members_map = diagram.get("members", {})
    color = DIAGRAM_COLORS.get(dtype, "#e06c75")

    # Find max absolute value for scaling
    max_val = 0
    for stations in data.values():
        for _, val in stations:
            max_val = max(max_val, abs(val))
    if max_val < 1e-6:
        return

    for mid, stations in data.items():
        if mid not in members_map:
            continue
        n_start, n_end = members_map[mid]
        if n_start not in ns or n_end not in ns:
            continue

        sx, sy = ns[n_start]
        ex, ey = ns[n_end]

        # Member direction and normal
        dx = ex - sx
        dy = ey - sy
        length = math.hypot(dx, dy)
        if length < 1:
            continue

        # Normal: perpendicular to member (rotated 90 CCW)
        nx = -dy / length
        ny = dx / length

        # Build polygon points: baseline (member) + diagram curve
        baseline_pts = []
        diagram_pts = []
        for pct, val in stations:
            t = pct / 100.0
            px = sx + dx * t
            py = sy + dy * t
            baseline_pts.append((px, py))
            offset = (val / max_val) * DIAGRAM_MAX_PX
            diagram_pts.append((px + nx * offset, py + ny * offset))

        # Draw filled polygon
        poly_pts = []
        for pt in baseline_pts:
            poly_pts.extend(pt)
        for pt in reversed(diagram_pts):
            poly_pts.extend(pt)

        if len(poly_pts) >= 6:
            self.create_polygon(
                *poly_pts, fill="", outline=color, width=2,
                tags=("diagram",))
            # Fill with stipple for visual distinction
            self.create_polygon(
                *poly_pts, fill=color, outline="", stipple="gray25",
                tags=("diagram",))

        # Draw diagram curve line on top
        curve_coords = []
        for pt in diagram_pts:
            curve_coords.extend(pt)
        if len(curve_coords) >= 4:
            self.create_line(*curve_coords, fill=color, width=2,
                             tags=("diagram",))

        # Label peak value
        peak_val = max(stations, key=lambda s: abs(s[1]))
        if abs(peak_val[1]) > 1e-6:
            t = peak_val[0] / 100.0
            px = sx + dx * t
            py = sy + dy * t
            offset = (peak_val[1] / max_val) * DIAGRAM_MAX_PX
            lx = px + nx * (offset + 12 * (1 if offset >= 0 else -1))
            ly = py + ny * (offset + 12 * (1 if offset >= 0 else -1))
            unit = {"M": "kNm", "V": "kN", "N": "kN"}[dtype]
            self._create_label(
                lx, ly, f"{peak_val[1]:.1f} {unit}",
                f"diag_{mid}_{dtype}", fill=color)
```

- [ ] **Step 2: Update `update_frame()` to accept diagram parameter**

Modify the `update_frame()` method signature:

```python
def update_frame(self, geom: dict, supports: tuple, loads: dict = None, diagram: dict = None):
```

Add before `self._resolve_overlaps()` (right before the end of the method):

```python
# Force diagram overlay
if diagram and diagram.get("data"):
    self.draw_force_diagram(diagram, ns)
```

Add diagram legend entry (after the existing load legend around line 390):

```python
if diagram and diagram.get("data"):
    dtype = diagram.get("type", "M")
    dcolor = DIAGRAM_COLORS.get(dtype, "#e06c75")
    ly += 16
    self.create_line(lx, ly, lx + 20, ly, fill=dcolor, width=2)
    label_map = {"M": "Moment", "V": "Shear", "N": "Axial"}
    self.create_text(lx + 25, ly, text=label_map.get(dtype, dtype),
                     fill=COLORS["fg_dim"], font=FONT_SMALL, anchor="w")
```

- [ ] **Step 3: Test visually**

Run: `python -m portal_frame.run_gui`
Expected: After clicking "ANALYSE (PyNite)", select a case/combo from the Diagram dropdown and M/V/N type. Force diagrams should appear overlaid on the frame, with peak values labeled. Colors should be distinct from existing load arrows.

- [ ] **Step 4: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "feat: add force diagram overlay on preview canvas"
```

---

## Task 8: Integration Validation

**Files:**
- Test: `tests/test_pynite_solver.py`

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All existing tests PASS + all new PyNite tests PASS

- [ ] **Step 2: Run GUI end-to-end test**

Run: `python -m portal_frame.run_gui`

Manual verification checklist:
1. Open app, set geometry (12m span, 4.5m eave, 5 deg pitch, 7.2m bay)
2. Click "GENERATE SPACEGASS FILE" — should produce valid .txt file (unchanged behavior)
3. Click "ANALYSE (PyNite)" — status should show "Analysing..." then "Analysis complete"
4. Results panel should show ULS/SLS envelope values
5. Select "G" from Diagram dropdown, "M" from type → moment diagram appears on rafters
6. Select "ULS-1" → scaled moment diagram (1.35x dead)
7. Switch to "V" → shear diagram appears
8. Switch to "N" → axial diagram appears
9. Change geometry inputs → results panel clears, diagram resets to "(none)"
10. Re-analyse → new results appear

- [ ] **Step 3: Commit final state**

```bash
git add -A
git commit -m "feat: complete PyNite solver integration with GUI and force diagrams"
```

---

## Verification Summary

| Check | Command | Expected |
|-------|---------|----------|
| All tests pass | `python -m pytest tests/ -v` | All PASS |
| PyNite import works | `python -c "from Pynite import FEModel3D; print('OK')"` | OK |
| GUI launches | `python -m portal_frame.run_gui` | Window opens with Analyse button |
| SpaceGass export unchanged | Generate file, diff against previous output | Identical |
| Analysis produces results | Click Analyse, check results panel | Envelope values shown |
| Force diagrams render | Select case + diagram type | Diagrams visible on canvas |
| Diagram types work | Switch M/V/N | Different diagrams, different colors |
| State invalidation | Change inputs after analysis | Results clear, diagram resets |
