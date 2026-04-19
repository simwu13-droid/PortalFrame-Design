"""Diagram controller -- preview updates, diagram data, results dropdowns."""

from portal_frame.models.loads import EarthquakeInputs
from portal_frame.standards.earthquake_nzs1170_5 import calculate_earthquake_forces


def synthesise_envelope_reactions(analysis_output, combo_names):
    """Build per-node reactions = signed value with max |magnitude| across combos.

    For each support node seen in the selected combos, independently picks
    the combo whose |fx| is largest (keeping sign), same for fy, same for mz.
    Returns dict[node_id] -> ReactionResult.
    """
    from portal_frame.analysis.results import ReactionResult

    node_best = {}  # node_id -> {fx: (abs, signed), fy: ..., mz: ...}
    for name in combo_names:
        cr = analysis_output.combo_results.get(name)
        if cr is None:
            continue
        for nid, r in cr.reactions.items():
            entry = node_best.setdefault(nid, {"fx": (-1.0, 0.0),
                                               "fy": (-1.0, 0.0),
                                               "mz": (-1.0, 0.0)})
            for field, val in (("fx", r.fx), ("fy", r.fy), ("mz", r.mz)):
                if abs(val) > entry[field][0]:
                    entry[field] = (abs(val), val)

    return {
        nid: ReactionResult(node_id=nid,
                            fx=vals["fx"][1], fy=vals["fy"][1], mz=vals["mz"][1])
        for nid, vals in node_best.items()
    }


def update_preview(app, *args):
    """Called when inputs change -- invalidates stale analysis and redraws.

    Use this from input-change callbacks only. For display-only refresh
    (load case dropdown, diagram selection), call draw_preview() directly.
    """
    app._invalidate_analysis()
    draw_preview(app)


def on_diagram_type_changed(app):
    """Handle diagram type combobox change -- notify preview and redraw."""
    dtype = app.diagram_type_var.get()
    # Map combobox values to scale keys used by _diagram_scales
    # "delta" (Unicode delta) maps to "D"; M/V/N pass through unchanged
    scale_key = {"M": "M", "V": "V", "N": "N", "\u03b4": "D", "Reactions": "R"}.get(dtype, dtype)
    app.preview.set_diagram_type(scale_key)
    draw_preview(app)


def draw_preview(app, *args):
    """Redraw the preview canvas without touching analysis state.

    Use this for display-only refresh (combo selection). Does not invalidate.
    """
    geom_obj = app._build_geometry()
    geom = {
        "span": geom_obj.span,
        "eave_height": geom_obj.eave_height,
        "roof_pitch": geom_obj.roof_pitch,
        "roof_pitch_2": geom_obj.right_pitch,
        "roof_type": geom_obj.roof_type,
        "apex_x": geom_obj.apex_x,
        "ridge_height": geom_obj.ridge_height,
    }
    if geom_obj.crane_rail_height is not None:
        geom["crane_rail_height"] = geom_obj.crane_rail_height
    supports = (app.left_support.get(), app.right_support.get())
    loads = build_preview_loads(app)

    diagram = None
    if (app._analysis_output is not None and
            hasattr(app, 'diagram_case_var') and
            app.diagram_case_var.get() != "(none)"):
        diagram = build_diagram_data(app)

    app.preview.set_design_checks(app._group_design_checks_by_member())
    app.preview.set_sls_checks(
        app._analysis_output.sls_checks if app._analysis_output else None
    )
    app.preview.update_frame(geom, supports, loads, diagram)
    update_summary(app)


