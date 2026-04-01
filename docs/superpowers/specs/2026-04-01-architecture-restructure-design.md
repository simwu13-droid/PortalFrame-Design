# Architecture Restructure Design Spec

## Context

The portal frame generator is currently 2 monolith files (~2,564 lines total):
- `portal_frame_generator.py` (1,098 lines) — backend engine mixing domain logic, NZ standards calculations, SpaceGass formatting, and CLI
- `portal_frame_gui.py` (1,466 lines) — tkinter GUI with hard-coded 2D topology

**Problems this solves:**
1. SpaceGass output formatting is intertwined with load case business logic in a 235-line `generate()` method
2. Hard-coded 5-node/4-member topology throughout both files makes 3D impossible without rewriting everything
3. No analysis engine abstraction — cannot swap SpaceGass for an integrated solver
4. No test infrastructure — standards calculations are untestable without importing the entire generator
5. Adding features (earthquake, 3D, optimization) requires modifying both monolith files
6. No dependency management or project packaging

**Future goals driving this restructure:**
- Integrated open-source structural analysis (solver TBD: PyNite, OpenSeesPy, or other)
- 3D frame modeling
- Structural optimization within the app
- Earthquake loading (NZS 1170.5:2004) — already planned
- Keep SpaceGass export as one output option alongside integrated solving

---

## Package Structure

```
portal_frame/
  __init__.py
  models/
    __init__.py
    geometry.py         # Node, Member, FrameTopology, PortalFrameGeometry
    sections.py         # CFS_Section (+ future material types)
    loads.py            # LoadCase, WindCase, RafterZoneLoad, LoadCombination, LoadInput, EarthquakeInputs
    supports.py         # SupportCondition
  standards/
    __init__.py
    utils.py            # _lerp(), shared interpolation utilities
    wind_nzs1170_2.py   # All wind pressure calculations
    combinations_nzs1170_0.py  # ULS/SLS load combination builder
    earthquake_nzs1170_5.py    # Placeholder for planned earthquake feature
  io/
    __init__.py
    section_library.py  # XML library parsing (find, parse, load, get)
    spacegass_writer.py # SpaceGass v14 text format output
    config.py           # JSON config read/write, example generation
  solvers/
    __init__.py
    base.py             # AnalysisSolver ABC, AnalysisResults dataclass
    spacegass.py        # SpaceGass solver (export-only, no integrated analysis)
  gui/
    __init__.py
    app.py              # Main window, tab orchestration, generate flow
    preview.py          # FramePreview canvas (topology-driven rendering)
    widgets.py          # LabeledEntry, LabeledCombo
    dialogs.py          # CrosswindZoneDialog, WindCaseTable
    tabs/
      __init__.py
      frame_tab.py      # Geometry, sections, supports, dead/live loads
      wind_tab.py       # Wind parameters, auto-generate, case table
      combos_tab.py     # Combination reference display
  cli.py                # CLI entry point (--list-sections, --config, --example-config)
  run_gui.py            # GUI entry point
pyproject.toml          # Project metadata, dependencies, entry points
```

---

## Module Designs

### 1. `models/geometry.py` — Frame Topology Abstraction

**Classes:**

```python
@dataclass
class Node:
    id: int
    x: float
    y: float
    z: float = 0.0  # 3D-ready, defaults to 0 for 2D

@dataclass
class Member:
    id: int
    node_start: int  # Node ID
    node_end: int    # Node ID
    section_id: int  # Maps to section assignment

@dataclass
class FrameTopology:
    nodes: dict[int, Node]
    members: dict[int, Member]

    def get_node(self, node_id: int) -> Node: ...
    def get_members_at_node(self, node_id: int) -> list[Member]: ...
    def get_base_nodes(self) -> list[Node]: ...
    def get_eave_nodes(self) -> list[Node]: ...

@dataclass
class PortalFrameGeometry:
    """Current portal frame parameters — generates a 5-node/4-member topology."""
    span: float
    eave_height: float
    roof_pitch: float
    bay_spacing: float

    def to_topology(self) -> FrameTopology:
        """Builds the standard 2D portal frame:
        Node 1 (0,0) → Node 2 (0,eave) → Node 3 (span/2,ridge) → Node 4 (span,eave) → Node 5 (span,0)
        Members: 1(col), 2(raft-L), 3(raft-R), 4(col)
        """
        ...
```

