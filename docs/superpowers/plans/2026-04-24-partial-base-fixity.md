# Partial Base Fixity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Partial" base-support option alongside Pinned/Fixed. When selected, the in-app PyNite solver models the base as a rotational spring `kθ = α · 4EI/L` (MZ DOF) for both ULS and SLS. SpaceGass export remains pinned.

**Architecture:** Extend `SupportCondition` with `fixity_percent`; update `PyNiteSolver._apply_support()` to add a rotational spring when `"partial"`; add a third radio + shared `[  ]%` entry on the Frame tab's supports row; persist the new field. No changes to standards, writer, canvas, or envelope logic.

**Tech Stack:** Python 3, dataclasses, PyNiteFEA 2.4.1 (`FEModel3D.def_support_spring(name, "RZ", kθ)` — signature verified), tkinter, pytest.

**Spec:** [docs/superpowers/specs/2026-04-24-partial-base-fixity-design.md](../specs/2026-04-24-partial-base-fixity-design.md)

---

## File Structure

**Files created:**
- `tests/test_partial_base_fixity.py` — unit tests for solver + model behaviour

**Files modified:**
- `portal_frame/models/supports.py` — add `fixity_percent` field and expanded `"partial"` value
- `portal_frame/solvers/pynite_solver.py` — handle `"partial"` in `_apply_support()`, add `_compute_partial_ktheta()`
- `portal_frame/gui/tabs/frame_tab.py` — add Partial radio on both rows + shared `[  ]%` entry with enable/disable trace
- `portal_frame/gui/analysis_runner.py` — pass `fixity_percent` into `SupportCondition`
- `portal_frame/gui/persistence.py` — save/load `fixity_percent`
- `portal_frame/io/spacegass_writer.py` — optional header comment when partial fixity is active
- `CLAUDE.md` — document the new option in a short note under "Design Spec" section

---

## Task 1: Extend SupportCondition model

**Files:**
- Modify: `portal_frame/models/supports.py`
- Test: `tests/test_partial_base_fixity.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `tests/test_partial_base_fixity.py`:

```python
"""Tests for partial base fixity feature."""

import pytest

from portal_frame.models.supports import SupportCondition


def test_support_condition_defaults_unchanged():
    s = SupportCondition()
    assert s.left_base == "pinned"
    assert s.right_base == "pinned"
    assert s.fixity_percent == 0.0


def test_support_condition_accepts_partial():
    s = SupportCondition(left_base="partial", right_base="pinned",
                         fixity_percent=25.0)
    assert s.left_base == "partial"
    assert s.right_base == "pinned"
    assert s.fixity_percent == 25.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_partial_base_fixity.py -v`
Expected: FAIL — `SupportCondition.__init__() got an unexpected keyword argument 'fixity_percent'`

- [ ] **Step 3: Implement the field**

Replace the body of `portal_frame/models/supports.py`:

```python
"""Support condition data model."""

from dataclasses import dataclass


@dataclass
class SupportCondition:
    """Support conditions for portal frame bases.

    left_base / right_base: "pinned" | "fixed" | "partial".
    fixity_percent: 0–100, used only when either side is "partial".
    Interpreted as α in kθ = α · 4EI/L (linear fixity-factor convention).
    """
    left_base: str = "pinned"
    right_base: str = "pinned"
    fixity_percent: float = 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_partial_base_fixity.py -v`
Expected: PASS for both tests.

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

Run: `python -m pytest tests/ -q`
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add portal_frame/models/supports.py tests/test_partial_base_fixity.py
git commit -m "feat(supports): add partial fixity field to SupportCondition"
```

---

## Task 2: Compute kθ helper in PyNiteSolver

**Files:**
- Modify: `portal_frame/solvers/pynite_solver.py`
- Test: `tests/test_partial_base_fixity.py`

- [ ] **Step 1: Write the failing unit test**

Append to `tests/test_partial_base_fixity.py`:

```python
from portal_frame.solvers.pynite_solver import PyNiteSolver


class _StubSection:
    def __init__(self, Iz_m):
        self.Ax_m = 1e-3
        self.Iy_m = 1e-6
        self.Iz_m = Iz_m
        self.J_m = 1e-6


class _StubNode:
    def __init__(self, nid, x, y):
        self.id = nid
        self.x = x
        self.y = y


class _StubTopology:
    def __init__(self, base_y, knee_y):
        self.nodes = {
            1: _StubNode(1, 0.0, base_y),
            2: _StubNode(2, 0.0, knee_y),
        }


class _StubRequest:
    def __init__(self, Iz_m, L, alpha_pct):
        self.column_section = _StubSection(Iz_m)
        self.topology = _StubTopology(base_y=0.0, knee_y=L)

        class S:
            pass
        self.supports = S()
        self.supports.fixity_percent = alpha_pct


def test_compute_partial_ktheta_linear_formula():
    # E = 200e6 kN/m^2, Iz = 1e-6 m^4, L = 6.0 m, alpha = 50%
    # k = 0.50 * 4 * 200e6 * 1e-6 / 6.0 = 66.666... kN·m/rad
    solver = PyNiteSolver()
    solver._request = _StubRequest(Iz_m=1e-6, L=6.0, alpha_pct=50.0)
    base_node = solver._request.topology.nodes[1]
    k = solver._compute_partial_ktheta(base_node)
    assert k == pytest.approx(400.0 / 6.0, rel=1e-9)


def test_compute_partial_ktheta_alpha_zero_returns_zero():
    solver = PyNiteSolver()
    solver._request = _StubRequest(Iz_m=1e-6, L=6.0, alpha_pct=0.0)
    base_node = solver._request.topology.nodes[1]
    assert solver._compute_partial_ktheta(base_node) == 0.0


def test_compute_partial_ktheta_alpha_clamped_to_100():
    # alpha > 100 clamps to 100
    solver = PyNiteSolver()
    solver._request = _StubRequest(Iz_m=1e-6, L=6.0, alpha_pct=150.0)
    base_node = solver._request.topology.nodes[1]
    k_150 = solver._compute_partial_ktheta(base_node)
    solver._request.supports.fixity_percent = 100.0
    k_100 = solver._compute_partial_ktheta(base_node)
    assert k_150 == pytest.approx(k_100)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_partial_base_fixity.py -v`
Expected: FAIL — `AttributeError: 'PyNiteSolver' object has no attribute '_compute_partial_ktheta'`.

- [ ] **Step 3: Implement the helper**

Add this method inside the `PyNiteSolver` class in `portal_frame/solvers/pynite_solver.py`, placed immediately after `_apply_support()`:

```python
    def _compute_partial_ktheta(self, base_node) -> float:
        """Rotational spring stiffness for a partial-fixity base (kN·m/rad).

        kθ = α · 4 · E · Iz / L, where:
          α  — fixity_percent / 100, clamped to [0, 1]
          E  — 200e6 kN/m^2 (matches Steel material)
          Iz — column section Iz_m (m^4)
          L  — distance from base node to the highest node directly above
                (eave / knee), computed from topology coords
        """
        r = self._request
        alpha = max(0.0, min(1.0, r.supports.fixity_percent / 100.0))
        if alpha == 0.0:
            return 0.0

        E = 200e6  # kN/m^2, matches add_material("Steel", 200e6, ...)
        Iz = r.column_section.Iz_m

        # Find knee height: highest node with the same x as the base node.
        x0 = base_node.x
        ys_above = [n.y for n in r.topology.nodes.values()
                    if abs(n.x - x0) < 1e-6 and n.y > base_node.y]
        if not ys_above:
            raise ValueError(
                f"Partial fixity: no column node above base N{base_node.id}."
            )
        L = max(ys_above) - base_node.y

        return alpha * 4.0 * E * Iz / L
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_partial_base_fixity.py -v`
Expected: all three new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add portal_frame/solvers/pynite_solver.py tests/test_partial_base_fixity.py
git commit -m "feat(solver): add _compute_partial_ktheta helper for semi-rigid bases"
```

---

## Task 3: Apply rotational spring in `_apply_support()`

**Files:**
- Modify: `portal_frame/solvers/pynite_solver.py:124-129`
- Test: `tests/test_partial_base_fixity.py`

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_partial_base_fixity.py`:

```python
from portal_frame.solvers.base import AnalysisRequest
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import LoadInput, RafterZoneLoad, WindCase
from portal_frame.io.section_library import load_all_sections


def _base_request(supports: SupportCondition) -> AnalysisRequest:
    sections = load_all_sections()
    col = sections["63020S2"]
    raf = sections["63020S2"]
    geom = PortalFrameGeometry(
        span=10.0, eave_height=4.0, roof_pitch=10.0, roof_pitch_2=10.0,
        bay_spacing=6.0, building_depth=30.0,
    )
    topo = geom.to_topology()
    # Simple downward wind case to generate deflection
    wind = WindCase(
        name="W1",
        wall_windward=0.5, wall_leeward=-0.3, wall_side=-0.3,
        roof_rafter_left=[RafterZoneLoad(0.0, 100.0, -0.5)],
        roof_rafter_right=[RafterZoneLoad(0.0, 100.0, -0.5)],
    )
    loads = LoadInput(
        dead_load_roof=0.15, dead_load_wall=0.10, live_load_roof=0.25,
        wind_cases=[wind],
    )
    return AnalysisRequest(
        span=10.0, eave_height=4.0, roof_pitch=10.0, bay_spacing=6.0,
        topology=topo, column_section=col, rafter_section=raf,
        supports=supports, load_input=loads,
    )


def _apex_dy(output):
    # Worst absolute dy at any station of any member under 'G' case
    out = output["G"]
    worst = 0.0
    for m in out.members.values():
        for s in m.stations:
            if abs(s.dy_local) > abs(worst):
                worst = s.dy_local
    return worst


def test_partial_alpha_zero_matches_pinned():
    req_pinned = _base_request(SupportCondition(left_base="pinned",
                                                right_base="pinned"))
    req_zero = _base_request(SupportCondition(left_base="partial",
                                              right_base="partial",
                                              fixity_percent=0.0))
    s1 = PyNiteSolver(); s1.build_model(req_pinned); s1.solve()
    s2 = PyNiteSolver(); s2.build_model(req_zero); s2.solve()
    dy_pinned = _apex_dy(s1.output.case_results)
    dy_zero = _apex_dy(s2.output.case_results)
    assert dy_pinned == pytest.approx(dy_zero, rel=1e-6, abs=1e-9)


def test_partial_reduces_apex_deflection_monotonically():
    reqs = [
        _base_request(SupportCondition(left_base="partial",
                                       right_base="partial",
                                       fixity_percent=p))
        for p in (0.0, 25.0, 50.0, 75.0, 99.0)
    ]
    dys = []
    for req in reqs:
        s = PyNiteSolver(); s.build_model(req); s.solve()
        dys.append(abs(_apex_dy(s.output.case_results)))
    # Strictly decreasing (or equal only for degenerate cases)
    for a, b in zip(dys, dys[1:]):
        assert b <= a + 1e-9, f"non-monotonic: {dys}"
    assert dys[-1] < dys[0]  # real reduction end-to-end


def test_partial_asymmetric_fixity_produces_unequal_base_moments():
    req = _base_request(SupportCondition(left_base="partial",
                                         right_base="pinned",
                                         fixity_percent=50.0))
    s = PyNiteSolver(); s.build_model(req); s.solve()
    reactions = s.output.case_results["G"].reactions
    base_nodes = sorted(reactions.keys())
    mz_left = reactions[base_nodes[0]].MZ
    mz_right = reactions[base_nodes[-1]].MZ
    # Pinned side must carry ~zero MZ; partial side must not
    assert abs(mz_right) < 1e-3
    assert abs(mz_left) > 1e-2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_partial_base_fixity.py -v -k "partial_alpha_zero or partial_reduces or asymmetric"`
Expected: FAIL — partial branch in `_apply_support()` does not exist; currently falls through to the `"pinned"` else branch so spring is not applied. `test_partial_asymmetric_fixity_produces_unequal_base_moments` will fail because mz_left is ~0.

- [ ] **Step 3: Implement the partial branch**

Replace the body of `_apply_support()` in `portal_frame/solvers/pynite_solver.py` (currently lines 124–129) with:

```python
    def _apply_support(self, model, node, condition):
        name = f"N{node.id}"
        if condition == "fixed":
            model.def_support(name, True, True, True, True, True, True)
        elif condition == "partial":
            # Full restraint on DX, DY, DZ, RX, RY; RZ free and replaced
            # by a rotational spring about the in-plane axis.
            model.def_support(name, True, True, True, True, True, False)
            k_theta = self._compute_partial_ktheta(node)
            if k_theta > 0.0:
                model.def_support_spring(name, "RZ", k_theta)
        else:  # "pinned"
            model.def_support(name, True, True, True, True, True, False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_partial_base_fixity.py -v`
