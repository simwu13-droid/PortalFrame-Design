# GUI Enhancements Design: Reactions Diagram, Reactions CSV Export, Member Detail Popout

> **Status:** Approved for implementation

## Goal

Three additive GUI enhancements that make the analysis review workflow stronger without touching the solver, standards, or SpaceGass writer:

1. **Reactions diagram** — add "Reactions" as a new entry in the diagram-type dropdown. Draws scaled arrows at base support nodes showing FX/FY/MZ with kN/kNm labels, for both single cases and envelopes.
2. **Reactions CSV export** — new button next to ANALYSE. Writes one row per `(case, support_node)` with FX, FY, MZ columns.
3. **Member detail popout** — double-click a member to open a dedicated `Toplevel` window with an X-Y chart of the selected quantity along the member, a comma-separated "point of interest" input, and a table of Moment/Shear/Axial/Deflection at each POI.

## Non-Goals (YAGNI)

- No ULS/SLS overlay toggles in the popout — the main preview already exposes those at frame scale.
- Reactions export is CSV only (no TXT, no PDF).
- Reaction arrows only at base support nodes (node_id present in `CaseResult.reactions`) — not at bracket nodes or eaves.
- No new field in envelope curves for reactions — envelope reactions are synthesised on the fly in `diagram_controller` (max-abs across contributing cases), avoiding changes to `analysis/combinations.py` field tuples.
- Multiple popouts open simultaneously are independent; no cross-popout linking.

## Architecture

All three features follow the established `gui/canvas/` extraction pattern — free functions `fn(canvas, ...)` with the preview canvas delegating. New files are small and focused:

```
portal_frame/
  analysis/
    station_interp.py          NEW  ~30 lines — linear interp of MemberStationResult list at x
  io/
    reactions_csv.py           NEW  ~50 lines — write_reactions_csv(path, analysis_output)
  gui/
    app.py                     MOD  +25 lines — "Reactions" dropdown option, EXPORT button, double-click wire
    preview.py                 MOD  +15 lines — double-click binding, member-id resolution
    diagram_controller.py      MOD  +55 lines — Reactions branch in build_diagram_data, envelope reaction synthesis
    analysis_runner.py         MOD  +20 lines — _export_reactions handler
    member_popout.py           NEW  ~380 lines — MemberPopout(tk.Toplevel) class
    canvas/
      frame_render.py          MOD  +12 lines — tag member lines with f"member_{mid}", dispatch type=="R"
      reactions.py             NEW  ~140 lines — draw_reactions(canvas, payload) free function
```

All new files are under the 500-line target. `member_popout.py` at ~380 lines is the largest — split from `app.py` / preview to keep both stable.

## Feature 1: Reactions in Diagram Dropdown

### Data Flow

```
Combobox selects "Reactions"
  → diagram_controller.on_diagram_type_changed sets scale key "R"
  → draw_preview rebuilds diagram via build_diagram_data
  → build_diagram_data returns {"type": "R", "reactions": {node_id: ReactionResult}, "reactions_min": None | {...}}
  → preview.update_frame → frame_render.update_frame dispatches to canvas/reactions.draw_reactions
  → arrows + text labels drawn at base support nodes
```

For a single case: `reactions` is `CaseResult.reactions` (already populated by `PyNiteSolver`).

For an envelope (ULS/SLS/SLS Wind Only): synthesise per-node max-abs triplet across the contributing cases (combo_results whose name is in the envelope set).

### Dropdown Values

Current: `["M", "V", "N", "δ"]`
New: `["M", "V", "N", "δ", "Reactions"]`

Scale-key mapping extends `{..., "Reactions": "R"}`. The existing `_diagram_scales` dict gets a `"R": 1.0` entry. The `SCALE_KEYMAP` gains `"r"` for hold-scroll amplitude adjustment (consistent with m/n/s/d/f existing bindings).

### Rendering (`canvas/reactions.py::draw_reactions`)

