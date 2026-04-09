# PyNite Solver Integration Design

## Context

The portal frame generator currently exports SpaceGass v14 text files for external analysis. Engineers must open SpaceGass to see member forces, reactions, and deflections. Adding PyNite as an in-app solver enables instant analysis results, force diagram visualization, and lays the foundation for a future section optimization module that needs to call the solver in a tight loop.

SpaceGass export remains fully functional and unchanged. PyNite adds capability; it replaces nothing.

## Requirements

1. **Separate buttons**: "Generate SpaceGass File" (unchanged) and "Analyse (PyNite)" (new)
2. **Individual unfactored load cases** solved separately (G, Q, W1..W8, E+, E-, Gc, Qc, Hc...)
3. **Combination results** computed by applying NZS 1170.0 factors to per-case results in Python
4. **Results summary table** showing ULS and SLS envelope (max M, V, N, deflections with controlling combo)
5. **Force diagrams** (M, V, N) overlaid on existing FramePreview canvas with case/combo and type dropdowns
6. **All existing functionality preserved** -- no regressions to SpaceGass export, GUI, or tests

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `portal_frame/analysis/__init__.py` | Empty package init |
| `portal_frame/analysis/results.py` | Result dataclasses |
| `portal_frame/analysis/combinations.py` | Linear combination and envelope computation |
| `portal_frame/solvers/pynite_solver.py` | `PyNiteSolver` implementing `AnalysisSolver` ABC |
| `tests/test_pynite_solver.py` | Solver unit tests |

### Modified Files

| File | Changes |
|------|---------|
| `pyproject.toml` | Add `PyNiteFEA` dependency |
| `portal_frame/gui/app.py` | Analyse button, results panel, diagram dropdowns, refactor `_generate()` to share input collection |
| `portal_frame/gui/preview.py` | `draw_force_diagram()` method, `update_frame()` accepts optional `diagram` param |
| `portal_frame/gui/theme.py` | Add diagram colors |
| `build.spec` | Add `PyNite` to `hiddenimports` if needed for PyInstaller |

### Unchanged Files

| File | Why |
|------|-----|
| `portal_frame/solvers/base.py` | ABC stays as-is; `AnalysisResults` backward compatible |
| `portal_frame/solvers/spacegass.py` | Export-only path unchanged |
| `portal_frame/io/spacegass_writer.py` | No modifications |
| All existing tests | Must continue passing |

---

## 1. Result Dataclasses (`portal_frame/analysis/results.py`)

```python
@dataclass
class MemberStationResult:
    position: float       # Distance from member start (m)
    position_pct: float   # 0-100%
    axial: float          # kN, +ve = tension
    shear: float          # kN
    moment: float         # kNm

@dataclass
class MemberResult:
    member_id: int
    stations: list[MemberStationResult]  # 21 stations per member
    max_moment: float = 0.0
    min_moment: float = 0.0
    max_shear: float = 0.0    # absolute max
    max_axial: float = 0.0
    min_axial: float = 0.0

@dataclass
class NodeResult:
    node_id: int
    dx: float = 0.0   # mm (horizontal)
    dy: float = 0.0   # mm (vertical)
    rz: float = 0.0   # rad

@dataclass
class ReactionResult:
    node_id: int
    fx: float = 0.0   # kN
    fy: float = 0.0   # kN
    mz: float = 0.0   # kNm

@dataclass
class CaseResult:
    case_name: str
    members: dict[int, MemberResult]
    deflections: dict[int, NodeResult]
    reactions: dict[int, ReactionResult]

@dataclass
class EnvelopeEntry:
    value: float
    combo_name: str
    member_id: int = 0
    position_pct: float = 0.0

@dataclass
class AnalysisOutput:
    case_results: dict[str, CaseResult]    # "G", "Q", "W1", etc.
    combo_results: dict[str, CaseResult]   # "ULS-1", "SLS-2", etc.
    uls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
    sls_envelope: dict[str, EnvelopeEntry] = field(default_factory=dict)
```

Envelope keys: `max_moment`, `min_moment`, `max_shear`, `max_axial`, `min_axial`, `max_dx`, `max_dy`, `max_reaction_fy`.