def build_preview_loads(app) -> dict:
    selected = app.load_case_var.get()
    if selected == "(none)":
        return None

    bay = app.bay.get()
    if bay <= 0:
        return None

    is_mono = app.roof_type_var.get() == "mono"
    members = []

    if selected.startswith("G "):
        w_roof = app.dead_roof.get() * bay
        w_wall = app.dead_wall.get() * bay
        if w_roof > 0:
            rafter_pairs = [(2, 3)] if is_mono else [(2, 3), (3, 4)]
            for nf, nt in rafter_pairs:
                members.append({"from": nf, "to": nt, "segments": [
                    {"start_pct": 0, "end_pct": 100, "w_kn": w_roof,
                     "direction": "global_y"}]})
        if w_wall > 0:
            col_pairs = [(1, 2), (4, 3)] if is_mono else [(1, 2), (5, 4)]
            for nf, nt in col_pairs:
                members.append({"from": nf, "to": nt, "segments": [
                    {"start_pct": 0, "end_pct": 100, "w_kn": w_wall,
                     "direction": "global_y"}]})

    elif selected.startswith("Q "):
        w_live = app.live_roof.get() * bay
        if w_live > 0:
            rafter_pairs = [(2, 3)] if is_mono else [(2, 3), (3, 4)]
            for nf, nt in rafter_pairs:
                members.append({"from": nf, "to": nt, "segments": [
                    {"start_pct": 0, "end_pct": 100, "w_kn": w_live,
                     "direction": "global_y"}]})

    elif selected.startswith("E"):
        try:
            geom_obj = app._build_geometry()
            t1_val = app.eq_T1_override.get() if hasattr(app, 'eq_T1_override') else 0
            eq = EarthquakeInputs(
                Z=app.eq_Z.get(), soil_class=app.eq_soil.get(),
                R_uls=app.eq_R_uls.get(), R_sls=app.eq_R_sls.get(),
                mu=app.eq_mu.get(), Sp=app.eq_Sp.get(),
                Sp_sls=app.eq_Sp_sls.get(),
                near_fault=app.eq_near_fault.get(),
                extra_seismic_mass=app.eq_extra_mass.get(),
                T1_override=t1_val if t1_val > 0 else 0.0,
            )
            result = calculate_earthquake_forces(
                geom_obj, app.dead_roof.get(), app.dead_wall.get(), eq,
            )
            F = result["F_node"]
            is_negative = "E-" in selected
            if is_negative:
                F = -F
            # Point loads at eave/knee nodes
            eave_nodes = [2, 3] if is_mono else [2, 4]
            point_loads = []
            for nid in eave_nodes:
                point_loads.append({"node": nid, "fx": F, "label": f"E={'−' if is_negative else '+'}"})
            return {"members": [], "point_loads": point_loads}
        except Exception:
            pass

    elif selected.startswith("Gc ") or selected.startswith("Qc "):
        # Crane vertical loads at bracket nodes
        try:
            geom_obj = app._build_geometry()
            h = geom_obj.crane_rail_height
            if h is not None and 0 < h < geom_obj.eave_height:
                # Bracket nodes: left at (0, h), right at (span, h)
                # Use node IDs 6 and 7 for bracket nodes in the preview
                if selected.startswith("Gc"):
                    left_kn = app.crane_gc_left.get()
                    right_kn = app.crane_gc_right.get()
                else:
                    left_kn = app.crane_qc_left.get()
                    right_kn = app.crane_qc_right.get()
                point_loads = []
                if left_kn != 0:
                    point_loads.append({"node": "bracket_left", "fx": 0, "fy": -left_kn})
                if right_kn != 0:
                    point_loads.append({"node": "bracket_right", "fx": 0, "fy": -right_kn})
                return {"members": [], "point_loads": point_loads}
        except Exception:
            pass

    elif "Crane Transverse" in selected:
        # Crane horizontal loads at bracket nodes
        try:
            geom_obj = app._build_geometry()
            h = geom_obj.crane_rail_height
            if h is not None and 0 < h < geom_obj.eave_height:
                case_name = selected.split(" - ")[0].strip()
                left_kn = 0.0
                right_kn = 0.0
                rows = (app.crane_hc_uls_rows if "ULS" in selected
                        else app.crane_hc_sls_rows)
                for _, name_var, left_var, right_var in rows:
                    if name_var.get() == case_name:
                        try:
                            left_kn = float(left_var.get())
                        except ValueError:
                            left_kn = 0.0
                        try:
                            right_kn = float(right_var.get())
                        except ValueError:
                            right_kn = 0.0
                        break
                point_loads = []
                if left_kn != 0:
                    point_loads.append({"node": "bracket_left", "fx": left_kn, "fy": 0})
                if right_kn != 0:
                    point_loads.append({"node": "bracket_right", "fx": right_kn, "fy": 0})
                return {"members": [], "point_loads": point_loads}
        except Exception:
            pass

    else:
        wc_name = selected.split(" - ")[0].strip()
        try:
            wc_list = app._synthesize_wind_cases()
        except Exception:
            return None
        wc = None
        for w in wc_list:
            if w.name == wc_name:
                wc = w
                break
        if not wc:
            return None

        left_col = (1, 2)
        right_col = (4, 3) if is_mono else (5, 4)

        if wc.left_wall != 0:
            members.append({"from": left_col[0], "to": left_col[1], "segments": [
                {"start_pct": 0, "end_pct": 100,
                 "w_kn": wc.left_wall * bay,
                 "direction": "global_x"}]})
        if wc.right_wall != 0:
            members.append({"from": right_col[0], "to": right_col[1], "segments": [
                {"start_pct": 0, "end_pct": 100,
                 "w_kn": -wc.right_wall * bay,
                 "direction": "global_x"}]})

        if is_mono:
            if wc.is_crosswind and wc.left_rafter_zones:
                segs = []
                for z in wc.left_rafter_zones:
                    if z.pressure != 0:
                        segs.append({
                            "start_pct": z.start_pct,
                            "end_pct": z.end_pct,
                            "w_kn": z.pressure * bay,
                            "direction": "normal"})
                if segs:
                    members.append({"from": 2, "to": 3, "segments": segs})
            else:
                val = wc.left_rafter
                if val != 0:
                    members.append({"from": 2, "to": 3, "segments": [
                        {"start_pct": 0, "end_pct": 100,
                         "w_kn": val * bay,
                         "direction": "normal"}]})
        else:
            for nf, nt, zones, uni_val in [
                (2, 3, wc.left_rafter_zones, wc.left_rafter),
                (3, 4, wc.right_rafter_zones, wc.right_rafter),
            ]:
                if zones:
                    segs = []
                    for z in zones:
                        if z.pressure != 0:
                            segs.append({
                                "start_pct": z.start_pct,
                                "end_pct": z.end_pct,
                                "w_kn": z.pressure * bay,
                                "direction": "normal"})
                    if segs:
                        members.append({"from": nf, "to": nt, "segments": segs})
                elif uni_val != 0:
                    members.append({"from": nf, "to": nt, "segments": [
                        {"start_pct": 0, "end_pct": 100,
                         "w_kn": uni_val * bay,
                         "direction": "normal"}]})

    if not members:
        return None
    return {"members": members}


