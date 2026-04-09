# Save/Load Configuration + Load Case Groups — Design Spec

## Problem

1. Users cannot save their portal frame inputs and reload them later. All work is lost when the app closes.
2. SpaceGass output lacks LOAD CASE GROUPS, making it hard to organize ULS/SLS combos in SpaceGass.
3. SLS wind-only deflection cases (pure Ws without G) are not generated.

## Feature 1: Save/Load Configuration

### Approach
JSON file-based save/load with recent files list and auto-restore.

### Config JSON Format
```json
{
  "version": 1,
  "geometry": { "span", "eave_height", "roof_pitch", "roof_pitch_2", "bay_spacing", "roof_type" },
  "sections": { "column", "rafter" },
  "supports": { "left_base", "right_base" },
  "loads": { "dead_load_roof", "dead_load_wall", "live_load_roof", "include_self_weight", "building_depth" },
  "wind": { "qu", "qs", "kc_e", "kc_i", "cpi_uplift", "cpi_downward", "windward_wall_cpe" },
  "earthquake": { "enabled", "Z", "soil_class", "mu", "Sp", "Sp_sls", "R_uls", "R_sls", "near_fault", "extra_mass", "T1_override" },
  "crane": { "enabled", "rail_height", "gc_left", "gc_right", "qc_left", "qc_right", "transverse_uls": [...], "transverse_sls": [...] }
}
```

### GUI
- "Save" and "Load" buttons near the Generate button
- "Recent" dropdown showing last 10 opened configs
- Auto-save to `~/.portal_frame/last_session.json` on exit
- Auto-restore on startup if last session file exists

### App Data Location
`~/.portal_frame/` directory containing:
- `recent.json` — list of last 10 file paths
- `last_session.json` — auto-saved current state

### Methods
- `_collect_config() -> dict` — serialize all GUI fields to dict
- `_apply_config(cfg: dict)` — populate all GUI fields from dict
- `_save_config()` — file dialog + JSON write + update recent list
- `_load_config()` — file dialog + JSON read + apply + update recent list
- `_save_recent(path)` — add path to recent list, trim to 10
- `_load_recent() -> list[str]` — read recent list from disk

## Feature 2: LOAD CASE GROUPS + SLS Wind-Only Cases

### New SLS Wind-Only Cases
Append **pure Ws cases** (wind-only, no G) to the end of the SLS block:
- One case per wind case: factor = ws_factor on the wind case, nothing else
- Naming: "Ws1", "Ws2", ... "Ws8"
- Description: "W1(s) wind only", "W2(s) wind only", etc.

### ULS Combo Ordering (within 101+ block)
1. Static ULS: 1.35G, 1.2G+1.5Q → **group "ULS-GQ"**
2. ULS Wind: 1.2G+Wu, 0.9G+Wu per wind case → **group "ULS-Wind"**
3. ULS EQ: 1.0G+E per EQ case → **group "ULS-EQ"**
4. ULS Crane (with crane): 1.35(G+Gc), 1.2(G+Gc)+1.5Q, 1.2(G+Gc)+1.5Qc, 1.2(G+Gc)+1.5Qc+Hc, 0.9(G+Gc)+Hc, 1.2(G+Gc)+Wu, 0.9(G+Gc)+Wu, 1.0(G+Gc)+E

### SLS Combo Ordering (within 201+ block)
1. Static SLS: G+0.7Q, G → **group "SLS-GQ"** (part of)
2. SLS G+Wind: G+Ws per wind case → **group "SLS-Wind"**
3. SLS EQ: G+E(s) per EQ case → **group "SLS-EQ"**
4. SLS Crane (with crane): (G+Gc)+0.7Q, (G+Gc), (G+Gc)+Ws, (G+Gc)+E(s), (G+Gc)+Qc(s), (G+Gc)+Hc_s
5. SLS Wind-Only: pure Ws per wind case → **group "SLS-Wind Only"**

### Load Case Groups Output
```
LOAD CASE GROUPS
1,"ULS",101,-{uls_end}
2,"ULS-GQ",{uls_gq_start},-{uls_gq_end}
3,"ULS-Wind",{uls_wind_start},-{uls_wind_end}
4,"ULS-EQ",{uls_eq_start},-{uls_eq_end}
5,"SLS",201,-{sls_end}
6,"SLS-Wind",{sls_wind_start},-{sls_wind_end}
7,"SLS-EQ",{sls_eq_start},-{sls_eq_end}
8,"SLS-Wind Only",{sls_wo_start},-{sls_wo_end}
```

Group 1 "ULS" and Group 5 "SLS" cover the full ranges. Groups 2-4 and 6-8 are sub-ranges within them. Groups only appear if they contain cases (e.g. ULS-EQ only if earthquake is enabled).

### Implementation
- Modify `build_combinations()` in `combinations_nzs1170_0.py` to append wind-only SLS combos and return sub-group range info
- Add `_load_case_groups()` method to `SpaceGassWriter`
- Insert in `write()` after `_combinations()`, before `_titles()`

## Files to Modify
- `portal_frame/gui/app.py` — Save/Load/Recent buttons, collect/apply config methods
- `portal_frame/io/spacegass_writer.py` — LOAD CASE GROUPS section
- `portal_frame/standards/combinations_nzs1170_0.py` — Wind-only SLS combos + group ranges
