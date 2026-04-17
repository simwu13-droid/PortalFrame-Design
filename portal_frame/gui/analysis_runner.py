"""Analysis orchestration — generate SpaceGass, run PyNite, compute design checks."""

import os
from tkinter import filedialog, messagebox

from portal_frame.models.loads import LoadInput, EarthquakeInputs
from portal_frame.models.supports import SupportCondition
from portal_frame.solvers.base import AnalysisRequest
from portal_frame.solvers.spacegass import SpaceGassSolver
from portal_frame.gui.theme import COLORS


def build_analysis_request(app):
    """Collect all GUI inputs and return an AnalysisRequest."""
    col_name = app.col_section.get()
    raf_name = app.raf_section.get()

    if not col_name or col_name not in app.section_library:
        raise ValueError("Please select a valid column section.")
    if not raf_name or raf_name not in app.section_library:
        raise ValueError("Please select a valid rafter section.")

    col_sec = app.section_library[col_name]
    raf_sec = app.section_library[raf_name]

    geom = app._build_geometry()

    supports = SupportCondition(
        left_base=app.left_support.get(),
        right_base=app.right_support.get(),
    )

    wind_cases = app._synthesize_wind_cases()

    qu_val = app.qu.get()
    qs_val = app.qs.get()
    ws_factor = qs_val / qu_val if qu_val > 0 else 0.75

    earthquake = None
    if app.eq_enabled_var.get():
        t1_val = app.eq_T1_override.get()
        earthquake = EarthquakeInputs(
            Z=app.eq_Z.get(),
            soil_class=app.eq_soil.get(),
            R_uls=app.eq_R_uls.get(),
            R_sls=app.eq_R_sls.get(),
            mu=app.eq_mu.get(),
            Sp=app.eq_Sp.get(),
            Sp_sls=app.eq_Sp_sls.get(),
            near_fault=app.eq_near_fault.get(),
            extra_seismic_mass=app.eq_extra_mass.get(),
            T1_override=t1_val if t1_val > 0 else 0.0,
        )

    crane_inputs = None
    if app.crane_enabled_var.get():
        from portal_frame.models.crane import CraneTransverseCombo, CraneInputs
        hc_uls = []
        for _, name_var, left_var, right_var in app.crane_hc_uls_rows:
            try:
                hc_uls.append(CraneTransverseCombo(
                    name=name_var.get(),
                    left=float(left_var.get()),
                    right=float(right_var.get()),
                ))
            except ValueError:
                pass
        hc_sls = []
        for _, name_var, left_var, right_var in app.crane_hc_sls_rows:
            try:
                hc_sls.append(CraneTransverseCombo(
                    name=name_var.get(),
                    left=float(left_var.get()),
                    right=float(right_var.get()),
                ))
            except ValueError:
                pass
        crane_inputs = CraneInputs(
            rail_height=app.crane_rail_height.get(),
            dead_left=app.crane_gc_left.get(),
            dead_right=app.crane_gc_right.get(),
            live_left=app.crane_qc_left.get(),
            live_right=app.crane_qc_right.get(),
            transverse_uls=hc_uls,
            transverse_sls=hc_sls,
        )

    loads = LoadInput(
        dead_load_roof=app.dead_roof.get(),
        dead_load_wall=app.dead_wall.get(),
        live_load_roof=app.live_roof.get(),
        wind_cases=wind_cases,
        include_self_weight=app.self_weight_var.get(),
        ws_factor=ws_factor,
        earthquake=earthquake,
        crane=crane_inputs,
    )

    topology = geom.to_topology()

    return AnalysisRequest(
        topology=topology,
        column_section=col_sec,
        rafter_section=raf_sec,
        supports=supports,
        load_input=loads,
        span=geom.span,
        eave_height=geom.eave_height,
        roof_pitch=geom.roof_pitch,
        bay_spacing=geom.bay_spacing,
    )


def generate(app):
    """Collect all inputs and generate the SpaceGass file via solver interface."""
    try:
        request = build_analysis_request(app)
        geom = app._build_geometry()

        solver = SpaceGassSolver()
        solver.build_model(request)
        output = solver.generate_text()

        default_name = f"portal_{geom.span:.0f}m_{geom.roof_pitch:.0f}deg.txt"
        filepath = filedialog.asksaveasfilename(
            title="Save SpaceGass File",
            defaultextension=".txt",
            filetypes=[("SpaceGass Text", "*.txt"), ("All Files", "*.*")],
            initialfile=default_name,
        )

        if filepath:
            with open(filepath, "w") as f:
                f.write(output)
            app.status_label.config(
                text=f"Saved: {os.path.basename(filepath)}",
                fg=COLORS["success"]
            )

    except Exception as e:
        messagebox.showerror("Generation Error", str(e))
        app.status_label.config(text=f"Error: {e}", fg=COLORS["error"])


