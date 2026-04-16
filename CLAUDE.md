# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A SpaceGass 2D portal frame generator for Formsteel (NZ structural engineering). It reads custom cold-formed steel (CFS) sections from SpaceGass XML library files and outputs SpaceGass v14 text files with NZ load combinations per AS/NZS 1170.0:2002 (including Amendments 1-5).

## Commands

```bash
# Run the GUI
python -m portal_frame.run_gui
python portal_frame_gui.py              # backward-compatible wrapper

# CLI usage
python -m portal_frame.cli --list-sections          # Show available CFS sections
python -m portal_frame.cli --config my_frame.json   # Generate from config
python -m portal_frame.cli --example-config          # Write example JSON config
python -m portal_frame.cli                           # Run with built-in defaults
python portal_frame_generator.py ...                 # backward-compatible wrapper

# Run tests
python -m pytest tests/ -v
```

## Architecture

Domain-driven Python package with separated concerns:

```
portal_frame/
  models/          Pure dataclasses — no I/O, no standards logic
    geometry.py      Node, Member, FrameTopology, PortalFrameGeometry
    sections.py      CFS_Section
    loads.py         RafterZoneLoad, WindCase, EarthquakeInputs, CraneInputs, LoadInput
    crane.py         CraneTransverseCombo, CraneInputs
    supports.py      SupportCondition
  standards/       NZ code calculations — pure functions, no I/O
    utils.py         lerp() shared interpolation
    wind_nzs1170_2.py           Wind pressure tables & 8-case generation
    combinations_nzs1170_0.py   ULS/SLS load combinations + LoadCombination dataclass
    earthquake_nzs1170_5.py     NZS 1170.5:2004 equivalent static method
    cfs_span_table.py           Formsteel span table loader (CFS_Span_Table.xlsx)
    cfs_check.py                AS/NZS 4600 ULS member capacity checks
    serviceability.py           SLS apex deflection + eave drift checks
  io/              File I/O — reading and writing
    section_library.py   XML library parsing (find, parse, load, get)
    spacegass_writer.py  SpaceGass v14 text output (SpaceGassWriter class)
    config.py            JSON config parsing (FrameConfig dataclass) + example generation
  solvers/         Engine-agnostic analysis interface
    base.py          AnalysisSolver ABC, AnalysisRequest, AnalysisResults
    spacegass.py     SpaceGassSolver (export-only, analysis done externally)
    pynite_solver.py PyNiteSolver — in-app FEM, per-station M/V/N/dy_local/dx_local
  analysis/        Post-processing and combinations (solver-agnostic)
    results.py       MemberStationResult, MemberResult, CaseResult, AnalysisOutput, MemberDesignCheck, SLSCheck
    combinations.py  combine_case_results() (linear superposition), compute_envelopes, compute_envelope_curves (ULS, SLS, SLS Wind Only)
  gui/             Tkinter desktop GUI
    theme.py         COLORS, FONT constants
    widgets.py       LabeledEntry, LabeledCombo
    dialogs.py       WindSurfacePanel (surface-based Cp,e table with Walls/Roof tabs)
    preview.py       FramePreview canvas (2D rendering with loads)
    app.py           PortalFrameApp main window, tab orchestration, generate flow
    tabs/            (empty — tabs currently built inline in app.py)
  cli.py           CLI entry point
  run_gui.py       GUI entry point
tests/             213 unit tests (standards, models, output, crane, PyNite solver, CFS checks incl. shear, serviceability)
docs/
  CFS_Span_Table.xlsx  Formsteel span table (P kN, Mx kNm, Vy kN sheets; 1m–25m for P/Mx, no L for Vy)
```

**Backward-compatible wrappers** (root level):
- `portal_frame_generator.py` — re-exports all backend classes/functions, wraps `PortalFrameGenerator` around `SpaceGassWriter`
- `portal_frame_gui.py` — imports and launches `PortalFrameApp`

### Key Design Patterns

