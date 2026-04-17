"""Earthquake tab — NZS 1170.5:2004 equivalent static inputs + live results."""

import math
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.gui.widgets import LabeledEntry, LabeledCombo
from portal_frame.standards.earthquake_nzs1170_5 import (
    NZ_HAZARD_FACTORS, NZ_FAULT_DISTANCES, calculate_earthquake_forces,
)
from portal_frame.models.loads import EarthquakeInputs


def build_earthquake_tab(app, parent):
    pad = {"padx": 10, "pady": (0, 2)}

    app._section_header(parent, "EARTHQUAKE  (NZS 1170.5:2004)")

    app.eq_enabled_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        parent, text="Include earthquake loading",
        variable=app.eq_enabled_var, font=FONT_BOLD,
        fg=COLORS["fg"], bg=COLORS["bg_panel"],
        selectcolor=COLORS["bg_input"],
        activebackground=COLORS["bg_panel"],
        activeforeground=COLORS["fg"],
        command=app._on_eq_toggle,
    ).pack(fill="x", padx=10, pady=(0, 6))

    app.eq_content = tk.Frame(parent, bg=COLORS["bg_panel"])
    # Initially hidden — shown on toggle

    app._section_header(app.eq_content, "SEISMIC HAZARD")
    locations = sorted(NZ_HAZARD_FACTORS.keys())
    app.eq_location = LabeledCombo(
        app.eq_content, "Location", values=locations, default="Wellington", width=20,
    )
    app.eq_location.pack(fill="x", **pad)
    app.eq_location.bind_change(app._on_eq_location_change)
    # Schedule initial fault-distance label update after layout finishes.
    # Using after_idle avoids a chicken-and-egg with the widget below
    # that the handler also touches (eq_fault_dist_label).
    parent.after_idle(app._on_eq_location_change)

    app.eq_Z = LabeledEntry(app.eq_content, "Z (hazard factor)", 0.40, "")
    app.eq_Z.pack(fill="x", **pad)
    app.eq_Z.bind_change(app._update_eq_results)

    # D(km) info label — shown when the selected location has a
    # specified shortest major fault distance. User uses this to pick
    # the N(T,D) near-fault factor below.
    app.eq_fault_dist_label = tk.Label(
        app.eq_content, text="", font=FONT_SMALL,
        fg=COLORS["warning"], bg=COLORS["bg_panel"],
        anchor="w", justify="left",
    )
    app.eq_fault_dist_label.pack(fill="x", padx=10, pady=(0, 2))

    app.eq_soil = LabeledCombo(
        app.eq_content, "Soil Class", values=["A", "B", "C", "D", "E"],
        default="C", width=6,
    )
    app.eq_soil.pack(fill="x", **pad)
    app.eq_soil.bind_change(app._update_eq_results)

    app._section_header(app.eq_content, "DUCTILITY & IMPORTANCE")

    duct_presets = [
        "Nominally ductile (mu=1.25, Sp=0.925)",
        "Limited ductile (mu=2.0, Sp=0.7)",
        "Ductile (mu=4.0, Sp=0.7)",
        "Elastic (mu=1.0, Sp=1.0)",
        "Custom",
    ]
    app.eq_ductility = LabeledCombo(
        app.eq_content, "Ductility Preset", values=duct_presets,
        default=duct_presets[0], width=36,
    )
    app.eq_ductility.pack(fill="x", **pad)
    app.eq_ductility.bind_change(app._on_ductility_change)

    app.eq_mu = LabeledEntry(app.eq_content, "mu (ductility)", 1.25, "")
    app.eq_mu.pack(fill="x", **pad)
    app.eq_mu.bind_change(app._update_eq_results)

    app.eq_Sp = LabeledEntry(app.eq_content, "Sp ULS (structural perf.)", 0.925, "")
    app.eq_Sp.pack(fill="x", **pad)
    app.eq_Sp.bind_change(app._update_eq_results)

    app.eq_Sp_sls = LabeledEntry(app.eq_content, "Sp SLS (Cl 4.4.4)", 0.7, "")
    app.eq_Sp_sls.pack(fill="x", **pad)
    app.eq_Sp_sls.bind_change(app._update_eq_results)

    app.eq_R_uls = LabeledEntry(app.eq_content, "R (ULS return period)", 1.0, "")
    app.eq_R_uls.pack(fill="x", **pad)
    app.eq_R_uls.bind_change(app._update_eq_results)

    app.eq_R_sls = LabeledEntry(app.eq_content, "R (SLS return period)", 0.25, "")
    app.eq_R_sls.pack(fill="x", **pad)
    app.eq_R_sls.bind_change(app._update_eq_results)

    app.eq_near_fault = LabeledEntry(app.eq_content, "N(T,D) near-fault", 1.0, "")
    app.eq_near_fault.pack(fill="x", **pad)
    app.eq_near_fault.bind_change(app._update_eq_results)

    app.eq_extra_mass = LabeledEntry(app.eq_content, "Extra seismic mass", 0.0, "kN")
    app.eq_extra_mass.pack(fill="x", **pad)
    app.eq_extra_mass.bind_change(app._update_eq_results)

    app.eq_T1_override = LabeledEntry(app.eq_content, "T1 override (0=auto)", 0.0, "s")
    app.eq_T1_override.pack(fill="x", **pad)
    app.eq_T1_override.bind_change(app._update_eq_results)

    app._section_header(app.eq_content, "CALCULATED VALUES")

    app.eq_results_label = tk.Label(
        app.eq_content, text="(enable earthquake loading to see results)",
        font=FONT_MONO, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
        anchor="w", justify="left",
    )
    app.eq_results_label.pack(fill="x", padx=10, pady=(0, 8))