def refresh_load_case_list(app):
    if not hasattr(app, 'load_case_combo'):
        return
    choices = ["(none)", "G - Dead Load", "Q - Live Load"]
    try:
        wc_list = app._synthesize_wind_cases()
        for wc in wc_list:
            choices.append(f"{wc.name} - {wc.description}"[:50])
    except Exception:
        pass
    if hasattr(app, 'eq_enabled_var') and app.eq_enabled_var.get():
        choices.append("E+ - Earthquake positive")
        choices.append("E- - Earthquake negative")
    if hasattr(app, 'crane_enabled_var') and app.crane_enabled_var.get():
        choices.append("Gc - Crane Dead")
        choices.append("Qc - Crane Live")
        for _, name_var, _, _ in app.crane_hc_uls_rows:
            choices.append(f"{name_var.get()} - Crane Transverse ULS")
        for _, name_var, _, _ in app.crane_hc_sls_rows:
            choices.append(f"{name_var.get()} - Crane Transverse SLS")
    app.load_case_combo["values"] = choices


def update_section_info(app, *args):
    lines = []
    for label, name in [("Col", app.col_section.get()),
                         ("Raf", app.raf_section.get())]:
        if name in app.section_library:
            s = app.section_library[name]
            lines.append(
                f"{label}: A={s.Ax:.0f} mm2  Iy={s.Iy:.0f} mm4  "
                f"Iz={s.Iz:.0f} mm4  J={s.J:.0f} mm4"
            )
    app.sec_info.config(text="\n".join(lines))


def update_summary(app):
    geom = app._build_geometry()
    roof_label = "Gable" if geom.roof_type == "gable" else "Mono"
    ridge = geom.ridge_height
    pitch_info = f"a1={geom.left_pitch:.1f} a2={geom.right_pitch:.1f}" if geom.roof_type == "gable" else f"{geom.roof_pitch:.1f} deg"
    app.summary_label.config(
        text=f"{roof_label}  |  Span: {geom.span:.1f}m  |  Eave: {geom.eave_height:.1f}m  |  "
             f"Ridge: {ridge:.2f}m  |  {pitch_info}"
    )


