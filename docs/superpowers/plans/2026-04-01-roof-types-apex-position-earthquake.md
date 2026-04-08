# Roof Types, Apex Position & Earthquake Loading — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add gable/mono-roof selection with variable apex position (with pitch warnings), and implement NZS 1170.5:2004 equivalent static earthquake loading with forces lumped to portal frame knee nodes.

**Architecture:** Three independent subsystems that touch shared files at well-defined interfaces: (1) Geometry model gets `roof_type` and `apex_position_pct` fields, changing `to_topology()` to place the ridge at an arbitrary X position or eliminate it for mono-roof; (2) Wind zone splitting uses the new apex position instead of hardcoded 50%; (3) Earthquake module adds spectral calculations, JOINTLOADS output, and EQ load combinations. All three converge in `gui/app.py` and `io/spacegass_writer.py`.

**Tech Stack:** Python 3.11+, tkinter, pytest, dataclasses

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `portal_frame/models/geometry.py` | Add `roof_type`, `apex_position_pct` to `PortalFrameGeometry`; handle mono-roof (3 nodes) vs gable (5 nodes) in `to_topology()` |
| Modify | `portal_frame/models/loads.py` | `EarthquakeInputs` already exists — no changes needed |
| Create | `portal_frame/standards/earthquake_nzs1170_5.py` | NZ hazard factors, Ch table, spectral shape factor, `calculate_earthquake_forces()` |
| Modify | `portal_frame/standards/combinations_nzs1170_0.py` | Add `eq_case_names` parameter to `build_combinations()` for EQ ULS/SLS combos |
| Modify | `portal_frame/standards/wind_nzs1170_2.py` | Pass `split_pct` from apex position instead of hardcoded 50.0 in `generate_standard_wind_cases()` |
| Modify | `portal_frame/io/spacegass_writer.py` | Handle mono-roof members, add JOINTLOADS section for EQ, integrate EQ case numbering |
| Modify | `portal_frame/gui/app.py` | Roof type selector, apex position slider, pitch warnings, Earthquake tab, EQ preview |
| Modify | `portal_frame/gui/preview.py` | Render mono-roof (no ridge node), render EQ arrows at knee nodes |
| Modify | `portal_frame/io/config.py` | Add `roof_type`, `apex_position_pct`, `earthquake` to config schema |
| Modify | `portal_frame/solvers/base.py` | Add `roof_type` to `AnalysisRequest` (for context) |
| Modify | `tests/test_models.py` | Tests for mono-roof topology, variable apex gable topology |
| Modify | `tests/test_standards.py` | Tests for earthquake calculations, EQ combinations, variable apex wind splitting |
| Modify | `tests/test_output.py` | Tests for mono-roof output, JOINTLOADS output |

---

## Part A: Roof Types & Variable Apex Position

### Task 1: Geometry Model — Variable Apex Position for Gable Roof

**Files:**
- Modify: `portal_frame/models/geometry.py:57-92`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for variable apex gable roof**

Add to `tests/test_models.py`:

```python
class TestVariableApexGable:
    def test_apex_at_midspan_default(self):
        """Default apex_position_pct=50 produces same as current behavior."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="gable", apex_position_pct=50.0,
        )
        topo = geom.to_topology()
        assert len(topo.nodes) == 5
        assert len(topo.members) == 4
        assert topo.nodes[3].x == pytest.approx(6.0)  # span/2

    def test_apex_at_one_third(self):
        """Apex at 33% of span."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="gable", apex_position_pct=33.333,
        )
        topo = geom.to_topology()
        assert len(topo.nodes) == 5
        assert topo.nodes[3].x == pytest.approx(4.0, rel=1e-2)
        # Ridge height: eave + apex_x * tan(pitch)
        expected_ridge = 4.5 + 4.0 * math.tan(math.radians(5.0))
        assert topo.nodes[3].y == pytest.approx(expected_ridge, rel=1e-3)

    def test_apex_at_two_thirds(self):
        """Apex at 67% — left rafter is longer than right."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="gable", apex_position_pct=66.667,
        )
        topo = geom.to_topology()
        assert topo.nodes[3].x == pytest.approx(8.0, rel=1e-2)

    def test_ridge_height_uses_apex_distance(self):
        """Ridge = eave + apex_x * tan(pitch), where apex_x is shorter side."""
        geom = PortalFrameGeometry(
            span=20.0, eave_height=6.0, roof_pitch=10.0, bay_spacing=8.0,
            roof_type="gable", apex_position_pct=30.0,
        )
        apex_x = 20.0 * 0.30  # 6.0m
        expected = 6.0 + apex_x * math.tan(math.radians(10.0))
        assert geom.ridge_height == pytest.approx(expected, rel=1e-3)

    def test_left_rafter_pitch_differs_from_right(self):
        """When apex is off-center, left and right rafter pitches differ."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="gable", apex_position_pct=33.333,
        )
        topo = geom.to_topology()
        ridge_y = topo.nodes[3].y
        rise = ridge_y - 4.5
        left_run = topo.nodes[3].x  # ~4.0m
        right_run = 12.0 - topo.nodes[3].x  # ~8.0m
        left_pitch = math.degrees(math.atan2(rise, left_run))
        right_pitch = math.degrees(math.atan2(rise, right_run))
        assert left_pitch == pytest.approx(5.0, rel=1e-2)
        assert right_pitch < left_pitch  # right is shallower
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py::TestVariableApexGable -v`
Expected: FAIL — `PortalFrameGeometry.__init__() got unexpected keyword arguments`

- [ ] **Step 3: Implement variable apex in geometry model**

In `portal_frame/models/geometry.py`, modify `PortalFrameGeometry`:

```python
@dataclass
class PortalFrameGeometry:
    """Portal frame parameters — generates a 2D topology.
    
    Supports gable roof (5-node, 4-member with variable apex position)
    and mono-roof (4-node, 3-member single slope).
    """
    span: float           # Clear span (m)
    eave_height: float    # Eave height (m)
    roof_pitch: float     # Roof pitch (degrees) — for gable, this is the steeper side
    bay_spacing: float    # Bay spacing / tributary width (m) — for load calc
    roof_type: str = "gable"           # "gable" or "mono"
    apex_position_pct: float = 50.0    # Apex position as % of span (0-100), gable only

    @property
    def apex_x(self) -> float:
        """X coordinate of the apex/ridge."""
        if self.roof_type == "mono":
            return self.span  # ridge is at far end for mono
        return self.span * self.apex_position_pct / 100.0

    @property
    def ridge_height(self) -> float:
        if self.roof_type == "mono":
            return self.eave_height + self.span * math.tan(math.radians(self.roof_pitch))
        # For gable: ridge height defined by pitch on the shorter side from apex
        apex_dist = self.apex_x
        return self.eave_height + apex_dist * math.tan(math.radians(self.roof_pitch))

    @property
    def left_pitch(self) -> float:
        """Left rafter pitch in degrees."""
        if self.roof_type == "mono":
            return self.roof_pitch
        return self.roof_pitch  # Left side defines the pitch

    @property
    def right_pitch(self) -> float:
        """Right rafter pitch in degrees."""
        if self.roof_type == "mono":
            return self.roof_pitch
        rise = self.ridge_height - self.eave_height
        right_run = self.span - self.apex_x
        if right_run <= 0:
            return 90.0
        return math.degrees(math.atan2(rise, right_run))

    def to_topology(self) -> FrameTopology:
        """Build the 2D portal frame topology.
        
        Gable: 5 nodes, 4 members (variable apex position)
        Mono:  4 nodes, 3 members (single slope, no ridge node)
        """
        if self.roof_type == "mono":
            return self._build_mono_topology()
        return self._build_gable_topology()

    def _build_gable_topology(self) -> FrameTopology:
        """5-node gable frame with apex at apex_position_pct of span."""
        ridge = self.ridge_height
        apex_x = self.apex_x
        nodes = {
            1: Node(1, 0.0, 0.0),
            2: Node(2, 0.0, self.eave_height),
            3: Node(3, apex_x, ridge),
            4: Node(4, self.span, self.eave_height),
            5: Node(5, self.span, 0.0),
        }
        members = {
            1: Member(1, 1, 2, 1),  # Left column
            2: Member(2, 2, 3, 2),  # Left rafter
            3: Member(3, 3, 4, 2),  # Right rafter
            4: Member(4, 4, 5, 1),  # Right column
        }
        return FrameTopology(nodes=nodes, members=members)

    def _build_mono_topology(self) -> FrameTopology:
        """4-node mono-slope frame — no ridge node.
        
        Node 1 (0,0) -> Node 2 (0,eave) -> Node 3 (span,ridge)
        -> Node 4 (span,0)
        
        Members: 1(col-L), 2(rafter), 3(col-R)
        """
        ridge = self.ridge_height
        nodes = {
            1: Node(1, 0.0, 0.0),
            2: Node(2, 0.0, self.eave_height),
            3: Node(3, self.span, ridge),
            4: Node(4, self.span, 0.0),
        }
        members = {
            1: Member(1, 1, 2, 1),  # Left column
            2: Member(2, 2, 3, 2),  # Rafter (single span)
            3: Member(3, 3, 4, 1),  # Right column
        }
        return FrameTopology(nodes=nodes, members=members)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py::TestVariableApexGable -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: All 21+ tests PASS (existing tests use default `roof_type="gable"`, `apex_position_pct=50.0`)

- [ ] **Step 6: Commit**

```bash
git add portal_frame/models/geometry.py tests/test_models.py
git commit -m "feat: add variable apex position and mono-roof to geometry model"
```

---

### Task 2: Mono-Roof Topology Tests

**Files:**
- Test: `tests/test_models.py`
- (Implementation already in geometry.py from Task 1)

- [ ] **Step 1: Write failing tests for mono-roof topology**

Add to `tests/test_models.py`:

```python
class TestMonoRoofTopology:
    def test_mono_node_count(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="mono",
        )
        topo = geom.to_topology()
        assert len(topo.nodes) == 4

    def test_mono_member_count(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="mono",
        )
        topo = geom.to_topology()
        assert len(topo.members) == 3

    def test_mono_ridge_height(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="mono",
        )
        expected = 4.5 + 12.0 * math.tan(math.radians(5.0))
        assert geom.ridge_height == pytest.approx(expected, rel=1e-3)

    def test_mono_base_nodes(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="mono",
        )
        topo = geom.to_topology()
        base = topo.get_base_nodes()
        assert len(base) == 2

    def test_mono_eave_nodes(self):
        """Mono has 2 eave nodes (both connect column to rafter)."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="mono",
        )
        topo = geom.to_topology()
        eave = topo.get_eave_nodes()
        assert len(eave) == 2

    def test_mono_right_column_height(self):
        """Right column goes from (span, 0) to (span, ridge_height)."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="mono",
        )
        topo = geom.to_topology()
        assert topo.nodes[3].y == pytest.approx(geom.ridge_height, rel=1e-3)
        assert topo.nodes[3].x == pytest.approx(12.0)

    def test_mono_single_rafter(self):
        """Mono has exactly one rafter member (section_id=2)."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
            roof_type="mono",
        )
        topo = geom.to_topology()
        rafters = [m for m in topo.members.values() if m.section_id == 2]
        assert len(rafters) == 1
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py::TestMonoRoofTopology -v`
Expected: PASS (implementation from Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/test_models.py
git commit -m "test: add mono-roof topology tests"
```

---

### Task 3: Pitch Warning Validation

**Files:**
- Create: `portal_frame/models/validation.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for pitch validation**

Add to `tests/test_models.py`:

```python
from portal_frame.models.validation import validate_roof_pitch


class TestPitchValidation:
    def test_normal_pitch_no_warnings(self):
        warnings = validate_roof_pitch(5.0)
        assert warnings == []

    def test_low_pitch_warning(self):
        warnings = validate_roof_pitch(2.0)
        assert len(warnings) == 1
        assert "ponding" in warnings[0].lower()

    def test_exactly_3deg_no_warning(self):
        warnings = validate_roof_pitch(3.0)
        assert warnings == []

    def test_high_pitch_warning(self):
        warnings = validate_roof_pitch(35.0)
        assert len(warnings) == 1
        assert "30" in warnings[0]

    def test_exactly_30deg_no_warning(self):
        warnings = validate_roof_pitch(30.0)
        assert warnings == []

    def test_gable_both_pitches_checked(self):
        """For off-center apex, the shallower side may be below 3 deg."""
        from portal_frame.models.geometry import PortalFrameGeometry
        geom = PortalFrameGeometry(
            span=20.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
            roof_type="gable", apex_position_pct=20.0,
        )
        from portal_frame.models.validation import validate_geometry_pitch
        warnings = validate_geometry_pitch(geom)
        # Right side pitch: rise over 80% of span — likely < 3 deg
        assert any("right rafter" in w.lower() or "ponding" in w.lower() for w in warnings)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py::TestPitchValidation -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'portal_frame.models.validation'`

- [ ] **Step 3: Implement pitch validation**

Create `portal_frame/models/validation.py`:

```python
"""Geometry validation — pitch warnings and sanity checks."""

import math


def validate_roof_pitch(pitch_deg: float) -> list[str]:
    """Check a single pitch value for warnings.
    
    Returns list of warning strings (empty if OK).
    """
    warnings = []
    if pitch_deg < 3.0:
        warnings.append(
            f"Roof pitch {pitch_deg:.1f} deg is less than 3 deg — "
            f"risk of water ponding. Consider increasing pitch."
        )
    if pitch_deg > 30.0:
        warnings.append(
            f"Roof pitch {pitch_deg:.1f} deg exceeds 30 deg — "
            f"unusual for portal frames. Check geometry."
        )
    return warnings


def validate_geometry_pitch(geom) -> list[str]:
    """Validate all rafter pitches for a PortalFrameGeometry.
    
    For gable roofs with off-center apex, checks both left and right pitches.
    For mono-roof, checks the single pitch.
    """
    warnings = []
    if geom.roof_type == "mono":
        warnings.extend(validate_roof_pitch(geom.roof_pitch))
    else:
        # Left side pitch
        left_warnings = validate_roof_pitch(geom.left_pitch)
        for w in left_warnings:
            warnings.append(f"Left rafter: {w}")

        # Right side pitch (may differ from left when apex is off-center)
        right_warnings = validate_roof_pitch(geom.right_pitch)
        for w in right_warnings:
            warnings.append(f"Right rafter: {w}")

    return warnings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_models.py::TestPitchValidation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add portal_frame/models/validation.py tests/test_models.py
git commit -m "feat: add roof pitch validation with ponding and steep pitch warnings"
```

---

### Task 4: Wind Zone Splitting with Variable Apex Position

**Files:**
- Modify: `portal_frame/standards/wind_nzs1170_2.py:251-367`
- Test: `tests/test_standards.py`

- [ ] **Step 1: Write failing tests for variable split point**

Add to `tests/test_standards.py`:

```python
from portal_frame.standards.wind_nzs1170_2 import _split_zones_to_rafters


class TestVariableApexWindSplit:
    def test_split_at_50_matches_default(self):
        """50% split should match existing behavior."""
        from portal_frame.models.loads import RafterZoneLoad
        zones = [
            RafterZoneLoad(0.0, 50.0, -1.0),
            RafterZoneLoad(50.0, 100.0, -0.5),
        ]
        left, right = _split_zones_to_rafters(zones, 50.0)
        assert len(left) == 1
        assert left[0].start_pct == pytest.approx(0.0)
        assert left[0].end_pct == pytest.approx(100.0)
        assert left[0].pressure == pytest.approx(-1.0)
        assert len(right) == 1
        assert right[0].pressure == pytest.approx(-0.5)

    def test_split_at_33(self):
        """33% split: left rafter is shorter, gets fewer zones."""
        from portal_frame.models.loads import RafterZoneLoad
        zones = [
            RafterZoneLoad(0.0, 33.3, -1.0),
            RafterZoneLoad(33.3, 66.7, -0.7),
            RafterZoneLoad(66.7, 100.0, -0.3),
        ]
        left, right = _split_zones_to_rafters(zones, 33.3)
        # Left covers 0-33.3% -> remapped to 0-100%
        assert len(left) == 1
        assert left[0].start_pct == pytest.approx(0.0)
        assert left[0].end_pct == pytest.approx(100.0)
        # Right covers 33.3-100% -> remapped to 0-100%
        assert len(right) == 2


class TestGenerateWindCasesWithApex:
    def test_custom_split_pct(self):
        """generate_standard_wind_cases accepts split_pct parameter."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 5.0, 50.0, cp, split_pct=33.0,
        )
        assert len(cases) == 8
        # Crosswind cases should have zones split at 33%
        w1 = cases[0]
        assert w1.is_crosswind

    def test_default_split_is_50(self):
        """Without split_pct, behavior is unchanged."""
        cp = WindCpInputs()
        cases_default = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp)
        cases_explicit = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp, split_pct=50.0)
        for a, b in zip(cases_default, cases_explicit):
            assert a.left_wall == b.left_wall
            assert a.right_wall == b.right_wall
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_standards.py::TestGenerateWindCasesWithApex -v`
Expected: FAIL — `generate_standard_wind_cases() got an unexpected keyword argument 'split_pct'`

- [ ] **Step 3: Add split_pct parameter to generate_standard_wind_cases**

In `portal_frame/standards/wind_nzs1170_2.py`, modify the function signature:

```python
def generate_standard_wind_cases(
    span: float,
    eave_height: float,
    roof_pitch: float,
    building_depth: float,
    cp: WindCpInputs,
    split_pct: float = 50.0,
) -> list[WindCase]:
```

Then change line 315 (inside the crosswind loop) from:

```python
        left_zones, right_zones = _split_zones_to_rafters(full_zones, 50.0)
```

to:

```python
        left_zones, right_zones = _split_zones_to_rafters(full_zones, split_pct)
```

- [ ] **Step 4: Run all standards tests**

Run: `python -m pytest tests/test_standards.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add portal_frame/standards/wind_nzs1170_2.py tests/test_standards.py
git commit -m "feat: support variable apex split in wind zone calculations"
```

---

### Task 5: SpaceGass Writer — Mono-Roof Support

**Files:**
- Modify: `portal_frame/io/spacegass_writer.py`
- Modify: `tests/test_output.py`

- [ ] **Step 1: Write failing test for mono-roof output**

Add to `tests/test_output.py`:

```python
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import LoadInput
from portal_frame.models.supports import SupportCondition
from portal_frame.io.section_library import load_all_sections
from portal_frame.io.spacegass_writer import SpaceGassWriter


