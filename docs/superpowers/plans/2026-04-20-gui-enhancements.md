# GUI Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Reactions diagram, Reactions CSV export, and double-click member detail popout to the PortalFrame GUI.

**Architecture:** Three additive features built on the existing `gui/canvas/` free-function pattern. No solver, standards, or SpaceGass writer changes. One new small pure helper (`analysis/station_interp.py`), one new CSV writer (`io/reactions_csv.py`), one new canvas renderer (`canvas/reactions.py`), one new Toplevel window (`gui/member_popout.py`). Existing modules (`app.py`, `preview.py`, `diagram_controller.py`, `frame_render.py`, `analysis_runner.py`) get small additions.

**Tech Stack:** Python 3, Tkinter (`tk.Toplevel`, `ttk.Treeview`, `ttk.Combobox`), pytest, PyNiteFEA (already wired), existing `ReactionResult` / `MemberStationResult` dataclasses.

**Reference spec:** `docs/superpowers/specs/2026-04-20-gui-enhancements-design.md`

---

## File Plan

### New Files
- `portal_frame/analysis/station_interp.py` (~30 lines) — `interpolate_station()` linear interp helper
- `portal_frame/io/reactions_csv.py` (~50 lines) — `write_reactions_csv()` writer
- `portal_frame/gui/canvas/reactions.py` (~140 lines) — `draw_reactions()` arrow/label renderer
- `portal_frame/gui/member_popout.py` (~380 lines) — `MemberPopout(tk.Toplevel)` window
- `tests/test_station_interp.py` (~60 lines)
- `tests/test_reactions_csv.py` (~60 lines)
- `tests/test_envelope_reactions.py` (~50 lines)

### Modified Files
- `portal_frame/gui/app.py` — add "Reactions" dropdown option, EXPORT REACTIONS button, double-click handler wiring (+~25 lines)
- `portal_frame/gui/preview.py` — `<Double-Button-1>` binding, member ID resolution from tags, `set_member_dblclick_handler` (+~15 lines)
- `portal_frame/gui/diagram_controller.py` — "R" scale key, Reactions branch in `build_diagram_data`, envelope reaction synthesis (+~55 lines)
- `portal_frame/gui/analysis_runner.py` — `_export_reactions` handler, enable/disable export button (+~20 lines)
- `portal_frame/gui/canvas/frame_render.py` — tag member lines `f"member_{mid}"`, dispatch `type == "R"` to `draw_reactions` (+~12 lines)

---

## Task 1: Station Interpolation Helper

**Files:**
- Create: `portal_frame/analysis/station_interp.py`
- Test: `tests/test_station_interp.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_station_interp.py`:

```python
"""Unit tests for analysis.station_interp."""
import pytest

from portal_frame.analysis.results import MemberStationResult
from portal_frame.analysis.station_interp import interpolate_station, STATION_FIELDS


def _stations():
    """Three-station sample: position 0.0, 1.0, 2.0 m with simple linear values."""
    return [
        MemberStationResult(position=0.0, position_pct=0.0,
                            axial=-10.0, shear=5.0, moment=0.0, dy_local=0.0),
        MemberStationResult(position=1.0, position_pct=50.0,
                            axial=-10.0, shear=5.0, moment=10.0, dy_local=2.0),
        MemberStationResult(position=2.0, position_pct=100.0,
                            axial=-10.0, shear=5.0, moment=20.0, dy_local=4.0),
    ]


def test_interpolate_at_exact_station():
    result = interpolate_station(_stations(), 1.0)
    assert result == {"moment": 10.0, "shear": 5.0, "axial": -10.0, "dy_local": 2.0}


def test_interpolate_at_midpoint():
    result = interpolate_station(_stations(), 0.5)
    assert result["moment"] == pytest.approx(5.0)
    assert result["dy_local"] == pytest.approx(1.0)
    assert result["axial"] == -10.0


def test_interpolate_below_range_clamps_to_start():
    result = interpolate_station(_stations(), -0.5)
    assert result["moment"] == 0.0
    assert result["dy_local"] == 0.0


def test_interpolate_above_range_clamps_to_end():
    result = interpolate_station(_stations(), 3.0)
    assert result["moment"] == 20.0
    assert result["dy_local"] == 4.0


def test_empty_stations_raises():
    with pytest.raises(ValueError, match="stations is empty"):
        interpolate_station([], 0.5)


def test_station_fields_constant():
    assert STATION_FIELDS == ("moment", "shear", "axial", "dy_local")
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `python -m pytest tests/test_station_interp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portal_frame.analysis.station_interp'`.

- [ ] **Step 3: Implement the helper**

Create `portal_frame/analysis/station_interp.py`:

```python
"""Linear interpolation of MemberStationResult at an arbitrary position."""

from portal_frame.standards.utils import lerp


STATION_FIELDS = ("moment", "shear", "axial", "dy_local")


def interpolate_station(stations, x_query):
    """Linear interp of station fields at x_query (m along the member).

    Returns a dict with keys STATION_FIELDS. Clamps x_query to the
    [first.position, last.position] range (no extrapolation).

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
                f: lerp(x_query, a.position, b.position,
                        getattr(a, f), getattr(b, f))
                for f in STATION_FIELDS
            }
    raise RuntimeError("unreachable: POI inside range but no bracket found")
```

- [ ] **Step 4: Run tests — verify pass**

Run: `python -m pytest tests/test_station_interp.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add portal_frame/analysis/station_interp.py tests/test_station_interp.py
git commit -m "feat(analysis): add interpolate_station helper for arbitrary-position queries"
```

---

## Task 2: Reactions CSV Writer

**Files:**
- Create: `portal_frame/io/reactions_csv.py`
- Test: `tests/test_reactions_csv.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reactions_csv.py`:

```python
"""Unit tests for io.reactions_csv."""
import csv

from portal_frame.analysis.results import (
    AnalysisOutput, CaseResult, ReactionResult,
)
from portal_frame.io.reactions_csv import write_reactions_csv


def _make_case(name, rx_1=(0.0, -10.0, 0.0), rx_5=(0.0, -10.0, 0.0)):
    return CaseResult(
        case_name=name, members={}, deflections={},
        reactions={
            1: ReactionResult(node_id=1, fx=rx_1[0], fy=rx_1[1], mz=rx_1[2]),
            5: ReactionResult(node_id=5, fx=rx_5[0], fy=rx_5[1], mz=rx_5[2]),
        },
    )


def test_writes_header_and_case_rows(tmp_path):
    out = AnalysisOutput(
        case_results={"G": _make_case("G"), "Q": _make_case("Q", rx_1=(0.0, -5.0, 0.0), rx_5=(0.0, -5.0, 0.0))},
        combo_results={},
    )
    path = tmp_path / "rx.csv"
    write_reactions_csv(str(path), out)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["Case", "Node", "FX (kN)", "FY (kN)", "MZ (kNm)"]
    # 2 cases × 2 nodes = 4 data rows
    assert len(rows) == 5  # header + 4


def test_combo_rows_included_after_cases(tmp_path):
    out = AnalysisOutput(
        case_results={"G": _make_case("G")},
        combo_results={"ULS-1": _make_case("ULS-1", rx_1=(1.2, -20.3, 0.5))},
    )
    path = tmp_path / "rx.csv"
    write_reactions_csv(str(path), out)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))

    data_rows = rows[1:]
    # First rows = base cases, later rows = combos
    assert data_rows[0][0] == "G"
    uls_rows = [r for r in data_rows if r[0] == "ULS-1"]
    assert len(uls_rows) == 2
    assert uls_rows[0][1] == "1"
    assert uls_rows[0][2] == "1.20"
    assert uls_rows[0][3] == "-20.30"
    assert uls_rows[0][4] == "0.50"


def test_values_formatted_two_decimals(tmp_path):
    out = AnalysisOutput(
        case_results={"G": _make_case("G", rx_1=(1.234, -5.678, 0.9012))},
        combo_results={},
    )
    path = tmp_path / "rx.csv"
    write_reactions_csv(str(path), out)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))

    # Node 1 row is the first data row
    assert rows[1][2] == "1.23"
    assert rows[1][3] == "-5.68"
    assert rows[1][4] == "0.90"
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `python -m pytest tests/test_reactions_csv.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portal_frame.io.reactions_csv'`.

- [ ] **Step 3: Implement the writer**

Create `portal_frame/io/reactions_csv.py`:

```python
"""Write a CSV of support reactions from an AnalysisOutput."""

import csv


def _combo_sort_key(name):
    """Sort combos by prefix (ULS before SLS) then numeric suffix."""
    prefix = 0 if name.startswith("ULS") else 1
    try:
        num = int(name.split("-")[1])
    except (IndexError, ValueError):
        num = 0
    return (prefix, num)


def write_reactions_csv(path, analysis_output):
    """Write reactions as CSV to `path`.

    Row order:
      1. Header
      2. All base cases in case_results insertion order, each with one row
         per support node (sorted by node_id).
      3. All combos in combo_results, sorted ULS-N then SLS-N.

    Values formatted to 2 decimal places.
    """
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Case", "Node", "FX (kN)", "FY (kN)", "MZ (kNm)"])

        for case_name, cr in analysis_output.case_results.items():
            _write_case(w, case_name, cr)

        for combo_name in sorted(
                analysis_output.combo_results.keys(), key=_combo_sort_key):
            _write_case(w, combo_name, analysis_output.combo_results[combo_name])


def _write_case(w, name, cr):
    for nid in sorted(cr.reactions.keys()):
        r = cr.reactions[nid]
        w.writerow([
            name, str(nid),
            f"{r.fx:.2f}", f"{r.fy:.2f}", f"{r.mz:.2f}",
        ])
```

- [ ] **Step 4: Run tests — verify pass**

Run: `python -m pytest tests/test_reactions_csv.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add portal_frame/io/reactions_csv.py tests/test_reactions_csv.py
git commit -m "feat(io): add reactions CSV writer"
```

---

## Task 3: Envelope Reaction Synthesis

**Files:**
- Create: `tests/test_envelope_reactions.py`
- Modify: `portal_frame/gui/diagram_controller.py` (add `synthesise_envelope_reactions` helper at module level)

- [ ] **Step 1: Write failing tests**

Create `tests/test_envelope_reactions.py`:

```python
"""Unit tests for envelope reaction synthesis in diagram_controller."""
from portal_frame.analysis.results import (
    AnalysisOutput, CaseResult, ReactionResult,
)
from portal_frame.gui.diagram_controller import synthesise_envelope_reactions


def _case(name, rx):
    """rx: dict[node_id] -> (fx, fy, mz)."""
    return CaseResult(
        case_name=name, members={}, deflections={},
        reactions={nid: ReactionResult(node_id=nid, fx=v[0], fy=v[1], mz=v[2])
                   for nid, v in rx.items()},
    )


def test_picks_max_abs_across_cases():
    out = AnalysisOutput(
        case_results={},
        combo_results={
            "ULS-1": _case("ULS-1", {1: (5.0, -20.0, 0.0), 5: (-5.0, -20.0, 0.0)}),
            "ULS-2": _case("ULS-2", {1: (-10.0, -10.0, 2.0), 5: (10.0, -10.0, -2.0)}),
            "ULS-3": _case("ULS-3", {1: (3.0, -25.0, 1.0), 5: (-3.0, -25.0, -1.0)}),
        },
    )
    result = synthesise_envelope_reactions(out, ["ULS-1", "ULS-2", "ULS-3"])
    # Node 1: max|fx|=10 from ULS-2 (signed), max|fy|=25 from ULS-3, max|mz|=2 from ULS-2
    assert result[1].fx == -10.0
    assert result[1].fy == -25.0
    assert result[1].mz == 2.0
    # Node 5: max|fx|=10 from ULS-2, max|fy|=25 from ULS-3, max|mz|=2 from ULS-2
    assert result[5].fx == 10.0
    assert result[5].fy == -25.0
    assert result[5].mz == -2.0


def test_missing_combos_skipped():
    out = AnalysisOutput(
        case_results={},
        combo_results={
            "ULS-1": _case("ULS-1", {1: (5.0, -20.0, 0.0)}),
        },
    )
    result = synthesise_envelope_reactions(out, ["ULS-1", "ULS-99-nonexistent"])
    assert set(result.keys()) == {1}
    assert result[1].fx == 5.0


def test_empty_combo_list_returns_empty():
    out = AnalysisOutput(case_results={}, combo_results={})
    result = synthesise_envelope_reactions(out, [])
    assert result == {}
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `python -m pytest tests/test_envelope_reactions.py -v`
Expected: FAIL with `ImportError: cannot import name 'synthesise_envelope_reactions'`.

- [ ] **Step 3: Implement synthesis helper**

Add to `portal_frame/gui/diagram_controller.py` at module level (near the top, after the imports):

```python
def synthesise_envelope_reactions(analysis_output, combo_names):
    """Build per-node reactions = signed value with max |magnitude| across combos.

    For each support node seen in the selected combos, independently picks
    the combo whose |fx| is largest (keeping sign), same for fy, same for mz.
    This is a conservative display — max-abs from potentially different combos.

    Returns dict[node_id] -> ReactionResult.
    """
    from portal_frame.analysis.results import ReactionResult

    node_best = {}  # node_id -> {fx: (abs, signed), fy: ..., mz: ...}
    for name in combo_names:
        cr = analysis_output.combo_results.get(name)
        if cr is None:
            continue
        for nid, r in cr.reactions.items():
            entry = node_best.setdefault(nid, {"fx": (-1.0, 0.0),
                                               "fy": (-1.0, 0.0),
                                               "mz": (-1.0, 0.0)})
            for field, val in (("fx", r.fx), ("fy", r.fy), ("mz", r.mz)):
                if abs(val) > entry[field][0]:
                    entry[field] = (abs(val), val)

    return {
        nid: ReactionResult(node_id=nid,
                            fx=vals["fx"][1], fy=vals["fy"][1], mz=vals["mz"][1])
        for nid, vals in node_best.items()
    }