---

## 2. PyNiteSolver (`portal_frame/solvers/pynite_solver.py`)

Implements `AnalysisSolver` ABC. Key design decisions:

### Unit System

PyNite uses consistent units. With coordinates in metres:
- E = 200,000 MPa = 200,000,000 kN/m^2
- G = 80,000 MPa = 80,000,000 kN/m^2
- Section properties: use existing `CFS_Section._m` properties (m^2, m^4)
- Forces: kN, distributed loads: kN/m
- Deflections from PyNite in metres, convert to mm for display

### 2D Constraint in 3D Solver

PyNite is natively 3D (6 DOF/node). To constrain to 2D (XY plane, Rz rotation):
- Every node gets out-of-plane restraints: `Dz=True, Rx=True, Ry=True`
- Base nodes additionally get: `Dx=True, Dy=True` (pinned adds `Rz=False`, fixed adds `Rz=True`)

```python
# Non-support nodes:
model.def_support(name, False, False, True, True, True, False)

# Pinned base:
model.def_support(name, True, True, True, True, True, False)

# Fixed base:
model.def_support(name, True, True, True, True, True, True)
```

### Per-Case Solving Strategy

Build a fresh `FEModel3D` for each load case. Each model gets one load combo `"LC"` with factor 1.0 on the single case. This avoids PyNite's internal combination system and gives us full control over NZS 1170.0 combination logic.

Why fresh model per case: PyNite doesn't cleanly support extracting per-case results when multiple cases are loaded simultaneously. Building per-case is cleaner and for 5-node frames the overhead is negligible (<0.1s per case).

### Case Map

Replicates SpaceGassWriter's case numbering logic:
```
G=1, Q=2, W1=3, W2=4, ..., E+=N, E-=N+1, Gc=N+2, Qc=N+3, Hc1=N+4, ...
```

### Load Application

| Case | Load Type | PyNite API |
|------|-----------|------------|
| G (dead) | Distributed on rafters/columns (global Y) + self-weight | `add_member_dist_load(name, "FY", w, w, 0, None, case)` |
| Q (live) | Distributed on rafters (global Y) | `add_member_dist_load(name, "FY", w, w, 0, None, case)` |
| Wind | Columns: global X. Rafters: local y (normal). Zones for crosswind. | Columns: `"FX"`. Rafters: `"Fy"` (lowercase = local). Zoned: partial `x1, x2` |
| E+/E- | Point forces at eave nodes (+ crane brackets if crane) | `add_node_load(name, "FX", force, case)` |
| Gc/Qc | Vertical point loads at bracket nodes | `add_node_load(name, "FY", -force, case)` |
| Hc | Horizontal point loads at bracket nodes | `add_node_load(name, "FX", force, case)` |

Self-weight: computed manually as `w_sw = -7850 * 9.81 / 1000 * A_m2` kN/m per member, applied as global Y distributed load in the G case.

Wind sign conventions: left wall `+ve = +X`, right wall `+ve = -X` (into surface). Rafter wind `+ve into surface = -ve local y` (PyNite local y points outward from surface for typical member orientations). Must verify with test case.

### Result Extraction

At 21 evenly-spaced stations per member:
```python
axial  = model.Members[name].axial(x, "LC")
shear  = model.Members[name].shear("Fy", x, "LC")
moment = model.Members[name].moment("Mz", x, "LC")
```

Nodal deflections:
```python
dx = model.Nodes[name].DX["LC"] * 1000  # m -> mm
dy = model.Nodes[name].DY["LC"] * 1000
rz = model.Nodes[name].RZ["LC"]
```

Reactions at base nodes:
```python
fx = model.Nodes[name].RxnFX.get("LC", 0)
fy = model.Nodes[name].RxnFY.get("LC", 0)
mz = model.Nodes[name].RxnMZ.get("LC", 0)
```

### Public Interface

```python
class PyNiteSolver(AnalysisSolver):
    def build_model(self, request: AnalysisRequest) -> None
    def solve(self) -> AnalysisResults      # Also populates self.output
    def export(self, path: str) -> None     # No-op

    @property
    def output(self) -> AnalysisOutput | None
```

