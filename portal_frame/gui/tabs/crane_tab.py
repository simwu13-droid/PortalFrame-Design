"""Crane tab — gantry crane loading inputs (Gc, Qc, Hc transverse).

Note: add_crane_hc_row and remove_crane_hc_row do not reference `app` in their
bodies — they only use local variables, tk.*, and theme constants.  The `app`
parameter is kept as the first argument for consistency with the module pattern.
"""

import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.gui.widgets import LabeledEntry


def build_crane_tab(app, parent):
    pad = {"padx": 10, "pady": (0, 2)}

    app._section_header(parent, "GANTRY CRANE LOADING")

    app.crane_enabled_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        parent, text="Enable Gantry Crane Loading",
        variable=app.crane_enabled_var, font=FONT_BOLD,
        fg=COLORS["fg"], bg=COLORS["bg_panel"],
        selectcolor=COLORS["bg_input"],
        activebackground=COLORS["bg_panel"],
        activeforeground=COLORS["fg"],
        command=app._on_crane_toggle,
    ).pack(fill="x", padx=10, pady=(0, 6))

    app.crane_content = tk.Frame(parent, bg=COLORS["bg_panel"])
    # Initially hidden — shown on toggle

    app._section_header(app.crane_content, "CRANE PARAMETERS")
    app.crane_rail_height = LabeledEntry(
        app.crane_content, "Rail Height", 3.0, "m")
    app.crane_rail_height.pack(fill="x", **pad)
    app.crane_rail_height.bind_change(app._on_crane_param_change)

    app._section_header(app.crane_content, "CRANE DEAD LOAD (Gc) -- unfactored")
    app.crane_gc_left = LabeledEntry(
        app.crane_content, "Gc Left Bracket", 0.0, "kN")
    app.crane_gc_left.pack(fill="x", **pad)
    app.crane_gc_right = LabeledEntry(
        app.crane_content, "Gc Right Bracket", 0.0, "kN")
    app.crane_gc_right.pack(fill="x", **pad)

    app._section_header(app.crane_content, "CRANE LIVE LOAD (Qc) -- unfactored")
    app.crane_qc_left = LabeledEntry(
        app.crane_content, "Qc Left Bracket", 0.0, "kN")
    app.crane_qc_left.pack(fill="x", **pad)
    app.crane_qc_right = LabeledEntry(
        app.crane_content, "Qc Right Bracket", 0.0, "kN")
    app.crane_qc_right.pack(fill="x", **pad)

    # Transverse ULS
    app._section_header(
        app.crane_content,
        "TRANSVERSE ULS (Hc) -- pre-factored from manufacturer")
    app.crane_hc_uls_frame = tk.Frame(
        app.crane_content, bg=COLORS["bg_panel"])
    app.crane_hc_uls_frame.pack(fill="x", padx=10, pady=(0, 4))
    app.crane_hc_uls_rows = []

    uls_btn_row = tk.Frame(app.crane_content, bg=COLORS["bg_panel"])
    uls_btn_row.pack(fill="x", padx=10, pady=(0, 6))
    tk.Button(
        uls_btn_row, text="+ Add ULS Row", font=FONT_SMALL,
        fg=COLORS["fg_bright"], bg=COLORS["accent"],
        activebackground=COLORS["accent_hover"],
        relief="flat", cursor="hand2", padx=6, pady=2,
        command=lambda: app._add_crane_hc_row(
            app.crane_hc_uls_frame, app.crane_hc_uls_rows,
            "Hc", len(app.crane_hc_uls_rows) + 1),
    ).pack(side="left", padx=(0, 4))
    tk.Button(
        uls_btn_row, text="- Remove Last", font=FONT_SMALL,
        fg=COLORS["fg_bright"], bg=COLORS["border"],
        activebackground=COLORS["fg_dim"],
        relief="flat", cursor="hand2", padx=6, pady=2,
        command=lambda: app._remove_crane_hc_row(app.crane_hc_uls_rows),
    ).pack(side="left")

    # Transverse SLS
    app._section_header(
        app.crane_content,
        "TRANSVERSE SLS (Hc) -- pre-factored from manufacturer")
    app.crane_hc_sls_frame = tk.Frame(
        app.crane_content, bg=COLORS["bg_panel"])
    app.crane_hc_sls_frame.pack(fill="x", padx=10, pady=(0, 4))
    app.crane_hc_sls_rows = []

    sls_btn_row = tk.Frame(app.crane_content, bg=COLORS["bg_panel"])
    sls_btn_row.pack(fill="x", padx=10, pady=(0, 6))
    tk.Button(
        sls_btn_row, text="+ Add SLS Row", font=FONT_SMALL,
        fg=COLORS["fg_bright"], bg=COLORS["accent"],
        activebackground=COLORS["accent_hover"],
        relief="flat", cursor="hand2", padx=6, pady=2,
        command=lambda: app._add_crane_hc_row(
            app.crane_hc_sls_frame, app.crane_hc_sls_rows,
            "Hcs", len(app.crane_hc_sls_rows) + 1),
    ).pack(side="left", padx=(0, 4))
    tk.Button(
        sls_btn_row, text="- Remove Last", font=FONT_SMALL,
        fg=COLORS["fg_bright"], bg=COLORS["border"],
        activebackground=COLORS["fg_dim"],
        relief="flat", cursor="hand2", padx=6, pady=2,
        command=lambda: app._remove_crane_hc_row(app.crane_hc_sls_rows),
    ).pack(side="left")


