# Partial Base Fixity — Design Spec

**Date:** 2026-04-24
**Author:** nat@formsteel.co.nz
**Status:** Approved for planning

## Summary

Add a third base-support option — **Partial** — alongside the existing
Pinned and Fixed options. When Partial is selected on either column base,
the in-app PyNite solver models that base as a rotational spring about the
in-plane axis (MZ). The SpaceGass text export is unchanged and remains
pinned.

## Motivation

Real portal-frame column bases are neither perfectly pinned nor perfectly
fixed. Bolted base plates on concrete footings behave as semi-rigid
connections. Assuming a pin over-predicts apex deflection and eave drift
for serviceability checks, while assuming a full fix under-predicts base
moments. Allowing the engineer to dial in a fixity percentage produces a
more realistic frame response for both ULS and SLS in-app results.

## Formula

Linear rotational-stiffness model keyed to the column's own bending
stiffness:

```
kθ = α · (4 · E · Iz) / L
```

Where:
- `α` — user-entered fixity fraction, 0.0 to 1.0 (entered as 0–100 %)
- `E`  — Young's modulus of the column material (steel: 200 GPa)
- `Iz` — column section second moment of area about the in-plane bending
        axis (already stored on `CFS_Section.Iz_m`, in m⁴)
- `L`  — column length from base to knee (eave height, in m)

Interpretation:
- α = 0 % → kθ = 0 (pin)
- α = 25 % → kθ = 1.0 · EI/L
- α = 50 % → kθ = 2.0 · EI/L
- α = 100 % → kθ = 4.0 · EI/L (the slope-deflection "fixed-far-end"
  reference; treated as the maximum realistic base stiffness, **not** as
  a true rigid fix)

The linear definition is consistent with common NZ/AU practical design
guides and gives 20 % → 0.8 · EI/L.

## Scope

**In scope**

- Per-side Pinned / Fixed / **Partial** selection on Frame tab.
- Single shared fixity-percent input applied to whichever side(s) are
  Partial.
- In-app PyNite analysis uses the computed `kθ` as a rotational spring on
  the MZ DOF of the affected base nodes.
- Applies to both ULS and SLS combinations in-app (one model per case,
  same base condition across all cases).
- Persistence (save/restore via `gui/persistence.py`).
- Unit tests covering α = 0 / intermediate / 100 endpoints.

**Out of scope**

- SpaceGass text-file export — remains pinned. A header comment is added
  to note the in-app analysis used a partial fixity value.
- Per-case or per-combo base stiffness variation.
- Nonlinear or moment-rotation-curve base models.
- Design checks on the base connection itself (bolt group, baseplate).
- Out-of-plane (RX, RY) partial fixity — only MZ is affected.

## Architecture

Four layers touched: model, solver, GUI, persistence. No changes to the
standards package, writer, or canvas/rendering code.

### 1. Model — `portal_frame/models/supports.py`

Extend `SupportCondition` with a single shared `fixity_percent` field.
Legal values of the two `_base` fields become `"pinned" | "fixed" | "partial"`.

```python
@dataclass
class SupportCondition:
    left_base: str = "pinned"         # "pinned" | "fixed" | "partial"
    right_base: str = "pinned"        # "pinned" | "fixed" | "partial"
    fixity_percent: float = 0.0       # 0–100, used when either side == "partial"
```

Rationale for a single shared percent (not one per side): confirmed with
user that a single global value is the desired UX; reduces input burden
and matches typical symmetric detailing.

Validation (at GUI layer, not in the dataclass — dataclasses stay pure):
clamp to `[0.0, 100.0]`; warn if `> 100`; treat empty / unparseable as 0.

### 2. Solver — `portal_frame/solvers/pynite_solver.py`

Update `_apply_support()` to handle the new `"partial"` case.

```python
def _apply_support(self, model, node, condition):
    name = f"N{node.id}"
    if condition == "fixed":
        model.def_support(name, True, True, True, True, True, True)
    elif condition == "partial":
        # Translate full restraint on DX, DY, DZ, RX, RY; leave RZ free,
        # then add a rotational spring about the MZ DOF.
        model.def_support(name, True, True, True, True, True, False)
        kθ = self._compute_partial_ktheta(node)  # kN·m/rad
        model.def_support_spring(name, "RZ", kθ, direction=None)
    else:  # "pinned"
        model.def_support(name, True, True, True, True, True, False)
```

`_compute_partial_ktheta(node)` resolves `E`, `Iz`, and `L` as follows:

- `E` — constant 200e6 kN/m² (matches `add_material("Steel", 200e6, ...)`)
- `Iz` — `self._request.column_section.Iz_m`
- `L` — length of the column member attached to this base node, computed
  from topology node coordinates (handles mono-roof and crane-bracket
  cases where the column may be split into sub-members — use the
  full base-to-knee distance, not the sub-member length)
- `α` — `self._request.supports.fixity_percent / 100.0`, clamped to
  `[0.0, 1.0]`

Return: `kθ = α * 4.0 * E * Iz / L` in kN·m/rad.