Expected: all partial tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all previously passing tests still pass (244 + new ones).

- [ ] **Step 6: Commit**

```bash
git add portal_frame/solvers/pynite_solver.py tests/test_partial_base_fixity.py
git commit -m "feat(solver): apply MZ rotational spring for partial base fixity"
```

---

## Task 4: Frame-tab GUI — Partial radio + shared % entry

**Files:**
- Modify: `portal_frame/gui/tabs/frame_tab.py:131-170`

- [ ] **Step 1: Replace the SUPPORTS block**

Open `portal_frame/gui/tabs/frame_tab.py`. Locate the existing block from the `app._section_header(parent, "SUPPORTS")` line through the end of the second `Radiobutton` for `right_support` (currently ending at line ~170). Replace that whole block with:

```python
    app._section_header(parent, "SUPPORTS")

    sup_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
    sup_frame.pack(fill="x", **pad)

    def _mk_radio(row, var, text, value):
        return tk.Radiobutton(
            sup_frame, text=text, variable=var, value=value, font=FONT,
            fg=COLORS["fg"], bg=COLORS["bg_panel"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["fg"],
            command=lambda: (app._update_fixity_entry_state(),
                             app._update_preview()),
        )

    # Left base
    tk.Label(sup_frame, text="Left Base", font=FONT, fg=COLORS["fg"],
             bg=COLORS["bg_panel"]).grid(row=0, column=0, sticky="w")
    app.left_support = tk.StringVar(value="pinned")
    _mk_radio(0, app.left_support, "Pinned", "pinned").grid(
        row=0, column=1, padx=(10, 4))
    _mk_radio(0, app.left_support, "Fixed", "fixed").grid(
        row=0, column=2, padx=(0, 4))
    _mk_radio(0, app.left_support, "Partial", "partial").grid(
        row=0, column=3)

    # Right base
    tk.Label(sup_frame, text="Right Base", font=FONT, fg=COLORS["fg"],
             bg=COLORS["bg_panel"]).grid(row=1, column=0, sticky="w",
                                          pady=(4, 0))
    app.right_support = tk.StringVar(value="pinned")
    _mk_radio(1, app.right_support, "Pinned", "pinned").grid(
        row=1, column=1, padx=(10, 4), pady=(4, 0))
    _mk_radio(1, app.right_support, "Fixed", "fixed").grid(
        row=1, column=2, padx=(0, 4), pady=(4, 0))
    _mk_radio(1, app.right_support, "Partial", "partial").grid(
        row=1, column=3, pady=(4, 0))

    # Shared fixity percent entry (row 2, spanning)
    tk.Label(sup_frame, text="Fixity", font=FONT, fg=COLORS["fg"],
             bg=COLORS["bg_panel"]).grid(row=2, column=0, sticky="w",
                                          pady=(6, 0))
    app.fixity_pct = tk.StringVar(value="0")
    app._fixity_entry = tk.Entry(
        sup_frame, textvariable=app.fixity_pct, width=6, font=FONT,
        fg=COLORS["fg"], bg=COLORS["bg_input"],
        insertbackground=COLORS["fg"], relief="flat",
    )
    app._fixity_entry.grid(row=2, column=1, padx=(10, 4), pady=(6, 0),
                           sticky="w")
    tk.Label(sup_frame, text="%", font=FONT, fg=COLORS["fg"],
             bg=COLORS["bg_panel"]).grid(row=2, column=2, sticky="w",
                                          pady=(6, 0))

    def _on_fixity_change(*_):
        # Clamp to [0, 100] silently; ignore empty/unparseable (treated
        # as 0 at analysis time).
        txt = app.fixity_pct.get().strip()
        if txt == "":
            app._update_preview()
            return
        try:
            v = float(txt)
        except ValueError:
            return
        clamped = max(0.0, min(100.0, v))
        if clamped != v:
            app.fixity_pct.set(f"{clamped:g}")
        app._update_preview()

    app.fixity_pct.trace_add("write", _on_fixity_change)

    def _update_fixity_entry_state():
        either_partial = (app.left_support.get() == "partial"
                          or app.right_support.get() == "partial")
        app._fixity_entry.configure(
            state="normal" if either_partial else "disabled")

    app._update_fixity_entry_state = _update_fixity_entry_state
    _update_fixity_entry_state()
```

