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
    loads.py         RafterZoneLoad, WindCase, EarthquakeInputs, LoadInput
    supports.py      SupportCondition
  standards/       NZ code calculations — pure functions, no I/O
    utils.py         lerp() shared interpolation
    wind_nzs1170_2.py           Wind pressure tables & 8-case generation
    combinations_nzs1170_0.py   ULS/SLS load combinations + LoadCombination dataclass
    earthquake_nzs1170_5.py     Placeholder (NZS 1170.5:2004)
  io/              File I/O — reading and writing
    section_library.py   XML library parsing (find, parse, load, get)
    spacegass_writer.py  SpaceGass v14 text output (SpaceGassWriter class)
    config.py            JSON config parsing (FrameConfig dataclass) + example generation
  solvers/         Engine-agnostic analysis interface
    base.py          AnalysisSolver ABC, AnalysisRequest, AnalysisResults
    spacegass.py     SpaceGassSolver (export-only, analysis done externally)
  gui/             Tkinter desktop GUI
    theme.py         COLORS, FONT constants
    widgets.py       LabeledEntry, LabeledCombo
    dialogs.py       CrosswindZoneDialog, WindCaseTable
    preview.py       FramePreview canvas (2D rendering with loads)
    app.py           PortalFrameApp main window, tab orchestration, generate flow
    tabs/            (empty — tabs currently built inline in app.py)
  cli.py           CLI entry point
  run_gui.py       GUI entry point
tests/             28 unit tests (standards, models, output integration)
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

## Critical Domain Knowledge

### SpaceGass Text File Format
- Version line must be `SPACE GASS Text File - Version 1420`
- SECTIONS must reference the library by name (e.g., `1,"63020S2","FS"`) — NOT inline property definitions. This is required for 3D section rendering in SpaceGass.
- MEMBFORCES column order: `Case,Mem,Sl,Ax,Un,St,Fi,Xs,Xf,Ys,Yf,Zs,Zf` — values grouped by axis direction (start,finish pairs), NOT by position.

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

## Next Feature: Earthquake Loading (NZS 1170.5:2004)

**Status: PLANNED — not yet implemented.**
Full plan at: `C:\Users\CadWork4\.claude\plans\indexed-questing-lake.md`

### What needs to be built

**Step 0 — JOINTLOADS format verification (do this first)**
- Generate a minimal SpaceGass test file with a JOINTLOADS section and have the user open it in SpaceGass v14.25 to confirm the format is accepted
- Suspected format: `Case,Joint,FX,FY,FZ,MX,MY,MZ` (e.g. `3,2,10.0,0.0,0.0,0.0,0.0,0.0`)

**Step 1 — Backend data & calculations** (`standards/earthquake_nzs1170_5.py`):
- Add `NZ_HAZARD_FACTORS` dict (19 NZ locations -> Z values)
- Add `_CH_TABLE` spectral shape factor table (5 soil classes, Table 3.1)
- Add `spectral_shape_factor(T, soil_class)` using `standards/utils.py:lerp()`
- `EarthquakeInputs` dataclass already exists in `models/loads.py`
- Add `calculate_earthquake_forces(geom, loads, eq)` -> returns T1, Ch, k_mu, Cd_uls, Cd_sls, Wt, V_uls, V_sls, F_node
  - Wt = (SDL_roof * span + SDL_wall * 2 * eave) * bay + extra_seismic_mass (kN)

**Step 2 — Backend integration**:
- `standards/combinations_nzs1170_0.py`: add `eq_case_names` param to `build_combinations()`; add EQ ULS combos `1.0G + E+/E-` and EQ SLS combos `G + E+(s)/E-(s)`
- `io/spacegass_writer.py`: add E+/E- case numbering (after wind cases), write JOINTLOADS section (point loads at eave nodes), pass EQ cases to build_combinations, add EQ titles

**Step 3 — GUI Earthquake tab** (`gui/app.py`):
- Add `"Earthquake"` to `tab_names` list in `_build_ui()`
- Add `_build_earthquake_tab(parent)` with:
  - Enable/disable checkbox
  - Location dropdown (auto-fills Z) + editable Z override
  - Soil class dropdown (A/B/C/D/E)
  - Ductility preset dropdown (fills mu & Sp) + individual overrides
  - R_uls, R_sls editable fields
  - Near-fault N(T,D) field
  - Extra seismic mass (kN) field
  - Read-only calculated values: T1, Ch(T1), k_mu, Cd_uls, Cd_sls, Wt, V_uls, V_sls, F_node
- `_generate()`: collect earthquake inputs, create `EarthquakeInputs`, pass to `LoadInput`
- `refresh_load_case_list()`: add E+/E- cases to dropdown
- `_build_preview_loads()`: draw horizontal arrows at eave nodes for EQ cases
- `_build_combos_tab()`: add earthquake combo info text

### Key NZS 1170.5:2004 formulas (for reference)
```
V = Cd(T1) * Wt
Cd(T1) = Ch(T1) * Z * R * N(T,D) * Sp / k_mu
k_mu: if T1 >= 0.7s -> k_mu = mu; if T1 < 0.7s -> k_mu = (mu-1)*T1/0.7 + 1
T1 = 1.25 * 0.085 * h_n^0.75  (steel MRF, Clause 4.1.2.1)
Floor: Cd(T1) >= max(0.03, Z*R*0.02)
EQ ULS combo factor on G = 1.0 (not 1.2); Q drops out (psi_c=0 for roofs)
SLS: Cd_sls = Ch(T1) * Z * R_sls * N (no Sp or k_mu reduction)
Forces split equally to eave nodes: F_node = V/2
```

## Testing
- Unit tests: `python -m pytest tests/ -v` (28 tests covering standards, models, output integration)
- GUI launch test: `python -m portal_frame.run_gui &`, wait a few seconds, then `tasklist | grep python`
- SpaceGass output files must be opened in SpaceGass v14.25 to verify format correctness.
- Output verification: generate with both old wrapper and new package, `diff` must show identical output.

## Design Spec
- Full architecture design: `docs/superpowers/specs/2026-04-01-architecture-restructure-design.md`

## External References
- NZ loading standards: `C:\Users\CadWork4\Formsteel\Formsteel Engineers - Documents\Simon\_3.0 NZS & REFERENCE DOCUMENTS\STANDARDS - Loading ASNZS1170\`
- Most current: AS/NZS 1170.0-2002 (Amdt 1-5), 1170.1, 1170.2-2021, 1170.3-2003 (Amdt 1-2), 1170.5-2004 (Amdt 1)
