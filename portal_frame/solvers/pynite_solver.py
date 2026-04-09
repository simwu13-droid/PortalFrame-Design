"""PyNite structural analysis solver — in-app FEM analysis."""

import math

from Pynite import FEModel3D

from portal_frame.solvers.base import AnalysisSolver, AnalysisRequest, AnalysisResults
from portal_frame.analysis.results import (
    AnalysisOutput, CaseResult, MemberResult, MemberStationResult,
    NodeResult, ReactionResult,
)
from portal_frame.analysis.combinations import combine_case_results, compute_envelopes
from portal_frame.standards.combinations_nzs1170_0 import build_combinations
from portal_frame.standards.earthquake_nzs1170_5 import calculate_earthquake_forces

NUM_STATIONS = 21
STEEL_DENSITY = 7850  # kg/m^3 — only valid for steel. Update if extending to timber.


class PyNiteSolver(AnalysisSolver):
    """In-app structural solver using PyNite FEModel3D.

    Note on member end releases: currently all member ends are fully rigid
    (moment-connected). If pinned apex or base-to-column joints are needed
    in future, use model.def_releases(member_name, ...) after add_member().
    """

    def __init__(self):
        self._request: AnalysisRequest | None = None
        self._output: AnalysisOutput | None = None

    @property
    def output(self) -> AnalysisOutput | None:
        return self._output

    def build_model(self, request: AnalysisRequest) -> None:
        self._request = request
        self._output = None

    def solve(self) -> AnalysisResults:
        r = self._request
        case_names = self._build_case_names()

        # Solve each unfactored load case individually
        case_results = {}
        for case_name in case_names:
            model = self._new_model()
            self._apply_loads(model, case_name)
            model.add_load_combo("LC", {case_name: 1.0})
            try:
                model.analyze()
            except Exception as e:
                raise RuntimeError(
                    f"PyNite analysis failed for case '{case_name}': {e}\n"
                    "Check supports (singular stiffness matrix = mechanism) "
                    "and member connectivity."
                ) from e
            case_results[case_name] = self._extract_results(model, case_name)

        # Build combinations from NZS 1170.0
        combos = self._get_combinations()
        combo_results = {}
        combo_descriptions = {}
        for combo in combos:
            combo_results[combo.name] = combine_case_results(
                case_results, combo.factors, combo.name
            )
            combo_descriptions[combo.name] = combo.description

        self._output = AnalysisOutput(
            case_results=case_results,
            combo_results=combo_results,
            combo_descriptions=combo_descriptions,
        )
        compute_envelopes(self._output)

        return AnalysisResults(solved=True)

    def export(self, path: str) -> None:
        pass  # PyNite solver does not export files

    # ── Model construction ──

    def _new_model(self) -> FEModel3D:
        """Build a fresh PyNite model with nodes, members, supports (no loads)."""
        r = self._request
        model = FEModel3D()

        # Material: CFS steel (units: kN/m^2 for E and G)
        model.add_material("Steel", 200e6, 80e6, 0.3, 7850)

        # Sections
        col = r.column_section
        raf = r.rafter_section
        model.add_section("Col", col.Ax_m, col.Iy_m, col.Iz_m, col.J_m)
        model.add_section("Raf", raf.Ax_m, raf.Iy_m, raf.Iz_m, raf.J_m)

        # Nodes
        for nid, node in r.topology.nodes.items():
            model.add_node(f"N{nid}", node.x, node.y, 0.0)

        # 2D constraints: restrain out-of-plane DOFs at ALL nodes first
        for nid in r.topology.nodes:
            model.def_support(f"N{nid}", False, False, True, True, True, False)

        # Base supports (override out-of-plane-only with full support)
        base_nodes = sorted(r.topology.get_base_nodes(), key=lambda n: n.x)
        if len(base_nodes) >= 2:
            left_cond = r.supports.left_base
            right_cond = r.supports.right_base
            self._apply_support(model, base_nodes[0], left_cond)
            self._apply_support(model, base_nodes[-1], right_cond)

        # Members
        for mid, mem in r.topology.members.items():
            sec_name = "Col" if mem.section_id == 1 else "Raf"
            model.add_member(f"M{mid}", f"N{mem.node_start}",
                             f"N{mem.node_end}", "Steel", sec_name)

        return model

    def _apply_support(self, model, node, condition):
        name = f"N{node.id}"
        if condition == "fixed":
            model.def_support(name, True, True, True, True, True, True)
        else:  # pinned
            model.def_support(name, True, True, True, True, True, False)

    # ── Case map ──

    def _build_case_names(self) -> list[str]:
        """Build ordered list of unfactored case names matching SpaceGassWriter."""
        r = self._request
        names = ["G", "Q"]
        for wc in r.load_input.wind_cases:
            names.append(wc.name)
        if r.load_input.earthquake is not None:
            names.extend(["E+", "E-"])
        crane = r.load_input.crane
        if crane is not None:
            names.extend(["Gc", "Qc"])
            for tc in crane.transverse_uls:
                names.append(tc.name)
            for tc in crane.transverse_sls:
                names.append(tc.name)
        return names

    # ── Load application ──

    def _apply_loads(self, model: FEModel3D, case_name: str) -> None:
        r = self._request
        bay = r.bay_spacing
        topo = r.topology

        rafter_ids = sorted(m.id for m in topo.members.values() if m.section_id == 2)
        column_ids = sorted(m.id for m in topo.members.values() if m.section_id == 1)

        if case_name == "G":
            self._apply_dead_loads(model, case_name, rafter_ids, column_ids, bay)
        elif case_name == "Q":
            self._apply_live_loads(model, case_name, rafter_ids, bay)
        elif case_name in ("E+", "E-"):
            self._apply_earthquake_loads(model, case_name)
        elif case_name == "Gc":
            self._apply_crane_dead(model, case_name)
        elif case_name == "Qc":
            self._apply_crane_live(model, case_name)
        else:
            # Wind case or crane transverse
            wc_match = next((w for w in r.load_input.wind_cases
                             if w.name == case_name), None)
            if wc_match:
                self._apply_wind_loads(model, case_name, wc_match,
                                       rafter_ids, column_ids, bay)
            else:
                self._apply_crane_transverse(model, case_name)

    def _apply_dead_loads(self, model, case_name, rafter_ids, column_ids, bay):
        r = self._request
        # Roof dead: global -Y on rafters
        if r.load_input.dead_load_roof > 0:
            w = -r.load_input.dead_load_roof * bay
            for mid in rafter_ids:
                model.add_member_dist_load(f"M{mid}", "FY", w, w, case=case_name)
        # Wall dead: global -Y on columns
        if r.load_input.dead_load_wall > 0:
            w = -r.load_input.dead_load_wall * bay
            for mid in column_ids:
                model.add_member_dist_load(f"M{mid}", "FY", w, w, case=case_name)
        # Self-weight
        if r.load_input.include_self_weight:
            for mid, mem in r.topology.members.items():
                sec = r.column_section if mem.section_id == 1 else r.rafter_section
                w_sw = -STEEL_DENSITY * 9.81 / 1000 * sec.Ax_m  # kN/m
                model.add_member_dist_load(f"M{mid}", "FY", w_sw, w_sw,
                                           case=case_name)

    def _apply_live_loads(self, model, case_name, rafter_ids, bay):
        r = self._request
        if r.load_input.live_load_roof > 0:
            w = -r.load_input.live_load_roof * bay
            for mid in rafter_ids:
                model.add_member_dist_load(f"M{mid}", "FY", w, w, case=case_name)

    def _apply_wind_loads(self, model, case_name, wc, rafter_ids, column_ids, bay):
        r = self._request
        topo = r.topology

        # Classify left/right columns
        left_col_ids = []
        right_col_ids = []
        for mid in column_ids:
            mem = topo.members[mid]
            n1 = topo.nodes[mem.node_start]
            n2 = topo.nodes[mem.node_end]
            x = min(n1.x, n2.x)
            if x == 0.0:
                left_col_ids.append(mid)
            else:
                right_col_ids.append(mid)

        # Wall loads — global X
        if wc.left_wall != 0:
            w = wc.left_wall * bay  # +ve into surface = +X
            for mid in left_col_ids:
                model.add_member_dist_load(f"M{mid}", "FX", w, w, case=case_name)
        if wc.right_wall != 0:
            w = -wc.right_wall * bay  # +ve into surface = -X for right wall
            for mid in right_col_ids:
                model.add_member_dist_load(f"M{mid}", "FX", w, w, case=case_name)

        # Rafter loads — local y (normal to surface)
        if len(rafter_ids) >= 2:
            rafter_data = [
                (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
                (rafter_ids[1], wc.right_rafter_zones, wc.right_rafter),
            ]
        else:
            rafter_data = [
                (rafter_ids[0], wc.left_rafter_zones, wc.left_rafter),
            ]

        for mid, zones, uniform in rafter_data:
            mem = topo.members[mid]
            n1 = topo.nodes[mem.node_start]
            n2 = topo.nodes[mem.node_end]
            mem_len = math.hypot(n2.x - n1.x, n2.y - n1.y)

            if wc.is_crosswind and zones:
                for zone in zones:
                    if zone.pressure != 0:
                        w = -zone.pressure * bay  # into surface = -local y
                        x1 = zone.start_pct / 100.0 * mem_len
                        x2 = zone.end_pct / 100.0 * mem_len
                        model.add_member_dist_load(
                            f"M{mid}", "Fy", w, w, x1, x2, case=case_name)
            elif uniform != 0:
                w = -uniform * bay
                model.add_member_dist_load(f"M{mid}", "Fy", w, w, case=case_name)

    def _apply_earthquake_loads(self, model, case_name):
        r = self._request
        from types import SimpleNamespace
        geom_ns = SimpleNamespace(
            span=r.span, eave_height=r.eave_height,
            ridge_height=r.eave_height + (r.span / 2.0) * math.tan(
                math.radians(r.roof_pitch)),
            bay_spacing=r.bay_spacing,
        )
        eq_result = calculate_earthquake_forces(
            geom_ns, r.load_input.dead_load_roof,
            r.load_input.dead_load_wall, r.load_input.earthquake,
        )
        F_uls = eq_result["F_node"]
        sign = 1.0 if case_name == "E+" else -1.0

        eave_nodes = sorted(r.topology.get_eave_nodes(), key=lambda n: n.x)
        for node in eave_nodes:
            model.add_node_load(f"N{node.id}", "FX", sign * F_uls,
                                case=case_name)

        # Crane seismic at bracket nodes
        crane = r.load_input.crane
        if crane is not None:
            gc_total = crane.dead_left + crane.dead_right
            qc_total = crane.live_left + crane.live_right
            crane_wt = gc_total + 0.6 * qc_total
            if crane_wt > 0:
                Cd_uls = eq_result["Cd_uls"]
                F_crane = Cd_uls * crane_wt / 2.0
                bracket_nodes = self._get_bracket_nodes()
                for node in bracket_nodes:
                    model.add_node_load(f"N{node.id}", "FX",
                                        sign * F_crane, case=case_name)

    def _apply_crane_dead(self, model, case_name):
        r = self._request
        crane = r.load_input.crane
        bracket_nodes = self._get_bracket_nodes()
        if len(bracket_nodes) >= 2:
            model.add_node_load(f"N{bracket_nodes[0].id}", "FY",
                                -crane.dead_left, case=case_name)
            model.add_node_load(f"N{bracket_nodes[-1].id}", "FY",
                                -crane.dead_right, case=case_name)

    def _apply_crane_live(self, model, case_name):
        r = self._request
        crane = r.load_input.crane
        bracket_nodes = self._get_bracket_nodes()
        if len(bracket_nodes) >= 2:
            model.add_node_load(f"N{bracket_nodes[0].id}", "FY",
                                -crane.live_left, case=case_name)
            model.add_node_load(f"N{bracket_nodes[-1].id}", "FY",
                                -crane.live_right, case=case_name)

    def _apply_crane_transverse(self, model, case_name):
        r = self._request
        crane = r.load_input.crane
        if crane is None:
            return
        bracket_nodes = self._get_bracket_nodes()
        if len(bracket_nodes) < 2:
            return
        # Find the matching transverse combo
        tc = None
        for t in crane.transverse_uls + crane.transverse_sls:
            if t.name == case_name:
                tc = t
                break
        if tc is None:
            return
        model.add_node_load(f"N{bracket_nodes[0].id}", "FX",
                            tc.left, case=case_name)
        model.add_node_load(f"N{bracket_nodes[-1].id}", "FX",
                            tc.right, case=case_name)

    def _get_bracket_nodes(self):
        """Find crane bracket nodes (same logic as SpaceGassWriter)."""
        r = self._request
        crane = r.load_input.crane
        if crane is None:
            return []
        h = crane.rail_height
        bracket_nodes = [
            n for n in r.topology.nodes.values()
            if abs(n.y - h) < 0.01 and n.y > 0
        ]
        return sorted(bracket_nodes, key=lambda n: n.x)

    # ── Result extraction ──

    def _extract_results(self, model: FEModel3D, case_name: str) -> CaseResult:
        r = self._request
        members = {}
        for mid, mem in r.topology.members.items():
            name = f"M{mid}"
            L = model.members[name].L()

            stations = []
            for i in range(NUM_STATIONS):
                x = i / (NUM_STATIONS - 1) * L
                pct = i / (NUM_STATIONS - 1) * 100
                # Negate moment and axial to match standard convention:
                # standard: +moment = sagging, +axial = tension
                # PyNite: +moment = hogging, +axial = compression
                axial = -model.members[name].axial(x, "LC")
                shear = model.members[name].shear("Fy", x, "LC")
                moment = -model.members[name].moment("Mz", x, "LC")
                # Local-y deflection in mm (PyNite returns metres).
                # Negate so positive = sagging (into frame interior), matching
                # the convention already used for axial and moment extraction.
                dy_local = -model.members[name].deflection('dy', x, "LC") * 1000
                stations.append(MemberStationResult(
                    position=x, position_pct=pct,
                    axial=axial, shear=shear, moment=moment,
                    dy_local=dy_local,
                ))

            mr = MemberResult(member_id=mid, stations=stations)
            mr.compute_extremes()
            members[mid] = mr

        deflections = {}
        for nid in r.topology.nodes:
            name = f"N{nid}"
            node = model.nodes[name]
            dx = node.DX.get("LC", 0.0) * 1000  # m -> mm
            dy = node.DY.get("LC", 0.0) * 1000
            rz = node.RZ.get("LC", 0.0)
            deflections[nid] = NodeResult(nid, dx, dy, rz)

        reactions = {}
        for base_node in r.topology.get_base_nodes():
            name = f"N{base_node.id}"
            node = model.nodes[name]
            fx = node.RxnFX.get("LC", 0.0)
            fy = node.RxnFY.get("LC", 0.0)
            mz = node.RxnMZ.get("LC", 0.0)
            reactions[base_node.id] = ReactionResult(base_node.id, fx, fy, mz)

        return CaseResult(case_name, members, deflections, reactions)

    # ── Combinations ──

    def _get_combinations(self):
        """Get NZS 1170.0 combinations using existing build_combinations()."""
        r = self._request
        wind_names = [wc.name for wc in r.load_input.wind_cases]
        eq_names = ["E+", "E-"] if r.load_input.earthquake else None

        eq_sls_factor = 1.0
        if r.load_input.earthquake and hasattr(r.load_input.earthquake, 'R_sls'):
            from types import SimpleNamespace
            geom_ns = SimpleNamespace(
                span=r.span, eave_height=r.eave_height,
                ridge_height=r.eave_height + (r.span / 2.0) * math.tan(
                    math.radians(r.roof_pitch)),
                bay_spacing=r.bay_spacing,
            )
            eq_result = calculate_earthquake_forces(
                geom_ns, r.load_input.dead_load_roof,
                r.load_input.dead_load_wall, r.load_input.earthquake,
            )
            # SLS EQ factor = F_node_sls / F_node_uls (scales the ULS case)
            if eq_result["F_node"] > 0:
                eq_sls_factor = eq_result["F_node_sls"] / eq_result["F_node"]

        crane = r.load_input.crane
        crane_gc = "Gc" if crane else None
        crane_qc = "Qc" if crane else None
        crane_hc_uls = [tc.name for tc in crane.transverse_uls] if crane else None
        crane_hc_sls = [tc.name for tc in crane.transverse_sls] if crane else None

        uls, sls, groups = build_combinations(
            wind_case_names=wind_names,
            ws_factor=r.load_input.ws_factor,
            eq_case_names=eq_names,
            eq_sls_factor=eq_sls_factor,
            crane_gc_name=crane_gc,
            crane_qc_name=crane_qc,
            crane_hc_uls_names=crane_hc_uls,
            crane_hc_sls_names=crane_hc_sls,
        )

        from portal_frame.standards.combinations_nzs1170_0 import LoadCombination
        combos = []
        for i, (name, desc, factors) in enumerate(uls):
            combos.append(LoadCombination(name, desc, factors, 101 + i))
        for i, (name, desc, factors) in enumerate(sls):
            combos.append(LoadCombination(name, desc, factors, 201 + i))
        return combos
