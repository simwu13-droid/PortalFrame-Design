"""Configuration parsing and example generation."""

import json
from dataclasses import dataclass, field

from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import RafterZoneLoad, WindCase, LoadInput, EarthquakeInputs
from portal_frame.models.supports import SupportCondition
from portal_frame.io.section_library import load_all_sections, get_section
from portal_frame.standards.wind_nzs1170_2 import WindCpInputs, generate_standard_wind_cases
from portal_frame.io.spacegass_writer import SpaceGassWriter


@dataclass
class FrameConfig:
    """Validated configuration for a portal frame generation."""
    geometry: PortalFrameGeometry
    column_section_name: str
    rafter_section_name: str
    supports: SupportCondition
    loads: LoadInput
    building_depth: float = 50.0
    wind_cp_inputs: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, cfg: dict) -> "FrameConfig":
        """Parse and validate a JSON config dict."""
        g = cfg["geometry"]
        geom = PortalFrameGeometry(
            span=g["span"],
            eave_height=g["eave_height"],
            roof_pitch=g["roof_pitch"],
            bay_spacing=g.get("bay_spacing", 6.0),
            roof_type=g.get("roof_type", "gable"),
            apex_position_pct=g.get("apex_position_pct", 50.0),
        )

        supports = SupportCondition(
            left_base=cfg.get("supports", {}).get("left_base", "pinned"),
            right_base=cfg.get("supports", {}).get("right_base", "pinned"),
        )

        wind_cases = []
        for wc_cfg in cfg.get("loads", {}).get("wind_cases", []):
            wc_dict = dict(wc_cfg)  # copy to avoid mutating config
            zones_left = [RafterZoneLoad(**z) for z in wc_dict.pop("left_rafter_zones", [])]
            zones_right = [RafterZoneLoad(**z) for z in wc_dict.pop("right_rafter_zones", [])]
            wc = WindCase(**wc_dict, left_rafter_zones=zones_left, right_rafter_zones=zones_right)
            wind_cases.append(wc)

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

        loads = LoadInput(
            dead_load_roof=cfg.get("loads", {}).get("dead_load_roof", 0.0),
            dead_load_wall=cfg.get("loads", {}).get("dead_load_wall", 0.0),
            live_load_roof=cfg.get("loads", {}).get("live_load_roof", 0.25),
            wind_cases=wind_cases,
            include_self_weight=cfg.get("loads", {}).get("include_self_weight", True),
            earthquake=eq,
        )

        return cls(
            geometry=geom,
            column_section_name=cfg["sections"]["column"],
            rafter_section_name=cfg["sections"]["rafter"],
            supports=supports,
            loads=loads,
            building_depth=cfg.get("loads", {}).get("building_depth", 50.0),
            wind_cp_inputs=cfg.get("loads", {}).get("wind_cp_inputs", {}),
        )


def build_from_config(cfg: dict) -> str:
    """Build SpaceGass file from config dictionary."""
    config = FrameConfig.from_dict(cfg)
    library = load_all_sections()

    col_sec = get_section(config.column_section_name, library)
    raf_sec = get_section(config.rafter_section_name, library)

    topology = config.geometry.to_topology()

    writer = SpaceGassWriter(
        topology=topology,
        column_section=col_sec,
        rafter_section=raf_sec,
        supports=config.supports,
        loads=config.loads,
        span=config.geometry.span,
        eave_height=config.geometry.eave_height,
        roof_pitch=config.geometry.roof_pitch,
        bay_spacing=config.geometry.bay_spacing,
    )
    return writer.write()


def create_example_config() -> dict:
    """Create an example config using Formsteel library sections."""
    span = 12.0
    eave = 4.5
    pitch = 5.0
    depth = 50.0
    roof_type = "gable"
    apex_position_pct = 50.0
    cp = WindCpInputs()
    split_pct = apex_position_pct if roof_type == "gable" else 50.0
    cases = generate_standard_wind_cases(span, eave, pitch, depth, cp, split_pct=split_pct, roof_type=roof_type)

    wind_list = []
    for wc in cases:
        entry = {
            "name": wc.name,
            "description": wc.description,
            "direction": wc.direction,
            "envelope": wc.envelope,
            "is_crosswind": wc.is_crosswind,
            "left_wall": wc.left_wall,
            "right_wall": wc.right_wall,
        }
        if wc.left_rafter_zones:
            entry["left_rafter_zones"] = [
                {"start_pct": z.start_pct, "end_pct": z.end_pct, "pressure": z.pressure}
                for z in wc.left_rafter_zones
            ]
            entry["right_rafter_zones"] = [
                {"start_pct": z.start_pct, "end_pct": z.end_pct, "pressure": z.pressure}
                for z in wc.right_rafter_zones
            ]
        else:
            entry["left_rafter"] = wc.left_rafter
            entry["right_rafter"] = wc.right_rafter
        wind_list.append(entry)

    return {
        "geometry": {
            "span": span,
            "eave_height": eave,
            "roof_pitch": pitch,
            "bay_spacing": 6.0,
        },
        "sections": {
            "column": "63020S2",
            "rafter": "650180295S2",
        },
        "supports": {
            "left_base": "pinned",
            "right_base": "pinned",
        },
        "loads": {
            "dead_load_roof": 0.15,
            "dead_load_wall": 0.10,
            "live_load_roof": 0.25,
            "include_self_weight": True,
            "building_depth": depth,
            "wind_cp_inputs": {
                "qu": cp.qu, "qs": cp.qs,
                "kc_e": cp.kc_e, "kc_i": cp.kc_i,
                "cpi_uplift": cp.cpi_uplift,
                "cpi_downward": cp.cpi_downward,
                "windward_wall_cpe": cp.windward_wall_cpe,
            },
            "wind_cases": wind_list,
        },
    }