def analyse(app):
    """Run PyNite analysis on current inputs."""
    try:
        # Clear any stale results first — if solve fails mid-way, we won't
        # leave old results visible.
        app._invalidate_analysis()
        request = build_analysis_request(app)
        app._analysis_topology = request.topology

        from portal_frame.solvers.pynite_solver import PyNiteSolver
        solver = PyNiteSolver()
        solver.build_model(request)

        app.status_label.config(text="Analysing...", fg=COLORS["warning"])
        app.update_idletasks()

        solver.solve()

        app._analysis_output = solver.output
        run_design_checks(app)
        update_results_panel(app)
        app._update_diagram_dropdowns()
        app._draw_preview()

        app.status_label.config(
            text="Analysis complete", fg=COLORS["success"]
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        messagebox.showerror("Analysis Error", str(e))
        app.status_label.config(text=f"Analysis error: {e}", fg=COLORS["error"])


def group_design_checks_by_member(app) -> dict | None:
    """Group design checks into canvas-line buckets for the preview overlay.

    Returns a dict with keys "col_L", "col_R", "raf_L", "raf_R" (mono
    omits "raf_R") whose values are the worst-utilisation
    MemberDesignCheck for each canvas line, or None if no checks exist.

    Crane-bracket sub-members and any other split members are collapsed
    into the parent line via worst-case utilisation.
    """
    out = app._analysis_output
    if out is None or not out.design_checks:
        return None
    topo = app._analysis_topology
    if topo is None:
        return None

    # Resolve span to determine which side each member belongs to
    try:
        span = app.span.get()
    except Exception:
        return None
    if span <= 0:
        return None
    eps = 1e-3 * max(span, 1.0)

    groups: dict[str, object] = {}

    def _consider(key: str, chk):
        existing = groups.get(key)
        if existing is None:
            groups[key] = chk
            return
        # Worst (highest util) wins; NO_DATA is treated as -inf so any
        # actual check supersedes it. Use max of (combined, shear) so
        # shear-dominated members can win their bucket.
        def rank(c):
            if c.status == "NO_DATA":
                return -1.0
            return max(c.util_combined, c.util_shear)
        if rank(chk) > rank(existing):
            groups[key] = chk

    for chk in out.design_checks:
        member = topo.members.get(chk.member_id)
        if member is None:
            continue
        n_start = topo.nodes[member.node_start]
        n_end = topo.nodes[member.node_end]
        xs = [n_start.x, n_end.x]
        x_min = min(xs)
        x_max = max(xs)

        if chk.member_role == "col":
            if x_max <= eps:
                _consider("col_L", chk)
            elif x_min >= span - eps:
                _consider("col_R", chk)
            else:
                # Unexpected column orientation — skip (shouldn't happen)
                pass
        else:  # rafter
            # Left rafter: starts at left eave (x~0), ends at apex (x<span)
            # Right rafter: starts at apex, ends at right eave (x~span)
            # Mono: single rafter spanning x=0 to x=span -> "raf_L"
            if x_min <= eps and x_max < span - eps:
                _consider("raf_L", chk)
            elif x_min > eps and x_max >= span - eps:
                _consider("raf_R", chk)
            else:
                # Mono full-span rafter, or unusual case — bucket as raf_L
                _consider("raf_L", chk)

    return groups


def run_design_checks(app):
    """Run AS/NZS 4600 capacity checks on the current analysis output.

    Looks up section capacities from the Formsteel span table at the
    user-supplied effective lengths, then writes a list of
    MemberDesignCheck onto app._analysis_output.design_checks.
    """
    out = app._analysis_output
    if out is None or out.uls_envelope_curves is None:
        return
    if app._analysis_topology is None:
        return

    from portal_frame.standards.cfs_check import check_all_members
    from portal_frame.standards.serviceability import (
        check_apex_deflection, check_eave_drift,
    )

    col_name = app.col_section.get()
    raf_name = app.raf_section.get()
    col_sec = app.section_library.get(col_name)
    raf_sec = app.section_library.get(raf_name)
    if col_sec is None or raf_sec is None:
        return

    out.design_checks = check_all_members(
        topology=app._analysis_topology,
        envelope_curves=out.uls_envelope_curves,
        column_section=col_sec,
        rafter_section=raf_sec,
        L_col=app.col_Le.get(),
        L_raf=app.raf_Le.get(),
        combo_results=out.combo_results,
    )

    apex_checks = check_apex_deflection(
        topology=app._analysis_topology,
        combo_results=out.combo_results,
        combo_descriptions=out.combo_descriptions,
        limit_ratio_wind=int(round(app.apex_limit_wind.get())),
        limit_ratio_eq=int(round(app.apex_limit_eq.get())),
    )
    drift_checks = check_eave_drift(
        topology=app._analysis_topology,
        combo_results=out.combo_results,
        combo_descriptions=out.combo_descriptions,
        limit_ratio_wind=int(round(app.drift_limit_wind.get())),
        limit_ratio_eq=int(round(app.drift_limit_eq.get())),
    )
    out.sls_checks = apex_checks + drift_checks


def invalidate_analysis(app):
    """Clear stale analysis results when inputs change.

    Called from input change callbacks to prevent the user from mistakenly
    applying outdated analysis results to design.
    """
    app._analysis_output = None
    app._analysis_topology = None
    if hasattr(app, '_results_text'):
        app._results_text.config(state="normal")
        app._results_text.delete("1.0", "end")
        app._results_text.config(state="disabled")
    if hasattr(app, 'diagram_case_var'):
        app.diagram_case_var.set("(none)")
    if hasattr(app, 'diagram_case_combo'):
        app.diagram_case_combo["values"] = ["(none)"]
    if hasattr(app, '_diagram_display_to_name'):
        app._diagram_display_to_name = {"(none)": None}
    # Clear the green "Analysis complete" status message
    if hasattr(app, 'status_label'):
        app.status_label.config(text="", fg=COLORS["fg_dim"])


def update_results_panel(app):
    """Display envelope results and design checks in the summary widget."""
    out = app._analysis_output
    if out is None:
        return

    lines = []
    if out.uls_envelope:
        lines.append("ULS Envelope:")
        for key, label in [("max_moment", "Max M+"), ("min_moment", "Max M-"),
                           ("max_shear", "Max V"), ("min_axial", "Max N(c)")]:
            if key in out.uls_envelope:
                e = out.uls_envelope[key]
                unit = "kNm" if "moment" in key else "kN"
                lines.append(f"  {label:8s} = {e.value:>8.1f} {unit}  "
                             f"({e.combo_name})  M{e.member_id} @ {e.position_pct:.0f}%")

    if out.sls_envelope:
        lines.append("SLS Envelope:")
        for key, label in [("max_dy", "Max dy"), ("max_dx", "Max dx")]:
            if key in out.sls_envelope:
                e = out.sls_envelope[key]
                lines.append(f"  {label:8s} = {e.value:>8.1f} mm   "
                             f"({e.combo_name})")

    # Design check block — appended below envelopes
    fail_lines: list[int] = []   # 0-based line indices to highlight red
    nodata_lines: list[int] = []
    if out.design_checks:
        lines.append("Design Check (AS/NZS 4600):")
        for chk in out.design_checks:
            if chk.status == "NO_DATA":
                line = (
                    f"  M{chk.member_id} ({chk.member_role}) {chk.section_name:12s}"
                    f"  L={chk.L_eff:.1f}m  NO DATA"
                )
                nodata_lines.append(len(lines))
            else:
                line = (
                    f"  M{chk.member_id} ({chk.member_role}) {chk.section_name:12s}"
                    f"  L={chk.L_eff:.1f}m"
                    f"  N/\u03c6N={chk.util_axial:.2f}"
                    f"  M/\u03c6Mb={chk.util_bending:.2f}"
                    f"  V/\u03c6V={chk.util_shear:.2f}"
                    f"  \u03a3={chk.util_combined:.2f}  {chk.status}"
                )
                if chk.status == "FAIL":
                    fail_lines.append(len(lines))
            lines.append(line)

    # SLS deflection rows — grouped by metric (apex_dy, drift)
    if out.sls_checks:
        metric_labels = {
            "apex_dy": ("Serviceability (Apex dy):", "\u03b4v"),
            "drift":   ("Serviceability (Eave drift):", "\u03b4h"),
        }
        for metric, (header, symbol) in metric_labels.items():
            metric_rows = [c for c in out.sls_checks if c.metric == metric]
            if not metric_rows:
                continue
            lines.append(header)
            for slc in metric_rows:
                line = (
                    f"  {slc.category.upper():4s}  "
                    f"{symbol}={slc.deflection_mm:>7.1f}mm  "
                    f"limit={slc.reference_symbol}/{slc.ratio} "
                    f"({slc.limit_mm:.1f}mm)  "
                    f"actual={slc.reference_symbol}/{slc.actual_ratio}  "
                    f"util={slc.util:.2f}  {slc.status}  "
                    f"({slc.controlling_combo})"
                )
                if slc.status == "FAIL":
                    fail_lines.append(len(lines))
                lines.append(line)

    # Auto-grow the text widget so all lines are visible
    new_height = max(8, len(lines))
    if int(app._results_text.cget("height")) != new_height:
        app._results_text.config(height=new_height)

    app._results_text.config(state="normal")
    app._results_text.delete("1.0", "end")
    app._results_text.insert("1.0", "\n".join(lines))

    # Tag FAIL rows red and NO_DATA rows dim
    app._results_text.tag_configure("dc_fail", foreground=COLORS["error"])
    app._results_text.tag_configure("dc_nodata", foreground=COLORS["fg_dim"])
    for ln in fail_lines:
        app._results_text.tag_add("dc_fail", f"{ln+1}.0", f"{ln+1}.end")
    for ln in nodata_lines:
        app._results_text.tag_add("dc_nodata", f"{ln+1}.0", f"{ln+1}.end")

    app._results_text.config(state="disabled")
