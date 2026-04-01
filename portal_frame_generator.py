"""
SpaceGass 2D Portal Frame Generator — Backward-compatible wrapper.

This file re-exports everything from the portal_frame package so that
existing code (including portal_frame_gui.py) continues to work unchanged.

The actual implementation lives in portal_frame/ subpackages.
"""

# Models
from portal_frame.models.geometry import PortalFrameGeometry as FrameGeometry
from portal_frame.models.sections import CFS_Section
from portal_frame.models.loads import RafterZoneLoad, WindCase, LoadInput
from portal_frame.models.supports import SupportCondition

# Standards
from portal_frame.standards.utils import lerp as _lerp
from portal_frame.standards.wind_nzs1170_2 import (
    leeward_cpe_lookup, cfig, roof_cpe_zones,
    calculate_crosswind_zones, TABLE_5_3A_ZONES,
    _compute_zone_loads, _mirror_zones, _split_zones_to_rafters,
    WindCpInputs, generate_standard_wind_cases,
    _TABLE_53A_HD_LOW, _TABLE_53A_HD_HIGH,
)
from portal_frame.standards.combinations_nzs1170_0 import build_combinations

# I/O
from portal_frame.io.section_library import (
    find_library_file, parse_section_library, load_all_sections, get_section,
    LIBRARY_SEARCH_PATHS, SECTION_LIBRARY_FILES,
)
from portal_frame.io.config import build_from_config, create_example_config

# SpaceGass generator (backward-compatible class that wraps the new writer)
import math
from portal_frame.io.spacegass_writer import SpaceGassWriter
from portal_frame.models.geometry import PortalFrameGeometry


class PortalFrameGenerator:
    """Backward-compatible wrapper around SpaceGassWriter."""

    def __init__(self, geometry, column_section, rafter_section, supports, loads):
        self.geom = geometry
        self.col_sec = column_section
        self.raf_sec = rafter_section
        self.supports = supports
        self.loads = loads
        self.ridge_height = (
            self.geom.eave_height
            + (self.geom.span / 2.0) * math.tan(math.radians(self.geom.roof_pitch))
        )

    def generate(self) -> str:
        pfg = PortalFrameGeometry(
            span=self.geom.span,
            eave_height=self.geom.eave_height,
            roof_pitch=self.geom.roof_pitch,
            bay_spacing=self.geom.bay_spacing,
        )
        topology = pfg.to_topology()
        writer = SpaceGassWriter(
            topology=topology,
            column_section=self.col_sec,
            rafter_section=self.raf_sec,
            supports=self.supports,
            loads=self.loads,
            span=self.geom.span,
            eave_height=self.geom.eave_height,
            roof_pitch=self.geom.roof_pitch,
            bay_spacing=self.geom.bay_spacing,
        )
        return writer.write()


# CLI
def list_sections():
    from portal_frame.cli import list_sections as _ls
    _ls()


def main():
    from portal_frame.cli import main as _main
    _main()


if __name__ == "__main__":
    main()