- **FrameTopology** is the universal intermediate representation. Everything downstream (writers, solvers, preview) consumes `FrameTopology`, never `PortalFrameGeometry` directly. A future 3D builder just produces a `FrameTopology`.
- **AnalysisSolver ABC** with `AnalysisRequest`/`AnalysisResults`. SpaceGass is one solver (export-only). Future integrated solvers (PyNite, OpenSees) implement the same interface.
- **Library name normalization** (`LIBRARY_SG14_SECTION_FS.slsc` -> `"FS"`) happens at parse time in `io/section_library.py`, stored in `CFS_Section.library_name`.
- **LoadCombination** dataclass lives in `standards/combinations_nzs1170_0.py` (output of standards logic, not raw input data).

### Adding New Features

| Feature | Where to add |
|---------|-------------|
| New load type (earthquake) | `standards/earthquake_nzs1170_5.py` + `models/loads.py` (if new inputs) |
| New GUI tab | Add name to `tab_names` in `gui/app.py:_build_ui()`, write `_build_X_tab()` method |
| New solver | `solvers/new_solver.py` implementing `AnalysisSolver` |
| New output format | `io/new_writer.py` (e.g., DXF, IFC) |
| New section type | `models/sections.py` |
| New capacity check | Add lookup in `standards/cfs_span_table.py`, add check in `standards/cfs_check.py` |
| New SLS metric | Add check function in `standards/serviceability.py`, wire in `app.py::_run_design_checks()` |
| New span table section | Add entry to `LIBRARY_TO_SPANTABLE` dict in `cfs_span_table.py` |

## Critical Domain Knowledge

### SpaceGass Text File Format
- Version line must be `SPACE GASS Text File - Version 1420`
- SECTIONS must reference the library by name (e.g., `1,"63020S2","FS"`) — NOT inline property definitions. This is required for 3D section rendering in SpaceGass.
- MEMBFORCES column order: `Case,Mem,Sl,Ax,Un,St,Fi,Xs,Xf,Ys,Yf,Zs,Zf` — values grouped by axis direction (start,finish pairs), NOT by position.
- UNITS line requires ALL 11 categories. ACC unit must be `g's` (with apostrophe), NOT `g` or `m/sec^2`. See spacegass.com/manual for valid values.
- LOAD CASE GROUPS section groups ULS (101+) and SLS (201+) with sub-groups (ULS-GQ, ULS-Wind, ULS-EQ, SLS-Wind, SLS-EQ, SLS-Wind Only)

### Section Libraries
- Primary library: `C:\ProgramData\SPACE GASS\Custom Libraries\LIBRARY_SG14_SECTION_FS.slsc` (Formsteel "FS" library)
- XML format with Groups > Group > Sections > Section > SectionProperties
- Library name for SECTIONS block is extracted from filename at parse time in `io/section_library.py`
- Section properties in XML are in mm units; converted to m for SpaceGass output.

### NZ Loading Standard
- AS/NZS 1170.0:2002 Clause 4.2.2 (ULS) and Clause 4.3 (SLS)
- Table 4.1 roof factors: psi_s=0.7, psi_l=0.0, psi_c=0.0
- ULS combos: 1.35G, 1.2G+1.5Q, 1.2G+Wu, 0.9G+Wu (per wind case)
- SLS combos: G+0.7Q, G, G+Ws (per wind case)
- Companion Q drops out of wind combinations because psi_c=0.0 for roofs
- **Combo naming**: ULS-1, ULS-2, ... (sequential); SLS-1, SLS-2, ... (sequential)
- **Combo numbering in output**: ULS combos start at case 101; SLS combos start at case 201

### Wind Loads Convention
- Input pressures are net (kPa), sign convention: +ve = pressure into surface
- Wall loads applied as global-X forces; rafter loads applied as local-Y (normal to surface)