```

- [ ] **Step 4: Run tests — verify pass**

Run: `python -m pytest tests/test_envelope_reactions.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add portal_frame/gui/diagram_controller.py tests/test_envelope_reactions.py
git commit -m "feat(diagrams): add envelope reaction synthesis helper"
```

---

## Task 4: Reactions Canvas Renderer

**Files:**
- Create: `portal_frame/gui/canvas/reactions.py`

No new tests — this is canvas drawing code. Coverage comes from the GUI smoke test in Task 11.

- [ ] **Step 1: Create the renderer**

Create `portal_frame/gui/canvas/reactions.py`:

```python
"""Reaction arrow/label rendering at support nodes.

Free functions operating on a FramePreview canvas (first arg). Follows the
same pattern as canvas/loads.py and canvas/diagrams.py.
"""

import math

from portal_frame.gui.theme import COLORS, FONT_SMALL
from portal_frame.gui.canvas.interaction import tx as _tx
from portal_frame.gui.canvas.labels import create_boxed_draggable_label


ARROW_MAX_PX = 60       # cap on arrow length (pixels)
MZ_SCALE_FACTOR = 0.1   # MZ drawn 10× larger than proportional, since kNm is
                        # typically smaller magnitude than kN forces
MZ_ARC_RADIUS = 18      # px — curved-arrow radius for moment glyph
MZ_THRESHOLD = 0.01     # kNm below which MZ is treated as zero (pinned base)

REACTION_COLOR = "#98c379"  # soft green, visually distinct from M/V/N/δ


def draw_reactions(canvas, payload):
    """Draw reaction arrows + labels at each support node in the payload.

    payload = {
        "type": "R",
        "reactions": dict[int, ReactionResult],
        "topology_nodes": dict[int, (x_world, y_world)],  # required
    }
    """
    reactions = payload.get("reactions") or {}
    nodes = payload.get("topology_nodes") or {}
    if not reactions or not nodes:
        return

    amp = canvas._diagram_scales.get("R", 1.0)

    # Determine per-component max magnitude for independent scaling (so small
    # FX values still get visible arrows when FY dominates).
    max_fx = max((abs(r.fx) for r in reactions.values()), default=0.0)
    max_fy = max((abs(r.fy) for r in reactions.values()), default=0.0)
    max_mz = max((abs(r.mz) for r in reactions.values()), default=0.0)

    for nid, r in reactions.items():
        world = nodes.get(nid)
        if world is None:
            continue
        sx, sy = _tx(canvas, world[0], world[1])

        _draw_fx(canvas, sx, sy, r.fx, max_fx, amp)
        _draw_fy(canvas, sx, sy, r.fy, max_fy, amp)
        if abs(r.mz) >= MZ_THRESHOLD:
            _draw_mz(canvas, sx, sy, r.mz, max_mz, amp)

        # Compact text label stacked below the node
        label_text = (f"FX={r.fx:.1f} kN\n"
                      f"FY={r.fy:.1f} kN\n"
                      f"MZ={r.mz:.1f} kNm")
        create_boxed_draggable_label(
            canvas, sx + 20, sy + 30, label_text,
            key=f"reaction_label_{nid}",
            fg=REACTION_COLOR, tags=("diagram", "reaction_label"),
        )


def _draw_fx(canvas, sx, sy, fx, max_fx, amp):
    if max_fx <= 1e-9 or abs(fx) < 1e-9:
        return
    # +FX arrow points in +screen-x direction (world +X = canvas right)
    length = amp * ARROW_MAX_PX * (fx / max_fx)
    canvas.create_line(
        sx, sy, sx + length, sy,
        fill=REACTION_COLOR, width=2, arrow="last",
        tags=("diagram", "reaction_arrow"),
    )


def _draw_fy(canvas, sx, sy, fy, max_fy, amp):
    if max_fy <= 1e-9 or abs(fy) < 1e-9:
        return
    # +FY world is upward — but screen Y increases downward, so negate
    length = amp * ARROW_MAX_PX * (fy / max_fy)
    canvas.create_line(
        sx, sy, sx, sy - length,
        fill=REACTION_COLOR, width=2, arrow="last",
        tags=("diagram", "reaction_arrow"),
    )


def _draw_mz(canvas, sx, sy, mz, max_mz, amp):
    if max_mz <= 1e-9:
        return
    # Curved arrow glyph: arc from 120° to 30° (counterclockwise for +MZ,
    # clockwise for -MZ). Tkinter create_arc uses degrees, with 0° at 3 o'clock.
    r = MZ_ARC_RADIUS * amp * min(1.0, abs(mz) / max_mz * MZ_SCALE_FACTOR * 10)
    r = max(r, 6)
    start = 30 if mz > 0 else 210
    extent = 270 if mz > 0 else -270
    canvas.create_arc(
        sx - r, sy - r, sx + r, sy + r,
        start=start, extent=extent, style="arc",
        outline=REACTION_COLOR, width=2,
        tags=("diagram", "reaction_moment"),
    )
    # Tiny arrow at the arc end to suggest rotation direction
    end_angle_rad = math.radians(start + extent)
    ax = sx + r * math.cos(end_angle_rad)
    ay = sy - r * math.sin(end_angle_rad)
    # Small tangent segment for arrowhead
    tangent = end_angle_rad + (math.pi / 2 if mz > 0 else -math.pi / 2)
    ex = ax + 4 * math.cos(tangent)
    ey = ay - 4 * math.sin(tangent)
    canvas.create_line(
        ax, ay, ex, ey,
        fill=REACTION_COLOR, width=2, arrow="last",
        tags=("diagram", "reaction_moment"),
    )
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from portal_frame.gui.canvas.reactions import draw_reactions"`
Expected: no output, exit 0.

- [ ] **Step 3: Run existing test suite — no regressions**

Run: `python -m pytest tests/ -v --tb=short -q`
Expected: all 232+6 tests still pass.

- [ ] **Step 4: Commit**

```bash
git add portal_frame/gui/canvas/reactions.py
git commit -m "feat(canvas): add reactions renderer with FX/FY/MZ arrows and labels"
```

---

## Task 5: Wire Reactions into the Diagram Dropdown

