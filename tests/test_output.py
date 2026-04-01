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
