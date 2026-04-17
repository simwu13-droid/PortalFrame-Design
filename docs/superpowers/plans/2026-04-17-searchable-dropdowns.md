# Searchable Dropdowns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `LabeledCombo` in `portal_frame/gui/widgets.py` so every combobox in the Portal Frame GUI supports type-to-filter without any changes to the 5 existing call sites.

**Architecture:** Modify the existing `LabeledCombo` class in place. Extract the substring-filter as a pure module-level function so the logic can be unit-tested (the widget glue stays manual-verified). Add instance state (`_all_values`, `_last_valid`, `_filtering`) and Tk event bindings for keystroke filtering, Enter/Escape commit/revert, and focus-out revert. All 5 call sites (`col_section`, `raf_section`, `eq_location`, `eq_soil`, `eq_ductility`) pick up the behaviour automatically.

**Tech Stack:** Python 3.13, Tkinter `ttk.Combobox`, pytest.

**Spec:** [docs/superpowers/specs/2026-04-17-searchable-dropdowns-design.md](../specs/2026-04-17-searchable-dropdowns-design.md)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `portal_frame/gui/widgets.py` | Modify | Upgrade `LabeledCombo`: add pure `_filter_substring` helper, add instance state, bind events, implement handlers. |
| `tests/test_widgets.py` | Create | Unit tests for the pure `_filter_substring` helper. |
| (no other files touched) | — | `app.py` call sites unchanged; config, standards, analysis unchanged. |

---

## Task 1: Pure filter helper (TDD)

Extract the case-insensitive substring filter as a module-level function so it can be unit-tested without a Tk display. The widget will call this helper from its `<KeyRelease>` handler.

**Files:**
- Create: `tests/test_widgets.py`
- Modify: `portal_frame/gui/widgets.py` — add `_filter_substring` at module scope, above the class definitions

---

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_widgets.py`:

```python
"""Unit tests for pure helpers in portal_frame.gui.widgets."""

from portal_frame.gui.widgets import _filter_substring


class TestFilterSubstring:
    def test_empty_text_returns_full_list(self):
        master = ["Wellington", "Auckland", "Christchurch"]
        assert _filter_substring(master, "") == master

    def test_whitespace_only_returns_full_list(self):
        master = ["Wellington", "Auckland"]
        assert _filter_substring(master, "   ") == master

    def test_case_insensitive_match(self):
        master = ["Wellington", "WELLINGTON CBD", "Auckland"]
        assert _filter_substring(master, "well") == ["Wellington", "WELLINGTON CBD"]

    def test_substring_matches_middle(self):
        master = ["Lower Hutt", "Upper Hutt", "Auckland"]
        assert _filter_substring(master, "hutt") == ["Lower Hutt", "Upper Hutt"]

    def test_no_match_returns_empty(self):
        master = ["Wellington", "Auckland"]
        assert _filter_substring(master, "xyz") == []

    def test_preserves_master_order(self):
        master = ["Zanzibar", "Auckland", "Wellington"]
        assert _filter_substring(master, "a") == ["Zanzibar", "Auckland"]

    def test_matches_section_codes(self):
        master = ["63020S2", "440180195S2", "50020"]
        assert _filter_substring(master, "S2") == ["63020S2", "440180195S2"]

    def test_empty_master_returns_empty(self):
        assert _filter_substring([], "anything") == []

    def test_does_not_mutate_master(self):
        master = ["a", "b", "c"]
        _filter_substring(master, "a")
        assert master == ["a", "b", "c"]
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `python -m pytest tests/test_widgets.py -v`
Expected: ImportError — `_filter_substring` does not exist yet.

- [ ] **Step 1.3: Implement the helper**

Open `portal_frame/gui/widgets.py` and add the helper near the top of the file, after the imports and before the `LabeledEntry` class definition:

```python
def _filter_substring(master: list[str], text: str) -> list[str]:
    """Case-insensitive substring filter. Preserves master order.

    Empty/whitespace-only text returns the full list.
    """
    needle = text.strip().lower()
    if not needle:
        return list(master)
    return [item for item in master if needle in item.lower()]
```

- [ ] **Step 1.4: Run tests to verify they pass**