**Key design decision:** `FrameTopology` is the universal intermediate representation. Everything downstream (writers, solvers, preview) consumes `FrameTopology`, never `PortalFrameGeometry` directly. This means a future `3DFrameBuilder` or `MultiSpanGeometry` just needs to produce a `FrameTopology`.

### 2. `models/sections.py` — Section Properties

```python
@dataclass
class CFS_Section:
    name: str
    library: str
    library_name: str   # Normalized display name (prefix stripped at parse time)
    area: float         # mm²
    Iyy: float          # mm⁴
    Izz: float          # mm⁴
    J: float            # mm⁴

    @property
    def area_m2(self) -> float: ...
    @property
    def Iyy_m4(self) -> float: ...
    @property
    def Izz_m4(self) -> float: ...
    @property
    def J_m4(self) -> float: ...
```

**Change from current:** `library_name` (the normalized display name like `"FS"`) is computed at parse time in `io/section_library.py`, not at output time in the writer. This removes the prefix-stripping logic from the generator.

### 3. `models/loads.py` — Load Cases (Input Data Only)

```python
@dataclass
class RafterZoneLoad:
    start_pct: float
    end_pct: float
    pressure: float  # kPa

@dataclass
class WindCase:
    name: str
    description: str
    direction: str        # "crosswind" or "transverse"
    envelope: str         # "uplift" or "downward"
    is_crosswind: bool
    left_wall: float      # kPa
    right_wall: float     # kPa
    left_rafter: float    # kPa (uniform, transverse)
    right_rafter: float   # kPa (uniform, transverse)
    left_rafter_zones: list[RafterZoneLoad]   # zone-based (crosswind)
    right_rafter_zones: list[RafterZoneLoad]  # zone-based (crosswind)

# NOTE: LoadCombination lives in standards/combinations_nzs1170_0.py
# (it's an output of standards logic, not raw input data)

@dataclass
class EarthquakeInputs:
    """Placeholder for NZS 1170.5:2004 — matches planned feature spec."""
    Z: float
    soil_class: str
    R_uls: float
    R_sls: float
    mu: float
    Sp: float
    near_fault: float
    extra_seismic_mass: float

@dataclass
class LoadInput:
    dead_load_roof: float
    dead_load_wall: float
    live_load_roof: float
    include_self_weight: bool
    wind_cases: list[WindCase]
    ws_factor: float = 1.0
    earthquake: EarthquakeInputs | None = None
```

### 4. `standards/wind_nzs1170_2.py` — Wind Pressure Calculations

Moves all wind functions from `portal_frame_generator.py`:
- `leeward_cpe_lookup(d_over_b, pitch)` — Table 5.2(B)
- `cfig(cpe, kce, cpi, kci)` — Eq 5.2(1) & 5.2(2)
- `roof_cpe_zones(h_over_d, envelope)` — Table 5.3(A)
- `_compute_zone_loads(...)` — Zone-based rafter pressures
- `_split_zones_to_rafters(...)` — Ridge split
- `_mirror_zones(...)` — Symmetry
- `generate_standard_wind_cases(span, eave, pitch, depth, cp_inputs)` — 8 standard cases
- `WindCpInputs` dataclass
- Table data: `_TABLE_53A_HD_LOW`, `_TABLE_53A_HD_HIGH`

**No changes to calculation logic.** Pure relocation.

### 5. `standards/combinations_nzs1170_0.py` — Load Combinations

`LoadCombination` dataclass lives here (output of standards logic, not raw input):

```python
@dataclass
class LoadCombination:
    """Replaces raw tuples from build_combinations()."""
    name: str             # e.g., "ULS-1"
    description: str      # e.g., "1.35G"
    factors: dict[str, float]  # e.g., {"G": 1.35}
    case_number: int      # Output case number (101+, 201+)

def build_combinations(
    wind_case_names: list[str],
    eq_case_names: list[str] | None = None,
    ws_factor: float = 1.0,
) -> list[LoadCombination]:
    """AS/NZS 1170.0:2002 Clause 4.2.2 (ULS) and 4.3 (SLS).
    Returns LoadCombination objects instead of raw tuples.
    ULS cases start at 101, SLS at 201.
    """
```