### Wind Pressure Implementation (NZS 1170.2:2021)
- Cfig = Cp,e * Kc,e - Cp,i * Kc,i (Eq 5.2(1) & 5.2(2)); Wu = Cfig * qu
- 8 wind cases: W1-W4 crosswind (theta=0/180 x uplift/downward), W5-W8 transverse (theta=90/270 x uplift/downward)
- Crosswind (W1-W4): roof zones from Table 5.3(A) vary ACROSS the span — must split at ridge into L/R rafter zones with remapped 0-100% percentages
- Transverse (W5-W8): roof zones vary along BUILDING LENGTH (ridge direction), NOT across the span — 2D frame sees UNIFORM roof pressure (use worst-case zone for conservative envelope)
- Leeward Cp,e is NOT hardcoded — looked up from Table 5.2(B) by d/b ratio and roof pitch
- Cp,i differs by envelope: +0.2 (max uplift), -0.3 (max downward) per Table 5.1(A)
- Key functions in `standards/wind_nzs1170_2.py`: `leeward_cpe_lookup()`, `roof_cpe_zones()`, `_split_zones_to_rafters()`, `generate_standard_wind_cases()`

## Platform Notes
- Windows environment; use `python` not `python3`
- Console output must avoid Unicode superscript characters (mm2 not mm², mm4 not mm⁴) due to cp1252 encoding
- tkinter does not support alpha hex colors (e.g., `#ffffffaa` is invalid; use 6-digit hex only)
- tkinter `pack()` does not accept `sticky` — that's a `grid()` option. Don't mix layout manager kwargs.
- SpaceGass can be automated via CLI with the `-s` flag for scripting.

## Roof Types & Geometry
- **Gable roof**: Dual pitch inputs (alpha1, alpha2). Apex X derived from pitches: `span * tan(a2) / (tan(a1) + tan(a2))`. 5 nodes, 4 members.
- **Mono-roof**: Single pitch, no ridge node. 4 nodes, 3 members.
- Pitch warnings: <3 deg (ponding risk), >30 deg (unusually steep)
- `roof_pitch_2` field on `PortalFrameGeometry`; legacy `apex_position_pct` still supported for backward compat

## Earthquake Loading (NZS 1170.5:2004)

**Status: IMPLEMENTED** — equivalent static method, forces lumped at knee nodes.

### Implementation
- `standards/earthquake_nzs1170_5.py`: `NZ_HAZARD_FACTORS` (19 locations), `_CH_TABLE` (5 soil classes), `spectral_shape_factor()`, `calculate_earthquake_forces()`
- `_CH_TABLE` uses NON-BRACKETED values from Table 3.1 (equivalent static method). Bracketed values are for modal response spectrum only. Classes B-E plateau at the non-bracketed value for T=0 to ~0.3-0.6s.
- `standards/combinations_nzs1170_0.py`: `eq_case_names` param on `build_combinations()` adds `1.0G + E+/E-` (ULS) and `G + E(s)` (SLS)
- `io/spacegass_writer.py`: NODELOADS section with `Case,Node,FX,FY,FZ,MX,MY,MZ,LoadCategory` (9 columns, verified in SpaceGass v14.25)
- GUI Earthquake tab: enable/disable, location dropdown (auto-fills Z), soil class, ductility presets, live calculated values
- Seismic weight (Wt): top-half tributary only (full roof SDL + half wall SDL + half column SW + full rafter SW + extra mass)

### Key NZS 1170.5:2004 formulas
```
V = Cd(T1) * Wt
Cd(T1) = Ch(T1) * Z * R * N(T,D) * Sp / k_mu
k_mu: if T1 >= 0.7s -> k_mu = mu; if T1 < 0.7s -> k_mu = (mu-1)*T1/0.7 + 1
T1 = 1.25 * 0.085 * h_n^0.75  (steel MRF, Clause 4.1.2.1)
Floor: Cd(T1) >= max(0.03, Z*R*0.02)
EQ ULS combo factor on G = 1.0 (not 1.2); Q drops out (psi_c=0 for roofs)
SLS: Cd_sls = Ch(T1) * Z * R_sls * N * Sp_sls / k_mu_sls  (Sp_sls=0.7 per Cl 4.4.4, k_mu_sls=1.0)
Forces split equally to eave nodes: F_node = V/2
```