Run: `python -m pytest tests/test_widgets.py -v`
Expected: all 9 tests pass.

- [ ] **Step 1.5: Run full test suite to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: 223 + 9 = 232 tests pass.

- [ ] **Step 1.6: Commit**

```bash
git add portal_frame/gui/widgets.py tests/test_widgets.py
git commit -m "$(cat <<'EOF'
feat: add _filter_substring helper for searchable combo filtering

Extract the substring-match logic used by the upcoming LabeledCombo
type-to-filter feature. Pure function, unit-tested independently of
Tk so widget glue can stay manual-verified.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Upgrade `LabeledCombo` constructor

Change `state="readonly"` → `state="normal"`, add instance state (`_all_values`, `_last_valid`, `_filtering`), and bind the five events the handlers in Task 3 will react to.

**Files:**
- Modify: `portal_frame/gui/widgets.py` — replace the current `LabeledCombo.__init__` and surrounding class body

---

- [ ] **Step 2.1: Replace `LabeledCombo.__init__`**

In `portal_frame/gui/widgets.py`, replace the entire `LabeledCombo` class (lines 45-70 of the current file) with the new constructor below. The public methods (`get`, `set`, `set_values`, `bind_change`) are preserved verbatim for now — Task 3 updates them.

Find:

```python
class LabeledCombo(tk.Frame):
    """A label + combobox pair."""

    def __init__(self, parent, label, values=None, default="", width=20):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.columnconfigure(1, weight=1)

        tk.Label(self, text=label, font=FONT, fg=COLORS["fg"], bg=COLORS["bg_panel"],
                 anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6))

        self.var = tk.StringVar(value=default)
        self.combo = ttk.Combobox(self, textvariable=self.var, values=values or [],
                                  width=width, state="readonly", font=FONT_MONO)
        self.combo.grid(row=0, column=1, sticky="ew", padx=2)

    def get(self) -> str:
        return self.var.get()

    def set(self, value):
        self.var.set(value)

    def set_values(self, values):
        self.combo["values"] = values

    def bind_change(self, callback):
        self.combo.bind("<<ComboboxSelected>>", lambda _: callback())
```

Replace with:

```python
class LabeledCombo(tk.Frame):
    """A label + combobox pair with type-to-filter support.

    Typing filters the dropdown by case-insensitive substring. Commits
    only happen on list-item click, Enter (when filter is unique or a
    row is highlighted), or programmatic set(). Invalid typed text
    reverts on Escape or focus-out. Public API unchanged.
    """

    _NAV_KEYSYMS = {
        "Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next",
        "Tab", "ISO_Left_Tab",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        "Caps_Lock", "Return", "Escape",
    }

    def __init__(self, parent, label, values=None, default="", width=20):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.columnconfigure(1, weight=1)

        tk.Label(self, text=label, font=FONT, fg=COLORS["fg"], bg=COLORS["bg_panel"],
                 anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6))

        self._all_values: list[str] = list(values or [])
        self._last_valid: str = default if default in self._all_values else ""
        self._filtering: bool = False
        self._change_callback = None

        self.var = tk.StringVar(value=default)
        self.combo = ttk.Combobox(self, textvariable=self.var, values=self._all_values,
                                  width=width, state="normal", font=FONT_MONO)
        self.combo.grid(row=0, column=1, sticky="ew", padx=2)

        self.combo.bind("<KeyRelease>", self._on_key_release)
        self.combo.bind("<Return>", self._on_return)
        self.combo.bind("<Escape>", self._on_escape)
        self.combo.bind("<FocusOut>", self._on_focus_out)
        self.combo.bind("<<ComboboxSelected>>", self._on_selected)

    # Public API — signatures unchanged.

    def get(self) -> str:
        return self.var.get()

    def set(self, value):
        self.var.set(value)
        if value in self._all_values:
            self._last_valid = value

    def set_values(self, values):
        self._all_values = list(values)
        self.combo["values"] = self._all_values
        if self.var.get() not in self._all_values:
            self.var.set("")
            self._last_valid = ""

    def bind_change(self, callback):
        self._change_callback = callback
