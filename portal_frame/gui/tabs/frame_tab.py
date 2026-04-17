"""Frame tab — geometry, sections, loads, design-check inputs."""

import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT, FONT_BOLD, FONT_SMALL
from portal_frame.gui.widgets import LabeledEntry, LabeledCombo
from portal_frame.models.geometry import PortalFrameGeometry


def build_frame_tab(app, parent):
    pad = {"padx": 10, "pady": (0, 2)}

    app._section_header(parent, "GEOMETRY")

    # Roof type selector
    roof_type_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
    roof_type_frame.pack(fill="x", **pad)

    tk.Label(roof_type_frame, text="Roof Type", font=FONT, fg=COLORS["fg"],
             bg=COLORS["bg_panel"], width=14, anchor="w").pack(side="left")
    app.roof_type_var = tk.StringVar(value="gable")
    for text, val in [("Gable", "gable"), ("Mono", "mono")]:
        tk.Radiobutton(
            roof_type_frame, text=text, variable=app.roof_type_var,
            value=val, font=FONT, fg=COLORS["fg"],
            bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["fg"],
            command=app._on_roof_type_change,
        ).pack(side="left", padx=(4, 8))

    app.span = LabeledEntry(parent, "Span", 12.0, "m")
    app.span.pack(fill="x", **pad)
    app.span.bind_change(app._on_frame_change)

    app.eave = LabeledEntry(parent, "Eave Height", 4.5, "m")
    app.eave.pack(fill="x", **pad)
    app.eave.bind_change(app._on_frame_change)

    app.pitch = LabeledEntry(parent, "Roof Pitch 1 (a1)", 5.0, "deg")
    app.pitch.pack(fill="x", **pad)
    app.pitch.bind_change(app._on_pitch_change)

    app.pitch2_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
    app.pitch2_frame.pack(fill="x", **pad)
    app.pitch2 = LabeledEntry(app.pitch2_frame, "Roof Pitch 2 (a2)", 5.0, "deg")
    app.pitch2.pack(fill="x")
    app.pitch2.bind_change(app._on_pitch_change)

    app.pitch_warning_label = tk.Label(
        parent, text="", font=FONT_SMALL, fg=COLORS["warning"],
        bg=COLORS["bg_panel"], anchor="w", justify="left",
    )
    app.pitch_warning_label.pack(fill="x", padx=10, pady=(0, 2))

    app.bay = LabeledEntry(parent, "Bay Spacing", 6.0, "m")
    app.bay.pack(fill="x", **pad)
    app.bay.bind_change(app._on_frame_change)

    app.building_depth = LabeledEntry(parent, "Building Depth (d)", 24.0, "m")
    app.building_depth.pack(fill="x", **pad)

    app._section_header(parent, "SECTIONS  (from SpaceGass Library)")

    app.col_section = LabeledCombo(
        parent, "Column", values=app.section_names, default="63020S2", width=24
    )
    app.col_section.pack(fill="x", **pad)

    app.raf_section = LabeledCombo(
        parent, "Rafter", values=app.section_names, default="650180295S2", width=24
    )
    app.raf_section.pack(fill="x", **pad)

    app.sec_info = tk.Label(parent, text="", font=FONT_SMALL,
                            fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                            anchor="w", justify="left")
    app.sec_info.pack(fill="x", padx=10, pady=(0, 4))

    app.col_section.bind_change(app._on_section_change)
    app.raf_section.bind_change(app._on_section_change)
    app._update_section_info()

    app._section_header(parent, "EFFECTIVE LENGTHS  (ULS Capacity Check)")

    app.col_Le = LabeledEntry(parent, "Column unbraced L", 4.5, "m")
    app.col_Le.pack(fill="x", **pad)
    app.col_Le.bind_change(app._on_design_input_change)

    app.raf_Le = LabeledEntry(parent, "Rafter unbraced L", 6.0, "m")
    app.raf_Le.pack(fill="x", **pad)
    app.raf_Le.bind_change(app._on_design_input_change)

    app._section_header(parent, "SERVICEABILITY LIMITS  (SLS Deflection)")

    app.apex_limit_wind = LabeledEntry(
        parent, "Apex dy limit (Wind)    span /", 180, "")
    app.apex_limit_wind.pack(fill="x", **pad)
    app.apex_limit_wind.bind_change(app._on_design_input_change)

    app.apex_limit_eq = LabeledEntry(
        parent, "Apex dy limit (EQ)      span /", 360, "")
    app.apex_limit_eq.pack(fill="x", **pad)
    app.apex_limit_eq.bind_change(app._on_design_input_change)

    app.drift_limit_wind = LabeledEntry(
        parent, "Eave drift limit (Wind) h /", 150, "")
    app.drift_limit_wind.pack(fill="x", **pad)
    app.drift_limit_wind.bind_change(app._on_design_input_change)

    app.drift_limit_eq = LabeledEntry(
        parent, "Eave drift limit (EQ)   h /", 300, "")
    app.drift_limit_eq.pack(fill="x", **pad)
    app.drift_limit_eq.bind_change(app._on_design_input_change)

    app._section_header(parent, "SUPPORTS")

    sup_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
    sup_frame.pack(fill="x", **pad)

    tk.Label(sup_frame, text="Left Base", font=FONT, fg=COLORS["fg"],
             bg=COLORS["bg_panel"]).grid(row=0, column=0, sticky="w")
    app.left_support = tk.StringVar(value="pinned")
    tk.Radiobutton(sup_frame, text="Pinned", variable=app.left_support,
                    value="pinned", font=FONT, fg=COLORS["fg"],
                    bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                    activebackground=COLORS["bg_panel"],
                    activeforeground=COLORS["fg"],
                    command=app._update_preview
                    ).grid(row=0, column=1, padx=(10, 4))
    tk.Radiobutton(sup_frame, text="Fixed", variable=app.left_support,
                    value="fixed", font=FONT, fg=COLORS["fg"],
                    bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                    activebackground=COLORS["bg_panel"],
                    activeforeground=COLORS["fg"],
                    command=app._update_preview
                    ).grid(row=0, column=2)

    tk.Label(sup_frame, text="Right Base", font=FONT, fg=COLORS["fg"],
             bg=COLORS["bg_panel"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
    app.right_support = tk.StringVar(value="pinned")
    tk.Radiobutton(sup_frame, text="Pinned", variable=app.right_support,
                    value="pinned", font=FONT, fg=COLORS["fg"],
                    bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                    activebackground=COLORS["bg_panel"],
                    activeforeground=COLORS["fg"],
                    command=app._update_preview
                    ).grid(row=1, column=1, padx=(10, 4), pady=(4, 0))
    tk.Radiobutton(sup_frame, text="Fixed", variable=app.right_support,
                    value="fixed", font=FONT, fg=COLORS["fg"],
                    bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                    activebackground=COLORS["bg_panel"],
                    activeforeground=COLORS["fg"],
                    command=app._update_preview
                    ).grid(row=1, column=2, pady=(4, 0))

    app._section_header(parent, "LOADS  (unfactored, kPa)")

    app.dead_roof = LabeledEntry(parent, "Dead Load - Roof (SDL)", 0.15, "kPa")
    app.dead_roof.pack(fill="x", **pad)
    app.dead_roof.bind_change(app._on_frame_change)

    app.dead_wall = LabeledEntry(parent, "Dead Load - Wall", 0.10, "kPa")
    app.dead_wall.pack(fill="x", **pad)
    app.dead_wall.bind_change(app._on_frame_change)

    app.live_roof = LabeledEntry(parent, "Live Load - Roof (Q)", 0.25, "kPa")
    app.live_roof.pack(fill="x", **pad)
    app.live_roof.bind_change(app._on_frame_change)

    app.self_weight_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        parent, text="Include self-weight in Dead Load case",
        variable=app.self_weight_var, font=FONT,
        fg=COLORS["fg"], bg=COLORS["bg_panel"],
        selectcolor=COLORS["bg_input"],
        activebackground=COLORS["bg_panel"],
        activeforeground=COLORS["fg"],
        command=app._on_frame_change
    ).pack(fill="x", padx=10, pady=(0, 4))


def on_frame_change(app, *args):
    """Geometry or dead load changed — update preview and EQ results."""
    app._update_preview()
    app._update_eq_results()


def on_section_change(app, *args):
    """Section selection changed — update info display and EQ results."""
    app._invalidate_analysis()
    app._update_section_info()
    app._update_eq_results()


def on_design_input_change(app, *args):
    """Effective length changed — invalidate stale design checks."""
    app._invalidate_analysis()


def on_roof_type_change(app, *args):
    if app.roof_type_var.get() == "mono":
        app.pitch2_frame.pack_forget()
        app.pitch_warning_label.pack_forget()
    else:
        # Re-pack after pitch1 widget to maintain correct order
        app.pitch2_frame.pack(fill="x", padx=10, pady=(0, 2), after=app.pitch)
        app.pitch_warning_label.pack(fill="x", padx=10, pady=(0, 2), after=app.pitch2_frame)
    check_pitch_warnings(app)
    app._update_preview()
    app._update_eq_results()


def on_pitch_change(app, *args):
    check_pitch_warnings(app)
    app._update_preview()
    app._update_eq_results()


def check_pitch_warnings(app):
    from portal_frame.models.validation import validate_geometry_pitch
    geom = app._build_geometry()
    warnings = validate_geometry_pitch(geom)
    if warnings:
        app.pitch_warning_label.config(text="\n".join(warnings))
    else:
        app.pitch_warning_label.config(text="")


def build_geometry(app) -> PortalFrameGeometry:
    crane_rail_height = None
    if hasattr(app, 'crane_enabled_var') and app.crane_enabled_var.get():
        crane_rail_height = app.crane_rail_height.get()

    if app.roof_type_var.get() == "mono":
        return PortalFrameGeometry(
            span=app.span.get(),
            eave_height=app.eave.get(),
            roof_pitch=app.pitch.get(),
            bay_spacing=app.bay.get(),
            roof_type="mono",
            crane_rail_height=crane_rail_height,
        )
    return PortalFrameGeometry(
        span=app.span.get(),
        eave_height=app.eave.get(),
        roof_pitch=app.pitch.get(),
        bay_spacing=app.bay.get(),
        roof_type="gable",
        roof_pitch_2=app.pitch2.get(),
        crane_rail_height=crane_rail_height,
    )