### SpaceGass Node Loads Format
- Keyword: `NODELOADS` (NOT `JOINTLOADS`)
- 9 columns: `Case,Node,FX,FY,FZ,MX,MY,MZ,LoadCategory`
- LoadCategory is an integer (e.g. `1`), NOT empty

## CFS Member Design Check (AS/NZS 4600)

**Status: IMPLEMENTED** — ULS bending, axial, shear, combined via Formsteel span table lookup.

### Implementation
- `standards/cfs_span_table.py`: loads `docs/CFS_Span_Table.xlsx` (3 sheets: P kN, Mx kNm, Vy kN), provides `phi_Nc(library_name, L_m)`, `phi_Mbx(library_name, L_m)` (linear interpolation between integer-meter columns, clamped 1m–25m), and `phi_Vy(library_name)` (single value per section, no L dependence)
- `standards/cfs_check.py`: `check_member()` (single member), `check_all_members()` (full topology), `phi_Nt()` (tension)
- `analysis/results.py`: `MemberDesignCheck` dataclass on `AnalysisOutput.design_checks`
- GUI: Frame tab inputs for `col_Le` and `raf_Le` (effective lengths), results panel shows per-member utilisation with FAIL/PASS/NO_DATA colouring, HUD `[ULS]` toggle button with colour-coded member overlay and draggable boxed midpoint labels showing `util\ncombo_name`

### Section Name Mapping
SpaceGass library names differ from span table names. Static mapping in `LIBRARY_TO_SPANTABLE`:
```
63020N -> G550 63020N        63020S1 -> G550 63020NS1
63020S2 -> G550 63020NS2     50020 -> G550 50020
270115 -> G550 270115        650180295S2 -> Superspan 650x180x2.95 2S
```
The 63020 family uses convention: N = nested base, S1/S2 = stiffener variant. Sections without entries (100x1, 27075, etc.) return `None` -> `NO_DATA` status.

### Key Formulas
```
Tension:    phi_Nt = 0.85 * kt * An * fu  (kt=1, An=Ag, fu=550 MPa for G550)
Axial util: max(|N*c|/phi_Nc, N*t/phi_Nt)
Bending:    M*/phi_Mbx
Shear:      V*/phi_Vy
Combined:   util_axial + util_bending <= 1.0  (simple linear interaction)
```
PASS if (combined <= 1.0) AND (shear <= 1.0). Shear is checked independently from combined — a member failing shear alone still triggers FAIL. Moment amplification (Cl 3.5.1 alpha_n) and combined moment+shear interaction (Cl 3.3.5) intentionally omitted — the current conservative separate checks are adequate for typical NZ portal frames.

### Canvas Overlay
HUD `[ULS]` button toggles per-member colour overlay (green <= 0.85, amber <= 1.0, red > 1.0, grey = NO_DATA). Member stroke colour reflects `max(util_combined, util_shear)` so shear-dominated failures show red. Each member gets a draggable boxed label showing `util\nULS-X` where the displayed util is whichever dominates (`Σ=...` when combined leads, `V/φV=...` when shear leads), and ULS-X is the corresponding controlling combo. Mutually exclusive with SLS overlay.

## Serviceability Checks (SLS)

**Status: IMPLEMENTED** — apex vertical deflection + eave horizontal drift, each split into wind and earthquake categories.

### Implementation
- `standards/serviceability.py`: `check_apex_deflection()` and `check_eave_drift()` — pure functions, span derived from topology via `_topology_span_m()` to avoid input-staleness
- `analysis/results.py`: `SLSCheck` dataclass on `AnalysisOutput.sls_checks`
- `analysis/combinations.py`: `compute_envelope_curves()` now also builds `sls_wind_only_envelope_curves` filtered by description substring `"wind only"`
- GUI: Frame tab inputs for apex limits (span/X for wind and EQ) and drift limits (h/X for wind and EQ), results panel shows grouped rows, HUD `[SLS]` toggle button with rafter colour overlay and draggable apex + drift badges

### SLS Metrics
- **Apex vertical deflection** (`apex_dy`): worst |dy| at the highest-y topology node, reference = span, symbol = L
- **Eave horizontal drift** (`drift`): worst |dx| across all eave nodes (nodes connected to both a column and a rafter), reference = eave height, symbol = h
- Default limits: apex L/180 (wind), L/360 (EQ); drift h/150 (wind), h/300 (EQ)

