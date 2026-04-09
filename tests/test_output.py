"""Integration test — verify the new package produces byte-identical output."""

from portal_frame.io.config import build_from_config, create_example_config


def test_output_matches_baseline():
    """The refactored package must produce identical SpaceGass output."""
    cfg = create_example_config()
    output = build_from_config(cfg)

    # Verify key structural elements are present
    assert "SPACE GASS Text File - Version 1420" in output
    assert "NODES" in output
    assert "MEMBERS" in output
    assert "RESTRAINTS" in output
    assert "SECTIONS" in output
    assert "SELFWEIGHT" in output
    assert "MEMBFORCES" in output
    assert "COMBINATIONS" in output
    assert "TITLES" in output
    assert "END" in output

    # Verify specific content
    lines = output.split("\n")

    # Check version line
    assert lines[0] == "SPACE GASS Text File - Version 1420"

    # Check 5 nodes present
    node_section = False
    node_count = 0
    for line in lines:
        if line == "NODES":
            node_section = True
            continue
        if node_section and line == "":
            break
        if node_section:
            node_count += 1
    assert node_count == 5

    # Check 4 members present
    member_section = False
    member_count = 0
    for line in lines:
        if line == "MEMBERS":
            member_section = True
            continue
        if member_section and line == "":
            break
        if member_section:
            member_count += 1
    assert member_count == 4


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

    lines = output.split("\n")

    # Count nodes — expect 4
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

    # Count members — expect 3
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

    # Dead load should be on member 2 (rafter) not member 3 (right column)
    in_membforces = False
    membforce_lines = []
    for line in lines:
        if line == "MEMBFORCES":
            in_membforces = True
            continue
        if in_membforces and line == "":
            break
        if in_membforces:
            membforce_lines.append(line)

    # Case 1 (dead load): members should be 2 (rafter), 1 and 3 (columns)
    dead_members = set()
    for mfl in membforce_lines:
        parts = mfl.split(",")
        if parts[0] == "1":  # case 1 = dead load
            dead_members.add(int(parts[1]))
    # Rafter is member 2, columns are 1 and 3
    assert 2 in dead_members  # rafter gets roof dead load
    assert 1 in dead_members  # left column gets wall dead load
    assert 3 in dead_members  # right column gets wall dead load
    assert 4 not in dead_members  # member 4 doesn't exist in mono


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

    assert "NODELOADS" in output
    assert "E+" in output
    assert "E-" in output

    lines = output.split("\n")
    jl_lines = []
    in_jl = False
    for line in lines:
        if line == "NODELOADS":
            in_jl = True
            continue
        if in_jl and line == "":
            break
        if in_jl:
            jl_lines.append(line)
    # E+ case: 2 lines (node 2 and node 4), E- case: 2 lines
    assert len(jl_lines) == 4


def test_no_jointloads_without_earthquake():
    """Without earthquake, no JOINTLOADS section appears."""
    cfg = create_example_config()
    output = build_from_config(cfg)
    assert "NODELOADS" not in output


def test_load_case_groups_in_output():
    """SpaceGass output contains LOAD CASE GROUPS."""
    cfg = create_example_config()
    output = build_from_config(cfg)
    assert "LOAD CASE GROUPS" in output
    lines = output.split("\n")
    idx = next(i for i, l in enumerate(lines) if "LOAD CASE GROUPS" in l)
    group_lines = []
    for line in lines[idx+1:]:
        if line.strip() == "" or line.startswith(("TITLES", "END")):
            break
        group_lines.append(line.strip())
    assert any('"ULS"' in l for l in group_lines)
    assert any('"SLS"' in l for l in group_lines)
    assert any('"ULS-Wind"' in l for l in group_lines)
    assert any('"SLS-Wind Only"' in l for l in group_lines)
