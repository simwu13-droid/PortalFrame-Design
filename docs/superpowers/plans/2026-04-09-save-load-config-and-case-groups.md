# Save/Load Config + Load Case Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JSON save/load with recent files and auto-restore, SLS wind-only combos, and LOAD CASE GROUPS with ULS/SLS sub-groups to SpaceGass output.

**Architecture:** `build_combinations()` gains wind-only SLS combos and returns group range metadata. `SpaceGassWriter` gains `_load_case_groups()` method. GUI gains `_collect_config()`/`_apply_config()` with Save/Load/Recent buttons and auto-restore on startup.

**Tech Stack:** Python 3.12, tkinter, JSON, SpaceGass v14 text format

**Spec:** `docs/superpowers/specs/2026-04-09-save-load-config-and-case-groups-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `portal_frame/standards/combinations_nzs1170_0.py` | Modify | Add wind-only SLS combos, return group range metadata |
| `portal_frame/io/spacegass_writer.py` | Modify | Add `_load_case_groups()` method |
| `portal_frame/gui/app.py` | Modify | Save/Load/Recent buttons, collect/apply config, auto-restore |
| `tests/test_standards.py` | Modify | Tests for wind-only combos and group ranges |
| `tests/test_output.py` | Modify | Test LOAD CASE GROUPS in output |

---

### Task 1: Wind-Only SLS Combos + Group Range Metadata

**Files:**
- Modify: `portal_frame/standards/combinations_nzs1170_0.py`
- Test: `tests/test_standards.py`

- [ ] **Step 1: Write failing test for wind-only SLS combos**

```python
# tests/test_standards.py — append to existing file
class TestWindOnlySLSCombos:
    def test_wind_only_sls_present(self):
        uls, sls, groups = build_combinations(
            wind_case_names=["W1", "W2"], ws_factor=0.75)
        descs = [c[1] for c in sls]
        assert "W1(s) wind only" in descs
        assert "W2(s) wind only" in descs

    def test_wind_only_factor(self):
        uls, sls, groups = build_combinations(
            wind_case_names=["W1"], ws_factor=0.75)
        wo = next(c for c in sls if "wind only" in c[1])
        assert wo[2] == {"W1": 0.75}  # no G, just wind * ws_factor

    def test_groups_returned(self):
        uls, sls, groups = build_combinations(
            wind_case_names=["W1", "W2"])
        assert "uls_gq" in groups
        assert "uls_wind" in groups
        assert "sls_wind" in groups
        assert "sls_wind_only" in groups
        # Each group is (start_index, end_index) — 0-based within the combo list
        assert groups["uls_gq"] == (0, 1)  # 1.35G, 1.2G+1.5Q

    def test_groups_with_eq(self):
        uls, sls, groups = build_combinations(
            wind_case_names=["W1"], eq_case_names=["E+", "E-"])
        assert "uls_eq" in groups
        assert "sls_eq" in groups

    def test_groups_without_eq(self):
        uls, sls, groups = build_combinations(
            wind_case_names=["W1"])
        assert "uls_eq" not in groups
        assert "sls_eq" not in groups
```

- [ ] **Step 2: Run test — expect FAIL** (build_combinations returns 2 values, not 3)

Run: `python -m pytest tests/test_standards.py::TestWindOnlySLSCombos -v`

- [ ] **Step 3: Implement**

Modify `build_combinations()` in `portal_frame/standards/combinations_nzs1170_0.py`:

1. Track start/end indices for each group as combos are appended
2. Append wind-only SLS combos after all other SLS combos
3. Return `(uls, sls, groups)` where `groups` is a dict of `{group_name: (start_idx, end_idx)}`

The groups dict uses 0-based indices into the uls/sls lists:
```python
groups = {}
# ULS groups
groups["uls_gq"] = (0, uls_gq_end_idx)
groups["uls_wind"] = (uls_wind_start_idx, uls_wind_end_idx)  # if wind cases
groups["uls_eq"] = (uls_eq_start_idx, uls_eq_end_idx)  # if EQ cases
# SLS groups
groups["sls_wind"] = (sls_wind_start_idx, sls_wind_end_idx)
groups["sls_eq"] = (sls_eq_start_idx, sls_eq_end_idx)  # if EQ
groups["sls_wind_only"] = (sls_wo_start_idx, sls_wo_end_idx)
```

Wind-only SLS combos appended at end of sls list:
```python
    # Wind-only SLS: pure Ws per wind case (no G)
    if wind_case_names:
        sls_wo_start = sls_n - 1  # 0-based index
        for wname in wind_case_names:
            sls.append((f"SLS-{sls_n}", f"{wname}(s) wind only",
                        {wname: ws_factor})); sls_n += 1
        groups["sls_wind_only"] = (sls_wo_start, sls_n - 2)