def test_mono_roof_output():
    """Mono-roof produces valid SpaceGass file with 4 nodes and 3 members."""
    sections = load_all_sections()
    col_sec = sections["63020S2"]
    raf_sec = sections["650180295S2"]

    geom = PortalFrameGeometry(
        span=12.0, eave_height=4.5, roof_pitch=5.0, bay_spacing=6.0,
        roof_type="mono",
    )
    topology = geom.to_topology()
    supports = SupportCondition()
    loads = LoadInput(dead_load_roof=0.15, dead_load_wall=0.10)

    writer = SpaceGassWriter(
        topology=topology,
        column_section=col_sec,
        rafter_section=raf_sec,
        supports=supports,
        loads=loads,
        span=geom.span,
        eave_height=geom.eave_height,
        roof_pitch=geom.roof_pitch,
        bay_spacing=geom.bay_spacing,
    )
    output = writer.write()

    assert "SPACE GASS Text File - Version 1420" in output
    assert "NODES" in output
    assert "END" in output

    # Count nodes
    lines = output.split("\n")
    in_nodes = False
    node_count = 0
    for line in lines:
        if line == "NODES":
            in_nodes = True
            continue
        if in_nodes and line == "":
            break
        if in_nodes:
            node_count += 1
    assert node_count == 4

    # Count members
    in_members = False
    member_count = 0
    for line in lines:
        if line == "MEMBERS":
            in_members = True
            continue
        if in_members and line == "":
            break
        if in_members:
            member_count += 1
    assert member_count == 3
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_output.py::test_mono_roof_output -v`

The writer uses topology directly, so it should already handle 4 nodes and 3 members. However, the `_load_cases()` method hardcodes member IDs `[2, 3]` for rafters and `[1, 4]` for columns. For mono-roof, members are 1(col), 2(rafter), 3(col). **This will produce incorrect output** — dead/live loads will be applied to member 3 (right column) as a rafter.

Expected: FAIL or incorrect output — dead load applied to member 3 as rafter instead of column.

- [ ] **Step 3: Refactor writer to use topology section_id instead of hardcoded member IDs**

In `portal_frame/io/spacegass_writer.py`, modify `_load_cases()` to derive member roles from topology:

```python
    def _load_cases(self) -> str:
        """Generate MEMBFORCES section with dead, live, and wind loads."""
        # Build case numbering map
        case_map = {"G": 1, "Q": 2}
        next_case = 3
        for wc in self.loads.wind_cases:
            case_map[wc.name] = next_case
            next_case += 1

        bay = self.bay_spacing

        # Derive member roles from topology section_id
        rafter_ids = sorted(m.id for m in self.topology.members.values() if m.section_id == 2)
        column_ids = sorted(m.id for m in self.topology.members.values() if m.section_id == 1)
        # Identify left/right columns by x-position of their base node
        left_col_id = None
        right_col_id = None
        for mid in column_ids:
            mem = self.topology.members[mid]
            base_node = self.topology.nodes[mem.node_start]
            if base_node.x == 0.0:
                left_col_id = mid
            else:
                right_col_id = mid

        lines = ["MEMBFORCES"]

        # Case 1: Dead Load (G) — gravity loads downward (global -Y)
        if self.loads.dead_load_roof > 0:
            w = -self.loads.dead_load_roof * bay
            for mem in rafter_ids:
                lines.append(
                    f"1,{mem},1,G,%,0.0,100.0,0.0,0.0,{w:.4f},{w:.4f},0.0,0.0"
                )
        if self.loads.dead_load_wall > 0:
            w = -self.loads.dead_load_wall * bay
            for mem in column_ids:
                lines.append(
                    f"1,{mem},1,G,%,0.0,100.0,0.0,0.0,{w:.4f},{w:.4f},0.0,0.0"
                )

        # Case 2: Live Load (Q) — gravity on rafters (global -Y)
        if self.loads.live_load_roof > 0:
            w = -self.loads.live_load_roof * bay
            for mem in rafter_ids:
                lines.append(
                    f"2,{mem},1,G,%,0.0,100.0,0.0,0.0,{w:.4f},{w:.4f},0.0,0.0"
                )

        # Wind cases
        for wc in self.loads.wind_cases:
            cn = case_map[wc.name]
            mem_slice = {}

            def next_slice(mem_id):
                sl = mem_slice.get(mem_id, 1)
                mem_slice[mem_id] = sl + 1
                return sl

            # Wall loads — horizontal (global X direction)
            if wc.left_wall != 0 and left_col_id is not None:
                sl = next_slice(left_col_id)
                w = wc.left_wall * bay
                lines.append(
                    f"{cn},{left_col_id},{sl},G,%,0.0,100.0,{w:.4f},{w:.4f},0.0,0.0,0.0,0.0"
                )
            if wc.right_wall != 0 and right_col_id is not None:
                sl = next_slice(right_col_id)
                w = -wc.right_wall * bay
                lines.append(
                    f"{cn},{right_col_id},{sl},G,%,0.0,100.0,{w:.4f},{w:.4f},0.0,0.0,0.0,0.0"
                )

            # Rafter loads — normal to surface (local Y)
            # For gable: 2 rafters (left_rafter on first, right_rafter on second)
            # For mono: 1 rafter — use left_rafter zones/uniform only
            if len(rafter_ids) == 2:
                rafter_load_pairs = [
                    (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
                    (rafter_ids[1], wc.right_rafter_zones, wc.right_rafter),
                ]
            elif len(rafter_ids) == 1:
                # Mono-roof: single rafter gets the full-span zones or left_rafter uniform
                rafter_load_pairs = [
                    (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
                ]
            else:
                rafter_load_pairs = []

            for mem, zones, uniform in rafter_load_pairs:
                if wc.is_crosswind and zones:
                    for zone in zones:
                        if zone.pressure != 0:
                            sl = next_slice(mem)
                            w = -zone.pressure * bay
                            lines.append(
                                f"{cn},{mem},{sl},L,%,{zone.start_pct:.1f},{zone.end_pct:.1f},"
                                f"0.0,0.0,{w:.4f},{w:.4f},0.0,0.0"
                            )
                elif uniform != 0:
                    sl = next_slice(mem)
                    w = -uniform * bay
                    lines.append(
                        f"{cn},{mem},{sl},L,%,0.0,100.0,0.0,0.0,{w:.4f},{w:.4f},0.0,0.0"
                    )

        lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 4: Run all output tests**

Run: `python -m pytest tests/test_output.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add portal_frame/io/spacegass_writer.py tests/test_output.py
git commit -m "feat: SpaceGass writer supports mono-roof and topology-driven member roles"
```

---

### Task 6: Preview Canvas — Mono-Roof and Variable Apex Rendering

**Files:**
- Modify: `portal_frame/gui/preview.py:27-133`

- [ ] **Step 1: Update preview to use geometry-driven node positions**

The preview currently hardcodes 5 nodes with ridge at `span/2`. Modify `update_frame()` in `portal_frame/gui/preview.py` to accept `roof_type` and `apex_position_pct`:

```python
    def update_frame(self, geom: dict, supports: tuple, loads: dict = None):
        self._geom = geom
        self._supports = supports
        self._loads = loads
        self.delete("all")

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 50 or h < 50:
            return

        span = geom.get("span", 12)
        eave = geom.get("eave_height", 4.5)
        pitch = geom.get("roof_pitch", 5)
        roof_type = geom.get("roof_type", "gable")
        apex_pct = geom.get("apex_position_pct", 50.0)

        if roof_type == "mono":
            ridge = eave + span * math.tan(math.radians(pitch))
        else:
            apex_x = span * apex_pct / 100.0
            ridge = eave + apex_x * math.tan(math.radians(pitch))

        # Draw grid
        for i in range(0, w, 30):
            self.create_line(i, 0, i, h, fill=COLORS["canvas_grid"], dash=(1, 4))
        for i in range(0, h, 30):
            self.create_line(0, i, w, i, fill=COLORS["canvas_grid"], dash=(1, 4))

        # Scale to fit
        pad_side = 50
        pad_top = 80
        pad_bot = 50
        total_h = ridge * 1.0
        scale_x = (w - 2 * pad_side) / span if span > 0 else 1
        scale_y = (h - pad_top - pad_bot) / total_h if total_h > 0 else 1
        scale = min(scale_x, scale_y)

        ox = pad_side + (w - 2 * pad_side - span * scale) / 2
        oy = h - pad_bot

        def tx(x, y):
            return ox + x * scale, oy - y * scale

        # Ground line
        gx1 = ox - 20
        gx2 = ox + span * scale + 20
        gy = oy
        self.create_line(gx1, gy, gx2, gy, fill=COLORS["fg_dim"], width=1, dash=(4, 2))

        if roof_type == "mono":
            nodes = {
                1: (0, 0), 2: (0, eave),
                3: (span, ridge), 4: (span, 0),
            }
            ns = {k: tx(*v) for k, v in nodes.items()}
            # Members: col-L, rafter, col-R
            self.create_line(*ns[1], *ns[2], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[2], *ns[3], fill=COLORS["frame_raf"], width=3)
            self.create_line(*ns[3], *ns[4], fill=COLORS["frame_col"], width=3)
        else:
            apex_x = span * apex_pct / 100.0
            nodes = {
                1: (0, 0), 2: (0, eave), 3: (apex_x, ridge),
                4: (span, eave), 5: (span, 0),
            }
            ns = {k: tx(*v) for k, v in nodes.items()}
            # Members: col-L, raft-L, raft-R, col-R
            self.create_line(*ns[1], *ns[2], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[5], *ns[4], fill=COLORS["frame_col"], width=3)
            self.create_line(*ns[2], *ns[3], fill=COLORS["frame_raf"], width=3)
            self.create_line(*ns[3], *ns[4], fill=COLORS["frame_raf"], width=3)

        # Nodes
        r = 4
        for pt in ns.values():
            self.create_oval(pt[0]-r, pt[1]-r, pt[0]+r, pt[1]+r,
                             fill=COLORS["frame_node"], outline="")

        # Supports — use first and last base nodes
        base_ids = [nid for nid, (x, y) in nodes.items() if y == 0.0]
        base_ids_sorted = sorted(base_ids, key=lambda nid: nodes[nid][0])
        for idx, nid in enumerate(base_ids_sorted):
            condition = supports[idx] if idx < len(supports) else "pinned"
            bx, by = ns[nid]
            if condition == "pinned":
                sz = 12
                self.create_polygon(
                    bx, by, bx - sz, by + sz, bx + sz, by + sz,
                    outline=COLORS["frame_support"], fill="", width=2
                )
                for j in range(-1, 2):
                    hx = bx + j * 8
                    self.create_line(hx - 4, by + sz + 2, hx + 4, by + sz + 8,
                                     fill=COLORS["frame_support"], width=1)
            else:
                sz = 10
                self.create_rectangle(
                    bx - sz, by, bx + sz, by + sz * 1.5,
                    outline=COLORS["frame_support"], fill=COLORS["frame_support"],
                    stipple="gray50", width=2
                )

        # UDL load arrows
        if loads:
            self._draw_loads(loads, ns, scale)

        # Dimension annotations
        dim_col = COLORS["fg_dim"]
        left_base = ns[base_ids_sorted[0]]
        right_base = ns[base_ids_sorted[-1]]
        dy = oy + 30
        self.create_line(left_base[0], dy, right_base[0], dy,
                         fill=dim_col, width=1, arrow="both")
        self.create_text((left_base[0] + right_base[0]) / 2, dy + 12,
                         text=f"{span:.1f} m", fill=dim_col, font=FONT_SMALL, anchor="n")

        # Eave height on left
        dx = ns[1][0] - 25
        self.create_line(dx, ns[1][1], dx, ns[2][1], fill=dim_col, width=1, arrow="both")
        self.create_text(dx - 5, (ns[1][1] + ns[2][1]) / 2, text=f"{eave:.1f} m",
                         fill=dim_col, font=FONT_SMALL, anchor="e")

        # Rise annotation
        if roof_type == "gable":
            dx2 = ns[3][0]
            self.create_line(dx2, ns[2][1], dx2, ns[3][1], fill=dim_col, width=1, arrow="both")
            rise = ridge - eave
            self.create_text(dx2 + 10, (ns[2][1] + ns[3][1]) / 2, text=f"{rise:.2f} m",
                             fill=dim_col, font=FONT_SMALL, anchor="w")
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            self.create_text(mx - 15, my - 12, text=f"{pitch:.1f} deg",
                             fill=COLORS["frame_raf"], font=FONT_SMALL, anchor="e")
        else:
            # Mono: show pitch along the rafter
            mx = (ns[2][0] + ns[3][0]) / 2
            my = (ns[2][1] + ns[3][1]) / 2
            self.create_text(mx, my - 15, text=f"{pitch:.1f} deg",
                             fill=COLORS["frame_raf"], font=FONT_SMALL, anchor="center")

        # Legend
        ly = 15
        lx = 10
        self.create_line(lx, ly, lx + 20, ly, fill=COLORS["frame_col"], width=2)
        self.create_text(lx + 25, ly, text="Column", fill=COLORS["fg_dim"],
                         font=FONT_SMALL, anchor="w")
        ly += 16
        self.create_line(lx, ly, lx + 20, ly, fill=COLORS["frame_raf"], width=2)
        self.create_text(lx + 25, ly, text="Rafter", fill=COLORS["fg_dim"],
                         font=FONT_SMALL, anchor="w")
        if loads:
            ly += 16
            self.create_line(lx, ly, lx + 20, ly, fill=self.ARROW_COLOR, width=2)
            self.create_text(lx + 25, ly, text="Load", fill=COLORS["fg_dim"],
                             font=FONT_SMALL, anchor="w")
```

- [ ] **Step 2: Verify GUI launches and renders correctly**

Run: `python -m portal_frame.run_gui` and visually confirm gable roof displays correctly with default settings.

- [ ] **Step 3: Commit**

```bash
git add portal_frame/gui/preview.py
git commit -m "feat: preview canvas supports mono-roof and variable apex position"
```

---

### Task 7: GUI — Roof Type Selector and Apex Position

**Files:**
- Modify: `portal_frame/gui/app.py`

- [ ] **Step 1: Add roof type and apex position controls to Frame tab**

In `portal_frame/gui/app.py`, in the `_build_frame_tab()` method, add after the "GEOMETRY" header and before the span entry:

```python
        # Roof type selector
        roof_type_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        roof_type_frame.pack(fill="x", **pad)

        tk.Label(roof_type_frame, text="Roof Type", font=FONT, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"], width=14, anchor="w").pack(side="left")
        self.roof_type_var = tk.StringVar(value="gable")
        for text, val in [("Gable", "gable"), ("Mono", "mono")]:
            tk.Radiobutton(
                roof_type_frame, text=text, variable=self.roof_type_var,
                value=val, font=FONT, fg=COLORS["fg"],
                bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                activebackground=COLORS["bg_panel"],
                activeforeground=COLORS["fg"],
                command=self._on_roof_type_change,
            ).pack(side="left", padx=(4, 8))
```

Then add the apex position control after the pitch entry (inside `_build_frame_tab`):

```python
        # Apex position (gable only)
        self.apex_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        self.apex_frame.pack(fill="x", **pad)

        self.apex_position = LabeledEntry(self.apex_frame, "Apex Position", 50.0, "% of span")
        self.apex_position.pack(fill="x")
        self.apex_position.bind_change(self._on_apex_change)

        self.pitch_warning_label = tk.Label(
            parent, text="", font=FONT_SMALL, fg=COLORS["warning"],
            bg=COLORS["bg_panel"], anchor="w", justify="left",
        )
        self.pitch_warning_label.pack(fill="x", padx=10, pady=(0, 2))
```

- [ ] **Step 2: Add handler methods**

Add to the `PortalFrameApp` class:

```python
    def _on_roof_type_change(self, *_):
        """Show/hide apex position based on roof type."""
        if self.roof_type_var.get() == "mono":
            self.apex_frame.pack_forget()
        else:
            # Re-pack after pitch
            self.apex_frame.pack(fill="x", padx=10, pady=(0, 2),
                                 after=self.pitch)
        self._check_pitch_warnings()
        self._update_preview()

    def _on_apex_change(self, *_):
        self._check_pitch_warnings()
        self._update_preview()

    def _check_pitch_warnings(self):
        from portal_frame.models.validation import validate_geometry_pitch
        geom = self._build_geometry()
        warnings = validate_geometry_pitch(geom)
        if warnings:
            self.pitch_warning_label.config(text="\n".join(warnings))
        else:
            self.pitch_warning_label.config(text="")

    def _build_geometry(self) -> PortalFrameGeometry:
        """Build geometry from current UI values."""
        return PortalFrameGeometry(
            span=self.span.get(),
            eave_height=self.eave.get(),
            roof_pitch=self.pitch.get(),
            bay_spacing=self.bay.get(),
            roof_type=self.roof_type_var.get(),
            apex_position_pct=self.apex_position.get() if self.roof_type_var.get() == "gable" else 50.0,
        )
```

- [ ] **Step 3: Update _update_preview to pass roof type and apex**

Modify `_update_preview`:

```python
    def _update_preview(self, *_):
        geom = {
            "span": self.span.get(),
            "eave_height": self.eave.get(),
            "roof_pitch": self.pitch.get(),
            "roof_type": self.roof_type_var.get(),
            "apex_position_pct": self.apex_position.get(),
        }
        supports = (self.left_support.get(), self.right_support.get())
        loads = self._build_preview_loads()
        self.preview.update_frame(geom, supports, loads)
        self._update_summary()
```

- [ ] **Step 4: Update _generate to use _build_geometry**

In `_generate()`, replace the `PortalFrameGeometry(...)` constructor call:

```python
            geom = self._build_geometry()
```

- [ ] **Step 5: Update _update_summary for mono-roof**

```python
    def _update_summary(self):
        geom = self._build_geometry()
        roof_label = "Gable" if geom.roof_type == "gable" else "Mono"
        ridge = geom.ridge_height
        apex_info = ""
        if geom.roof_type == "gable" and geom.apex_position_pct != 50.0:
            apex_info = f"  |  Apex: {geom.apex_position_pct:.0f}%"
        self.summary_label.config(
            text=f"{roof_label}  |  Span: {geom.span:.1f}m  |  Eave: {geom.eave_height:.1f}m  |  "
                 f"Ridge: {ridge:.2f}m  |  Pitch: {geom.roof_pitch:.1f} deg{apex_info}"
        )
```

- [ ] **Step 6: Update _auto_generate_wind_cases to pass split_pct**

In `_auto_generate_wind_cases()`, modify the call to `generate_standard_wind_cases`:

```python
            split_pct = self.apex_position.get() if self.roof_type_var.get() == "gable" else 50.0
            cases = generate_standard_wind_cases(
                span=span, eave_height=eave, roof_pitch=pitch,
                building_depth=depth, cp=cp, split_pct=split_pct,
            )
```

- [ ] **Step 7: Update _build_preview_loads for mono-roof member node IDs**

Modify `_build_preview_loads` to use topology-aware node pairs. For simplicity, detect roof type and adjust:

```python
    def _build_preview_loads(self) -> dict:
        selected = self.load_case_var.get()
        if selected == "(none)":
            return None

        bay = self.bay.get()
        if bay <= 0:
            return None

        is_mono = self.roof_type_var.get() == "mono"
        members = []

        if selected.startswith("G "):
            w_roof = self.dead_roof.get() * bay
            w_wall = self.dead_wall.get() * bay
            if w_roof > 0:
                if is_mono:
                    members.append({"from": 2, "to": 3, "segments": [
                        {"start_pct": 0, "end_pct": 100, "w_kn": w_roof,
                         "direction": "global_y"}]})
                else:
                    for nf, nt in [(2, 3), (3, 4)]:
                        members.append({"from": nf, "to": nt, "segments": [
                            {"start_pct": 0, "end_pct": 100, "w_kn": w_roof,
                             "direction": "global_y"}]})
            if w_wall > 0:
                if is_mono:
                    for nf, nt in [(1, 2), (4, 3)]:
                        members.append({"from": nf, "to": nt, "segments": [
                            {"start_pct": 0, "end_pct": 100, "w_kn": w_wall,
                             "direction": "global_y"}]})
                else:
                    for nf, nt in [(1, 2), (5, 4)]:
                        members.append({"from": nf, "to": nt, "segments": [
                            {"start_pct": 0, "end_pct": 100, "w_kn": w_wall,
                             "direction": "global_y"}]})

        elif selected.startswith("Q "):
            w_live = self.live_roof.get() * bay
            if w_live > 0:
                if is_mono:
                    members.append({"from": 2, "to": 3, "segments": [
                        {"start_pct": 0, "end_pct": 100, "w_kn": w_live,
                         "direction": "global_y"}]})
                else:
                    for nf, nt in [(2, 3), (3, 4)]:
                        members.append({"from": nf, "to": nt, "segments": [
                            {"start_pct": 0, "end_pct": 100, "w_kn": w_live,
                             "direction": "global_y"}]})

        else:
            wc_name = selected.split(" - ")[0].strip()
            wc_list = self.wind_table.get_wind_cases()
            wc = None
            for w in wc_list:
                if w["name"] == wc_name:
                    wc = w
                    break
            if not wc:
                return None

            # Wall loads
            left_col_nodes = (1, 2)
            right_col_nodes = (4, 3) if is_mono else (5, 4)
            if wc.get("left_wall", 0) != 0:
                members.append({"from": left_col_nodes[0], "to": left_col_nodes[1], "segments": [
                    {"start_pct": 0, "end_pct": 100,
                     "w_kn": wc["left_wall"] * bay,
                     "direction": "global_x"}]})
            if wc.get("right_wall", 0) != 0:
                members.append({"from": right_col_nodes[0], "to": right_col_nodes[1], "segments": [
                    {"start_pct": 0, "end_pct": 100,
                     "w_kn": -wc["right_wall"] * bay,
                     "direction": "global_x"}]})

            # Rafter loads
            if is_mono:
                rafter_pairs = [(2, 3, "left_rafter_zones", "left_rafter")]
            else:
                rafter_pairs = [
                    (2, 3, "left_rafter_zones", "left_rafter"),
                    (3, 4, "right_rafter_zones", "right_rafter"),
                ]

            for nf, nt, zone_key, uniform_key in rafter_pairs:
                if wc.get("is_crosswind") and wc.get(zone_key):
                    segs = []
                    for z in wc.get(zone_key, []):
                        if z["pressure"] != 0:
                            segs.append({
                                "start_pct": z["start_pct"],
                                "end_pct": z["end_pct"],
                                "w_kn": z["pressure"] * bay,
                                "direction": "normal"})
                    if segs:
                        members.append({"from": nf, "to": nt, "segments": segs})
                else:
                    val = wc.get(uniform_key, 0)
                    if val != 0:
                        members.append({"from": nf, "to": nt, "segments": [
                            {"start_pct": 0, "end_pct": 100,
                             "w_kn": val * bay,
                             "direction": "normal"}]})

        if not members:
            return None
        return {"members": members}
```

- [ ] **Step 8: Verify GUI launches with roof type controls**

Run: `python -m portal_frame.run_gui`
Test: Switch between Gable/Mono, change apex position, verify preview updates, check pitch warnings appear.

- [ ] **Step 9: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add portal_frame/gui/app.py
git commit -m "feat: GUI roof type selector with apex position and pitch warnings"
```

---

## Part B: Earthquake Loading (NZS 1170.5:2004)

### Task 8: Earthquake Backend — Spectral Calculations

**Files:**
- Modify: `portal_frame/standards/earthquake_nzs1170_5.py`
- Test: `tests/test_standards.py`

- [ ] **Step 1: Write failing tests for earthquake calculations**

Add to `tests/test_standards.py`:

```python
from portal_frame.standards.earthquake_nzs1170_5 import (
    NZ_HAZARD_FACTORS,
    spectral_shape_factor,
    calculate_earthquake_forces,
)
from portal_frame.models.loads import EarthquakeInputs
from portal_frame.models.geometry import PortalFrameGeometry


class TestNZHazardFactors:
    def test_wellington_z(self):
        assert NZ_HAZARD_FACTORS["Wellington"] == 0.40

    def test_auckland_z(self):
        assert NZ_HAZARD_FACTORS["Auckland"] == 0.13

    def test_christchurch_z(self):
        assert NZ_HAZARD_FACTORS["Christchurch"] == 0.30


class TestSpectralShapeFactor:
    def test_soil_c_at_0s(self):
        """Ch(T=0) for Soil C should be in table."""
        ch = spectral_shape_factor(0.0, "C")
        assert ch == pytest.approx(1.33, rel=0.05)

    def test_soil_c_at_0_5s(self):
        ch = spectral_shape_factor(0.5, "C")
        assert ch == pytest.approx(2.36, rel=0.05)

    def test_soil_a_at_0s(self):
        ch = spectral_shape_factor(0.0, "A")
        assert ch == pytest.approx(1.89, rel=0.05)

    def test_interpolation(self):
        """Intermediate period should interpolate."""
        ch = spectral_shape_factor(0.25, "C")
        assert 1.0 < ch < 3.0  # sanity bounds

    def test_long_period_decay(self):
        """Ch should decrease at long periods."""
        ch_short = spectral_shape_factor(0.3, "C")
        ch_long = spectral_shape_factor(2.0, "C")
        assert ch_long < ch_short


class TestCalculateEarthquakeForces:
    def test_basic_portal_frame(self):
        """Standard portal frame with known inputs."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(
            Z=0.40, soil_class="C", R_uls=1.0, R_sls=0.25,
            mu=1.0, Sp=1.0, near_fault=1.0, extra_seismic_mass=0.0,
        )
        dead_roof = 0.15  # kPa
        dead_wall = 0.10  # kPa
        result = calculate_earthquake_forces(geom, dead_roof, dead_wall, eq)

        assert result["T1"] > 0
        assert result["Ch"] > 0
        assert result["k_mu"] == pytest.approx(1.0)  # mu=1
        assert result["Wt"] > 0
        assert result["V_uls"] > 0
        assert result["V_sls"] > 0
        assert result["V_sls"] < result["V_uls"]  # SLS < ULS
        assert result["F_node"] == pytest.approx(result["V_uls"] / 2.0)

    def test_period_calculation(self):
        """T1 = 1.25 * 0.085 * h_n^0.75 for steel MRF."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C")
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        h_n = geom.ridge_height
        expected_T1 = 1.25 * 0.085 * h_n ** 0.75
        assert result["T1"] == pytest.approx(expected_T1, rel=1e-3)

    def test_seismic_weight(self):
        """Wt = (SDL_roof * span + SDL_wall * 2 * eave) * bay + extra."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", extra_seismic_mass=10.0)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        expected_Wt = (0.15 * 12.0 + 0.10 * 2 * 6.0) * 8.0 + 10.0
        assert result["Wt"] == pytest.approx(expected_Wt, rel=1e-3)

    def test_k_mu_short_period(self):
        """k_mu for T1 < 0.7s: k_mu = (mu-1)*T1/0.7 + 1."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.0, roof_pitch=5.0, bay_spacing=6.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", mu=4.0, Sp=0.7)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        T1 = result["T1"]
        if T1 < 0.7:
            expected_k_mu = (4.0 - 1) * T1 / 0.7 + 1
            assert result["k_mu"] == pytest.approx(expected_k_mu, rel=1e-3)

    def test_cd_floor(self):
        """Cd(T1) >= max(0.03, Z*R*0.02)."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", R_uls=1.0)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        cd_floor = max(0.03, 0.40 * 1.0 * 0.02)
        assert result["Cd_uls"] >= cd_floor

    def test_f_node_sls(self):
        """SLS force per node = V_sls / 2."""
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", R_sls=0.25)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        assert result["F_node_sls"] == pytest.approx(result["V_sls"] / 2.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_standards.py::TestNZHazardFactors -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement earthquake module**

Replace contents of `portal_frame/standards/earthquake_nzs1170_5.py`:

```python
"""NZS 1170.5:2004 Earthquake Loading — Equivalent Static Method.