**Files:**
- Modify: `portal_frame/gui/app.py` (~line 173: add "Reactions" to combobox values)
- Modify: `portal_frame/gui/diagram_controller.py` (`on_diagram_type_changed`, `build_diagram_data`)
- Modify: `portal_frame/gui/preview.py` (`_diagram_scales` add "R", `SCALE_KEYMAP` add "r" — via interaction module)
- Modify: `portal_frame/gui/canvas/interaction.py` (add "r" to SCALE_KEYMAP)
- Modify: `portal_frame/gui/canvas/frame_render.py` (dispatch `type == "R"` to `draw_reactions`)

- [ ] **Step 1: Extend dropdown values in app.py**

In `portal_frame/gui/app.py` around line 173:

```python
self.diagram_type_combo = ttk.Combobox(
    load_bar, textvariable=self.diagram_type_var,
    values=["M", "V", "N", "δ", "Reactions"],   # <-- add "Reactions"
    state="readonly", font=FONT_MONO, width=10)  # <-- width 4 → 10
```

- [ ] **Step 2: Extend scale-key map in diagram_controller.on_diagram_type_changed**

In `portal_frame/gui/diagram_controller.py::on_diagram_type_changed`:

```python
def on_diagram_type_changed(app):
    """Handle diagram type combobox change -- notify preview and redraw."""
    dtype = app.diagram_type_var.get()
    # "δ" -> "D", "Reactions" -> "R", M/V/N pass through
    scale_key = {"M": "M", "V": "V", "N": "N", "\u03b4": "D",
                 "Reactions": "R"}.get(dtype, dtype)
    app.preview.set_diagram_type(scale_key)
    draw_preview(app)
```

- [ ] **Step 3: Register the "R" scale in preview._diagram_scales**

In `portal_frame/gui/preview.py::__init__` (around line 75):

```python
self._diagram_scales = {"M": 1.0, "V": 1.0, "N": 1.0, "D": 1.0,
                        "F": 1.0, "R": 1.0}
```

- [ ] **Step 4: Add "r" key to SCALE_KEYMAP**

In `portal_frame/gui/canvas/interaction.py` find the `SCALE_KEYMAP` dict (near the top) and add:

```python
SCALE_KEYMAP = {
    "m": "M", "n": "N", "s": "V", "d": "D", "f": "F",
    "r": "R",                                             # <-- new
}
```

- [ ] **Step 5: Handle Reactions in build_diagram_data**

In `portal_frame/gui/diagram_controller.py::build_diagram_data`, before the `attr = {...}[dtype]` line, add an early return branch:

```python
def build_diagram_data(app):
    display = app.diagram_case_var.get()
    dtype = app.diagram_type_var.get()
    out = app._analysis_output
    name = app._diagram_display_to_name.get(display)
    if name is None:
        return None

    # Topology node coords — reused below
    members_map = {}
    topology_nodes = {}
    if app._analysis_topology:
        members_map = {
            mid: (mem.node_start, mem.node_end)
            for mid, mem in app._analysis_topology.members.items()
        }
        topology_nodes = {
            nid: (node.x, node.y)
            for nid, node in app._analysis_topology.nodes.items()
        }

    # --- Reactions branch ---
    if dtype == "Reactions":
        if name in ("ULS Envelope", "SLS Envelope", "SLS Wind Only Envelope"):
            # Determine which combos feed this envelope
            if name == "ULS Envelope":
                combo_names = [n for n in out.combo_results if n.startswith("ULS")]
            elif name == "SLS Envelope":
                combo_names = [n for n in out.combo_results if n.startswith("SLS")]
            else:  # SLS Wind Only
                combo_names = [
                    n for n in out.combo_results
                    if n.startswith("SLS")
                    and "wind only" in out.combo_descriptions.get(n, "").lower()
                ]
            reactions = synthesise_envelope_reactions(out, combo_names)
        else:
            cr = out.case_results.get(name) or out.combo_results.get(name)
            if cr is None:
                return None
            reactions = cr.reactions
        return {
            "type": "R",
            "reactions": reactions,
            "topology_nodes": topology_nodes,
            "members": members_map,
        }
    # --- /Reactions branch ---

    attr = {"M": "moment", "V": "shear", "N": "axial", "\u03b4": "dy_local"}[dtype]
    # ... (rest unchanged — existing body continues below)
```

(You may need to remove the now-duplicate `members_map` / `topology_nodes` block later in the function, since it was hoisted to the top. If it was already near the top in the original, just delete the duplicate.)

- [ ] **Step 6: Dispatch type "R" in frame_render.update_frame**

In `portal_frame/gui/canvas/frame_render.py::update_frame`, locate the block that checks `diagram["type"]` and dispatches to `draw_force_diagram` / `_draw_deflection_diagram`. Add:

```python
from portal_frame.gui.canvas.reactions import draw_reactions as _draw_reactions

# In update_frame, where diagram type is dispatched:
if diagram is not None:
    dtype = diagram.get("type")
    if dtype == "R":
        _draw_reactions(canvas, diagram)
    elif dtype == "\u03b4":
        # existing deflection branch
        ...
    else:
        # existing force diagram branch
        draw_force_diagram(canvas, diagram, ...)
```

(Exact wiring depends on the current structure of `update_frame` — see `frame_render.py` for the existing dispatch. Insert the `"R"` case at the top of the if/elif chain so it short-circuits.)

- [ ] **Step 7: Smoke test the GUI**

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
kill %1
```
Expected: `clean` printed, no tracebacks.

Then manually:
- Launch GUI, generate + analyse default frame.
- Select Load Case "G - Dead Load", Diagram "Reactions" → green arrows should appear at base nodes with FX/FY/MZ labels.
- Select Diagram "ULS Envelope" (via case combobox) + Diagram Type "Reactions" → arrows show envelope max-abs values.

- [ ] **Step 8: Run full test suite — no regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: all tests pass (no new tests added in this task).

- [ ] **Step 9: Commit**

```bash
git add portal_frame/gui/app.py portal_frame/gui/diagram_controller.py \
        portal_frame/gui/preview.py portal_frame/gui/canvas/interaction.py \
        portal_frame/gui/canvas/frame_render.py
git commit -m "feat(gui): wire Reactions into diagram dropdown"
```

---

## Task 6: Export Reactions Button

**Files:**
- Modify: `portal_frame/gui/app.py` (~line 220: add button after analyse_btn)
- Modify: `portal_frame/gui/analysis_runner.py` (new `_export_reactions`; enable/disable in `_analyse` and `_invalidate_analysis`)

- [ ] **Step 1: Add the button in app._build_ui**

In `portal_frame/gui/app.py` immediately after `self.analyse_btn.pack(...)` (line ~220):

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

- [ ] **Step 2: Add `_export_reactions` method on PortalFrameApp**

In `portal_frame/gui/app.py` add near the other `_export_*` / `_save_*` methods:

```python
def _export_reactions(self):
    from portal_frame.gui.analysis_runner import export_reactions
    export_reactions(self)