```

**IMPORTANT**: Update all existing callers of `build_combinations()` to handle the new 3-tuple return. The callers are:
- `portal_frame/io/spacegass_writer.py:411` — `uls_combos, sls_combos = build_combinations(...)` → change to `uls_combos, sls_combos, combo_groups = ...`

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All pass (111+ existing + new)

- [ ] **Step 5: Commit** (when user says)

---

### Task 2: LOAD CASE GROUPS in SpaceGass Output

**Files:**
- Modify: `portal_frame/io/spacegass_writer.py:112-127` (write method), `399-439` (_combinations method)
- Test: `tests/test_output.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_output.py — append
def test_load_case_groups_in_output():
    """SpaceGass output contains LOAD CASE GROUPS for ULS and SLS."""
    output = _generate_default_output()  # existing helper
    assert "LOAD CASE GROUPS" in output
    lines = output.split("\n")
    idx = next(i for i, l in enumerate(lines) if "LOAD CASE GROUPS" in l)
    # Should have at least ULS and SLS parent groups
    group_lines = []
    for line in lines[idx+1:]:
        if line.strip() == "" or line.startswith(("TITLES", "END")):
            break
        group_lines.append(line.strip())
    assert any('"ULS"' in l for l in group_lines)
    assert any('"SLS"' in l for l in group_lines)
    assert any('"ULS-Wind"' in l for l in group_lines)
    assert any('"SLS-Wind Only"' in l for l in group_lines)
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement `_load_case_groups()`**

In `_combinations()`, store the groups dict and combo counts:
```python
        self._combo_groups = combo_groups
        self._uls_count = len(uls_combos)
        self._sls_count = len(sls_combos)
```

Add new method:
```python
    def _load_case_groups(self) -> str:
        """Generate LOAD CASE GROUPS section."""
        if not hasattr(self, '_uls_count') or self._uls_count == 0:
            return ""
        groups = getattr(self, '_combo_groups', {})
        uls_start = 101
        sls_start = 201
        uls_end = uls_start + self._uls_count - 1
        sls_end = sls_start + self._sls_count - 1

        lines = ["LOAD CASE GROUPS"]
        gid = 1

        # ULS parent group
        lines.append(f'{gid},"ULS",{uls_start},-{uls_end}'); gid += 1

        # ULS sub-groups
        for gname, label in [("uls_gq", "ULS-GQ"), ("uls_wind", "ULS-Wind"),
                              ("uls_eq", "ULS-EQ")]:
            if gname in groups:
                s, e = groups[gname]
                lines.append(f'{gid},"{label}",{uls_start + s},-{uls_start + e}')
                gid += 1

        # SLS parent group
        lines.append(f'{gid},"SLS",{sls_start},-{sls_end}'); gid += 1

        # SLS sub-groups
        for gname, label in [("sls_wind", "SLS-Wind"), ("sls_eq", "SLS-EQ"),
                              ("sls_wind_only", "SLS-Wind Only")]:
            if gname in groups:
                s, e = groups[gname]
                lines.append(f'{gid},"{label}",{sls_start + s},-{sls_start + e}')
                gid += 1

        lines.append("")
        return "\n".join(lines)
```

In `write()` parts list (line 112), insert after `_combinations()`:
```python
            self._combinations(),
            self._load_case_groups(),  # NEW
            self._titles(),
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v`

- [ ] **Step 5: Commit** (when user says)

---

### Task 3: Save/Load Config — Collect and Apply

**Files:**
- Modify: `portal_frame/gui/app.py`

- [ ] **Step 1: Implement `_collect_config()`**

Add method to `PortalFrameApp` that serializes all GUI fields to a dict. The method reads every `LabeledEntry.get()`, `StringVar.get()`, and `BooleanVar.get()` across all tabs and returns a nested dict with `"version": 1` at the top.

Key sections: geometry, sections, supports, loads, wind, earthquake (with enabled flag), crane (with enabled flag + dynamic transverse rows).

- [ ] **Step 2: Implement `_apply_config(cfg)`**

Add method that populates all GUI fields from a config dict. Sets every widget value, clears/rebuilds dynamic crane transverse rows, fires toggles for earthquake/crane enable states, and calls `_auto_generate_wind_cases()` + `_update_preview()` at the end.

