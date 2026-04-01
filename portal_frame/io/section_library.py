"""SpaceGass Section Library Reader — XML parsing and section lookup."""

import os
import sys
import xml.etree.ElementTree as ET
from typing import Optional

from portal_frame.models.sections import CFS_Section


# Library search paths (in order of priority)
LIBRARY_SEARCH_PATHS = [
    r"C:\ProgramData\SPACE GASS\Custom Libraries",
    r"C:\Program Files\SPACE GASS 14.2\Standard Libraries",
    r"C:\Program Files (x86)\SPACE GASS 14.2\Standard Libraries",
]

# Known library files — custom first, then standard NZ cold-formed
SECTION_LIBRARY_FILES = [
    "LIBRARY_SG14_SECTION_FS.slsc",   # Formsteel custom
    "LIBRARY_SECTION_NZCold.sls",      # Standard NZ cold-formed
    "LIBRARY_SECTION_AustCold.sls",    # Standard AU cold-formed
]


def _normalize_library_name(filename: str) -> str:
    """Extract display name from library filename.

    LIBRARY_SG14_SECTION_FS.slsc -> "FS"
    LIBRARY_SECTION_NZCold.sls -> "NZCold"
    """
    name = filename
    for prefix in ["LIBRARY_SG14_SECTION_", "LIBRARY_SECTION_"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    for ext in [".slsc", ".sls"]:
        if name.endswith(ext):
            name = name[:-len(ext)]
    return name


def find_library_file(filename: str) -> Optional[str]:
    """Search for a library file in known locations."""
    for base in LIBRARY_SEARCH_PATHS:
        path = os.path.join(base, filename)
        if os.path.isfile(path):
            return path
    return None


def parse_section_library(filepath: str) -> list[CFS_Section]:
    """Parse a SpaceGass .sls/.slsc XML section library file."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    lib_filename = os.path.basename(filepath)
    lib_name = _normalize_library_name(lib_filename)

    sections = []
    groups = root.find("Groups")
    if groups is None:
        return sections

    for group in groups.findall("Group"):
        gcode = ""
        if group.find("GroupCode") is not None:
            gcode = group.find("GroupCode").text or ""
        elif group.find("Name") is not None:
            gcode = group.find("Name").text or ""

        sec_container = group.find("Sections")
        if sec_container is None:
            continue

        for sec_elem in sec_container.findall("Section"):
            name_el = sec_elem.find("Name")
            if name_el is None or not name_el.text:
                continue

            props = sec_elem.find("SectionProperties")
            if props is None:
                continue

            def prop_val(tag: str) -> float:
                el = props.find(tag)
                if el is not None and el.text:
                    try:
                        return float(el.text)
                    except ValueError:
                        pass
                return 0.0

            sections.append(CFS_Section(
                name=name_el.text.strip(),
                library=lib_filename,
                library_name=lib_name,
                group=gcode,
                Ax=prop_val("A"),
                J=prop_val("J"),
                Iy=prop_val("Iyp"),
                Iz=prop_val("Izp"),
                Iw=prop_val("Iw"),
                Sy=prop_val("Syp"),
                Sz=prop_val("Szp"),
            ))

    return sections


def load_all_sections() -> dict[str, CFS_Section]:
    """Load all sections from all available library files. Returns dict keyed by name."""
    all_sections: dict[str, CFS_Section] = {}

    for lib_file in SECTION_LIBRARY_FILES:
        path = find_library_file(lib_file)
        if path is None:
            continue
        try:
            secs = parse_section_library(path)
            for s in secs:
                # First found wins (custom libraries searched first)
                if s.name not in all_sections:
                    all_sections[s.name] = s
        except ET.ParseError:
            print(f"Warning: Could not parse {path}", file=sys.stderr)

    return all_sections


def get_section(name: str, library: Optional[dict] = None) -> CFS_Section:
    """Look up a section by name from the library."""
    if library is None:
        library = load_all_sections()

    if name not in library:
        available = ", ".join(sorted(library.keys()))
        raise ValueError(
            f"Section '{name}' not found in library.\n"
            f"Available sections: {available}"
        )
    return library[name]