### Combo Classification
SLS combos classified by description substring: `"E+"` or `"E-"` in description -> earthquake, everything else -> wind (includes G, G+0.7Q, G+W*(s), W*(s) wind only)

### Canvas Badges
Each badge shows ALL categories for its metric (both wind and eq rows visible). Badge text shows the **actual deformation ratio** the frame reached (e.g. `L/293`), NOT the design limit. Colour reflects worst-util pass/fail. Both apex and drift badges are draggable (text + background rect move as a unit via `_label_partners` mechanism).

### SLS Wind Only Envelope
Separate envelope group (`sls_wind_only_envelope_curves`) containing only the `W*(s) wind only` SLS combos (no dead/live). Available in the diagram dropdown as "SLS Wind Only Envelope".

### Dataclass field names (SLSCheck)
- `metric`: `"apex_dy"` | `"drift"`
- `deflection_mm`: signed value at the measured node (mm)
- `limit_mm`: absolute limit = reference_length * 1000 / ratio
- `ratio`: user's design limit (the X in L/X or h/X)
- `actual_ratio`: what the frame actually deformed to (reference_length / |deflection|, capped at 9999)
- `reference_symbol`: `"L"` for span, `"h"` for column height

## HUD Controls

Canvas-drawn heads-up display in top-right corner. Layout (left to right):
```
[DIM] [SLS] [ULS] [Normalize] [-] M [+]
```
- **DIM**: toggle dimension annotations (span, eave, ridge, pitches) — bright when ON, dim when OFF
- **SLS**: toggle serviceability overlay on rafters — green when active, mutually exclusive with ULS
- **ULS**: toggle member capacity overlay — green when active, mutually exclusive with SLS
- **Normalize**: reset all diagram amplitude scales to 1.0
- **[-] M [+]**: decrease/increase the active diagram type's amplitude scale

Overlay state is single-slot (`_overlay_mode: "off" | "uls" | "sls"`), giving mutual exclusion for free.

HUD buttons support optional tooltips (hover text drawn as canvas items, chained via `add="+"` on Enter/Leave handlers). All annotation labels (dimensions, ULS capacity, SLS badges) are draggable — offsets persist across redraws and overlay toggles.

## Testing
- Unit tests: `python -m pytest tests/ -v` (213 tests covering standards, models, output, crane, PyNite solver, CFS checks incl. shear, serviceability)
- GUI launch test: `python -m portal_frame.run_gui &`, wait a few seconds, then `tasklist | grep python`
- SpaceGass output files must be opened in SpaceGass v14.25 to verify format correctness.
- Output verification: generate with both old wrapper and new package, `diff` must show identical output.

## Design Spec
- Full architecture design: `docs/superpowers/specs/2026-04-01-architecture-restructure-design.md`

## Crane Loading

**Status: IMPLEMENTED** — gantry crane with bracket nodes on columns.

### Implementation
- `models/crane.py`: `CraneTransverseCombo`, `CraneInputs` (dead/live/transverse per bracket)
- Topology: `_insert_crane_brackets()` splits columns at rail height, adding 2 nodes + 2 members
- Writer: Gc, Qc, Hc cases as NODELOADS at bracket nodes. Wind wall loads applied to ALL column segments (not just one)
- Combinations: with/without crane sets (crane not always at this frame)
- Crane seismic: F_crane = Cd × (Gc + 0.6×Qc) / 2 per bracket node (NOT at eave nodes)
- GUI: Crane tab with enable/disable, rail height, Gc/Qc per bracket, dynamic transverse ULS/SLS rows

## PyNite Solver (In-App FEM)

**Status: IMPLEMENTED** — in-app analysis for M/V/N/δ diagrams + ULS/SLS envelopes. Separate from SpaceGass export (unchanged).

