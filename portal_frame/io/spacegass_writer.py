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
        """Build case numbering map for all load cases including EQ and crane."""
        case_map = {"G": 1, "Q": 2}
        next_case = 3
        for wc in self.loads.wind_cases:
            case_map[wc.name] = next_case
            next_case += 1
        case_map.update(self._eq_case_map)
        # Advance past EQ cases
        if self._eq_case_map:
            next_case = max(self._eq_case_map.values()) + 1
        case_map.update(self._crane_case_map)
        return case_map

    def generate(self) -> str:
        """Alias for write() — backward compatibility."""
        return self.write()

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

        # Pre-compute crane case map
        self._crane_case_map = {}
        crane = self.loads.crane
        if crane is not None:
            next_case = 3 + len(self.loads.wind_cases)
            if self._eq_case_map:
                next_case = max(self._eq_case_map.values()) + 1
            self._crane_case_map["Gc"] = next_case
            next_case += 1
            self._crane_case_map["Qc"] = next_case
            next_case += 1
            for tc in crane.transverse_uls:
                self._crane_case_map[tc.name] = next_case
                next_case += 1
            for tc in crane.transverse_sls:
                self._crane_case_map[tc.name] = next_case
                next_case += 1

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
            self._load_case_groups(),
            self._titles(),
            "END",
        ]
        return "\n".join(p for p in parts if p)

    def _header(self) -> str:
        lines = []
        lines.append("SPACE GASS Text File - Version 1420")
        s = self.supports
        if getattr(s, "left_base", None) == "partial" or getattr(s, "right_base", None) == "partial":
            alpha = getattr(s, "fixity_percent", 0.0)
            sls_only = getattr(s, "sls_partial_only", True)
            applied_to = "SLS only" if sls_only else "ULS and SLS"
            lines.append(
                f"! NOTE: in-app analysis used partial base fixity "
                f"alpha = {alpha:g} % (k_theta = alpha*4EI/L)."
            )
            lines.append(
                f"!       Applied to: {applied_to}."
            )
            lines.append(
                "!       SpaceGass export retains pinned bases -- "
                "re-enter rotational springs"
            )
            lines.append("!       manually in SpaceGass if needed.")
        lines.append("")
        lines.append(
            "UNITS LENGTH:m, SECTION:mm, STRENGTH:MPa, DENSITY:kg/m^3, "
            "TEMP:Celsius, FORCE:kN, MOMENT:kNm, MASS:kg, ACC:g's, "
            "TRANS:mm, STRESS:MPa"
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
        lines.append("1,0.0,-1.0,0.0")
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

        # Identify left/right column groups by x-position of their nodes
        # After crane bracket splitting, each side may have 2 column segments
        left_col_ids = []
        right_col_ids = []
        for mid in column_ids:
            mem = self.topology.members[mid]
            n1 = self.topology.nodes[mem.node_start]
            n2 = self.topology.nodes[mem.node_end]
            x = min(n1.x, n2.x)
            if x == 0.0:
                left_col_ids.append(mid)
            else:
                right_col_ids.append(mid)

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
            # Applied to ALL column segments on each side (handles crane bracket split)
            if wc.left_wall != 0:
                w = wc.left_wall * bay
                for col_id in left_col_ids:
                    sl = next_slice(col_id)
                    lines.append(
                        f"{cn},{col_id},{sl},G,%,0.0,100.0,{w:.4f},{w:.4f},0.0,0.0,0.0,0.0"
                    )
            if wc.right_wall != 0:
                w = -wc.right_wall * bay
                for col_id in right_col_ids:
                    sl = next_slice(col_id)
                    lines.append(
                        f"{cn},{col_id},{sl},G,%,0.0,100.0,{w:.4f},{w:.4f},0.0,0.0,0.0,0.0"
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

    def _get_bracket_nodes(self):
        """Find crane bracket nodes: nodes at crane rail_height with y > 0."""
        crane = self.loads.crane
        if crane is None:
            return []
        h = crane.rail_height
        bracket_nodes = [
            n for n in self.topology.nodes.values()
            if abs(n.y - h) < 0.01 and n.y > 0
        ]
        return sorted(bracket_nodes, key=lambda n: n.x)

    def _jointloads(self) -> str:
        """Generate NODELOADS section for earthquake and crane forces."""
        has_eq = self._eq_result is not None
        has_crane = bool(self._crane_case_map)

        if not has_eq and not has_crane:
            return ""

        lines = ["NODELOADS"]

        # Earthquake loads — building mass at eave nodes, crane mass at bracket nodes
        if has_eq:
            eave_nodes = sorted(self.topology.get_eave_nodes(), key=lambda n: n.x)
            if len(eave_nodes) >= 2:
                F_uls = self._eq_result["F_node"]
                F_sls = self._eq_result["F_node_sls"]
                cn_pos = self._eq_case_map["E+"]
                cn_neg = self._eq_case_map["E-"]
                # Building seismic force at eave/knee nodes
                for node in eave_nodes:
                    lines.append(f"{cn_pos},{node.id},{F_uls:.4f},0.0,0.0,0.0,0.0,0.0,1")
                for node in eave_nodes:
                    lines.append(f"{cn_neg},{node.id},{-F_uls:.4f},0.0,0.0,0.0,0.0,0.0,1")

                # Crane seismic force at bracket nodes
                # F = Cd * (Gc + 0.6*Qc) / 2 per bracket
                # 0.6 = companion action factor for crane live during EQ
                crane = self.loads.crane
                if crane is not None:
                    gc_total = crane.dead_left + crane.dead_right
                    qc_total = crane.live_left + crane.live_right
                    crane_wt = gc_total + 0.6 * qc_total
                    if crane_wt > 0:
                        Cd_uls = self._eq_result["Cd_uls"]
                        F_crane = Cd_uls * crane_wt / 2.0
                        bracket_nodes = self._get_bracket_nodes()
                        for node in bracket_nodes:
                            lines.append(f"{cn_pos},{node.id},{F_crane:.4f},0.0,0.0,0.0,0.0,0.0,1")
                        for node in bracket_nodes:
                            lines.append(f"{cn_neg},{node.id},{-F_crane:.4f},0.0,0.0,0.0,0.0,0.0,1")

        # Crane loads at bracket nodes
        if has_crane:
            crane = self.loads.crane
            bracket_nodes = self._get_bracket_nodes()
            if len(bracket_nodes) >= 2:
                left_node = bracket_nodes[0]
                right_node = bracket_nodes[-1]

                # Gc — crane dead load (vertical, downward = -FY)
                cn_gc = self._crane_case_map["Gc"]
                lines.append(f"{cn_gc},{left_node.id},0.0,{-crane.dead_left:.4f},0.0,0.0,0.0,0.0,1")
                lines.append(f"{cn_gc},{right_node.id},0.0,{-crane.dead_right:.4f},0.0,0.0,0.0,0.0,1")

                # Qc — crane live load (vertical, downward = -FY)
                cn_qc = self._crane_case_map["Qc"]
                lines.append(f"{cn_qc},{left_node.id},0.0,{-crane.live_left:.4f},0.0,0.0,0.0,0.0,1")
                lines.append(f"{cn_qc},{right_node.id},0.0,{-crane.live_right:.4f},0.0,0.0,0.0,0.0,1")

                # Hc — transverse loads (horizontal, FX)
                for tc in crane.transverse_uls:
                    cn = self._crane_case_map[tc.name]
                    lines.append(f"{cn},{left_node.id},{tc.left:.4f},0.0,0.0,0.0,0.0,0.0,1")
                    lines.append(f"{cn},{right_node.id},{tc.right:.4f},0.0,0.0,0.0,0.0,0.0,1")
                for tc in crane.transverse_sls:
                    cn = self._crane_case_map[tc.name]
                    lines.append(f"{cn},{left_node.id},{tc.left:.4f},0.0,0.0,0.0,0.0,0.0,1")
                    lines.append(f"{cn},{right_node.id},{tc.right:.4f},0.0,0.0,0.0,0.0,0.0,1")

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

        crane = self.loads.crane
        has_crane = crane is not None
        uls_combos, sls_combos, combo_groups = build_combinations(
            wind_case_names,
            ws_factor=self.loads.ws_factor,
            eq_case_names=eq_case_names,
            eq_sls_factor=eq_sls_factor,
            crane_gc_name="Gc" if has_crane else None,
            crane_qc_name="Qc" if has_crane else None,
            crane_hc_uls_names=[c.name for c in crane.transverse_uls] if has_crane else None,
            crane_hc_sls_names=[c.name for c in crane.transverse_sls] if has_crane else None,
        )
        self._combo_groups = combo_groups
        self._uls_count = len(uls_combos)
        self._sls_count = len(sls_combos)
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

    def _load_case_groups(self) -> str:
        """Generate LOAD CASE GROUPS section for SpaceGass."""
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
        lines.append(f'{gid},"ULS",{uls_start},-{uls_end}')
        gid += 1
        # ULS sub-groups
        for gname, label in [("uls_gq", "ULS-GQ"), ("uls_wind", "ULS-Wind"),
                              ("uls_eq", "ULS-EQ")]:
            if gname in groups:
                s, e = groups[gname]
                lines.append(f'{gid},"{label}",{uls_start + s},-{uls_start + e}')
                gid += 1

        # SLS parent group
        lines.append(f'{gid},"SLS",{sls_start},-{sls_end}')
        gid += 1
        # SLS sub-groups
        for gname, label in [("sls_wind", "SLS-Wind"), ("sls_eq", "SLS-EQ"),
                              ("sls_wind_only", "SLS-Wind Only")]:
            if gname in groups:
                s, e = groups[gname]
                lines.append(f'{gid},"{label}",{sls_start + s},-{sls_start + e}')
                gid += 1

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
        # Crane base load case titles
        crane = self.loads.crane
        if crane is not None:
            cn_gc = self._crane_case_map.get("Gc")
            if cn_gc is not None:
                lines.append(f"{cn_gc},Gc - Crane Dead Load")
            cn_qc = self._crane_case_map.get("Qc")
            if cn_qc is not None:
                lines.append(f"{cn_qc},Qc - Crane Live Load")
            for i, tc in enumerate(crane.transverse_uls, 1):
                cn = self._crane_case_map.get(tc.name)
                if cn is not None:
                    lines.append(f"{cn},{tc.name} - Crane Transverse ULS {i}")
            for i, tc in enumerate(crane.transverse_sls, 1):
                cn = self._crane_case_map.get(tc.name)
                if cn is not None:
                    lines.append(f"{cn},{tc.name} - Crane Transverse SLS {i}")
        for cname, (combo_num, cdesc) in self._combo_id_map.items():
            lines.append(f"{combo_num},{cname}: {cdesc}")
        lines.append("")
        return "\n".join(lines)