def on_eq_toggle(app, *args):
    if app.eq_enabled_var.get():
        app.eq_content.pack(fill="x")
        update_eq_results(app)
    else:
        app.eq_content.pack_forget()
    app.refresh_load_case_list()


def on_eq_location_change(app, *args):
    loc = app.eq_location.get()
    if loc in NZ_HAZARD_FACTORS:
        app.eq_Z.set(NZ_HAZARD_FACTORS[loc])
    # Surface the fault-distance info when available. Locations without
    # a specified D have the near-fault factor N(T,D) default to 1.0.
    d_value = NZ_FAULT_DISTANCES.get(loc)
    if d_value:
        app.eq_fault_dist_label.config(
            text=f"D = {d_value} km  (shortest distance to a major fault) — "
                 f"set N(T,D) below per Table 3.6"
        )
    else:
        app.eq_fault_dist_label.config(
            text="No specified fault distance — N(T,D) = 1.0"
        )
    update_eq_results(app)


def on_ductility_change(app, *args):
    preset = app.eq_ductility.get()
    if "Nominally" in preset:
        app.eq_mu.set(1.25); app.eq_Sp.set(0.925)
    elif "Limited" in preset:
        app.eq_mu.set(2.0); app.eq_Sp.set(0.7)
    elif preset.startswith("Ductile"):
        app.eq_mu.set(4.0); app.eq_Sp.set(0.7)
    elif "Elastic" in preset:
        app.eq_mu.set(1.0); app.eq_Sp.set(1.0)
    update_eq_results(app)