Note on PyNite API: `FEModel3D.def_support_spring(node_name, dof, stiffness, direction=None)`
exists in PyNiteFEA 2.4.1. Confirm exact signature during implementation;
fall back to `add_node_load`-equivalent workaround only if the API differs.

### 3. GUI — `portal_frame/gui/tabs/frame_tab.py`

Extend both existing base-support rows with a third radio button, plus a
shared percent entry.

Layout target (grid coordinates relative to `sup_frame`):

```
Row 0: Left Base    [Pinned] [Fixed] [Partial]    │
                                                   │  Fixity [ __ ]%
Row 1: Right Base   [Pinned] [Fixed] [Partial]    │
```

- Two new `Radiobutton` widgets with `value="partial"` added to rows 0
  and 1 respectively.
- One new `LabeledEntry` ("Fixity") placed in column 3 spanning rows 0–1,
  or on its own row immediately below depending on what fits the existing
  panel width.
- The entry is enabled iff `left_support == "partial"` **or**
  `right_support == "partial"`. A small trace on both StringVars drives a
  `_update_fixity_entry_state()` helper that toggles the entry's `state`.
- Default value: `0` (preserves current behaviour — if a user selects
  Partial and leaves the box at 0, the result is identical to Pinned).
- Out-of-range input (negative, > 100, or unparseable) is clamped and the
  entry's displayed value is updated to the clamped number.

Wiring into the analysis pipeline (`gui/analysis_runner.py` /
`gui/persistence.py`) reads `fixity_percent` off the StringVar and stores
it on the `SupportCondition` built from the tab state.

### 4. Persistence — `portal_frame/gui/persistence.py`

Add `fixity_percent` to the JSON config schema. Missing key on load →
default to 0.0 (backward compatibility with existing configs). Update
`_collect_config()` and `_apply_config()` mirror functions.

### 5. SpaceGass Writer — no code change

Optional polish: add a one-line comment in the writer header when either
base is Partial:

```
! NOTE: in-app PyNite analysis used partial base fixity α = 25 %.
!       SpaceGass export remains pinned — re-enter base springs manually
!       in SpaceGass if matching the in-app behaviour is required.
```

## Data flow

```
Frame tab radios + %     ──►  SupportCondition(left_base="partial",
                                               right_base="pinned",
                                               fixity_percent=25.0)
                                              │
                                              ▼
AnalysisRequest.supports  ──►  PyNiteSolver._apply_support()
                                              │
                                              ▼
  base node with "partial"      ─►  def_support(... MZ=False) +
                                    def_support_spring("RZ", kθ)
  base node with "pinned"       ─►  def_support(... MZ=False)
  base node with "fixed"        ─►  def_support(... all=True)
```

## Error handling

- **α = 100 % and spring behaviour** — `kθ = 4 EI/L` is finite, not
  infinite. This is intentional per the linear convention. Users who want
  a truly rigid base should select Fixed instead.
- **Missing PyNite API** — if `def_support_spring` is unavailable in the
  installed PyNiteFEA version, surface a clear RuntimeError at
  `build_model()` time rather than silently reverting to pinned.
- **Degenerate topology** — if a base node somehow has no attached column
  (should not happen), raise a descriptive error naming the node id.
- **Numerical stability** — a very small kθ (≪ other spring stiffnesses
  in the model) is still well-conditioned because all other DOFs at the
  base are fully restrained.

## Testing

Unit tests in `tests/test_pynite_partial_fixity.py` (new file):

1. **α = 0 matches pinned** — run two analyses with identical loads, one
   with `left="partial", right="partial", fixity_percent=0` and the other
   pinned-pinned. Assert apex δ, eave drift, and base reactions match to
   floating-point tolerance.
2. **Monotonic reduction** — vary α across `[0, 25, 50, 75, 99]` and
   assert `|apex δ|` and `|eave drift|` decrease monotonically as α
   increases (wind case W5, gable frame, representative span/eave).
3. **kθ formula** — unit-level test of `_compute_partial_ktheta` against
   hand-computed values for known E, Iz, L, α.
4. **Symmetric vs asymmetric fixity** — test `(left=partial, right=pinned)`
   produces an asymmetric moment diagram with higher base moment on the
   partial side.
5. **Config round-trip** — save a config with Partial support, reload,
   assert `fixity_percent` preserved.

GUI smoke test: launch `python -m portal_frame.run_gui &`, verify no
Traceback in stderr, verify Partial radio renders and the entry
enable/disable behaviour works.

## Migration & backward compatibility

- Existing saved configs without `fixity_percent` load with 0.0 and
  current behaviour unchanged.
- Existing `"pinned"` / `"fixed"` string values on `SupportCondition` are
  unchanged.
- No data migration needed.

## Open items

None — all previously open items resolved with the user:
- Formula: linear `α · 4EI/L` ✓
- Applies to ULS and SLS ✓
- SpaceGass stays pinned ✓
- Single shared fixity % ✓
- Per-side Pinned/Fixed/Partial radios (option A) ✓
