"""Wind tab — surface-pressure table with wind-case dropdown."""

import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.gui.widgets import LabeledEntry
from portal_frame.gui.dialogs import WindSurfacePanel


def build_wind_tab(app, parent):
    pad = {"padx": 10, "pady": (0, 2)}

    app._section_header(parent, "WIND PARAMETERS  (NZS 1170.2:2021)")

    wind_param_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
    wind_param_frame.pack(fill="x", padx=10, pady=(0, 4))

    app.qu = LabeledEntry(wind_param_frame, "qu (ULS pressure)", 1.2, "kPa", width=6)
    app.qu.pack(fill="x", pady=(0, 2))

    app.qs = LabeledEntry(wind_param_frame, "qs (SLS pressure)", 0.9, "kPa", width=6)
    app.qs.pack(fill="x", pady=(0, 2))

    app.kc_e = LabeledEntry(wind_param_frame, "Kc,e (external)", 0.8, "", width=6)
    app.kc_e.pack(fill="x", pady=(0, 2))

    app.kc_i = LabeledEntry(wind_param_frame, "Kc,i (internal)", 1.0, "", width=6)
    app.kc_i.pack(fill="x", pady=(0, 2))

    tk.Label(wind_param_frame, text="Cp,i  (internal pressure - Table 5.1)",
             font=FONT_BOLD, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
             anchor="w").pack(fill="x", pady=(4, 2))

    cpi_grid = tk.Frame(wind_param_frame, bg=COLORS["bg_panel"])
    cpi_grid.pack(fill="x", pady=(0, 4))

    app.cpi_uplift_var = tk.StringVar(value="0.2")
    app.cpi_downward_var = tk.StringVar(value="-0.3")

    for i, (label, var) in enumerate([
        ("Cp,i (max uplift)", app.cpi_uplift_var),
        ("Cp,i (max downward)", app.cpi_downward_var),
    ]):
        tk.Label(cpi_grid, text=label, font=FONT_SMALL, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"], anchor="w", width=22
                 ).grid(row=i, column=0, sticky="w", padx=(0, 4))
        tk.Entry(cpi_grid, textvariable=var, font=FONT_MONO, width=7,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"]
                 ).grid(row=i, column=1, padx=2, pady=1)

    tk.Label(wind_param_frame, text="Cp,e  (external - Table 5.2A)",
             font=FONT_BOLD, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
             anchor="w").pack(fill="x", pady=(4, 2))

    cp_grid = tk.Frame(wind_param_frame, bg=COLORS["bg_panel"])
    cp_grid.pack(fill="x", pady=(0, 4))

    app.cp_vars = {}
    for i, (label, key, default) in enumerate([
        ("Windward Wall", "cp_ww", 0.7),
    ]):
        tk.Label(cp_grid, text=label, font=FONT_SMALL, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"], anchor="w", width=22
                 ).grid(row=i, column=0, sticky="w", padx=(0, 4))
        var = tk.StringVar(value=str(default))
        tk.Entry(cp_grid, textvariable=var, font=FONT_MONO, width=7,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"]
                 ).grid(row=i, column=1, padx=2, pady=1)
        app.cp_vars[key] = var

    tk.Label(wind_param_frame,
             text="Leeward Cp,e from Table 5.2(B) by d/b ratio\n"
                  "Roof zones from Table 5.3(A) by h/d ratio\n"
                  "Side wall zones from Table 5.2(C)",
             font=FONT_SMALL, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
             anchor="w", justify="left").pack(fill="x", pady=(2, 4))

    app.wind_ratios_label = tk.Label(
        wind_param_frame, text="", font=FONT_MONO,
        fg=COLORS["fg"], bg=COLORS["bg_panel"],
        anchor="w", justify="left",
    )
    app.wind_ratios_label.pack(fill="x", pady=(0, 4))

    tk.Button(
        wind_param_frame, text="  AUTO GENERATE 8 CASES  ", font=FONT_BOLD,
        fg=COLORS["fg_bright"], bg="#2d7d46",
        activebackground="#3a9d5a", activeforeground=COLORS["fg_bright"],
        relief="flat", cursor="hand2", padx=12, pady=4,
        command=app._auto_generate_wind_cases
    ).pack(fill="x", pady=(6, 4))

    app._section_header(parent, "WIND COEFFICIENTS  (Cp,e per surface)")

    app.wind_table = WindSurfacePanel(
        parent,
        get_geometry_fn=app._get_h_and_depth,
        get_wind_params_fn=app._get_wind_params,
        on_change_fn=app._on_wind_table_change,
        on_case_select_fn=app._on_wind_case_select,
    )
    app.wind_table.pack(fill="x", padx=10, pady=(0, 8))

    # Trace wind params so pe/pnet update when qu/kc/cpi change
    def _trigger_recalc():
        app.wind_table._schedule_recalc()
    for widget in [app.qu, app.qs, app.kc_e, app.kc_i]:
        widget.bind_change(_trigger_recalc)
    app.cpi_uplift_var.trace_add("write", lambda *_: _trigger_recalc())
    app.cpi_downward_var.trace_add("write", lambda *_: _trigger_recalc())


def on_wind_table_change(app):
    """Called when user edits any Cp,e or Ka value in the surface table."""
    if not hasattr(app, 'load_case_var'):
        return  # still building UI
    app.refresh_load_case_list()
    app._update_preview()


def on_wind_case_select(app, case_name):
    """Called when user clicks a W1-W8 tab in the surface panel."""
    if case_name is None:
        app.load_case_var.set("(none)")
    else:
        # Find the matching entry in the load case dropdown
        try:
            cases = app._synthesize_wind_cases()
            for wc in cases:
                if wc.name == case_name:
                    app.load_case_var.set(f"{wc.name} - {wc.description}"[:50])
                    break
        except Exception:
            pass
    app._draw_preview()
