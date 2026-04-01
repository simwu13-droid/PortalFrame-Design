"""SpaceGass v14 text file writer.

Generates SpaceGass Version 1420 text format from domain models.
Pure formatting — all business logic (load factors, combinations)
is computed before the writer sees it.
"""

import math

from portal_frame.models.geometry import FrameTopology
from portal_frame.models.sections import CFS_Section
from portal_frame.models.loads import LoadInput
from portal_frame.models.supports import SupportCondition
from portal_frame.standards.combinations_nzs1170_0 import build_combinations
from portal_frame.standards.earthquake_nzs1170_5 import calculate_earthquake_forces


class SpaceGassWriter:
    """Generates a complete SpaceGass v14 text file from domain models."""

    def __init__(
        self,
        topology: FrameTopology,
        column_section: CFS_Section,
        rafter_section: CFS_Section,
        supports: SupportCondition,
        loads: LoadInput,
        span: float,
        eave_height: float,
        roof_pitch: float,
        bay_spacing: float,
    ):
        self.topology = topology
        self.col_sec = column_section
        self.raf_sec = rafter_section
        self.supports = supports
        self.loads = loads
        self.span = span
        self.eave_height = eave_height
        self.roof_pitch = roof_pitch
        self.bay_spacing = bay_spacing
        self.ridge_height = (
            eave_height + (span / 2.0) * math.tan(math.radians(roof_pitch))
        )

    def _get_restraint(self, condition: str) -> str:
        """SpaceGass restraint: F=Fixed, R=Released. Order: Tx,Ty,Tz,Rx,Ry,Rz."""
        if condition == "fixed":
            return "FFFFFF"
        else:  # pinned
            return "FFFFFR"

    def _build_case_map(self) -> dict:
        """Build case numbering map for all load cases including EQ."""
        case_map = {"G": 1, "Q": 2}
        next_case = 3
        for wc in self.loads.wind_cases:
            case_map[wc.name] = next_case
            next_case += 1
        case_map.update(self._eq_case_map)
        return case_map

    def write(self) -> str:
        """Generate the complete SpaceGass text file."""
        # Pre-compute earthquake if enabled
        self._eq_result = None
        self._eq_case_map = {}
        if self.loads.earthquake is not None:
            from types import SimpleNamespace
            geom_ns = SimpleNamespace(
                span=self.span,
                eave_height=self.eave_height,
                ridge_height=self.ridge_height,
                bay_spacing=self.bay_spacing,
            )
            self._eq_result = calculate_earthquake_forces(
                geom_ns,
                self.loads.dead_load_roof,
                self.loads.dead_load_wall,
                self.loads.earthquake,
            )
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

    def _header(self) -> str:
        lines = []
        lines.append("SPACE GASS Text File - Version 1420")
        lines.append("")
        lines.append(
            "UNITS LENGTH:m, SECTION:m, STRENGTH:kPa, DENSITY:T/m^3, "
            "TEMP:Celsius, FORCE:kN, MOMENT:kNm, MASS:T, ACC:m/sec^2, "
            "TRANS:m, STRESS:kPa"
        )
        lines.append("")
        return "\n".join(lines)

    def _headings(self) -> str:
        lines = []
        lines.append("HEADINGS")
        lines.append(f'"2D Portal Frame - {self.span}m span"')
        lines.append(
            f'"Eave {self.eave_height}m, Pitch {self.roof_pitch} deg, '
            f'Bay {self.bay_spacing}m"'
        )
        lines.append('"AS/NZS 1170 Loading"')
        lines.append('""')
        lines.append("")
        return "\n".join(lines)

    def _nodes(self) -> str:
        lines = ["NODES"]
        for nid in sorted(self.topology.nodes):
            node = self.topology.nodes[nid]
            lines.append(f"{nid},{node.x:.4f},{node.y:.4f}")
        lines.append("")
        return "\n".join(lines)

    def _members(self) -> str:
        lines = ["MEMBERS"]
        for mid in sorted(self.topology.members):
            m = self.topology.members[mid]
            lines.append(f"{mid},0.00,0, ,N,{m.node_start},{m.node_end:>2},{m.section_id},1,FFFFFF,FFFFFF")
        lines.append("")
        return "\n".join(lines)

    def _restraints(self) -> str:
        lines = ["RESTRAINTS"]
        # Base nodes (nodes at y=0) get support restraints
        base_nodes = sorted(self.topology.get_base_nodes(), key=lambda n: n.x)
        if len(base_nodes) >= 2:
            lines.append(f"{base_nodes[0].id},{self._get_restraint(self.supports.left_base)}")
            lines.append(f"{base_nodes[1].id},{self._get_restraint(self.supports.right_base)}")
        lines.append("")
        return "\n".join(lines)

    def _sections(self) -> str:
        lines = ["SECTIONS"]
        for sec_num, sec in [(1, self.col_sec), (2, self.raf_sec)]:
            lines.append(f'{sec_num},"{sec.name}","{sec.library_name}"')
        lines.append("")
        return "\n".join(lines)

    def _materials(self) -> str:
        lines = ["MATERIALS"]
        lines.append('1,"STEEL","METRIC"')
        lines.append("")
        return "\n".join(lines)

    def _selfweight(self) -> str:
        if not self.loads.include_self_weight:
            return ""
        lines = ["SELFWEIGHT"]
        lines.append("1,0.0,-9.807E-03,0.0")
        lines.append("")
        return "\n".join(lines)

    def _load_cases(self) -> str:
        """Generate MEMBFORCES section with dead, live, and wind loads."""
        # Build case numbering map
        case_map = {"G": 1, "Q": 2}
        next_case = 3
        for wc in self.loads.wind_cases:
            case_map[wc.name] = next_case
            next_case += 1

        # Derive member roles from topology (supports mono and gable)
        rafter_ids = sorted(
            m.id for m in self.topology.members.values() if m.section_id == 2
        )
        column_ids = sorted(
            m.id for m in self.topology.members.values() if m.section_id == 1
        )

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

        bay = self.bay_spacing
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
            if len(rafter_ids) == 2:
                # Gable: left rafter gets left_rafter data, right rafter gets right_rafter data
                rafter_data = [
                    (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
                    (rafter_ids[1], wc.right_rafter_zones, wc.right_rafter),
                ]
            else:
                # Mono: single rafter gets left_rafter zones/uniform only
                rafter_data = [
                    (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
                ]
            for mem, zones, uniform in rafter_data:
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
            lines.append(f"{cn_pos},{node.id},{F_uls:.4f},0.0,0.0,0.0,0.0,0.0")

        # E- case: -X force at each eave node
        cn_neg = self._eq_case_map["E-"]
        for node in eave_nodes:
            lines.append(f"{cn_neg},{node.id},{-F_uls:.4f},0.0,0.0,0.0,0.0,0.0")

        lines.append("")
        return "\n".join(lines)

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