### Package
- Pip package: `PyNiteFEA` (v2.4.1). Import as `from Pynite import FEModel3D`. Pulls scipy (~117 MB), numpy (~33 MB), matplotlib (~29 MB, unused — exclude in build.spec to save ~25 MB).
- 2D portal frame uses 3D solver with out-of-plane DOFs restrained: `model.def_support(nid, False, False, True, True, True, False)` on all nodes.

### Sign conventions (stored in MemberStationResult)
- `axial`: +ve = tension (negated from PyNite raw)
- `moment`: +ve = sagging (negated from PyNite raw)
- `dy_local`: +ve = sagging/into-frame-interior (negated from PyNite raw)
- `dx_local`: **NOT negated** (raw PyNite, used only by δ renderer for rotation back to global)

### PyNite local coordinate system (empirically verified)
- Horizontal/tilted beam: local-x along member i→j; local-y is 90° CCW from local-x in world XY plane.
- Vertical column (base→top): local-x = +Y global, local-y = **−X global**, local-z = +Z global (out-of-plane).
- Vertical member Iy/Iz ordering matters: `add_section(name, A, Iy, Iz, J)` — for 2D frame bending, Iz is the in-plane strong axis.

### Deflection diagram rotation formula (LOAD-BEARING — do not refactor casually)
In `preview.py::_draw_deflection_diagram()`, global displacement is reconstructed from member-local `(dx_local, dy_local)` via:
- `Δscreen_x = α × (dx_local × mdx − dy_local × mdy) / L`
- `Δscreen_y = α × (dx_local × mdy + dy_local × mdx) / L`

This guarantees curves meet at shared nodes (apex, knee, crane brackets). Any sign/argument change here breaks continuity.

### Crane bracket gotcha
- `_insert_crane_brackets()` adds bracket nodes with IDs outside the hardcoded 1-5 range (e.g. 6, 7 for gable) and replaces column members with sub-members referencing those IDs.
- `update_frame()` builds its local `ns` dict from hardcoded keys — to render diagrams on column sub-members, `_build_diagram_data()` must pass `topology_nodes` dict and `update_frame()` merges them via `tx()`.

### combinations.py field-tuple pattern
Add new per-station fields to `_STATION_FIELDS`, per-node to `_NODE_FIELDS`, per-reaction to `_REACTION_FIELDS` at the top of `combinations.py`. Both `combine_case_results()` (linear superposition) and `_build_envelope_pair()` (max/min walk) iterate these tuples via getattr/setattr — adding a field in one place propagates to both.

### Dataclass field-name gotchas (hit when writing ad-hoc diagnostic scripts)
- `PortalFrameGeometry`: `roof_pitch`, `roof_pitch_2` (NOT `_deg` suffix — degrees implied)
- `RafterZoneLoad`: `start_pct, end_pct, pressure` (single segment, no `segments=` list)
- `LoadInput`: `dead_load_roof, dead_load_wall, live_load_roof` (NOT `dead_load=`/`live_load=`)
- `CraneInputs`: `rail_height, dead_left, dead_right, live_left, live_right` (NOT `enabled=`/`left_Gc=`)
- `AnalysisRequest`: `span`, `eave_height`, `roof_pitch`, `bay_spacing` as separate fields (NOT nested `geometry=`)
- `io.section_library`: use `load_all_sections() -> dict` (NOT `load_library()`)

## Packaging
- `pyinstaller build.spec --clean -y` builds single .exe to `dist/PortalFrameGenerator.exe`
- Section library: tries SpaceGass install path first, falls back to bundled copy via `sys._MEIPASS`
- CFS span table: `docs/CFS_Span_Table.xlsx` bundled into `docs/` inside the exe (same `sys._MEIPASS` fallback pattern)

## External References
- NZ loading standards: `C:\Users\CadWork4\Formsteel\Formsteel Engineers - Documents\Simon\_3.0 NZS & REFERENCE DOCUMENTS\STANDARDS - Loading ASNZS1170\`
- Most current: AS/NZS 1170.0-2002 (Amdt 1-5), 1170.1, 1170.2-2021, 1170.3-2003 (Amdt 1-2), 1170.5-2004 (Amdt 1)