At each node in the payload's `reactions` dict:

- `FX`: horizontal arrow, anchored at the node, length `= sign(FX) * amp_px * abs(FX) / max_force`. Text label `"FX = ±12.3 kN"` next to arrow tip.
- `FY`: vertical arrow, upward for +FY. Text label `"FY = ±45.6 kN"`.
- `MZ`: curved arc glyph (3-point bezier approximated as arc segment) near node, labelled `"MZ = 3.2 kNm"`. Skip if `|MZ| < 0.01` (pinned base).

Colours use `COLORS["frame_reaction"]` (new theme entry, e.g. `"#98c379"` soft green — not in current diagram colour map so it visually distinguishes from M/V/N/δ).

Labels are registered with `make_draggable` and the user-offset persistence dict (same pattern as existing annotation labels).

Arrow scaling: `max_force = max(abs(fx), abs(fy), abs(mz)*0.1 scale) across all rendered nodes`. MZ scaled to 10× because moment magnitudes (kNm) are typically smaller than forces (kN) — this keeps the moment glyph visible.

## Feature 2: Export Reactions CSV

### Button Placement

In `app.py::_build_ui()`, immediately after `self.analyse_btn.pack(...)` (line ~220):

```python
self.export_reactions_btn = tk.Button(
    btn_row, text="  EXPORT REACTIONS  ", font=FONT_BOLD,
    fg=COLORS["fg_bright"], bg="#555555",
    activebackground="#666666", activeforeground=COLORS["fg_bright"],
    relief="flat", cursor="hand2", padx=10, pady=8,
    command=self._export_reactions,
    state="disabled",
)
self.export_reactions_btn.pack(side="left", padx=(8, 0))
```

Enabled in `analysis_runner._analyse()` after a successful analysis: `self.export_reactions_btn.config(state="normal")`. Disabled on `_invalidate_analysis`.

### CSV Format (`io/reactions_csv.py`)

```
Case,Node,FX (kN),FY (kN),MZ (kNm)
G,1,0.00,-12.34,0.00
G,5,0.00,-12.34,0.00
Q,1,0.00,-5.20,0.00
...
ULS-1,1,-3.45,-18.20,1.23
...
```

- One row per `(case_or_combo, base_support_node)`.
- Order: all base cases in the order they appear in `analysis_output.case_results`, then combos ordered by ULS-N then SLS-N (numeric suffix), then envelope rows labelled `"ULS Envelope (max)"`, `"ULS Envelope (min)"`, etc.
- Floats at 2 decimal places.
- "Base support node" = any `node_id` key present in the `reactions` dict of the first case. (All cases share the same support set.)

### Handler

`analysis_runner._export_reactions(self)`:
1. `path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="reactions.csv")`
2. If user cancelled, return silently.
3. `write_reactions_csv(path, self._analysis_output)`
4. `messagebox.showinfo("Export complete", f"Reactions written to {path}")`

## Feature 3: Member Detail Popout

### Detection

Every member line drawn in `frame_render.update_frame()` gets tags `("member", f"member_{mid}")` added. `preview.py` binds `<Double-Button-1>`:

```python
def _on_member_double_click(self, event):
    item = self.find_closest(event.x, event.y, halo=3)
    if not item:
        return
    for tag in self.gettags(item[0]):
        if tag.startswith("member_"):
            mid = int(tag.split("_")[1])
            if self._member_dblclick_handler:
                self._member_dblclick_handler(mid)
            return
```

`app.py` registers `self.preview.set_member_dblclick_handler(self._open_member_popout)`. `_open_member_popout(mid)` instantiates a new `MemberPopout` (multiple allowed).

### Window Layout