- [ ] **Step 2: Smoke-test the GUI launches**

Run (Windows bash):
```bash
python -m portal_frame.run_gui 2>/tmp/pf_gui.err &
sleep 3
tasklist | grep -i python
cat /tmp/pf_gui.err
```
Expected: at least one `python.exe` in tasklist, and `/tmp/pf_gui.err` contains no `Traceback`. Manually verify: Partial radio appears on both rows, Fixity entry is disabled by default and becomes enabled when either Partial is selected. Close the GUI when done.

- [ ] **Step 3: Commit**

```bash
git add portal_frame/gui/tabs/frame_tab.py
git commit -m "feat(gui): add Partial base-support radio and shared fixity% entry"
```

---

## Task 5: Wire `fixity_percent` into AnalysisRequest

**Files:**
- Modify: `portal_frame/gui/analysis_runner.py:28-31`

- [ ] **Step 1: Replace the SupportCondition construction**

In `portal_frame/gui/analysis_runner.py`, change the block at lines 28–31 from:

```python
    supports = SupportCondition(
        left_base=app.left_support.get(),
        right_base=app.right_support.get(),
    )
```

to:

```python
    try:
        fixity_pct = float(app.fixity_pct.get() or "0")
    except ValueError:
        fixity_pct = 0.0
    fixity_pct = max(0.0, min(100.0, fixity_pct))

    supports = SupportCondition(
        left_base=app.left_support.get(),
        right_base=app.right_support.get(),
        fixity_percent=fixity_pct,
    )
```

- [ ] **Step 2: Manual verification**

Run the GUI, select Left Base = Partial, set Fixity = 50, click Analyse. Confirm no exception in console and that results panel updates (apex δ should differ from the pinned run with the same inputs).

- [ ] **Step 3: Commit**

```bash
git add portal_frame/gui/analysis_runner.py
git commit -m "feat(gui): pass fixity_percent from frame tab into AnalysisRequest"
```

---

## Task 6: Persistence — save/load `fixity_percent`

**Files:**
- Modify: `portal_frame/gui/persistence.py:43-46, 144-146`

- [ ] **Step 1: Update `collect_config`**

In `portal_frame/gui/persistence.py`, replace the `cfg["supports"] = {...}` block at lines 43–46 with:

```python
    cfg["supports"] = {
        "left_base": app.left_support.get(),
        "right_base": app.right_support.get(),
        "fixity_percent": float(app.fixity_pct.get() or "0"),
    }
```

- [ ] **Step 2: Update `apply_config`**

Replace the three-line block at lines 144–146 with:

```python
    sup = cfg.get("supports", {})
    app.left_support.set(sup.get("left_base", "pinned"))
    app.right_support.set(sup.get("right_base", "pinned"))
    app.fixity_pct.set(f"{float(sup.get('fixity_percent', 0.0)):g}")
    if hasattr(app, "_update_fixity_entry_state"):
        app._update_fixity_entry_state()
```

- [ ] **Step 3: Write the round-trip test**

Append to `tests/test_partial_base_fixity.py`:

```python
def test_support_condition_roundtrip_via_dict():
    # Pure-data round-trip; GUI config I/O exercised via manual smoke test.
    original = SupportCondition(left_base="partial", right_base="pinned",
                                fixity_percent=42.5)
    d = {
        "left_base": original.left_base,
        "right_base": original.right_base,
        "fixity_percent": original.fixity_percent,
    }
    restored = SupportCondition(
        left_base=d["left_base"], right_base=d["right_base"],
        fixity_percent=d["fixity_percent"],
    )
    assert restored == original
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_partial_base_fixity.py::test_support_condition_roundtrip_via_dict -v`
Expected: PASS.

- [ ] **Step 5: GUI round-trip smoke test**

Launch GUI, set Left Base=Partial, Fixity=35, save config to a temp JSON (File → Save Config), close GUI, relaunch, load that JSON, confirm Left Base=Partial and Fixity field shows `35`. (If no Save Config menu exists, rely on auto-restore: close GUI cleanly, relaunch, confirm state persisted via `last_session.json`.)

- [ ] **Step 6: Commit**

```bash
git add portal_frame/gui/persistence.py tests/test_partial_base_fixity.py
git commit -m "feat(persistence): save and restore fixity_percent in config"
```

---

## Task 7: SpaceGass writer header comment (optional polish)