```

- [ ] **Step 3: Implement `export_reactions` in analysis_runner.py**

In `portal_frame/gui/analysis_runner.py` add:

```python
from tkinter import filedialog, messagebox

from portal_frame.io.reactions_csv import write_reactions_csv


def export_reactions(app):
    """Ask for a path and write reactions CSV. Called from the GUI button."""
    if app._analysis_output is None:
        messagebox.showwarning("No analysis",
                               "Run Analyse (PyNite) first.")
        return
    path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        initialfile="reactions.csv",
    )
    if not path:
        return
    try:
        write_reactions_csv(path, app._analysis_output)
        messagebox.showinfo("Export complete",
                            f"Reactions written to:\n{path}")
    except Exception as e:
        messagebox.showerror("Export failed", str(e))
```

- [ ] **Step 4: Enable button after successful analyse, disable on invalidate**

In `portal_frame/gui/analysis_runner.py` find `analyse(app)` (the success path) and at the end add:

```python
if hasattr(app, "export_reactions_btn"):
    app.export_reactions_btn.config(state="normal")
```

Find the `_invalidate_analysis` method (on the app, likely in `app.py`) and add at the end:

```python
if hasattr(self, "export_reactions_btn"):
    self.export_reactions_btn.config(state="disabled")
```

- [ ] **Step 5: Smoke test**

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
kill %1
```

Manual: launch GUI, verify EXPORT REACTIONS button is disabled before analysis, enabled after. Click it, save to a path, open in a text editor — verify header + rows present.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add portal_frame/gui/app.py portal_frame/gui/analysis_runner.py
git commit -m "feat(gui): add Export Reactions CSV button"
```

---

## Task 7: Member Double-Click Plumbing

**Files:**
- Modify: `portal_frame/gui/canvas/frame_render.py` — tag each drawn member line with `f"member_{mid}"`
- Modify: `portal_frame/gui/preview.py` — `<Double-Button-1>` binding, `set_member_dblclick_handler`, member-id extraction
- Modify: `portal_frame/gui/app.py` — register handler, stub `_open_member_popout`

- [ ] **Step 1: Tag member lines with member IDs in frame_render**

In `portal_frame/gui/canvas/frame_render.py::update_frame`, find the loop that draws member lines (via `canvas.create_line(...)` for each member segment). Pass a member id into the drawing code. Example edit:

```python
# In the member-drawing loop (find the existing create_line for each member):
canvas.create_line(
    sx1, sy1, sx2, sy2,
    fill=COLORS["frame_member"], width=3,
    tags=("member", f"member_{mid}"),   # <-- add these tags
)
```

(If members are drawn in multiple passes — e.g. columns and rafters separately — tag all of them.)

- [ ] **Step 2: Add handler registration + binding in preview.py**

In `portal_frame/gui/preview.py::__init__` after the existing bindings (~line 100):

```python
self._member_dblclick_handler = None
self.bind("<Double-Button-1>", self._on_member_double_click)
```

Add the following methods on `FramePreview`:

```python
def set_member_dblclick_handler(self, handler):
    """Register a callable(mid) invoked when the user double-clicks a member."""
    self._member_dblclick_handler = handler

def _on_member_double_click(self, event):
    if self._member_dblclick_handler is None:
        return
    closest = self.find_closest(event.x, event.y, halo=3)
    if not closest:
        return
    for tag in self.gettags(closest[0]):
        if tag.startswith("member_"):
            try:
                mid = int(tag.split("_", 1)[1])
            except ValueError:
                return
            self._member_dblclick_handler(mid)
            return
```

- [ ] **Step 3: Register handler and stub popout in app.py**

In `portal_frame/gui/app.py::_build_ui` after `self.preview = FramePreview(...)`:

```python
self.preview.set_member_dblclick_handler(self._open_member_popout)
self._open_popouts = []  # keep references so Toplevels aren't GC'd
```

Add method on `PortalFrameApp`:

```python
def _open_member_popout(self, mid):
    """Open a MemberPopout for the given member id."""
    if self._analysis_output is None:
        from tkinter import messagebox
        messagebox.showinfo("No analysis",
                            "Run Analyse (PyNite) before inspecting members.")
        return
    from portal_frame.gui.member_popout import MemberPopout
    popout = MemberPopout(self, mid, self._analysis_output,
                          self._analysis_topology)
    self._open_popouts.append(popout)
```

- [ ] **Step 4: Smoke test — popout stub should exist**

Create a minimal stub `portal_frame/gui/member_popout.py`:

```python
"""Member detail popout window. Full implementation in Tasks 8-11."""
import tkinter as tk


class MemberPopout(tk.Toplevel):
    def __init__(self, parent, mid, analysis_output, topology):
        super().__init__(parent)
        self.title(f"Member {mid}")
        self.geometry("820x620")
        tk.Label(self, text=f"Member {mid} popout (stub)").pack(padx=20, pady=20)
```

Run:

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
kill %1
```

Manual: launch GUI, analyse, double-click a member — stub window should appear.

- [ ] **Step 5: Commit**

```bash
git add portal_frame/gui/canvas/frame_render.py portal_frame/gui/preview.py \
        portal_frame/gui/app.py portal_frame/gui/member_popout.py
git commit -m "feat(gui): add member double-click handler and popout stub"
```

---

## Task 8: MemberPopout — Window Skeleton and Controls

**Files:**
- Modify: `portal_frame/gui/member_popout.py` (replace stub)

- [ ] **Step 1: Build the window layout with controls and placeholders**

Overwrite `portal_frame/gui/member_popout.py`:

```python
"""Member detail popout window.

A Toplevel that shows a single-member X-Y diagram (M/V/N/δ) with a
Point-of-Interest input and a summary table. Multiple popouts may be open
simultaneously — each is independent.
"""
import tkinter as tk
from tkinter import ttk

from portal_frame.gui.theme import COLORS, FONT_MONO, FONT_SMALL


DIAGRAM_TYPES = ["M", "V", "N", "δ"]
DIAGRAM_UNITS = {"M": "kNm", "V": "kN", "N": "kN", "δ": "mm"}
DIAGRAM_ATTRS = {"M": "moment", "V": "shear", "N": "axial", "δ": "dy_local"}


class MemberPopout(tk.Toplevel):
    """One member × one case × one diagram type, with POI table."""

    def __init__(self, parent, mid, analysis_output, topology):
        super().__init__(parent)
        self._mid = mid
        self._out = analysis_output
        self._topology = topology
        self._member = topology.members[mid]
        self._length = self._compute_length()
        self._section_name = self._member.section_name if hasattr(
            self._member, "section_name") else str(self._member)

        self.title(f"Member {mid} — {self._section_name} "
                   f"(L={self._length:.2f} m)")
        self.geometry("820x620")
        self.configure(bg=COLORS["bg_panel"])

        self._build_controls()
        self._build_chart()
        self._build_poi_input()
        self._build_table()

        # Initial draw
        self._refresh_case_list()
        self._on_case_changed()

    # ---------------- layout ----------------
    def _build_controls(self):
        top = tk.Frame(self, bg=COLORS["bg_panel"])
        top.pack(fill="x", padx=12, pady=(12, 4))

        tk.Label(top, text="Load Case", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")
        self._case_var = tk.StringVar()
        self._case_combo = ttk.Combobox(
            top, textvariable=self._case_var, state="readonly",
            font=FONT_MONO, width=28)
        self._case_combo.pack(side="left", padx=(6, 16))
        self._case_combo.bind("<<ComboboxSelected>>",
                              lambda _: self._on_case_changed())

        tk.Label(top, text="Diagram", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")
        self._dtype_var = tk.StringVar(value="M")
        self._dtype_combo = ttk.Combobox(
            top, textvariable=self._dtype_var, state="readonly",
            values=DIAGRAM_TYPES, font=FONT_MONO, width=4)
        self._dtype_combo.pack(side="left", padx=(6, 0))
        self._dtype_combo.bind("<<ComboboxSelected>>",
                               lambda _: self._redraw_chart())

    def _build_chart(self):
        self._chart = tk.Canvas(
            self, bg=COLORS["canvas_bg"], highlightthickness=0,
            height=360)
        self._chart.pack(fill="both", expand=True, padx=12, pady=4)
        self._chart.bind("<Motion>", self._on_chart_motion)
        self._chart.bind("<Leave>", lambda _: self._clear_hover())

    def _build_poi_input(self):
        row = tk.Frame(self, bg=COLORS["bg_panel"])
        row.pack(fill="x", padx=12, pady=(4, 4))
        tk.Label(row, text="Point of interest", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")
        self._poi_var = tk.StringVar()
        self._poi_entry = tk.Entry(
            row, textvariable=self._poi_var, font=FONT_MONO, width=24,
            bg=COLORS["bg_input"], fg=COLORS["fg_bright"], relief="flat",
            highlightthickness=1, highlightcolor=COLORS["accent"],
            highlightbackground=COLORS["border"])
        self._poi_entry.pack(side="left", padx=(6, 4))
        self._poi_entry.bind("<Return>", lambda _: self._refresh_table())
        self._poi_entry.bind("<FocusOut>", lambda _: self._refresh_table())
        tk.Label(row, text="m", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")

    def _build_table(self):
        cols = ("position", "moment", "shear", "axial", "deflection")
        self._table = ttk.Treeview(self, columns=cols, show="headings",
                                   height=6)
        headings = {"position": "Position (m)", "moment": "Moment (kNm)",
                    "shear": "Shear (kN)", "axial": "Axial (kN)",
                    "deflection": "Deflection (mm)"}
        for c in cols:
            self._table.heading(c, text=headings[c])
            self._table.column(c, width=120, anchor="center")
        self._table.pack(fill="x", padx=12, pady=(4, 12))

    # ---------------- helpers ----------------
    def _compute_length(self):
        ns = self._topology.nodes[self._member.node_start]
        ne = self._topology.nodes[self._member.node_end]
        return ((ne.x - ns.x) ** 2 + (ne.y - ns.y) ** 2) ** 0.5

    def _refresh_case_list(self):
        values = list(self._out.case_results.keys())
        values.extend(sorted(self._out.combo_results.keys(),
                             key=lambda n: (0 if n.startswith("ULS") else 1,
                                            self._combo_num(n))))
        if self._out.uls_envelope_curves is not None:
            values.append("ULS Envelope")
        if self._out.sls_envelope_curves is not None:
            values.append("SLS Envelope")
        if self._out.sls_wind_only_envelope_curves is not None:
            values.append("SLS Wind Only Envelope")
        self._case_combo["values"] = values
        if values and not self._case_var.get():
            self._case_var.set(values[0])

    @staticmethod
    def _combo_num(name):
        try:
            return int(name.split("-")[1])
        except (IndexError, ValueError):
            return 0

    # ---------------- callbacks (stubs for later tasks) ----------------
    def _on_case_changed(self):
        self._redraw_chart()
        self._refresh_table()

    def _redraw_chart(self):
        # Implemented in Task 9
        self._chart.delete("all")
        self._chart.create_text(
            400, 180, text=f"Chart: {self._dtype_var.get()} @ {self._case_var.get()}",
            fill=COLORS["fg"], font=FONT_MONO)

    def _refresh_table(self):
        # Implemented in Task 10
        for row in self._table.get_children():
            self._table.delete(row)

    def _on_chart_motion(self, event):
        # Implemented in Task 11
        pass

    def _clear_hover(self):
        self._chart.delete("hover_marker")
```

- [ ] **Step 2: Smoke test**

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
kill %1
```

Manual: analyse, double-click member → Toplevel window opens with Load Case dropdown, Diagram dropdown, empty chart placeholder, POI entry, empty table. Select a case from dropdown → placeholder text updates.

- [ ] **Step 3: Commit**

```bash
git add portal_frame/gui/member_popout.py
git commit -m "feat(popout): add MemberPopout window skeleton with controls"
```

---

## Task 9: MemberPopout — Chart Rendering

**Files:**
- Modify: `portal_frame/gui/member_popout.py` — implement `_redraw_chart`

- [ ] **Step 1: Implement chart drawing**

Replace the `_redraw_chart` stub in `member_popout.py` with:

```python
def _redraw_chart(self):
    c = self._chart
    c.delete("all")

    w = c.winfo_width() or 780
    h = c.winfo_height() or 360
    ml, mr, mt, mb = 60, 20, 30, 50  # margins
    dw = w - ml - mr
    dh = h - mt - mb
    if dw <= 10 or dh <= 10:
        return

    case_name = self._case_var.get()
    dtype = self._dtype_var.get()
    attr = DIAGRAM_ATTRS[dtype]
    unit = DIAGRAM_UNITS[dtype]

    curves = self._get_curves(case_name, attr)
    if not curves:
        return

    # Collect all (position, value) pairs to determine y-range
    all_vals = [v for pts in curves for _, v in pts]
    if not all_vals:
        return
    y_max = max(all_vals + [0])
    y_min = min(all_vals + [0])
    y_half = max(abs(y_max), abs(y_min), 1e-6)

    L = self._length

    def sx(x):
        return ml + (x / L) * dw if L > 0 else ml

    def sy(v):
        return mt + dh / 2 - (v / y_half) * (dh / 2)

    # Axes
    c.create_line(ml, mt + dh / 2, ml + dw, mt + dh / 2,
                  fill=COLORS["fg_dim"], width=1)   # zero line
    c.create_line(ml, mt, ml, mt + dh,
                  fill=COLORS["fg_dim"], width=1)   # y-axis
    c.create_line(ml, mt + dh, ml + dw, mt + dh,
                  fill=COLORS["fg_dim"], width=1)   # x-axis (bottom)

    # X ticks
    for i in range(6):
        x = i / 5.0 * L
        tx_ = sx(x)
        c.create_line(tx_, mt + dh, tx_, mt + dh + 4,
                      fill=COLORS["fg_dim"])
        c.create_text(tx_, mt + dh + 14, text=f"{x:.2f}",
                      fill=COLORS["fg"], font=FONT_SMALL)

    # Y ticks (5 ticks evenly split around zero)
    for i in range(-2, 3):
        v = (i / 2.0) * y_half
        ty_ = sy(v)
        c.create_line(ml - 4, ty_, ml, ty_, fill=COLORS["fg_dim"])
        c.create_text(ml - 8, ty_, text=f"{v:.2f}", anchor="e",
                      fill=COLORS["fg"], font=FONT_SMALL)

    # Axis labels
    c.create_text(ml + dw / 2, h - 10,
                  text=f"Position (m)   — L = {L:.2f} m",
                  fill=COLORS["fg"], font=FONT_SMALL)
    c.create_text(12, mt + dh / 2,
                  text=f"{dtype} ({unit})",
                  fill=COLORS["fg"], font=FONT_SMALL, angle=90)

    # Plot each curve (single case → 1 curve, envelope → 2)
    colors = [COLORS.get("diagram_m", "#e06c75"), COLORS.get("fg_dim", "#7f7f7f")]
    for idx, pts in enumerate(curves):
        line_coords = []
        for x, v in pts:
            line_coords.extend([sx(x), sy(v)])
        if len(line_coords) >= 4:
            c.create_line(*line_coords, fill=colors[idx % len(colors)],
                          width=2, tags="curve")

    # Store mapping for hover lookup (used in Task 11)
    self._chart_geom = {
        "ml": ml, "mr": mr, "mt": mt, "mb": mb, "dw": dw, "dh": dh,
        "L": L, "y_half": y_half,
    }