- [ ] **Step 3: Verify roundtrip**

Launch GUI, set all fields to non-default values, call `_collect_config()` via Python console, call `_apply_config()` with the result, verify all fields match.

---

### Task 4: Save/Load/Recent Buttons in GUI

**Files:**
- Modify: `portal_frame/gui/app.py:146-157` (button row area)

- [ ] **Step 1: Add buttons to the button row**

After the Generate button (line 157), add Save, Load, and Recent buttons:
```python
        tk.Button(btn_row, text=" SAVE ", font=FONT_BOLD,
                  fg=COLORS["fg_bright"], bg=COLORS["bg_input"],
                  relief="flat", cursor="hand2", padx=8, pady=4,
                  command=self._save_config).pack(side="left", padx=(8, 0))
        tk.Button(btn_row, text=" LOAD ", font=FONT_BOLD,
                  fg=COLORS["fg_bright"], bg=COLORS["bg_input"],
                  relief="flat", cursor="hand2", padx=8, pady=4,
                  command=self._load_config).pack(side="left", padx=(4, 0))
```

- [ ] **Step 2: Implement `_save_config()`**

```python
    def _save_config(self):
        import json
        cfg = self._collect_config()
        path = filedialog.asksaveasfilename(
            title="Save Portal Frame Config",
            defaultextension=".json",
            filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")],
        )
        if path:
            with open(path, "w") as f:
                json.dump(cfg, f, indent=2)
            self._add_recent(path)
            self.status_label.config(text=f"Saved: {os.path.basename(path)}")
```

- [ ] **Step 3: Implement `_load_config()`**

```python
    def _load_config(self):
        import json
        path = filedialog.askopenfilename(
            title="Load Portal Frame Config",
            filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")],
        )
        if path:
            try:
                with open(path, "r") as f:
                    cfg = json.load(f)
                self._apply_config(cfg)
                self._add_recent(path)
                self.status_label.config(text=f"Loaded: {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load: {e}")
```

- [ ] **Step 4: Implement recent files**

App data directory: `~/.portal_frame/` (create on first use).

```python
    _APP_DIR = os.path.join(os.path.expanduser("~"), ".portal_frame")
    _RECENT_FILE = os.path.join(_APP_DIR, "recent.json")
    _LAST_SESSION = os.path.join(_APP_DIR, "last_session.json")

    def _add_recent(self, path):
        recent = self._load_recent_list()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]
        os.makedirs(self._APP_DIR, exist_ok=True)
        with open(self._RECENT_FILE, "w") as f:
            json.dump(recent, f)
        self._update_recent_menu()

    def _load_recent_list(self) -> list:
        try:
            with open(self._RECENT_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
```

Add a "Recent" dropdown (Combobox or Menubutton) next to Save/Load buttons.

- [ ] **Step 5: Implement auto-save on exit, auto-restore on startup**

```python
    # In __init__, after _build_ui():
    self.protocol("WM_DELETE_WINDOW", self._on_close)
    self._auto_restore()

    def _on_close(self):
        try:
            cfg = self._collect_config()
            os.makedirs(self._APP_DIR, exist_ok=True)
            with open(self._LAST_SESSION, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
        self.destroy()

    def _auto_restore(self):
        try:
            with open(self._LAST_SESSION) as f:
                cfg = json.load(f)
            self._apply_config(cfg)
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            pass
```

- [ ] **Step 6: Run all tests and launch GUI**

Run: `python -m pytest tests/ -v` (all pass)
Launch GUI → set values → Save → change values → Load → verify restored → close → reopen → verify auto-restored

- [ ] **Step 7: Commit** (when user says)

---

## Verification

1. `python -m pytest tests/ -v` — all 111+ tests pass
2. **Wind-only SLS**: Generate output → verify "W1(s) wind only" etc. appear in COMBINATIONS with only wind factor, no G
3. **LOAD CASE GROUPS**: Generate output → verify section present with ULS, ULS-GQ, ULS-Wind, SLS, SLS-Wind, SLS-Wind Only groups
4. **Save/Load roundtrip**: Complex frame (crane+EQ+wind) → Save → change all → Load → verify → Generate → compare
5. **Auto-restore**: Set values → close app → reopen → verify all values restored
6. **Recent files**: Save 3 configs → verify Recent dropdown shows all 3
7. Open generated file in SpaceGass v14 → verify load case groups display correctly