**Files:**
- Modify: `portal_frame/io/spacegass_writer.py`

- [ ] **Step 1: Locate the header-comment emission**

Run: `grep -n "Text File - Version\|^\s*!\|TITLE" portal_frame/io/spacegass_writer.py | head -20`

Identify where the top-of-file header / TITLE / comment lines are written (typically shortly after the `SPACE GASS Text File - Version 1420` line).

- [ ] **Step 2: Emit a note when partial fixity is active**

Immediately after the existing header/version emission, add:

```python
        s = self.request.supports
        if s.left_base == "partial" or s.right_base == "partial":
            f.write(
                f"! NOTE: in-app analysis used partial base fixity "
                f"α = {s.fixity_percent:g} % (kθ = α·4EI/L). "
                f"SpaceGass export retains pinned bases — re-enter "
                f"rotational springs manually in SpaceGass if needed.\n"
            )
```

(Exact file-handle name `f` and access to `self.request.supports` will match local conventions — adjust if the writer uses a different name such as `out`, `stream`, or pulls supports via a different attribute.)

- [ ] **Step 3: Manual verification**

Generate a SpaceGass file with Left Base=Partial, Fixity=50 via the CLI or GUI. Open the `.txt` output and confirm the comment line appears near the top and the `RESTRAINTS` / support section is still written as pinned.

- [ ] **Step 4: Commit**

```bash
git add portal_frame/io/spacegass_writer.py
git commit -m "docs(writer): add SG header comment when partial fixity active"
```

---

## Task 8: Final full-suite run + GUI smoke test

- [ ] **Step 1: Full pytest run**

Run: `python -m pytest tests/ -v`
Expected: all tests (previous 244 + the new partial-fixity tests) PASS.

- [ ] **Step 2: GUI launch + stderr scrape**

Run:
```bash
python -m portal_frame.run_gui 2>/tmp/pf_gui.err &
sleep 3
tasklist | grep -i python
grep -i "Traceback\|Error" /tmp/pf_gui.err || echo "CLEAN"
```
Expected: python.exe alive, stderr shows `CLEAN`.

- [ ] **Step 3: End-to-end manual verification**

In the GUI:
1. Default (Pinned/Pinned) → run Analyse → record apex δ for ULS envelope.
2. Change Left=Partial, Right=Partial, Fixity=0 → run Analyse → apex δ should match step 1 within floating-point tolerance.
3. Set Fixity=50 → run Analyse → apex δ should be visibly smaller.
4. Set Fixity=100 → run Analyse → apex δ should be smaller still but NOT identical to Fixed/Fixed (because linear definition caps at 4EI/L, not infinity).
5. Toggle Left=Fixed, Right=Partial @ 50% → run Analyse → frame response should be asymmetric.

- [ ] **Step 4: Update CLAUDE.md**

Append under the "Roof Types & Geometry" section (or a new "Supports" subsection near it) in `CLAUDE.md`:

```markdown
## Base Supports

Three options per base: **Pinned**, **Fixed**, **Partial**. Partial models a
rotational spring about the in-plane axis using the linear fixity-factor
convention `kθ = α · 4EI/L` (α = user %, E = 200 GPa, Iz from column
section, L = eave/knee height). Applies to both ULS and SLS in-app PyNite
analysis. SpaceGass export stays pinned regardless; a header comment notes
the fixity when partial is active.
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note partial base fixity option in CLAUDE.md"
```

---

## Self-Review

**Spec coverage:**
- Model change → Task 1 ✓
- Solver kθ helper → Task 2 ✓
- Solver spring application → Task 3 ✓
- GUI third radio + shared % entry → Task 4 ✓
- AnalysisRequest wiring → Task 5 ✓
- Persistence → Task 6 ✓
- SpaceGass writer comment → Task 7 ✓
- Tests for α=0 / monotonic / asymmetric → Task 3 ✓
- CLAUDE.md note → Task 8 ✓

**Placeholder scan:** none detected. Task 7 flags a local-variable-name dependency that requires reading the writer file — this is explicit, not a placeholder.

**Type consistency:** `fixity_percent` is a `float` everywhere (dataclass, GUI via `float()`, persistence via `float()`); radio values are the strings `"pinned" | "fixed" | "partial"` throughout; `_compute_partial_ktheta` returns `float` kN·m/rad matching PyNite's model units.