def update_diagram_dropdowns(app):
    """Populate diagram case dropdown with analysis cases and combos.

    Builds human-friendly display strings for combos (e.g., 'ULS-1: 1.35G')
    while maintaining a display_to_name map for reverse lookup.
    """
    out = app._analysis_output
    app._diagram_display_to_name = {"(none)": None}

    if out is None:
        app.diagram_case_combo["values"] = ["(none)"]
        return

    values = ["(none)"]

    # Individual unfactored cases -- name only
    for name in sorted(out.case_results.keys()):
        values.append(name)
        app._diagram_display_to_name[name] = name

    # Combinations -- "name: description"
    def _combo_sort_key(n):
        # ULS first, then SLS; numeric order within each
        prefix = 0 if n.startswith("ULS") else 1
        try:
            num = int(n.split("-")[1])
        except (IndexError, ValueError):
            num = 0
        return (prefix, num)

    for name in sorted(out.combo_results.keys(), key=_combo_sort_key):
        desc = out.combo_descriptions.get(name, "")
        display = f"{name}: {desc}" if desc else name
        values.append(display)
        app._diagram_display_to_name[display] = name

    # Envelope entries (last in the dropdown)
    if out.uls_envelope_curves is not None:
        values.append("ULS Envelope")
        app._diagram_display_to_name["ULS Envelope"] = "ULS Envelope"
    if out.sls_envelope_curves is not None:
        values.append("SLS Envelope")
        app._diagram_display_to_name["SLS Envelope"] = "SLS Envelope"
    if out.sls_wind_only_envelope_curves is not None:
        values.append("SLS Wind Only Envelope")
        app._diagram_display_to_name["SLS Wind Only Envelope"] = "SLS Wind Only Envelope"

    app.diagram_case_combo["values"] = values


def build_diagram_data(app):
    """Build diagram data dict for the preview canvas.

    For normal cases/combos, returns {'data': {mid: [(pct, val), ...]},
    'type': dtype, 'members': {mid: (n1, n2)}}.

    For envelopes, also includes 'data_min' with the min curve.

    For the delta diagram type, also includes 'data_dx' (and 'data_min_dx'
    for envelopes) -- per-station dx_local values needed by the renderer
    to reconstruct the global deformation vector and guarantee diagram
    continuity at shared nodes.
    """
    display = app.diagram_case_var.get()
    dtype = app.diagram_type_var.get()
    out = app._analysis_output

    # Translate display string back to actual case/combo name
    name = app._diagram_display_to_name.get(display)
    if name is None:
        return None

    # Topology node coords — needed for both reaction display and diagram data
    members_map = {}
    topology_nodes = {}
    if app._analysis_topology:
        members_map = {
            mid: (mem.node_start, mem.node_end)
            for mid, mem in app._analysis_topology.members.items()
        }
        topology_nodes = {
            nid: (node.x, node.y)
            for nid, node in app._analysis_topology.nodes.items()
        }

    # --- Reactions branch ---
    if dtype == "Reactions":
        if name in ("ULS Envelope", "SLS Envelope", "SLS Wind Only Envelope"):
            if name == "ULS Envelope":
                combo_names = [n for n in out.combo_results if n.startswith("ULS")]
            elif name == "SLS Envelope":
                combo_names = [n for n in out.combo_results if n.startswith("SLS")]
            else:
                combo_names = [
                    n for n in out.combo_results
                    if n.startswith("SLS")
                    and "wind only" in out.combo_descriptions.get(n, "").lower()
                ]
            reactions = synthesise_envelope_reactions(out, combo_names)
        else:
            cr = out.case_results.get(name) or out.combo_results.get(name)
            if cr is None:
                return None
            reactions = cr.reactions
        return {
            "type": "R",
            "reactions": reactions,
            "topology_nodes": topology_nodes,
            "members": members_map,
        }
    # --- /Reactions branch ---

    attr = {"M": "moment", "V": "shear", "N": "axial", "\u03b4": "dy_local"}[dtype]

    def _extract(cr, field):
        return {
            mid: [(s.position_pct, getattr(s, field)) for s in mr.stations]
            for mid, mr in cr.members.items()
        }

    base = {
        "type": dtype,
        "members": members_map,
        "topology_nodes": topology_nodes,
    }

    # Envelope selections return both max and min curves
    envelope_curves = None
    if name == "ULS Envelope":
        envelope_curves = out.uls_envelope_curves
    elif name == "SLS Envelope":
        envelope_curves = out.sls_envelope_curves
    elif name == "SLS Wind Only Envelope":
        envelope_curves = out.sls_wind_only_envelope_curves

    if envelope_curves is not None:
        env_max, env_min = envelope_curves
        result = {
            **base,
            "data": _extract(env_max, attr),
            "data_min": _extract(env_min, attr),
            "is_envelope": True,
        }
        if dtype == "\u03b4":
            result["data_dx"] = _extract(env_max, "dx_local")
            result["data_min_dx"] = _extract(env_min, "dx_local")
        return result

    # Normal case/combo lookup
    cr = out.case_results.get(name) or out.combo_results.get(name)
    if cr is None:
        return None

    result = {**base, "data": _extract(cr, attr)}
    if dtype == "\u03b4":
        result["data_dx"] = _extract(cr, "dx_local")
    return result