```
┌────────────────────────────────────────────────────────────┐
│  Load Case [ULS Envelope ▼]         Diagram [M ▼]          │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │    Moment (kNm)         ↑                            │  │
│  │                         │     Loads at hover         │  │
│  │                         │                            │  │
│  │   ─────────────────────────────────────→             │  │
│  │                         Position (m)                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  Point of interest  [0.3, 0.6]  m                          │
│                                                            │
│  ┌──────────┬─────────┬────────┬────────┬───────────────┐  │
│  │ Position │ Moment  │ Shear  │ Axial  │ Deflection    │  │
│  │   0.3    │  -4.53  │   8.10 │ -12.01 │      2.34     │  │
│  │   0.6    │  -2.20  │   7.85 │ -12.01 │      3.12     │  │
│  └──────────┴─────────┴────────┴────────┴───────────────┘  │
└────────────────────────────────────────────────────────────┘
```

- `tk.Toplevel`, title `"Member {mid} — {section_name} (L={length:.2f} m)"`, default size 820×620, resizable.
- **Top controls**: Load Case combobox (populated from `analysis_output.case_results` keys + `combo_results` keys + envelope names); Diagram combobox `["M", "V", "N", "δ"]`.
- **Chart canvas** (780×380): drawn from scratch — axes with tick marks & labels, grid, zero line, diagram curve built from station data (polyline through 21 stations).
- **POI entry**: `ttk.Entry`, `<Return>` and `<FocusOut>` trigger parse + table refresh.
- **POI table**: `ttk.Treeview` with 5 columns. Rows clear and repopulate on POI change or Load Case change.

### Chart Canvas Rendering

Margins: left=60 (Y-axis labels), right=20, top=30, bottom=50 (X-axis labels). Drawing area `= W - 80 × H - 80`.

For each station `s` in the selected member's stations:
- `x_screen = margin_left + (s.position / L) * drawing_width`
- `y_screen = margin_top + drawing_height/2 - (s.<attr> / y_range_half) * drawing_height/2`

`y_range_half = max(abs(min_val), abs(max_val), 1e-6)`.

Polyline connects all stations.

Ticks: 5 evenly-spaced ticks on each axis with numeric labels.

**Envelope handling**: if Load Case is `"ULS Envelope"`/`"SLS Envelope"`/`"SLS Wind Only Envelope"`, draw two polylines (max curve + min curve) in slightly different shades. For the table, compute max-abs value (with sign) across envelope contributing cases — but **only for display in the envelope row labelling**; the table itself shows worst per-quantity with sign.

### Hover Tracker

`<Motion>` on the chart canvas:
1. Compute `x_world = (event.x - margin_left) / px_per_meter`, clamp `[0, L]`.
2. Delete prior `"hover_marker"` items.
3. Draw vertical line from top margin to bottom margin at `event.x`.
4. Interpolate station data → marker dot at curve intersection, tag `"hover_marker"`.
5. Look up loads at `x_world` in the member's load input for this case. Render text annotation listing any UDLs whose `[start_pct, end_pct] / 100 * L` contains x, and any point loads at x (within 0.01 m). If no loads match, no annotation.

Loads lookup: popout receives a `build_member_loads(app, case_name, mid)` callable from `app.py` (or a small adapter). Reuses the logic from `diagram_controller.build_preview_loads` but per-member.

### POI Input and Table

Parse: split by comma/whitespace, convert each to float, filter `0 ≤ x ≤ L`. Invalid entries ignored silently. Entry border colour stays default; validation failures (all entries invalid) just show an empty table.

For each valid POI `x`:
1. Interpolate station data at `x` → `{moment, shear, axial, dy_local}`.
2. Insert table row `(f"{x:.2f}", f"{M:.2f}", f"{V:.2f}", f"{N:.2f}", f"{dy:.2f}")`.

Diagram-type change does NOT refresh the table — only the chart. Load Case change DOES refresh both.

**Envelope in table**: when envelope is selected, for each POI take the max-abs value (with sign) across the (max, min) envelope pair at that position. Column headers do NOT add suffix — the Load Case combobox already shows envelope context.