def _get_curves(self, case_name, attr):
    """Return list of [(position_m, value), ...] curve lists.

    Single case → 1 curve. Envelope → 2 curves (max, min).
    """
    mid = self._mid
    envelope_map = {
        "ULS Envelope": self._out.uls_envelope_curves,
        "SLS Envelope": self._out.sls_envelope_curves,
        "SLS Wind Only Envelope": self._out.sls_wind_only_envelope_curves,
    }
    if case_name in envelope_map:
        env = envelope_map[case_name]
        if env is None:
            return []
        env_max, env_min = env
        curves = []
        for cr in (env_max, env_min):
            mr = cr.members.get(mid)
            if mr is None:
                continue
            curves.append([(s.position, getattr(s, attr)) for s in mr.stations])
        return curves
    cr = self._out.case_results.get(case_name) or \
         self._out.combo_results.get(case_name)
    if cr is None:
        return []
    mr = cr.members.get(mid)
    if mr is None:
        return []
    return [[(s.position, getattr(s, attr)) for s in mr.stations]]
```

- [ ] **Step 2: Smoke test**

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
kill %1
```

Manual: analyse → double-click a rafter → chart now shows axes, ticks, and the M curve. Switch diagram to V/N/δ → curve redraws. Select "ULS Envelope" as case → two curves visible.

- [ ] **Step 3: Commit**

```bash
git add portal_frame/gui/member_popout.py
git commit -m "feat(popout): draw X-Y chart with axes, ticks, and curve(s)"
```

---

## Task 10: MemberPopout — POI Input and Table

**Files:**
- Modify: `portal_frame/gui/member_popout.py` — implement `_refresh_table`, `_parse_poi`

- [ ] **Step 1: Add imports and helpers**

Add at the top of `member_popout.py` (after existing imports):

```python
from portal_frame.analysis.station_interp import interpolate_station
```

- [ ] **Step 2: Implement _parse_poi and _refresh_table**

Replace the `_refresh_table` stub with:

```python
def _parse_poi(self):
    """Parse the POI entry → list of floats in [0, L]. Silently drops invalid."""
    raw = self._poi_var.get().strip()
    if not raw:
        return []
    out = []
    for tok in raw.replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            v = float(tok)
        except ValueError:
            continue
        if 0 <= v <= self._length:
            out.append(v)
    return out


def _refresh_table(self):
    for row in self._table.get_children():
        self._table.delete(row)

    case_name = self._case_var.get()
    pois = self._parse_poi()
    if not pois:
        return

    stations_for_case = self._get_stations_for_case(case_name)
    if not stations_for_case:
        return

    for x in pois:
        values = interpolate_station(stations_for_case, x)
        self._table.insert("", "end", values=(
            f"{x:.2f}",
            f"{values['moment']:.2f}",
            f"{values['shear']:.2f}",
            f"{values['axial']:.2f}",
            f"{values['dy_local']:.2f}",
        ))


def _get_stations_for_case(self, case_name):
    """Return stations for the popout's member under the given case.

    For envelopes, picks the max-|value|-per-station from the (max, min) pair
    into a synthetic station list. Returns empty list if case not found.
    """
    mid = self._mid
    envelope_map = {
        "ULS Envelope": self._out.uls_envelope_curves,
        "SLS Envelope": self._out.sls_envelope_curves,
        "SLS Wind Only Envelope": self._out.sls_wind_only_envelope_curves,
    }
    if case_name in envelope_map:
        env = envelope_map[case_name]
        if env is None:
            return []
        env_max, env_min = env
        mr_max = env_max.members.get(mid)
        mr_min = env_min.members.get(mid)
        if mr_max is None or mr_min is None:
            return []
        # Merge: for each station index, take signed value with larger |value|
        from portal_frame.analysis.results import MemberStationResult
        merged = []
        for a, b in zip(mr_max.stations, mr_min.stations):
            pick = {}
            for field in ("moment", "shear", "axial", "dy_local"):
                va = getattr(a, field)
                vb = getattr(b, field)
                pick[field] = va if abs(va) >= abs(vb) else vb
            merged.append(MemberStationResult(
                position=a.position, position_pct=a.position_pct, **pick))
        return merged
    cr = self._out.case_results.get(case_name) or \
         self._out.combo_results.get(case_name)
    if cr is None:
        return []
    mr = cr.members.get(mid)
    return mr.stations if mr else []
```

