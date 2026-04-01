"""CLI entry point for portal frame generator."""

import json
import math
import sys

from portal_frame.io.section_library import load_all_sections, get_section
from portal_frame.io.config import build_from_config, create_example_config
from portal_frame.standards.combinations_nzs1170_0 import build_combinations


def list_sections():
    """Print all available sections from the library."""
    library = load_all_sections()
    if not library:
        print("No section libraries found!")
        from portal_frame.io.section_library import LIBRARY_SEARCH_PATHS
        print(f"Searched: {LIBRARY_SEARCH_PATHS}")
        return

    by_lib: dict[str, list] = {}
    for sec in library.values():
        by_lib.setdefault(sec.library, []).append(sec)

    for lib_name, secs in by_lib.items():
        print(f"\n{'='*70}")
        print(f"Library: {lib_name}")
        print(f"{'='*70}")
        print(f"  {'Name':<25s}  {'Group':>5s}  {'A(mm2)':>12s}  {'Iy(mm4)':>14s}  {'Iz(mm4)':>14s}  {'J(mm4)':>14s}")
        print(f"  {'-'*25}  {'-'*5}  {'-'*12}  {'-'*14}  {'-'*14}  {'-'*14}")
        for s in sorted(secs, key=lambda x: (x.group, x.name)):
            print(
                f"  {s.name:<25s}  {s.group:>5s}  {s.Ax:>12.1f}  {s.Iy:>14.1f}  "
                f"{s.Iz:>14.1f}  {s.J:>14.1f}"
            )

    print(f"\nTotal: {len(library)} sections available")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list-sections":
        list_sections()
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--example-config":
        cfg = create_example_config()
        out_path = "example_portal_frame.json"
        with open(out_path, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"Example config written to: {out_path}")
        print("\nSections are specified by NAME from the SpaceGass library.")
        print("Run --list-sections to see available sections.")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        config_path = sys.argv[2]
        with open(config_path, "r") as f:
            cfg = json.load(f)
    else:
        cfg = create_example_config()
        print("No config file specified. Using built-in example.")
        print("  --list-sections     List all available library sections")
        print("  --example-config    Generate an editable JSON config file")
        print("  --config <file>     Load a custom config")
        print()

    output = build_from_config(cfg)

    span = cfg["geometry"]["span"]
    pitch = cfg["geometry"]["roof_pitch"]
    out_file = f"portal_{span:.0f}m_span_{pitch:.0f}deg.txt"

    with open(out_file, "w") as f:
        f.write(output)

    # Load sections for display
    library = load_all_sections()
    col = get_section(cfg["sections"]["column"], library)
    raf = get_section(cfg["sections"]["rafter"], library)

    eave = cfg["geometry"]["eave_height"]
    ridge = eave + (span / 2.0) * math.tan(math.radians(pitch))

    print(f"SpaceGass file generated: {out_file}")
    print()
    print("Frame summary:")
    print(f"  Span:         {span:.1f} m")
    print(f"  Eave height:  {eave:.1f} m")
    print(f"  Roof pitch:   {pitch:.1f} deg")
    print(f"  Bay spacing:  {cfg['geometry']['bay_spacing']:.1f} m")
    print(f"  Ridge height: {ridge:.3f} m")
    print(f"  Columns:      {col.name}  (A={col.Ax:.0f} mm2, Iz={col.Iz:.0f} mm4) [{col.library}]")
    print(f"  Rafters:      {raf.name}  (A={raf.Ax:.0f} mm2, Iz={raf.Iz:.0f} mm4) [{raf.library}]")
    left = cfg.get("supports", {}).get("left_base", "pinned")
    right = cfg.get("supports", {}).get("right_base", "pinned")
    print(f"  Supports:     L={left}, R={right}")
    print(f"  Wind cases:   {len(cfg.get('loads', {}).get('wind_cases', []))}")


if __name__ == "__main__":
    main()