### Interpolation Helper (`analysis/station_interp.py`)

```python
from portal_frame.analysis.results import MemberStationResult
from portal_frame.standards.utils import lerp

STATION_FIELDS = ("moment", "shear", "axial", "dy_local")

def interpolate_station(stations, x_query):
    """Linear interp of station fields at x_query (m).

    Returns dict {field: value}. Clamps x_query to [first.position, last.position].
    Raises ValueError if stations is empty.
    """
    if not stations:
        raise ValueError("stations is empty")
    sorted_st = sorted(stations, key=lambda s: s.position)
    if x_query <= sorted_st[0].position:
        s = sorted_st[0]
        return {f: getattr(s, f) for f in STATION_FIELDS}
    if x_query >= sorted_st[-1].position:
        s = sorted_st[-1]
        return {f: getattr(s, f) for f in STATION_FIELDS}
    for a, b in zip(sorted_st, sorted_st[1:]):
        if a.position <= x_query <= b.position:
            return {
                f: lerp(x_query, a.position, b.position, getattr(a, f), getattr(b, f))
                for f in STATION_FIELDS
            }
    raise RuntimeError("unreachable: POI inside range but no bracket found")
```

## Data Flow Summary

No changes to:
- `AnalysisOutput` structure (reactions already stored per case).
- `combinations.py` field tuples.
- Solver behaviour.
- SpaceGass writer.

Additions are pure display/export + one new helper (`interpolate_station`).

## Testing

### Unit Tests
- `tests/test_station_interp.py` — interpolation at endpoints, midpoint, exact station match, out-of-range clamp, empty list raises.
- `tests/test_reactions_csv.py` — write + re-read CSV with a synthetic `AnalysisOutput` containing 2 cases × 2 supports; assert header, row count, value formatting.
- `tests/test_envelope_reactions.py` — synthesise envelope reactions from a 3-case set, verify max-abs selection.

### GUI Smoke Tests (manual)
1. `python -m portal_frame.run_gui 2>/tmp/gui.log &`, wait 3s, `grep -i traceback /tmp/gui.log` → empty.
2. Generate + analyse default frame.
3. **Reactions diagram**: dropdown "Reactions" → arrows appear at base nodes, labels legible, values match Analysis results panel. Switch to envelope → arrows still drawn.
4. **CSV export**: button disabled before analysis; after analysis, click → save dialog → file opens in Excel with expected header and rows.
5. **Popout**:
   - Double-click a rafter → popout opens with M curve drawn.
   - Switch diagram to V/N/δ → chart redraws, table unchanged.
   - Hover chart → vertical tracker line + annotation with loads at cursor.
   - Type `0.5, 1.0, 2.0` into POI → table populates 3 rows with all 4 quantities.
   - Change Load Case to a combo → table values refresh.
   - Close popout; double-click column → popout opens for vertical member.
   - Open two popouts simultaneously → both behave independently.

### Regression
- `python -m pytest tests/ -v` → all 232 existing tests still pass.

## Open Questions

None. All scope decisions resolved during brainstorming.

## Estimated Sizes

| File | Type | Lines |
|------|------|-------|
| `analysis/station_interp.py` | NEW | ~30 |
| `io/reactions_csv.py` | NEW | ~50 |
| `gui/member_popout.py` | NEW | ~380 |
| `gui/canvas/reactions.py` | NEW | ~140 |
| `gui/app.py` | MOD | +25 |
| `gui/preview.py` | MOD | +15 |
| `gui/diagram_controller.py` | MOD | +55 |
| `gui/analysis_runner.py` | MOD | +20 |
| `gui/canvas/frame_render.py` | MOD | +12 |
| `tests/test_station_interp.py` | NEW | ~60 |
| `tests/test_reactions_csv.py` | NEW | ~60 |
| `tests/test_envelope_reactions.py` | NEW | ~50 |
| **Total new/modified** | | **~900** |

All files stay under the 500-line target.