- [ ] **Step 3: Smoke test**

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
kill %1
```

Manual: analyse → double-click rafter → type `0.5, 1.0, 1.5` into POI → table populates with 3 rows showing all 4 quantities. Switch Load Case → rows update. Switch Diagram type → table stays the same (correct — table is case-scoped, not type-scoped). Type invalid `-1, 99, abc` → ignored; empty table.

- [ ] **Step 4: Commit**

```bash
git add portal_frame/gui/member_popout.py
git commit -m "feat(popout): POI input drives 4-quantity summary table"
```

---

## Task 11: MemberPopout — Hover Tracker

**Files:**
- Modify: `portal_frame/gui/member_popout.py` — implement `_on_chart_motion`

- [ ] **Step 1: Implement hover tracker**

Replace the `_on_chart_motion` stub with:

```python
def _on_chart_motion(self, event):
    geom = getattr(self, "_chart_geom", None)
    if geom is None:
        return
    ml = geom["ml"]
    dw = geom["dw"]
    mt = geom["mt"]
    dh = geom["dh"]
    L = geom["L"]

    if event.x < ml or event.x > ml + dw:
        self._clear_hover()
        return

    x_world = ((event.x - ml) / dw) * L if dw > 0 else 0
    x_world = max(0.0, min(L, x_world))

    stations = self._get_stations_for_case(self._case_var.get())
    if not stations:
        self._clear_hover()
        return

    dtype = self._dtype_var.get()
    attr = DIAGRAM_ATTRS[dtype]
    unit = DIAGRAM_UNITS[dtype]

    vals = interpolate_station(stations, x_world)
    val = vals[attr]

    y_half = geom["y_half"]
    sy = mt + dh / 2 - (val / y_half) * (dh / 2) if y_half > 0 else mt + dh / 2

    self._clear_hover()
    c = self._chart
    c.create_line(event.x, mt, event.x, mt + dh,
                  fill=COLORS["fg_dim"], dash=(2, 2),
                  tags="hover_marker")
    c.create_oval(event.x - 4, sy - 4, event.x + 4, sy + 4,
                  fill=COLORS["accent"], outline="",
                  tags="hover_marker")
    # Annotation: value + distance + loads (loads lookup is a nice-to-have
    # but kept minimal here — shows only the value and distance)
    label = f"{dtype} = {val:.2f} {unit}\nx = {x_world:.2f} m from i-end"
    c.create_text(event.x + 8, sy - 20, text=label,
                  fill=COLORS["fg_bright"], font=FONT_SMALL,
                  anchor="w", tags="hover_marker")
```

- [ ] **Step 2: Smoke test**

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
kill %1
```

Manual: analyse → double-click member → hover along the chart → vertical dashed line tracks cursor, dot on curve, tooltip text shows `M = 12.34 kNm\nx = 2.45 m from i-end`. Move cursor off chart → tracker disappears.

- [ ] **Step 3: Run full test suite — no regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: all 232 + new tests pass.

- [ ] **Step 4: Commit**

```bash
git add portal_frame/gui/member_popout.py
git commit -m "feat(popout): live hover tracker showing value + distance from i-end"
```

---

## Task 12: End-to-End GUI Smoke Test and CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md` — document the new features in the Architecture section

- [ ] **Step 1: Run full regression**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: all tests pass including the 9 new ones from Tasks 1-3.

- [ ] **Step 2: Manual smoke test — all 3 features**

Launch GUI:

```bash
python -m portal_frame.run_gui 2>/tmp/gui.log &
sleep 5
grep -i traceback /tmp/gui.log || echo "clean"
```

Checks:

1. Generate + analyse default frame → Analysis completes.
2. Diagram dropdown "Reactions" → arrows at base nodes, labels present.
3. Switch case to each combo → arrows update.
4. Switch to "ULS Envelope" → envelope arrows (max-abs per node).
5. EXPORT REACTIONS → save to `/tmp/rx.csv`, open file → header + rows match case names.
6. Double-click left column → popout opens; chart shows M curve.
7. In popout: change Diagram to V/N/δ → chart redraws; table unchanged.
8. Type `0.5, 1.0` into POI → table shows 2 rows with all 4 quantities.
9. Change Load Case in popout → table values refresh.
10. Hover chart → tracker line + value annotation follow cursor.
11. Close popout; double-click a rafter → new popout opens.
12. Open two popouts simultaneously → each independent.
13. Close GUI. Relaunch, do NOT analyse, click EXPORT REACTIONS → warning dialog "Run Analyse first".
14. Double-click member without analysis → info dialog "Run Analyse first".

```bash
kill %1
```

- [ ] **Step 3: Update CLAUDE.md architecture section**

In `CLAUDE.md` find the `gui/` section under Architecture and add the new files:

```
  gui/
    ...
    member_popout.py (~380 lines) MemberPopout Toplevel — per-member X-Y chart + POI summary table
    ...
    canvas/
      reactions.py     draw_reactions — FX/FY/MZ arrow + label renderer at support nodes
  io/
    ...
    reactions_csv.py   write_reactions_csv — one row per (case, support node)
  analysis/
    ...
    station_interp.py  interpolate_station — linear interp of MemberStationResult fields at arbitrary x
```

Also add a brief entry under "Adding New Features":

```
| New diagram type | Add dropdown option in app.py, map scale key in diagram_controller.on_diagram_type_changed, register in preview._diagram_scales, add handler in canvas/<name>.py, dispatch from canvas/frame_render.update_frame |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Reactions diagram, CSV export, and MemberPopout"
```

- [ ] **Step 5: Final regression**

```bash
python -m pytest tests/ -v --tb=short
python -m portal_frame.run_gui 2>/tmp/gui_final.log &
sleep 5
grep -i traceback /tmp/gui_final.log || echo "clean"
kill %1
```

Both should be clean.

---

## Self-Review Checklist

- [x] **Spec coverage:** All 3 features from the design spec have tasks (1-6 = Reactions + CSV, 7-11 = Popout, 12 = docs).
- [x] **Placeholder scan:** All steps contain concrete code. No "TBD" / "add error handling".
- [x] **Type consistency:** `MemberStationResult`, `ReactionResult`, `AnalysisOutput.case_results`, `combo_results`, `uls_envelope_curves` match `portal_frame/analysis/results.py`. `interpolate_station` signature consistent across Tasks 1, 10, 11. `synthesise_envelope_reactions` signature consistent across Tasks 3, 5.
- [x] **TDD discipline:** Tasks 1-3 (pure logic) use TDD. Tasks 4-11 (canvas/GUI code) use smoke tests since Tkinter rendering is not unit-testable.
- [x] **Commit cadence:** Every task ends with a commit. No multi-feature commits.
- [x] **File size target:** Largest new file `member_popout.py` stays under 500 lines (~380 estimated).

---

## Execution Notes

**Order matters.** Task 7 (member click plumbing) must land before Task 8 (popout skeleton) — the stub popout is needed to verify the double-click wiring.

**If any smoke test fails with a traceback**, stop and fix before committing. The GUI smoke test grep must print `clean` — no tracebacks allowed in `/tmp/gui.log` at any commit boundary.

**Envelope combo filtering in Task 5 Step 5** uses the description substring `"wind only"` for the SLS Wind Only envelope. This matches the existing pattern in `analysis/combinations.py::compute_envelope_curves`. Verify the description strings match (`"W*(s) wind only"` or similar) by printing `out.combo_descriptions` in the GUI console if envelope synthesis returns zero nodes.