`solve()` returns a populated `AnalysisResults` (for ABC compatibility) and stores the full `AnalysisOutput` on `self.output` for GUI consumption.

---

## 3. Combination Post-Processing (`portal_frame/analysis/combinations.py`)

### Linear Combination

```python
def combine_case_results(
    case_results: dict[str, CaseResult],
    factors: dict[str, float],
    combo_name: str,
) -> CaseResult:
```

For each member station: `value = sum(factor_i * case_i.stations[j].value)` across axial, shear, moment. Same for nodal deflections and reactions.

Reuses the existing `build_combinations()` from `standards/combinations_nzs1170_0.py` to get the `LoadCombination` list with factors.

### Envelope Computation

```python
def compute_envelopes(output: AnalysisOutput) -> None:
```

Iterates all combo results, tracks max/min for each envelope key with the controlling combo name, member ID, and position. Populates `output.uls_envelope` and `output.sls_envelope` in-place.

---

## 4. GUI Changes (`portal_frame/gui/app.py`)

### Refactor: Extract `_build_analysis_request()`

Lines 1570-1668 of `_generate()` (input collection, topology building, request assembly) extracted to a shared method:

```python
def _build_analysis_request(self) -> AnalysisRequest:
    # Validates sections, builds geometry, collects loads, returns request
```

Both `_generate()` and `_analyse()` call this. `_generate()` becomes:
```python
def _generate(self):
    request = self._build_analysis_request()
    solver = SpaceGassSolver()
    solver.build_model(request)
    output = solver.generate_text()
    # ... file save dialog ...
```

### Analyse Button

Placed in `btn_row` after the Generate button:
```python
self.analyse_btn = tk.Button(
    btn_row, text="  ANALYSE (PyNite)  ", font=FONT_BOLD,
    fg=COLORS["fg_bright"], bg=COLORS["analyse_btn"],
    ...
    command=self._analyse
)
```

Green color (`#2d7d46`) to distinguish from blue Generate button.

### `_analyse()` Method

```python
def _analyse(self):
    request = self._build_analysis_request()
    solver = PyNiteSolver()
    solver.build_model(request)
    solver.solve()
    self._analysis_output = solver.output
    self._update_results_panel()
    self._update_diagram_dropdowns()
    self._update_preview()
```

### Results Summary Panel

A read-only `tk.Text` widget below the summary label in the bottom frame:

```
ULS Envelope:
  Max M+  =  42.3 kNm  (ULS-5: 1.2G+W3)  M2 @ 48%
  Max M-  = -31.1 kNm  (ULS-8: 0.9G+W4)  M3 @ 52%
  Max V   =  18.7 kN   (ULS-5)             M1 @ 0%
  Max N   =  -8.2 kN   (ULS-1: 1.35G)     M1 @ 0%
SLS Envelope:
  Max dy  =  12.3 mm   (SLS-4: G+Ws3)     N4
  Max dx  =   5.1 mm   (SLS-3: G+Ws1)     N2
```

### Diagram Controls

Added to `load_bar` (row 0 of right panel, above preview):

```
[Show Load Case: (none) v]    [Diagram: (none) v] [Type: M v]
```

- **Diagram case dropdown**: populated with all individual cases + all combos after analysis runs
- **Diagram type dropdown**: M, V, N (fixed values)
- Selecting "(none)" hides the diagram overlay
- Both dropdowns trigger `_update_preview()`

### State Invalidation

`_invalidate_analysis()` called from all `_on_*_change` callbacks:
- Sets `self._analysis_output = None`
- Clears results panel text
- Resets diagram dropdown to "(none)"

---

## 5. Force Diagram Drawing (`portal_frame/gui/preview.py`)

### New Method: `draw_force_diagram()`

```python
def draw_force_diagram(self, diagram_data, diagram_type, members_map, ns, scale):
```

Parameters:
- `diagram_data`: `dict[int, list[tuple[float, float]]]` -- member_id -> [(position_pct, value), ...]
- `diagram_type`: "M", "V", or "N"
- `members_map`: `dict[int, tuple[int, int]]` -- member_id -> (node_start, node_end)
- `ns`: transformed node screen coordinates
- `scale`: geometry scale factor