def on_crane_toggle(app, *args):
    if app.crane_enabled_var.get():
        app.crane_content.pack(fill="x", padx=10)
    else:
        app.crane_content.pack_forget()
    app.refresh_load_case_list()
    app._update_preview()


def on_crane_param_change(app, *args):
    """Called when crane rail height or loads change."""
    app.refresh_load_case_list()
    app._update_preview()


def add_crane_hc_row(app, frame, rows_list, prefix, idx):
    """Add a transverse combo row."""
    row_frame = tk.Frame(frame, bg=COLORS["bg_panel"])
    row_frame.pack(fill="x", pady=1)

    name_var = tk.StringVar(value=f"{prefix}{idx}")
    left_var = tk.StringVar(value="0.0")
    right_var = tk.StringVar(value="0.0")

    tk.Entry(row_frame, textvariable=name_var, font=FONT_MONO, width=8,
             bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
             insertbackground=COLORS["fg_bright"],
             relief="flat", highlightthickness=1,
             highlightcolor=COLORS["accent"],
             highlightbackground=COLORS["border"]).pack(side="left", padx=(0, 4))
    tk.Label(row_frame, text="L:", font=FONT_SMALL, fg=COLORS["fg_dim"],
             bg=COLORS["bg_panel"]).pack(side="left")
    tk.Entry(row_frame, textvariable=left_var, font=FONT_MONO, width=8,
             bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
             insertbackground=COLORS["fg_bright"],
             relief="flat", highlightthickness=1,
             highlightcolor=COLORS["accent"],
             highlightbackground=COLORS["border"]).pack(side="left", padx=(2, 4))
    tk.Label(row_frame, text="R:", font=FONT_SMALL, fg=COLORS["fg_dim"],
             bg=COLORS["bg_panel"]).pack(side="left")
    tk.Entry(row_frame, textvariable=right_var, font=FONT_MONO, width=8,
             bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
             insertbackground=COLORS["fg_bright"],
             relief="flat", highlightthickness=1,
             highlightcolor=COLORS["accent"],
             highlightbackground=COLORS["border"]).pack(side="left", padx=(2, 4))
    tk.Label(row_frame, text="kN", font=FONT_SMALL, fg=COLORS["fg_dim"],
             bg=COLORS["bg_panel"]).pack(side="left")

    rows_list.append((row_frame, name_var, left_var, right_var))


def remove_crane_hc_row(app, rows_list):
    """Remove the last transverse combo row."""
    if rows_list:
        row_frame, _, _, _ = rows_list.pop()
        row_frame.destroy()