### 6. `standards/utils.py` — Shared Utilities

```python
def lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """Linear interpolation. Used by wind and earthquake standards."""
```

### 7. `io/section_library.py` — XML Library Parsing

Moves from `portal_frame_generator.py`:
- `find_library_file(name)` — search known paths
- `parse_section_library(path)` — XML parsing, **now normalizes `library_name` at parse time**
- `load_all_sections()` — merge all libraries
- `get_section(name, library)` — lookup with error handling

**Key change:** Library name normalization (`LIBRARY_SG14_SECTION_FS` → `FS`) happens here, not in the writer.

### 8. `io/spacegass_writer.py` — SpaceGass Output

```python
class SpaceGassWriter:
    """Generates SpaceGass v14 text format from domain models."""

    def __init__(self, topology: FrameTopology,
                 column_section: CFS_Section, rafter_section: CFS_Section,
                 supports: SupportCondition, load_input: LoadInput,
                 combinations: list[LoadCombination]):
        ...

    def write(self) -> str:
        """Returns complete SpaceGass text file content."""
        parts = [
            self._header(),
            self._nodes(),
            self._members(),
            self._sections(),
            self._restraints(),
            self._load_cases(),
            self._combinations(),
            self._titles(),
        ]
        return "\n".join(parts)

    def _header(self) -> str: ...
    def _nodes(self) -> str: ...
    def _members(self) -> str: ...
    def _sections(self) -> str: ...
    def _restraints(self) -> str: ...
    def _load_cases(self) -> str: ...     # Dead, live, wind member forces
    def _combinations(self) -> str: ...
    def _titles(self) -> str: ...
```

**Key change:** The 235-line `generate()` is broken into ~8 focused methods, each 20-40 lines. Business logic (load factor calculations) is already done by `standards/` before the writer sees it.

### 9. `io/config.py` — Configuration

```python
@dataclass
class FrameConfig:
    """Validated configuration — replaces raw dict access."""
    geometry: PortalFrameGeometry
    column_section_name: str
    rafter_section_name: str
    supports: SupportCondition
    loads: LoadInput
    # Constructed from JSON with validation; no more silent .get() defaults

    @classmethod
    def from_dict(cls, cfg: dict) -> "FrameConfig":
        """Parse and validate a JSON config dict."""
        ...
```

- `build_from_config(cfg: dict) -> str` — parses JSON into `FrameConfig`, then builds models and generates output
- `create_example_config() -> FrameConfig` — returns a validated example config

### 10. `solvers/base.py` — Analysis Engine Interface

```python
from abc import ABC, abstractmethod

@dataclass
class AnalysisRequest:
    """Single input object bundling everything a solver needs."""
    topology: FrameTopology
    column_section: CFS_Section
    rafter_section: CFS_Section
    supports: SupportCondition
    load_input: LoadInput
    combinations: list[LoadCombination]

@dataclass
class AnalysisResults:
    """Results from structural analysis. Empty for export-only solvers."""
    reactions: dict[int, tuple[float, ...]] | None = None
    member_forces: dict[int, list] | None = None
    deflections: dict[int, tuple[float, ...]] | None = None
    solved: bool = False

class AnalysisSolver(ABC):
    @abstractmethod
    def build_model(self, request: AnalysisRequest) -> None:
        """Prepare the analysis model from a request."""

    @abstractmethod
    def solve(self) -> AnalysisResults:
        """Run analysis. Returns results (or empty results for export-only solvers)."""

    @abstractmethod
    def export(self, path: str) -> None:
        """Export model to file."""
```

### 11. `solvers/spacegass.py` — SpaceGass as a "Solver"

```python
class SpaceGassSolver(AnalysisSolver):
    """Wraps SpaceGass export as a solver interface.
    solve() is a no-op — SpaceGass does actual analysis externally.
    """

    def build_model(self, request: AnalysisRequest):
        self._request = request

    def solve(self) -> AnalysisResults:
        return AnalysisResults(solved=False)  # External solver

    def export(self, path: str) -> None:
        r = self._request
        writer = SpaceGassWriter(r.topology, r.column_section,
                                  r.rafter_section, r.supports,
                                  r.load_input, r.combinations)
        content = writer.write()
        with open(path, "w") as f:
            f.write(content)
```