```

- [ ] **Step 2.2: Smoke-test the constructor compiles**

Run: `python -c "from portal_frame.gui.widgets import LabeledCombo; print('ok')"`
Expected: `ok` printed with no errors.

- [ ] **Step 2.3: Run the full test suite to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: 232 tests pass (the filter-helper tests still pass; no widget-level tests yet).

- [ ] **Step 2.4: Commit**

```bash
git add portal_frame/gui/widgets.py
git commit -m "$(cat <<'EOF'
refactor: switch LabeledCombo to state=normal with filter state

Prepare for searchable behaviour: add _all_values, _last_valid, and
_filtering instance state, and bind the events the handlers will
attach to. Handlers stubbed in next commit. set() and set_values()
now maintain the master list invariant.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement event handlers

Add the five `_on_*` handlers plus a `_commit` helper to `LabeledCombo`. After this task, the widget is feature-complete per the behaviour contract.

**Files:**
- Modify: `portal_frame/gui/widgets.py` — append methods to the `LabeledCombo` class

---

- [ ] **Step 3.1: Add the handlers and `_commit` helper**

Append these methods to the end of the `LabeledCombo` class (after `bind_change`):

```python
    # --- Internal event handlers ---------------------------------------

    def _on_key_release(self, ev):
        """Filter master list by substring of current entry text."""
        if ev.keysym in self._NAV_KEYSYMS:
            return
        if self._filtering:
            return
        self._filtering = True
        try:
            filtered = _filter_substring(self._all_values, self.var.get())
            self.combo["values"] = filtered
            # Re-open the popdown so the narrowed list is visible.
            if filtered:
                self.combo.event_generate("<Down>")
        finally:
            self._filtering = False

    def _on_return(self, ev):
        """Commit on Enter: exact match > unique filter match > no-op."""
        text = self.var.get()
        if text in self._all_values:
            self._commit(text)
            return "break"
        filtered = _filter_substring(self._all_values, text)
        if len(filtered) == 1:
            self._commit(filtered[0])
            return "break"
        # Otherwise let Tk's default Enter behaviour run (highlighted row
        # in popdown will fire <<ComboboxSelected>>, which commits).
        return None

    def _on_escape(self, ev):
        """Revert entry text to last-committed value."""
        self.var.set(self._last_valid)
        self.combo["values"] = self._all_values
        # Close the popdown if it is open.
        try:
            self.combo.tk.call("ttk::combobox::Unpost", self.combo._w)
        except tk.TclError:
            pass
        return "break"

    def _on_focus_out(self, ev):
        """If typed text is not valid, revert."""
        text = self.var.get()
        if text not in self._all_values:
            self.var.set(self._last_valid)
        self.combo["values"] = self._all_values

    def _on_selected(self, ev):
        """List-item click or default Enter-on-highlighted-row commit."""
        self._commit(self.var.get())

    def _commit(self, value: str) -> None:
        """Update _last_valid and fire the change callback if the value changed."""
        changed = value != self._last_valid
        self.var.set(value)
        self._last_valid = value
        self.combo["values"] = self._all_values
        if changed and self._change_callback is not None:
            self._change_callback()
```

- [ ] **Step 3.2: Re-wire `_on_selected` into `bind_change`**

The old `bind_change` overwrote the `<<ComboboxSelected>>` binding directly. The new code binds `_on_selected` to that event in the constructor and fires the user callback from `_commit`. Verify `bind_change` no longer re-binds the event — it should only store the callback:

Re-read the class. `bind_change` must look exactly like:

```python
    def bind_change(self, callback):
        self._change_callback = callback
```

(No `self.combo.bind(...)` call inside it. If it still binds the event, delete that line.)

- [ ] **Step 3.3: Smoke-test the class compiles**

Run: `python -c "from portal_frame.gui.widgets import LabeledCombo; print('ok')"`
Expected: `ok` with no errors.

- [ ] **Step 3.4: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: 232 tests pass.

- [ ] **Step 3.5: Manual GUI smoke test**

Launch the GUI and verify each of the 5 combos behaves per the spec. Run in a separate terminal:

```bash
python -m portal_frame.run_gui
```

Then check:

1. **`col_section`** (Sections tab, Column)
   - Click the combo. Type `S2`. Dropdown narrows to `63020S2`, `440180195S2`, `650180295S2`. Click one — it commits and the section-info label below updates.
   - Type garbage (`xyz`). Press Escape. Entry reverts to the previously selected section.
   - Type garbage. Click somewhere else (focus away). Entry reverts.
   - Type `63020s2` (lowercase). Press Enter. Commits `63020S2` (case-insensitive unique match).

2. **`raf_section`** — same set as above.

3. **`eq_location`** (Earthquake tab)
   - Click the combo. Type `well`. Dropdown narrows to Wellington rows. Click one — the Z field and fault-distance label below update.
   - Type `hutt`. Dropdown shows Lower Hutt and Upper Hutt.
   - Type `xyz`. Escape. Reverts.

4. **`eq_soil`** — type `C`, see soil classes with C in them, pick one. Soil class updates.

5. **`eq_ductility`** — type part of a preset name, pick one. Updates.

6. **Regression: Analyse still works**
   - Click Analyse with any valid combination. Verify results panel populates, no errors.

- [ ] **Step 3.6: Commit**

```bash
git add portal_frame/gui/widgets.py
git commit -m "$(cat <<'EOF'
feat: implement searchable LabeledCombo event handlers

KeyRelease filters the popdown by substring, Return commits a unique
match, Escape and focus-out revert invalid text. Click-to-commit and
existing bind_change callbacks still fire. All 5 GUI combos (column
section, rafter section, eq location, soil class, ductility preset)
become searchable with zero call-site changes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Verify save/load round-trip

Config round-trip is the only non-widget surface that touches these combo values. Confirm nothing regressed.

**Files:**
- No edits. Verification only.

---

- [ ] **Step 4.1: Manual save/load test**

1. Launch GUI: `python -m portal_frame.run_gui`
2. Pick a non-default column section (e.g. `50020`), non-default rafter section (e.g. `270115N`), and a specific earthquake location (e.g. `Lower Hutt`).
3. Save the config (File → Save, or whichever menu you have). Note the path.
4. Close the GUI. Re-launch.
5. Load the saved config. Verify:
   - Column combo shows `50020`
   - Rafter combo shows `270115N`
   - EQ location shows `Lower Hutt` and Z auto-populates correctly
   - EQ soil class and ductility preset round-trip.

- [ ] **Step 4.2: Confirm no regressions in the full test suite**

Run: `python -m pytest tests/ -v`
Expected: 232 tests pass.

- [ ] **Step 4.3: Final commit (if Step 4.1 surfaced any fix)**

If Step 4.1 passed cleanly, skip this step — nothing to commit. Otherwise fix the issue and commit:

```bash
git add <files>
git commit -m "fix: <describe the regression>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Checklist

Before handing off to execution, the plan writer should confirm:

- [x] **Spec coverage:** Every behaviour-contract row in the spec maps to code in Task 3. Filter helper → Task 1. Constructor state → Task 2. Handlers → Task 3. Save/load → Task 4 verifies.
- [x] **No placeholders:** No TBD/TODO/"add error handling". All code is inline.
- [x] **Type consistency:** `_all_values: list[str]`, `_last_valid: str`, `_filtering: bool`, `_change_callback: Callable | None` — consistent across Task 2 constructor and Task 3 handlers. `_filter_substring` signature matches between Task 1 test and Task 3 call site.
- [x] **Command consistency:** All `pytest` commands use `python -m pytest`. All commit commands use HEREDOC with `Co-Authored-By:` footer per repo convention.
- [x] **Platform:** Windows + bash shell, verified `python` (not `python3`) per CLAUDE.md notes.

---

## Risks and open questions

- **None blocking.** Spec flagged that `<<ComboboxSelected>>` firing on Enter-with-highlighted-row is Tk-version-specific. The plan handles this: `_on_return` returns `None` when no unique match, allowing Tk's default to run (which fires `<<ComboboxSelected>>` → `_on_selected` → `_commit`). Verified by Step 3.5 manual test.
- **Step 3.5 has to be done manually** — no way to automate Tk popdown behaviour without a display server. The filter-logic tests in Task 1 cover the pure-function part; Step 3.5 covers the Tk glue.
