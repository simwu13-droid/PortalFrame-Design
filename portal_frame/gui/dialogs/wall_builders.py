"""Wall table builder functions for WindSurfacePanel."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.standards.wind_nzs1170_2 import SIDE_WALL_CPE_ZONES
from portal_frame.gui.dialogs.helpers import styled_entry


def build_walls_page(panel, parent):
    """Build the Walls sub-tab page on *parent*, registering vars on *panel*."""
    tk.Label(parent, text="EXTERNAL", font=FONT_BOLD,
             fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
             anchor="w").pack(fill="x", padx=4, pady=(4, 0))

    tbl = tk.Frame(parent, bg=COLORS["bg_panel"])
    tbl.pack(fill="x", padx=2, pady=2)

    headers_row0 = [
        ("Surface", 10, 1), ("Distance", 12, 1), ("Ka", 5, 1),
        ("Cp,e", 6, 1), ("pe", 12, 2), ("pnet", 12, 2),
    ]
    col = 0
    for text, w, span in headers_row0:
        lbl = tk.Label(tbl, text=text, font=FONT_BOLD, fg=COLORS["fg_dim"],
                       bg=COLORS["bg"], width=w, anchor="center")
        lbl.grid(row=0, column=col, columnspan=span, padx=1, pady=(2, 0),
                 sticky="ew")
        col += span

    sub_cols = [(4, "uplift", 6), (5, "downward", 6),
                (6, "uplift", 6), (7, "downward", 6)]
    for c, text, w in sub_cols:
        tk.Label(tbl, text=text, font=FONT_SMALL, fg=COLORS["fg_dim"],
                 bg=COLORS["bg"], width=w, anchor="center"
                 ).grid(row=1, column=c, padx=1, pady=(0, 2), sticky="ew")

    row = 2
    wall_rows = [
        ("windward", "Windward", "All"),
        ("leeward", "Leeward", ""),
    ]
    for key, surface, dist_text in wall_rows:
        add_wall_row(panel, tbl, row, key, surface, dist_text)
        row += 1

    tk.Label(tbl, text="Side", font=FONT_BOLD, fg=COLORS["fg"],
             bg=COLORS["bg_panel"], width=10, anchor="w"
             ).grid(row=row, column=0, padx=1, pady=(4, 0), sticky="w")
    row += 1

    for i, (s_mult, e_mult, cpe) in enumerate(SIDE_WALL_CPE_ZONES):
        zone_label = f"{s_mult:.0f}h" + (
            "-end" if e_mult is None else f"-{e_mult:.0f}h")
        add_wall_row(panel, tbl, row, f"side_{i}", "", zone_label,
                     default_cpe=cpe, is_side=True)
        row += 1

    panel._walls_table = tbl


def add_wall_row(panel, tbl, row, key, surface, dist_text,
                 default_cpe=0.0, is_side=False):
    """Add one wall data row to *tbl*, registering StringVars on *panel*."""
    if surface:
        tk.Label(tbl, text=surface, font=FONT_MONO, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"], width=10, anchor="w"
                 ).grid(row=row, column=0, padx=1, sticky="w")

    dist_lbl = tk.Label(tbl, text=dist_text, font=FONT_MONO,
                        fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                        width=12, anchor="w")
    dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
    panel._dist_labels[f"wall_{key}_dist"] = dist_lbl

    ka_var = tk.StringVar(value="1.0")
    styled_entry(tbl, ka_var, 5, row, 2)
    panel._wall_vars[f"{key}_ka"] = ka_var

    cpe_var = tk.StringVar(value=str(default_cpe))
    styled_entry(tbl, cpe_var, 6, row, 3)
    panel._wall_vars[f"{key}_cpe"] = cpe_var

    for j, env in enumerate(("uplift", "downward")):
        lbl = tk.Label(tbl, text="\u2014", font=FONT_MONO, fg=COLORS["warning"],
                       bg=COLORS["bg_panel"], width=6, anchor="e")
        lbl.grid(row=row, column=4 + j, padx=1, sticky="e")
        panel._pe_labels[f"wall_{key}_{env}"] = lbl

    for j, env in enumerate(("uplift", "downward")):
        lbl = tk.Label(tbl, text="\u2014", font=FONT_MONO, fg=COLORS["success"],
                       bg=COLORS["bg_panel"], width=6, anchor="e")
        lbl.grid(row=row, column=6 + j, padx=1, sticky="e")
        panel._pnet_labels[f"wall_{key}_{env}"] = lbl

    ka_var.trace_add("write", panel._schedule_recalc)
    cpe_var.trace_add("write", panel._schedule_recalc)
