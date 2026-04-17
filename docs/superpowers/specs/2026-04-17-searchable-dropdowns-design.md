# Searchable Dropdowns — Design

**Date:** 2026-04-17
**Status:** Approved — ready for implementation planning
**Scope:** `portal_frame/gui/widgets.py::LabeledCombo`

## Problem

Five `LabeledCombo` instances in the GUI currently run with `state="readonly"` — the user can only scroll and click. The lists are getting longer:

| Combo | Items | Painful? |
|---|---|---|
| `eq_location` | 129 (NZ hazard table) | Yes |
| `col_section`, `raf_section` | ~14 CFS sections | Moderate |
| `eq_soil`, `eq_ductility` | 5 each | Minor, but inconsistent with others |

Engineers asked for type-to-filter so they can jump straight to an entry instead of scrolling.

## Scope

**In:** Upgrade the existing `LabeledCombo` widget to support type-to-filter. All 5 existing call sites inherit the behaviour automatically.

**Out:** No new widget class, no per-site opt-in flag, no changes to caller code in `app.py`. No changes to save/load config, diagrams, or standards logic.

## Design decisions (agreed with user)

1. **Scope:** all 5 combos become searchable (Q1 → B). One class, one behaviour, no mixed types in the app.
2. **Invalid-text handling:** readonly-like semantics. Typing filters but does not commit. Only a list-item click or Enter-on-unique-match commits a value (Q2 → B).
3. **Matching:** case-insensitive **substring** match. `well` finds `Wellington CBD`; `S2` finds `63020S2`, `440180195S2`, `650180295S2` (Q3.1).
4. **Dropdown auto-opens on keystroke** so user sees narrowed list without extra click (Q3.2).
5. **Enter commits:** if exactly one match remains, Enter picks it; else Enter commits the highlighted row; else no-op (Q3.3).
6. **Escape reverts** the typed text to the last-committed value; closes popdown (Q3.4).
7. **Focus-out reverts** if current text is not in the master list (Q3.5).
8. **Implementation approach:** modify `LabeledCombo` in place (Approach A). Chosen for future-scalability — every new combo added later inherits the behaviour for free, with no flag to remember and no risk of bifurcation.

## Behaviour contract

| Event | Behaviour |
|---|---|
| User types a character | On `<KeyRelease>`, filter `_all_values` by case-insensitive substring of entry text. Update `combo['values']` to filtered list. Open popdown if not already open. Do not change `_last_valid`. Do not fire `<<ComboboxSelected>>`. |
| User clicks a list item | Commit value → update `_last_valid`. Close popdown. Fire `<<ComboboxSelected>>` (existing callbacks via `bind_change` run). Restore full master list for next filter. |
| User presses Enter | If entry text is an exact match in `_all_values` → commit, update `_last_valid`, fire callback. Else if exactly one filtered match → commit that match. Else if a popdown row is highlighted → commit that row. Else no-op. |
| User presses Escape | Restore entry text to `_last_valid`. Close popdown. Restore full master list. No callback. |
| User tabs / clicks away (`<FocusOut>`) | If entry text is not an exact match in `_all_values` → restore to `_last_valid`. Restore full master list. No callback. |
| Arrow keys (`Up`/`Down`/`Left`/`Right`/`Home`/`End`) | Do not trigger filter — they navigate the popdown or entry cursor. |
| `set(value)` programmatic | Update entry text to `value`. If `value` is in `_all_values`, update `_last_valid`. (Mirrors current behaviour — callers may set arbitrary text; no regression.) |
| `set_values(values)` programmatic | Replace `_all_values`. If current value still in the new list, keep it; else revert to empty. Reset filter. |
| `bind_change(cb)` | Unchanged: wires `<<ComboboxSelected>>` → cb. Fires only on commit events, not keystrokes. |

## Internal state

Added to `LabeledCombo.__init__`:

```python
self._all_values: list[str] = list(values or [])
self._last_valid: str = default if default in self._all_values else ""
self._filtering: bool = False   # re-entrancy guard
```

Constructor change:
- `state="readonly"` → `state="normal"`
- Bind handlers: `<KeyRelease>`, `<Return>`, `<Escape>`, `<FocusOut>`, `<<ComboboxSelected>>`

## Method plan

| Method | Purpose |
|---|---|
| `_on_key_release(ev)` | Ignore navigation/modifier keys. Filter `_all_values` by `substring.lower() in item.lower()`. Assign filtered list to `combo['values']`. Open popdown via `combo.event_generate('<Down>')` only if not already open, guarded by `_filtering`. |
| `_on_return(ev)` | Commit logic (exact match > unique-filter match > highlighted popdown row > no-op). |
| `_on_escape(ev)` | Revert entry text to `_last_valid`, restore full list, close popdown. |
| `_on_focus_out(ev)` | If current text not in `_all_values`, revert to `_last_valid` and restore full list. |
| `_on_selected(ev)` | Commit: update `_last_valid` to `self.var.get()`, restore full master list (so next filter starts clean). |
| `_commit(value)` | Shared helper: set `self.var`, update `_last_valid`, restore full list, fire callback if changed. |
| Public `get`/`set`/`set_values`/`bind_change` | Signatures unchanged. |

## Tkinter gotchas addressed

- **Recursive filter trigger:** writing to `combo['values']` inside `_on_key_release` can fire events — use `_filtering` flag as re-entrancy guard.
- **Arrow-key navigation into the popdown** must not re-filter or the user can't select. Skip filter if `ev.keysym` in `{Up, Down, Left, Right, Home, End, Tab, Shift_L, Shift_R, Control_L, Control_R, Return, Escape}`.
- **Popdown auto-open across Tk versions:** `event_generate('<Down>')` is the reliable path when the entry has focus. `combo.tk.call(combo._w, 'post')` varies; avoid.
- **`state="normal"` allows typing** but still supports programmatic `set()` and dropdown selection. No other state needed.
- **Tkinter on Windows 11** (user's platform): verified by prior work in this repo that `ttk.Combobox` in `state="normal"` behaves as expected with the bindings above.

## Testing

No logic tests — this is pure UI widget code and the behaviour is driven by Tk events that are hard to exercise in pytest without a display. Verification is manual:

1. Launch GUI (`python -m portal_frame.run_gui`).
2. For each of the 5 combos:
   - Click, type partial string → dropdown narrows.
   - Type garbage → Escape reverts.
   - Type garbage → click away → reverts.
   - Type unique match → Enter commits.
   - Type ambiguous partial → arrow down + Enter commits highlighted.
   - Click a list item → commits and fires existing callback (e.g., Z auto-fill on `eq_location`).
3. Save + load config — committed values round-trip unchanged (no regression in `io/config.py`).
4. Run full pytest suite — must remain at 223 passing (no regressions).

## Files changed

| File | Change |
|---|---|
| `portal_frame/gui/widgets.py` | Upgrade `LabeledCombo` per design above |
| (none else) | No callers change |

## Risks

- **Low:** `LabeledEntry` is untouched; only `LabeledCombo` changes.
- **Medium:** `eq_location`'s auto-fill of Z and fault-distance label depends on `<<ComboboxSelected>>` firing. Must verify manually that Enter-commits and click-commits both fire that event (spec above says they do — needs verification during implementation).
- **Low:** The current `default` passed to some combos may not exist in the initial `values` list (e.g., empty default). `_last_valid` initialisation must handle this — spec handles via conditional.

## Out of scope

- Keyboard-driven list scrolling beyond arrow keys (Page Up/Down).
- Fuzzy matching (e.g., Levenshtein) — substring is enough.
- Highlighting matched substring in popdown rows.
- Multi-select combos (not used anywhere).