### 12. GUI Modules

**`gui/app.py`** — Main application
- `PortalFrameApp` class, slimmed down
- Tab registration: `self.tabs = {"Frame": FrameTab, "Wind": WindTab, "Combos": CombosTab}`
- Each tab is a class with `build(parent)` and `collect() -> dict` methods
- Generate flow: collect from tabs → build models → call solver → save

**`gui/tabs/frame_tab.py`** — Frame geometry, sections, supports, gravity loads
**`gui/tabs/wind_tab.py`** — Wind parameters, auto-generate, case table
**`gui/tabs/combos_tab.py`** — Read-only combination reference

**`gui/preview.py`** — `FramePreview` refactored to render from `FrameTopology`
- Draws nodes and members from topology, not hard-coded coordinates
- Load visualization stays similar but uses topology node lookups

**`gui/widgets.py`** — `LabeledEntry`, `LabeledCombo` (unchanged)
**`gui/dialogs.py`** — `CrosswindZoneDialog`, `WindCaseTable` (relocated)

### 13. Entry Points

**`cli.py`** — CLI with argparse (current `main()` logic)
**`run_gui.py`** — `PortalFrameApp().mainloop()`

**`pyproject.toml`** — Project metadata:
```toml
[project]
name = "portal-frame"
version = "0.1.0"
requires-python = ">=3.10"

[project.scripts]
portal-frame = "portal_frame.cli:main"
portal-frame-gui = "portal_frame.run_gui:main"
```

---

## Data Flow (Current vs. Refactored)

### Current
```
JSON config → build_from_config() → PortalFrameGenerator.generate() → SpaceGass text
                                     (mixed: load calcs + formatting)
```

### Refactored
```
JSON config
  → io/config.py (parse)
  → models/ (FrameGeometry, LoadInput, etc.)
  → PortalFrameGeometry.to_topology() → FrameTopology
  → standards/ (wind calcs, combinations)
  → solvers/spacegass.py (or future solver)
    → io/spacegass_writer.py (formatting only)
  → SpaceGass text file

GUI collects inputs → same model pipeline → solver.export()
```

---

## Migration Strategy

**Behavioral equivalence is mandatory.** The refactored code must produce byte-identical SpaceGass output for the same inputs. This is the primary acceptance criterion.

1. Extract models first (no behavior change)
2. Move standards calculations (no behavior change)
3. Extract SpaceGass writer from `generate()` (output must match exactly)
4. Wire up solver interface
5. Restructure GUI last (most visible, highest risk)
6. Add `pyproject.toml` and entry points
7. Keep `portal_frame_generator.py` and `portal_frame_gui.py` as thin wrappers during transition (import from new package, delegate), remove once stable

---

## Verification Plan

1. **Output comparison:** Generate a SpaceGass file before and after refactor with identical inputs. `diff` the two files — must be identical.
2. **GUI launch test:** `python -m portal_frame.run_gui` must launch the GUI, all tabs functional.
3. **CLI test:** `python -m portal_frame.cli --list-sections` and `--example-config` must produce same output.
4. **SpaceGass validation:** Open generated file in SpaceGass v14.25 — must load without errors.
5. **Unit test foundation:** Add basic tests for `standards/` functions (e.g., `cfig()`, `build_combinations()`, `leeward_cpe_lookup()`) to prove the separation works.

---

## What This Enables (Future)

- **Earthquake loading:** Add `standards/earthquake_nzs1170_5.py` + `gui/tabs/earthquake_tab.py` — no changes to existing modules
- **3D modeling:** New `FrameTopology` builder + 3D preview widget — solver interface unchanged
- **Integrated solver:** Add `solvers/pynite.py` implementing `AnalysisSolver` — GUI just adds a solver dropdown
- **Optimization:** Loop over geometry/section parameters → call `solver.solve()` → compare `AnalysisResults` — all within the existing interface
- **New output formats:** Add writers in `io/` (e.g., `dxf_writer.py`, `ifc_writer.py`) without touching any other module