Implements the equivalent static method for portal frames.
Forces are lumped at eave (knee) nodes.

Key formulas:
    V = Cd(T1) * Wt
    Cd(T1) = Ch(T1) * Z * R * N(T,D) * Sp / k_mu
    k_mu: if T1 >= 0.7s -> k_mu = mu; if T1 < 0.7s -> k_mu = (mu-1)*T1/0.7 + 1
    T1 = 1.25 * 0.085 * h_n^0.75  (steel MRF, Clause 4.1.2.1)
    Floor: Cd(T1) >= max(0.03, Z*R*0.02)
    SLS: Cd_sls = Ch(T1) * Z * R_sls * N (no Sp or k_mu reduction)
"""

from portal_frame.standards.utils import lerp


# ──────────────────────────────────────────────────────────────────────
# NZS 1170.5:2004 Table 3.3 — Hazard factor Z for NZ locations
# ──────────────────────────────────────────────────────────────────────

NZ_HAZARD_FACTORS = {
    "Auckland":         0.13,
    "Blenheim":         0.33,
    "Christchurch":     0.30,
    "Dunedin":          0.13,
    "Gisborne":         0.36,
    "Greymouth":        0.30,
    "Hamilton":         0.13,
    "Hastings":         0.39,
    "Invercargill":     0.18,
    "Napier":           0.39,
    "Nelson":           0.27,
    "New Plymouth":     0.18,
    "Palmerston North": 0.38,
    "Queenstown":       0.20,
    "Rotorua":          0.20,
    "Tauranga":         0.20,
    "Timaru":           0.20,
    "Wellington":       0.40,
    "Whangarei":        0.10,
}


# ──────────────────────────────────────────────────────────────────────
# NZS 1170.5:2004 Table 3.1 — Spectral shape factor Ch(T)
# ──────────────────────────────────────────────────────────────────────
# Format: list of (T, Ch) pairs per soil class

_CH_TABLE = {
    "A": [
        (0.0, 1.89), (0.10, 1.89), (0.20, 1.89), (0.30, 1.89),
        (0.40, 1.89), (0.50, 1.60), (0.60, 1.33), (0.70, 1.14),
        (0.80, 1.00), (0.90, 0.89), (1.0, 0.80), (1.5, 0.53),
        (2.0, 0.40), (2.5, 0.32), (3.0, 0.27), (3.5, 0.23),
        (4.0, 0.20), (4.5, 0.18),
    ],
    "B": [
        (0.0, 1.00), (0.10, 1.35), (0.20, 1.88), (0.25, 2.36),
        (0.30, 2.36), (0.40, 2.36), (0.50, 2.00), (0.60, 1.67),
        (0.70, 1.43), (0.80, 1.25), (0.90, 1.11), (1.0, 1.00),
        (1.5, 0.67), (2.0, 0.50), (2.5, 0.40), (3.0, 0.33),
        (3.5, 0.29), (4.0, 0.25), (4.5, 0.22),
    ],
    "C": [
        (0.0, 1.33), (0.10, 1.80), (0.20, 2.36), (0.30, 2.36),
        (0.40, 2.36), (0.50, 2.36), (0.60, 2.00), (0.70, 1.71),
        (0.80, 1.50), (0.90, 1.33), (1.0, 1.20), (1.5, 0.80),
        (2.0, 0.60), (2.5, 0.48), (3.0, 0.40), (3.5, 0.34),
        (4.0, 0.30), (4.5, 0.27),
    ],
    "D": [
        (0.0, 1.12), (0.10, 1.12), (0.20, 1.12), (0.30, 1.50),
        (0.40, 1.88), (0.50, 2.25), (0.60, 2.63), (0.70, 3.00),
        (0.80, 3.00), (0.90, 3.00), (1.0, 3.00), (1.5, 2.00),
        (2.0, 1.50), (2.5, 1.20), (3.0, 1.00), (3.5, 0.86),
        (4.0, 0.75), (4.5, 0.67),
    ],
    "E": [
        (0.0, 1.12), (0.10, 1.12), (0.20, 1.12), (0.30, 1.50),
        (0.40, 1.88), (0.50, 2.25), (0.60, 2.63), (0.70, 3.00),
        (0.80, 3.00), (0.90, 3.00), (1.0, 3.00), (1.5, 3.00),
        (2.0, 3.00), (2.5, 2.40), (3.0, 2.00), (3.5, 1.71),
        (4.0, 1.50), (4.5, 1.33),
    ],
}


def spectral_shape_factor(T: float, soil_class: str) -> float:
    """NZS 1170.5:2004 Table 3.1 — Ch(T) by soil class, linearly interpolated.

    Args:
        T: Fundamental period (seconds)
        soil_class: "A", "B", "C", "D", or "E"
    """
    table = _CH_TABLE[soil_class]

    if T <= table[0][0]:
        return table[0][1]
    if T >= table[-1][0]:
        return table[-1][1]

    for i in range(len(table) - 1):
        t0, ch0 = table[i]
        t1, ch1 = table[i + 1]
        if t0 <= T <= t1:
            return lerp(T, t0, t1, ch0, ch1)

    return table[-1][1]


def calculate_earthquake_forces(
    geom,
    dead_load_roof: float,
    dead_load_wall: float,
    eq,
) -> dict:
    """Calculate equivalent static earthquake forces per NZS 1170.5:2004.

    Args:
        geom: PortalFrameGeometry (needs span, eave_height, ridge_height, bay_spacing)
        dead_load_roof: Superimposed dead load on roof (kPa)
        dead_load_wall: Dead load on walls (kPa)
        eq: EarthquakeInputs dataclass

    Returns:
        dict with keys: T1, Ch, k_mu, Cd_uls, Cd_sls, Wt, V_uls, V_sls,
                        F_node (ULS per knee), F_node_sls (SLS per knee)
    """
    # Height to apex (highest point)
    h_n = geom.ridge_height

    # Fundamental period: steel MRF, Clause 4.1.2.1
    T1 = 1.25 * 0.085 * h_n ** 0.75

    # Spectral shape factor
    Ch = spectral_shape_factor(T1, eq.soil_class)

    # Ductility reduction factor
    if T1 >= 0.7:
        k_mu = eq.mu
    else:
        k_mu = (eq.mu - 1.0) * T1 / 0.7 + 1.0

    # ULS design action coefficient
    Cd_uls = Ch * eq.Z * eq.R_uls * eq.near_fault * eq.Sp / k_mu
    # Floor per Clause 5.2.1.1
    cd_floor = max(0.03, eq.Z * eq.R_uls * 0.02)
    Cd_uls = max(Cd_uls, cd_floor)

    # SLS design action coefficient (no Sp or k_mu reduction)
    Cd_sls = Ch * eq.Z * eq.R_sls * eq.near_fault

    # Seismic weight
    Wt = (
        dead_load_roof * geom.span
        + dead_load_wall * 2 * geom.eave_height
    ) * geom.bay_spacing + eq.extra_seismic_mass

    # Base shear
    V_uls = Cd_uls * Wt
    V_sls = Cd_sls * Wt

    # Force per knee node (split equally)
    F_node = V_uls / 2.0
    F_node_sls = V_sls / 2.0

    return {
        "T1": round(T1, 4),
        "Ch": round(Ch, 4),
        "k_mu": round(k_mu, 4),
        "Cd_uls": round(Cd_uls, 4),
        "Cd_sls": round(Cd_sls, 4),
        "Wt": round(Wt, 4),
        "V_uls": round(V_uls, 4),
        "V_sls": round(V_sls, 4),
        "F_node": round(F_node, 4),
        "F_node_sls": round(F_node_sls, 4),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_standards.py::TestNZHazardFactors tests/test_standards.py::TestSpectralShapeFactor tests/test_standards.py::TestCalculateEarthquakeForces -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add portal_frame/standards/earthquake_nzs1170_5.py tests/test_standards.py
git commit -m "feat: NZS 1170.5:2004 earthquake calculations with spectral shape factor table"
```

---

### Task 9: Earthquake Load Combinations

**Files:**
- Modify: `portal_frame/standards/combinations_nzs1170_0.py`
- Test: `tests/test_standards.py`

- [ ] **Step 1: Write failing tests for EQ combinations**

Add to `tests/test_standards.py`:

```python
class TestEarthquakeCombinations:
    def test_eq_uls_combos(self):
        """EQ adds 1.0G + E+ and 1.0G + E- to ULS."""
        uls, sls = build_combinations(["W1"], eq_case_names=["E+", "E-"])
        eq_uls = [c for c in uls if "E+" in c[1] or "E-" in c[1]]
        assert len(eq_uls) == 2

    def test_eq_sls_combos(self):
        """EQ adds G + E+(s) and G + E-(s) to SLS."""
        uls, sls = build_combinations(["W1"], eq_case_names=["E+", "E-"])
        eq_sls = [c for c in sls if "E+" in c[1] or "E-" in c[1]]
        assert len(eq_sls) == 2

    def test_eq_uls_factor_on_G(self):
        """EQ ULS combo: G factor = 1.0 (not 1.2)."""
        uls, sls = build_combinations([], eq_case_names=["E+", "E-"])
        eq_combo = [c for c in uls if "E+" in c[1]][0]
        assert eq_combo[2]["G"] == 1.0

    def test_no_eq_when_empty(self):
        """No eq_case_names means no EQ combos."""
        uls, sls = build_combinations(["W1"], eq_case_names=[])
        for c in uls:
            assert "E+" not in c[1]

    def test_default_no_eq(self):
        """Default build_combinations has no EQ combos (backward compat)."""
        uls, sls = build_combinations(["W1"])
        for c in uls:
            assert "E+" not in c[1]

    def test_eq_combo_numbering(self):
        """EQ combos are numbered sequentially after wind combos."""
        uls, sls = build_combinations(["W1", "W2"], eq_case_names=["E+", "E-"])
        names = [c[0] for c in uls]
        # 1.35G, 1.2G+1.5Q, 1.2G+W1, 0.9G+W1, 1.2G+W2, 0.9G+W2, 1.0G+E+, 1.0G+E-
        assert len(names) == 8
        assert names[-2] == "ULS-7"
        assert names[-1] == "ULS-8"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_standards.py::TestEarthquakeCombinations -v`
Expected: FAIL — `build_combinations() got an unexpected keyword argument 'eq_case_names'`

- [ ] **Step 3: Add eq_case_names to build_combinations**

Modify `portal_frame/standards/combinations_nzs1170_0.py`:

```python
def build_combinations(
    wind_case_names: list[str],
    ws_factor: float = 1.0,
    eq_case_names: list[str] | None = None,
    eq_sls_factor: float = 1.0,
):
    """Build full combo list including wind and earthquake cases.

    Args:
        wind_case_names: List of wind case names (e.g. ["W1", "W2", ...])
        ws_factor: SLS wind scaling factor (qs/qu).
        eq_case_names: List of earthquake case names (e.g. ["E+", "E-"]).
            None or empty list means no earthquake combos.
        eq_sls_factor: SLS earthquake scaling (Cd_sls/Cd_uls ratio, applied
            as combo factor). Default 1.0 — caller should set from actual values.
    """
    if eq_case_names is None:
        eq_case_names = []

    uls = []
    uls_n = 1
    # Static ULS combos
    uls.append((f"ULS-{uls_n}", "1.35G", {"G": 1.35})); uls_n += 1
    uls.append((f"ULS-{uls_n}", "1.2G + 1.5Q", {"G": 1.2, "Q": 1.5})); uls_n += 1
    # Wind ULS combos
    for wname in wind_case_names:
        uls.append((f"ULS-{uls_n}", f"1.2G + {wname}", {"G": 1.2, wname: 1.0})); uls_n += 1
        uls.append((f"ULS-{uls_n}", f"0.9G + {wname}", {"G": 0.9, wname: 1.0})); uls_n += 1
    # Earthquake ULS combos: 1.0G + E
    for ename in eq_case_names:
        uls.append((f"ULS-{uls_n}", f"1.0G + {ename}", {"G": 1.0, ename: 1.0})); uls_n += 1

    sls = []
    sls_n = 1
    # Static SLS combos
    sls.append((f"SLS-{sls_n}", "G + 0.7Q", {"G": 1.0, "Q": 0.7})); sls_n += 1
    sls.append((f"SLS-{sls_n}", "G", {"G": 1.0})); sls_n += 1
    # Wind SLS combos
    for wname in wind_case_names:
        sls.append((f"SLS-{sls_n}", f"G + {wname}(s)", {"G": 1.0, wname: ws_factor})); sls_n += 1
    # Earthquake SLS combos: G + E(s)
    for ename in eq_case_names:
        sls.append((f"SLS-{sls_n}", f"G + {ename}(s)", {"G": 1.0, ename: eq_sls_factor})); sls_n += 1

    return uls, sls
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_standards.py::TestEarthquakeCombinations -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add portal_frame/standards/combinations_nzs1170_0.py tests/test_standards.py
git commit -m "feat: earthquake load combinations in NZS 1170.0 combos"
```

---

### Task 10: SpaceGass Writer — JOINTLOADS and Earthquake Integration

**Files:**
- Modify: `portal_frame/io/spacegass_writer.py`
- Modify: `tests/test_output.py`

- [ ] **Step 1: Write failing test for JOINTLOADS output**

Add to `tests/test_output.py`:

```python
def test_earthquake_jointloads_output():
    """Earthquake loads produce JOINTLOADS section with forces at eave nodes."""
    from portal_frame.models.loads import EarthquakeInputs

    sections = load_all_sections()
    col_sec = sections["63020S2"]
    raf_sec = sections["650180295S2"]

    geom = PortalFrameGeometry(
        span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
    )
    topology = geom.to_topology()
    supports = SupportCondition()

    eq = EarthquakeInputs(Z=0.40, soil_class="C", R_uls=1.0, R_sls=0.25)
    loads = LoadInput(
        dead_load_roof=0.15, dead_load_wall=0.10,
        earthquake=eq,
    )

    writer = SpaceGassWriter(
        topology=topology,
        column_section=col_sec,
        rafter_section=raf_sec,
        supports=supports,
        loads=loads,
        span=geom.span,
        eave_height=geom.eave_height,
        roof_pitch=geom.roof_pitch,
        bay_spacing=geom.bay_spacing,
    )
    output = writer.write()

    assert "JOINTLOADS" in output
    # Should have E+ and E- cases
    assert "E+" in output
    assert "E-" in output
    # JOINTLOADS lines should reference eave node IDs (2 and 4)
    lines = output.split("\n")
    jl_lines = []
    in_jl = False
    for line in lines:
        if line == "JOINTLOADS":
            in_jl = True
            continue
        if in_jl and line == "":
            break
        if in_jl:
            jl_lines.append(line)
    # E+ case: 2 lines (node 2 and node 4, +X force)
    # E- case: 2 lines (node 2 and node 4, -X force)
    assert len(jl_lines) == 4  # 2 nodes x 2 cases (E+ ULS only; SLS uses factor)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_output.py::test_earthquake_jointloads_output -v`
Expected: FAIL — `JOINTLOADS` not in output

- [ ] **Step 3: Implement earthquake integration in SpaceGass writer**

Modify `portal_frame/io/spacegass_writer.py`. Add import at top:

```python
from portal_frame.standards.earthquake_nzs1170_5 import calculate_earthquake_forces
```

Add `_earthquake_cases()` method and `_jointloads()` method. Modify `write()`, `_combinations()`, `_titles()`, and the case map logic.

Key changes to `write()`:

```python
    def write(self) -> str:
        """Generate the complete SpaceGass text file."""
        # Pre-compute earthquake if enabled
        self._eq_result = None
        self._eq_case_map = {}
        if self.loads.earthquake is not None:
            self._eq_result = calculate_earthquake_forces(
                # Build a minimal geometry-like object
                type('G', (), {
                    'span': self.span,
                    'eave_height': self.eave_height,
                    'ridge_height': self.ridge_height,
                    'bay_spacing': self.bay_spacing,
                })(),
                self.loads.dead_load_roof,
                self.loads.dead_load_wall,
                self.loads.earthquake,
            )
            # Assign case numbers after wind cases
            next_case = 3 + len(self.loads.wind_cases)
            self._eq_case_map["E+"] = next_case
            self._eq_case_map["E-"] = next_case + 1

        parts = [
            self._header(),
            self._headings(),
            self._nodes(),
            self._members(),
            self._restraints(),
            self._sections(),
            self._materials(),
            self._selfweight(),
            self._load_cases(),
            self._jointloads(),
            self._combinations(),
            self._titles(),
            "END",
        ]
        return "\n".join(p for p in parts if p)
```

Add `_jointloads()` method:

```python
    def _jointloads(self) -> str:
        """Generate JOINTLOADS section for earthquake forces at eave nodes."""
        if self._eq_result is None:
            return ""

        eave_nodes = sorted(self.topology.get_eave_nodes(), key=lambda n: n.x)
        if len(eave_nodes) < 2:
            return ""

        F_uls = self._eq_result["F_node"]
        lines = ["JOINTLOADS"]

        # E+ case: +X force at each eave node
        cn_pos = self._eq_case_map["E+"]
        for node in eave_nodes:
            lines.append(
                f"{cn_pos},{node.id},{F_uls:.4f},0.0,0.0,0.0,0.0,0.0"
            )

        # E- case: -X force at each eave node
        cn_neg = self._eq_case_map["E-"]
        for node in eave_nodes:
            lines.append(
                f"{cn_neg},{node.id},{-F_uls:.4f},0.0,0.0,0.0,0.0,0.0"
            )

        lines.append("")
        return "\n".join(lines)
```

Update `_build_full_case_map()` helper (extract case map building to avoid duplication):

```python
    def _build_case_map(self) -> dict:
        """Build complete case numbering map."""
        case_map = {"G": 1, "Q": 2}
        next_case = 3
        for wc in self.loads.wind_cases:
            case_map[wc.name] = next_case
            next_case += 1
        case_map.update(self._eq_case_map)
        return case_map
```

Update `_combinations()` to include EQ:

```python
    def _combinations(self) -> str:
        """Generate COMBINATIONS section."""
        case_map = self._build_case_map()
        wind_case_names = [wc.name for wc in self.loads.wind_cases]

        eq_case_names = list(self._eq_case_map.keys())
        eq_sls_factor = 1.0
        if self._eq_result and self._eq_result["Cd_uls"] > 0:
            eq_sls_factor = self._eq_result["Cd_sls"] / self._eq_result["Cd_uls"]

        uls_combos, sls_combos = build_combinations(
            wind_case_names,
            ws_factor=self.loads.ws_factor,
            eq_case_names=eq_case_names,
            eq_sls_factor=eq_sls_factor,
        )
        uls_start = 101
        sls_start = 201

        lines = ["COMBINATIONS"]
        self._combo_id_map = {}
        for idx, (cname, cdesc, cfactors) in enumerate(uls_combos):
            combo_num = uls_start + idx
            self._combo_id_map[cname] = (combo_num, cdesc)
            for lc_key, factor in cfactors.items():
                if lc_key in case_map:
                    lines.append(f"{combo_num},{case_map[lc_key]},{factor:.2f}")
        for idx, (cname, cdesc, cfactors) in enumerate(sls_combos):
            combo_num = sls_start + idx
            self._combo_id_map[cname] = (combo_num, cdesc)
            for lc_key, factor in cfactors.items():
                if lc_key in case_map:
                    lines.append(f"{combo_num},{case_map[lc_key]},{factor:.2f}")
        lines.append("")
        return "\n".join(lines)
```

Update `_titles()`:

```python
    def _titles(self) -> str:
        """Generate TITLES section."""
        case_map = self._build_case_map()

        lines = ["TITLES"]
        lines.append("1,Dead load (G)")
        lines.append("2,Imposed roof load (Q)")
        for wc in self.loads.wind_cases:
            lines.append(f"{case_map[wc.name]},{wc.name} - {wc.description}")
        for ename, cn in self._eq_case_map.items():
            if ename == "E+":
                lines.append(f"{cn},E+ - Earthquake positive")
            else:
                lines.append(f"{cn},E- - Earthquake negative")
        for cname, (combo_num, cdesc) in self._combo_id_map.items():
            lines.append(f"{combo_num},{cname}: {cdesc}")
        lines.append("")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_output.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add portal_frame/io/spacegass_writer.py tests/test_output.py
git commit -m "feat: SpaceGass JOINTLOADS output for earthquake forces at eave nodes"
```

---

### Task 11: GUI — Earthquake Tab

**Files:**
- Modify: `portal_frame/gui/app.py`

- [ ] **Step 1: Add "Earthquake" to tab list in _build_ui**

In `_build_ui()`, change:

```python
        tab_names = ["Frame", "Wind", "Combos"]
```

to:

```python
        tab_names = ["Frame", "Wind", "Earthquake", "Combos"]
```

And add after the `_build_combos_tab` call:

```python
        self._build_earthquake_tab(self._tab_pages["Earthquake"])
```

- [ ] **Step 2: Implement _build_earthquake_tab**

Add import at top of `portal_frame/gui/app.py`:

```python
from portal_frame.standards.earthquake_nzs1170_5 import (
    NZ_HAZARD_FACTORS, calculate_earthquake_forces,
)
from portal_frame.models.loads import EarthquakeInputs
```

Add the method:

```python
    def _build_earthquake_tab(self, parent):
        pad = {"padx": 10, "pady": (0, 2)}

        self._section_header(parent, "EARTHQUAKE  (NZS 1170.5:2004)")

        self.eq_enabled_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parent, text="Include earthquake loading",
            variable=self.eq_enabled_var, font=FONT_BOLD,
            fg=COLORS["fg"], bg=COLORS["bg_panel"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["fg"],
            command=self._on_eq_toggle,
        ).pack(fill="x", padx=10, pady=(0, 6))

        self.eq_content = tk.Frame(parent, bg=COLORS["bg_panel"])
        self.eq_content.pack(fill="x")

        # Location dropdown
        self._section_header(self.eq_content, "SEISMIC HAZARD")
        loc_frame = tk.Frame(self.eq_content, bg=COLORS["bg_panel"])
        loc_frame.pack(fill="x", **pad)

        locations = sorted(NZ_HAZARD_FACTORS.keys())
        self.eq_location = LabeledCombo(
            loc_frame, "Location", values=locations, default="Wellington", width=20,
        )
        self.eq_location.pack(fill="x")
        self.eq_location.bind_change(self._on_eq_location_change)

        self.eq_Z = LabeledEntry(self.eq_content, "Z (hazard factor)", 0.40, "")
        self.eq_Z.pack(fill="x", **pad)
        self.eq_Z.bind_change(self._update_eq_results)

        self.eq_soil = LabeledCombo(
            self.eq_content, "Soil Class", values=["A", "B", "C", "D", "E"],
            default="C", width=6,
        )
        self.eq_soil.pack(fill="x", **pad)
        self.eq_soil.bind_change(self._update_eq_results)

        self._section_header(self.eq_content, "DUCTILITY & IMPORTANCE")

        # Ductility presets
        duct_presets = ["Nominally ductile (mu=1.25, Sp=0.925)",
                        "Limited ductile (mu=2.0, Sp=0.7)",
                        "Ductile (mu=4.0, Sp=0.7)",
                        "Elastic (mu=1.0, Sp=1.0)",
                        "Custom"]
        self.eq_ductility = LabeledCombo(
            self.eq_content, "Ductility Preset", values=duct_presets,
            default=duct_presets[0], width=36,
        )
        self.eq_ductility.pack(fill="x", **pad)
        self.eq_ductility.bind_change(self._on_ductility_change)

        self.eq_mu = LabeledEntry(self.eq_content, "mu (ductility)", 1.25, "")
        self.eq_mu.pack(fill="x", **pad)
        self.eq_mu.bind_change(self._update_eq_results)

        self.eq_Sp = LabeledEntry(self.eq_content, "Sp (structural perf.)", 0.925, "")
        self.eq_Sp.pack(fill="x", **pad)
        self.eq_Sp.bind_change(self._update_eq_results)

        self.eq_R_uls = LabeledEntry(self.eq_content, "R (ULS return period)", 1.0, "")
        self.eq_R_uls.pack(fill="x", **pad)
        self.eq_R_uls.bind_change(self._update_eq_results)

        self.eq_R_sls = LabeledEntry(self.eq_content, "R (SLS return period)", 0.25, "")
        self.eq_R_sls.pack(fill="x", **pad)
        self.eq_R_sls.bind_change(self._update_eq_results)

        self.eq_near_fault = LabeledEntry(self.eq_content, "N(T,D) near-fault", 1.0, "")
        self.eq_near_fault.pack(fill="x", **pad)
        self.eq_near_fault.bind_change(self._update_eq_results)

        self.eq_extra_mass = LabeledEntry(self.eq_content, "Extra seismic mass", 0.0, "kN")
        self.eq_extra_mass.pack(fill="x", **pad)
        self.eq_extra_mass.bind_change(self._update_eq_results)

        self._section_header(self.eq_content, "CALCULATED VALUES")

        self.eq_results_label = tk.Label(
            self.eq_content, text="(enable earthquake loading to see results)",
            font=FONT_MONO, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
            anchor="w", justify="left",
        )
        self.eq_results_label.pack(fill="x", padx=10, pady=(0, 8))

        # Initially hide content
        self.eq_content.pack_forget()

    def _on_eq_toggle(self, *_):
        if self.eq_enabled_var.get():
            self.eq_content.pack(fill="x")
            self._update_eq_results()
        else:
            self.eq_content.pack_forget()
        self.refresh_load_case_list()

    def _on_eq_location_change(self, *_):
        loc = self.eq_location.get()
        if loc in NZ_HAZARD_FACTORS:
            self.eq_Z.set(NZ_HAZARD_FACTORS[loc])
        self._update_eq_results()

    def _on_ductility_change(self, *_):
        preset = self.eq_ductility.get()
        if "Nominally" in preset:
            self.eq_mu.set(1.25)
            self.eq_Sp.set(0.925)
        elif "Limited" in preset:
            self.eq_mu.set(2.0)
            self.eq_Sp.set(0.7)
        elif "Ductile" in preset and "Limited" not in preset:
            self.eq_mu.set(4.0)
            self.eq_Sp.set(0.7)
        elif "Elastic" in preset:
            self.eq_mu.set(1.0)
            self.eq_Sp.set(1.0)
        # "Custom" — leave values as-is
        self._update_eq_results()

    def _update_eq_results(self, *_):
        if not self.eq_enabled_var.get():
            return
        try:
            geom = self._build_geometry()
            eq = EarthquakeInputs(
                Z=self.eq_Z.get(),
                soil_class=self.eq_soil.get(),
                R_uls=self.eq_R_uls.get(),
                R_sls=self.eq_R_sls.get(),
                mu=self.eq_mu.get(),
                Sp=self.eq_Sp.get(),
                near_fault=self.eq_near_fault.get(),
                extra_seismic_mass=self.eq_extra_mass.get(),
            )
            result = calculate_earthquake_forces(
                geom, self.dead_roof.get(), self.dead_wall.get(), eq,
            )
            text = (
                f"T1 = {result['T1']:.3f} s\n"
                f"Ch(T1) = {result['Ch']:.3f}\n"
                f"k_mu = {result['k_mu']:.3f}\n"
                f"Cd(T1) ULS = {result['Cd_uls']:.4f}\n"
                f"Cd(T1) SLS = {result['Cd_sls']:.4f}\n"
                f"Wt = {result['Wt']:.2f} kN\n"
                f"V_uls = {result['V_uls']:.2f} kN\n"
                f"V_sls = {result['V_sls']:.2f} kN\n"
                f"F_node ULS = {result['F_node']:.2f} kN (per knee)\n"
                f"F_node SLS = {result['F_node_sls']:.2f} kN (per knee)"
            )
            self.eq_results_label.config(text=text)
        except Exception as e:
            self.eq_results_label.config(text=f"Error: {e}")
```

- [ ] **Step 3: Update refresh_load_case_list to include EQ cases**

Modify `refresh_load_case_list`:

```python
    def refresh_load_case_list(self):
        choices = ["(none)", "G - Dead Load", "Q - Live Load"]
        wc_list = self.wind_table.get_wind_cases()
        for wc in wc_list:
            choices.append(f"{wc['name']} - {wc.get('description', '')}"[:50])
        if self.eq_enabled_var.get():
            choices.append("E+ - Earthquake positive")
            choices.append("E- - Earthquake negative")
        self.load_case_combo["values"] = choices
```

- [ ] **Step 4: Update _build_preview_loads for EQ visualization**

Add to end of `_build_preview_loads`, before the final `return`:

```python
        elif selected.startswith("E"):
            # Earthquake loads: horizontal arrows at eave nodes
            try:
                geom_obj = self._build_geometry()
                eq = EarthquakeInputs(
                    Z=self.eq_Z.get(), soil_class=self.eq_soil.get(),
                    R_uls=self.eq_R_uls.get(), R_sls=self.eq_R_sls.get(),
                    mu=self.eq_mu.get(), Sp=self.eq_Sp.get(),
                    near_fault=self.eq_near_fault.get(),
                    extra_seismic_mass=self.eq_extra_mass.get(),
                )
                result = calculate_earthquake_forces(
                    geom_obj, self.dead_roof.get(), self.dead_wall.get(), eq,
                )
                F = result["F_node"]
                is_negative = "E-" in selected
                if is_negative:
                    F = -F

                is_mono = self.roof_type_var.get() == "mono"
                # Represent as point loads on columns at eave height
                # Use a short segment at the top of each column
                left_col = (1, 2) if not is_mono else (1, 2)
                right_col = (5, 4) if not is_mono else (4, 3)
                for nf, nt in [left_col, right_col]:
                    members.append({"from": nf, "to": nt, "segments": [
                        {"start_pct": 90, "end_pct": 100,
                         "w_kn": F,
                         "direction": "global_x"}]})
            except Exception:
                pass
```

- [ ] **Step 5: Update _generate to pass earthquake inputs**

In `_generate()`, after creating `loads = LoadInput(...)`, add earthquake:

```python
            earthquake = None
            if self.eq_enabled_var.get():
                earthquake = EarthquakeInputs(
                    Z=self.eq_Z.get(),
                    soil_class=self.eq_soil.get(),
                    R_uls=self.eq_R_uls.get(),
                    R_sls=self.eq_R_sls.get(),
                    mu=self.eq_mu.get(),
                    Sp=self.eq_Sp.get(),
                    near_fault=self.eq_near_fault.get(),
                    extra_seismic_mass=self.eq_extra_mass.get(),
                )

            loads = LoadInput(
                dead_load_roof=self.dead_roof.get(),
                dead_load_wall=self.dead_wall.get(),
                live_load_roof=self.live_roof.get(),
                wind_cases=wind_cases,
                include_self_weight=self.self_weight_var.get(),
                ws_factor=ws_factor,
                earthquake=earthquake,
            )
```

- [ ] **Step 6: Update _build_combos_tab to mention EQ combos**

Update the combo text in `_build_combos_tab`:

```python
    def _build_combos_tab(self, parent):
        self._section_header(parent, "LOAD COMBINATIONS  (AS/NZS 1170.0:2002)")

        combo_text = (
            "ULS-1: 1.35G              (101+)\n"
            "ULS-2: 1.2G + 1.5Q\n"
            "ULS-n: 1.2G + Wu  (per wind case)\n"
            "ULS-n: 0.9G + Wu  (per wind case)\n"
            "ULS-n: 1.0G + E+  (if EQ enabled)\n"
            "ULS-n: 1.0G + E-  (if EQ enabled)\n"
            "SLS-1: G + 0.7Q           (201+)\n"
            "SLS-2: G\n"
            "SLS-n: G + Ws  (per wind case)\n"
            "SLS-n: G + E(s)  (if EQ enabled)\n\n"
            "Table 4.1 roof factors: psi_s=0.7, psi_l=0.0, psi_c=0.0\n"
            "EQ combo: G factor = 1.0 (not 1.2), Q drops out (psi_c=0)"
        )
        tk.Label(parent, text=combo_text, font=FONT_MONO, fg=COLORS["fg_dim"],
                 bg=COLORS["bg_panel"], anchor="w", justify="left"
                 ).pack(fill="x", padx=10, pady=(0, 12))
```

- [ ] **Step 7: Verify GUI launches with Earthquake tab**

Run: `python -m portal_frame.run_gui`
Test: Enable earthquake, select Wellington, choose ductility preset, verify calculated values appear.

- [ ] **Step 8: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add portal_frame/gui/app.py
git commit -m "feat: GUI earthquake tab with location, ductility, and calculated values"
```

---

### Task 12: Config Schema Update

**Files:**
- Modify: `portal_frame/io/config.py`

- [ ] **Step 1: Update FrameConfig and from_dict to support new fields**

In `portal_frame/io/config.py`, update `FrameConfig`:

```python
@dataclass
class FrameConfig:
    geometry: PortalFrameGeometry
    column_section_name: str
    rafter_section_name: str
    supports: SupportCondition
    loads: LoadInput
    building_depth: float = 50.0
    wind_cp_inputs: dict = field(default_factory=dict)
```

Update `from_dict` to handle `roof_type` and `apex_position_pct` in the geometry section:

```python
        geom = PortalFrameGeometry(
            span=g["span"],
            eave_height=g["eave_height"],
            roof_pitch=g["roof_pitch"],
            bay_spacing=g.get("bay_spacing", 6.0),
            roof_type=g.get("roof_type", "gable"),
            apex_position_pct=g.get("apex_position_pct", 50.0),
        )
```

Update `from_dict` to handle earthquake:

```python
        eq = None
        if "earthquake" in cfg:
            eq_cfg = cfg["earthquake"]
            eq = EarthquakeInputs(
                Z=eq_cfg.get("Z", 0.0),
                soil_class=eq_cfg.get("soil_class", "C"),
                R_uls=eq_cfg.get("R_uls", 1.0),
                R_sls=eq_cfg.get("R_sls", 0.25),
                mu=eq_cfg.get("mu", 1.0),
                Sp=eq_cfg.get("Sp", 1.0),
                near_fault=eq_cfg.get("near_fault", 1.0),
                extra_seismic_mass=eq_cfg.get("extra_seismic_mass", 0.0),
            )
```

Then pass `earthquake=eq` to the `LoadInput` constructor.

Also update `build_from_config` to pass `split_pct` to `generate_standard_wind_cases` if using auto-generation.

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS (existing configs don't have new fields — defaults apply)

- [ ] **Step 3: Commit**

```bash
git add portal_frame/io/config.py
git commit -m "feat: config schema supports roof type, apex position, and earthquake"
```

---

### Task 13: Step 0 — JOINTLOADS Format Verification File

**Files:**
- (no code changes — generate a test file for SpaceGass verification)

- [ ] **Step 1: Generate a minimal test file with JOINTLOADS**

Create a script or use CLI to generate a SpaceGass file with earthquake enabled. This file should be opened in SpaceGass v14.25 by the user to verify the JOINTLOADS format is accepted.

Run:
```bash
python -c "
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import LoadInput, EarthquakeInputs
from portal_frame.models.supports import SupportCondition
from portal_frame.io.section_library import load_all_sections
from portal_frame.io.spacegass_writer import SpaceGassWriter

sections = load_all_sections()
geom = PortalFrameGeometry(span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0)
topo = geom.to_topology()
eq = EarthquakeInputs(Z=0.40, soil_class='C', R_uls=1.0, R_sls=0.25, mu=1.25, Sp=0.925)
loads = LoadInput(dead_load_roof=0.15, dead_load_wall=0.10, earthquake=eq)
writer = SpaceGassWriter(
    topology=topo, column_section=sections['63020S2'], rafter_section=sections['650180295S2'],
    supports=SupportCondition(), loads=loads,
    span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
)
with open('test_jointloads.txt', 'w') as f:
    f.write(writer.write())
print('Generated test_jointloads.txt')
"
```

- [ ] **Step 2: Open test_jointloads.txt in SpaceGass v14.25**

User action: Open the file in SpaceGass and confirm:
- JOINTLOADS section is parsed without error
- E+ and E- load cases appear with correct horizontal forces at nodes 2 and 4
- Combinations include earthquake combos

- [ ] **Step 3: Report results**

If format is rejected, adjust the JOINTLOADS format in `spacegass_writer.py` based on SpaceGass error messages.

---

### Task 14: Final Integration Test and Backward Compatibility

**Files:**
- Modify: `portal_frame_generator.py` (backward compat wrapper)
- Run: full test suite

- [ ] **Step 1: Update backward compatibility wrapper**

In `portal_frame_generator.py`, the `PortalFrameGenerator` class creates a `PortalFrameGeometry`. Ensure the new fields have defaults so existing code works without changes.

Verify: The wrapper should work without changes since `roof_type` defaults to `"gable"` and `apex_position_pct` defaults to `50.0`.

Run: `python -c "from portal_frame_generator import PortalFrameGenerator; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Run GUI end-to-end test**

Run: `python -m portal_frame.run_gui`
Test checklist:
- Switch to Mono roof — preview shows single-slope frame
- Switch to Gable, move apex to 30% — preview shows asymmetric gable
- Set pitch to 2 deg — warning about ponding appears
- Set pitch to 35 deg — warning about steep pitch
- Enable earthquake tab, select Christchurch, Soil D, Limited ductile
- Verify calculated values update live
- Generate file — verify it saves and contains JOINTLOADS section
- Open generated file in SpaceGass v14.25 for final verification

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration fixes from end-to-end testing"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete roof types, variable apex, and earthquake loading implementation"
```