def estimate_member_self_weight(app, geom) -> float:
    """Estimate steel self-weight tributary to knee level (kN).

    Only the top half of columns and full rafters contribute to
    the seismic mass lumped at the knee nodes.
    """
    STEEL_DENSITY = 7850  # kg/m3
    G = 9.81 / 1000  # kN per kg

    col_name = app.col_section.get()
    raf_name = app.raf_section.get()
    col_ax = 0.0  # m2
    raf_ax = 0.0
    if col_name in app.section_library:
        col_ax = app.section_library[col_name].Ax * 1e-6
    if raf_name in app.section_library:
        raf_ax = app.section_library[raf_name].Ax * 1e-6

    # Top half of columns only (bottom half goes to foundation)
    left_col_len = geom.eave_height / 2.0
    if geom.roof_type == "mono":
        right_col_len = geom.ridge_height / 2.0
    else:
        right_col_len = geom.eave_height / 2.0

    # Full rafter length
    rise = geom.ridge_height - geom.eave_height
    if geom.roof_type == "mono":
        raf_len = math.hypot(geom.span, rise)
    else:
        left_run = geom.apex_x
        right_run = geom.span - geom.apex_x
        raf_len = math.hypot(left_run, rise) + math.hypot(right_run, rise)

    col_wt = col_ax * (left_col_len + right_col_len) * STEEL_DENSITY * G
    raf_wt = raf_ax * raf_len * STEEL_DENSITY * G
    return col_wt + raf_wt


def update_eq_results(app, *args):
    app._invalidate_analysis()
    if not app.eq_enabled_var.get():
        return
    try:
        geom = app._build_geometry()
        sw_kn = estimate_member_self_weight(app, geom)

        t1_val = app.eq_T1_override.get()
        eq = EarthquakeInputs(
            Z=app.eq_Z.get(),
            soil_class=app.eq_soil.get(),
            R_uls=app.eq_R_uls.get(),
            R_sls=app.eq_R_sls.get(),
            mu=app.eq_mu.get(),
            Sp=app.eq_Sp.get(),
            Sp_sls=app.eq_Sp_sls.get(),
            near_fault=app.eq_near_fault.get(),
            extra_seismic_mass=app.eq_extra_mass.get() + sw_kn,
            T1_override=t1_val if t1_val > 0 else 0.0,
        )
        result = calculate_earthquake_forces(
            geom, app.dead_roof.get(), app.dead_wall.get(), eq,
        )
        t1_val = app.eq_T1_override.get()
        t1_label = f"T1 = {result['T1']:.3f} s"
        if t1_val > 0:
            t1_label += " (user override)"
        else:
            t1_label += " (auto)"
        text = (
            f"{t1_label}\n"
            f"Ch(T1) = {result['Ch']:.3f}\n"
            f"k_mu = {result['k_mu']:.3f}\n"
            f"Cd(T1) ULS = {result['Cd_uls']:.4f}\n"
            f"Cd(T1) SLS = {result['Cd_sls']:.4f}\n"
            f"Wt = {result['Wt']:.2f} kN  "
            f"(SDL={result['Wt'] - eq.extra_seismic_mass:.2f} "
            f"+ SW={sw_kn:.2f} "
            f"+ extra={app.eq_extra_mass.get():.2f})\n"
            f"V_uls = {result['V_uls']:.2f} kN\n"
            f"V_sls = {result['V_sls']:.2f} kN\n"
            f"F_node ULS = {result['F_node']:.2f} kN (per knee)\n"
            f"F_node SLS = {result['F_node_sls']:.2f} kN (per knee)"
        )
        # Show crane seismic contribution if crane is enabled
        if hasattr(app, 'crane_enabled_var') and app.crane_enabled_var.get():
            gc_total = app.crane_gc_left.get() + app.crane_gc_right.get()
            qc_total = app.crane_qc_left.get() + app.crane_qc_right.get()
            crane_wt = gc_total + 0.6 * qc_total
            if crane_wt > 0:
                F_crane_uls = result['Cd_uls'] * crane_wt / 2.0
                F_crane_sls = result['Cd_sls'] * crane_wt / 2.0
                text += (
                    f"\n--- Crane seismic (at bracket nodes) ---\n"
                    f"Wt_crane = Gc + 0.6Qc = {gc_total:.1f} + 0.6x{qc_total:.1f}"
                    f" = {crane_wt:.2f} kN\n"
                    f"F_crane ULS = {F_crane_uls:.2f} kN (per bracket)\n"
                    f"F_crane SLS = {F_crane_sls:.2f} kN (per bracket)"
                )
        app.eq_results_label.config(text=text)
    except Exception as e:
        app.eq_results_label.config(text=f"Error: {e}")