Drawing logic:
1. Find max absolute value across all members for scaling
2. `DIAGRAM_MAX_PX = 60` -- max perpendicular offset in pixels
3. For each member:
   - Get start/end screen coordinates from `ns` via `members_map`
   - Compute member direction vector and perpendicular (normal)
   - At each station, compute perpendicular offset = `(value / max_val) * DIAGRAM_MAX_PX`
   - Draw filled polygon: member baseline + offset curve
   - Label peak value on the diagram

### Color Scheme

Distinct from existing load arrows (yellow `#dcdcaa`) and frame members (teal/blue):
- Moment: `#e06c75` (red-pink)
- Shear: `#c678dd` (purple)
- Axial: `#e5c07b` (gold)

### Convention

- Moment diagram drawn on tension side (positive moment = diagram below for horizontal beam, perpendicular outward for inclined members)
- Shear and axial drawn perpendicular to member, positive = outward from frame
- Fill with semi-transparent stipple for visual clarity against the frame

### Integration with `update_frame()`

Add optional `diagram` parameter:
```python
def update_frame(self, geom, supports, loads=None, diagram=None):
    # ... existing drawing ...
    if diagram:
        self.draw_force_diagram(
            diagram["data"], diagram["type"],
            diagram["members"], ns, scale
        )
    self._resolve_overlaps()
```

---

## 6. Theme Additions (`portal_frame/gui/theme.py`)

```python
"diagram_moment":    "#e06c75",
"diagram_shear":     "#c678dd",
"diagram_axial":     "#e5c07b",
"analyse_btn":       "#2d7d46",
"analyse_btn_hover": "#38a055",
```

---

## 7. Testing Strategy

### Unit Tests (`tests/test_pynite_solver.py`)

**Validation cases with known analytical solutions:**

1. **Simply supported beam, UDL**: M_max = wL^2/8 at midspan, V_max = wL/2 at supports
2. **Cantilever, point load at tip**: M_max = PL at fixed end, V = P constant
3. **Symmetric pinned portal frame, gravity**: vertical reactions = total load / 2

**Integration tests:**

4. **Full portal frame with wind**: verify reactions sum to applied load in each direction
5. **Combination results**: verify ULS-1 (1.35G) = 1.35 * G-only results
6. **Equilibrium check**: sum of reactions = sum of applied loads for each case

### Existing Test Preservation

Run `python -m pytest tests/ -v` -- all 119 existing tests must pass unchanged.

---

## 8. Key Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| PyNite local axis conventions differ from SpaceGass | Validation test: symmetric gable under gravity. If moment signs differ, adjust sign mapping in `_apply_wind_loads()` |
| 2D constraint via Dz/Rx/Ry restraints causes numerical issues | Test with simple beam first. Fallback: use spring supports with very large stiffness |
| PyNite API changes across versions | Pin `PyNiteFEA>=0.0.93` in pyproject.toml. Verify API against installed source |
| Performance with 12+ load cases | Each solve <0.1s for 5-node frames. Total <2s. No threading needed |
| Force diagram visual clarity | Fixed 60px max height, distinct colors from loads/frame, stipple fill |

---

## 9. Implementation Phases

**Phase 1 -- Core solver (no GUI):**
1. Add PyNiteFEA dependency
2. Create `analysis/results.py` dataclasses
3. Create `analysis/combinations.py` post-processing
4. Create `solvers/pynite_solver.py` with full implementation
5. Write `tests/test_pynite_solver.py` and validate

**Phase 2 -- GUI integration:**
6. Refactor `_generate()` to extract `_build_analysis_request()`
7. Add Analyse button and `_analyse()` method
8. Add results summary panel
9. Add state invalidation

**Phase 3 -- Force diagrams:**
10. Add diagram dropdowns to load_bar
11. Implement `draw_force_diagram()` in preview.py
12. Wire up `_build_diagram_data()` in app.py
13. Add theme colors

**Phase 4 -- Validation:**
14. Full portal frame analysis, compare against SpaceGass
15. Test all load case types (G, Q, W, E, Crane)
16. Verify combination results against manual calculation
