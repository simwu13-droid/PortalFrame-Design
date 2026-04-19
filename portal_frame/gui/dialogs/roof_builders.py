"""Roof table builder functions for WindSurfacePanel."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.standards.wind_nzs1170_2 import TABLE_5_3A_ZONES
from portal_frame.gui.dialogs.helpers import styled_entry


def build_roof_page(panel, parent):
    """Build the Roof sub-tab page on *parent*, registering state on *panel*."""
    panel._roof_header_lbl = tk.Label(
        parent, text="EXTERNAL \u2014 Crosswind Slope (Table 5.3A)",
        font=FONT_BOLD, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
        anchor="w")
    panel._roof_header_lbl.pack(fill="x", padx=4, pady=(4, 0))

    panel._roof_container = tk.Frame(parent, bg=COLORS["bg_panel"])
    panel._roof_container.pack(fill="x", padx=2, pady=2)
    panel._roof_direction = "crosswind"

    # Initial build — panel._rebuild_roof_table is defined on WindSurfacePanel
    panel._rebuild_roof_table("crosswind")


def rebuild_roof_table(panel, direction, case_name=None):
    """Rebuild the roof Cp,e table based on wind direction and selected case.

    Clears existing roof vars/labels, destroys old widgets, then rebuilds.
    Called both on initial page build (nothing to clear) and on case change.
    """
    for key in list(panel._roof_vars.keys()):
        del panel._roof_vars[key]
    for key in list(panel._pe_labels.keys()):
        if key.startswith("roof_"):
            del panel._pe_labels[key]
    for key in list(panel._pnet_labels.keys()):
        if key.startswith("roof_"):
            del panel._pnet_labels[key]
    for key in list(panel._dist_labels.keys()):
        if key.startswith("roof_"):
            del panel._dist_labels[key]

    for child in panel._roof_container.winfo_children():
        child.destroy()

    panel._roof_direction = direction
    tbl = tk.Frame(panel._roof_container, bg=COLORS["bg_panel"])
    tbl.pack(fill="x")

    if direction == "crosswind":
        is_LR = case_name not in ("W3", "W4")
        build_roof_crosswind_per_rafter(panel, tbl, is_LR)
    else:
        panel._roof_header_lbl.config(
            text="EXTERNAL \u2014 Transverse (Tables 5.3B / 5.3C)")
        build_roof_transverse(panel, tbl)

    panel._roof_table = tbl
    panel._recalc_pressures()


def build_roof_header_row(tbl):
    """Build the standard multi-level header for roof tables."""
    headers_row0 = [
        ("Surface", 10, 1), ("Distance", 12, 1), ("Ka", 5, 1),
        ("Cp,e", 12, 2), ("pe", 12, 2), ("pnet", 12, 2),
    ]
    col = 0
    for text, w, span in headers_row0:
        tk.Label(tbl, text=text, font=FONT_BOLD, fg=COLORS["fg_dim"],
                 bg=COLORS["bg"], width=w, anchor="center"
                 ).grid(row=0, column=col, columnspan=span, padx=1,
                        pady=(2, 0), sticky="ew")
        col += span
    sub_cols = [(3, "uplift", 6), (4, "downward", 6),
                (5, "uplift", 6), (6, "downward", 6),
                (7, "uplift", 6), (8, "downward", 6)]
    for c, text, w in sub_cols:
        tk.Label(tbl, text=text, font=FONT_SMALL, fg=COLORS["fg_dim"],
                 bg=COLORS["bg"], width=w, anchor="center"
                 ).grid(row=1, column=c, padx=1, pady=(0, 2), sticky="ew")


def build_roof_crosswind_per_rafter(panel, tbl, is_LR=True):
    """Build crosswind roof rows per-rafter based on pitch and wind direction.

    Each rafter independently uses the correct table:
    - pitch < 10 deg: Table 5.3(A) zone-based
    - pitch >= 10 deg, upwind: Table 5.3(B) uniform
    - pitch >= 10 deg, downwind: Table 5.3(C) uniform
    """
    build_roof_header_row(tbl)
    row = 2

    left_uni = panel._roof_uniform.get("left_uniform")
    right_uni = panel._roof_uniform.get("right_uniform")

    if is_LR:
        left_role, right_role = "upwind", "downwind"
        dir_desc = "L\u2192R"
    else:
        left_role, right_role = "downwind", "upwind"
        dir_desc = "R\u2192L"

    panel._roof_header_lbl.config(
        text=f"EXTERNAL \u2014 Crosswind ({dir_desc})")

    rafter_configs = []
    for side, role, uni_data in [
        ("Left", left_role, left_uni),
        ("Right", right_role, right_uni),
    ]:
        has_uniform = uni_data is not None
        if has_uniform and role == "upwind":
            cpe_up_val = uni_data[0] if len(uni_data) >= 1 else -0.9
            cpe_dn_val = uni_data[1] if len(uni_data) >= 2 else -0.4
            rafter_configs.append((side, role, "uniform", "5.3(B)",
                                   cpe_up_val, cpe_dn_val))
        elif has_uniform and role == "downwind":
            cpe_val = uni_data[2] if len(uni_data) >= 3 else uni_data[0]
            rafter_configs.append((side, role, "uniform", "5.3(C)",
                                   cpe_val, cpe_val))
        else:
            rafter_configs.append((side, role, "zones", "5.3(A)",
                                   None, None))

    for side, role, mode, table_ref, cpe_up_val, cpe_dn_val in rafter_configs:
        surface_label = f"{side} ({role})"
        table_label = f"Tbl {table_ref}"

        if mode == "uniform":
            key = f"roof_{side.lower()}_{role}"
            tk.Label(tbl, text=surface_label, font=FONT_MONO,
                     fg=COLORS["fg"], bg=COLORS["bg_panel"],
                     width=14, anchor="w"
                     ).grid(row=row, column=0, padx=1, sticky="w")
            tk.Label(tbl, text=table_label, font=FONT_MONO,
                     fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                     width=12, anchor="w"
                     ).grid(row=row, column=1, padx=1, sticky="w")

            ka_var = tk.StringVar(value="1.0")
            styled_entry(tbl, ka_var, 5, row, 2)
            panel._roof_vars[f"{key}_ka"] = ka_var

            cpe_up_var = tk.StringVar(value=str(cpe_up_val))
            styled_entry(tbl, cpe_up_var, 6, row, 3)
            panel._roof_vars[f"{key}_cpe_up"] = cpe_up_var

            cpe_dn_var = tk.StringVar(value=str(cpe_dn_val))
            styled_entry(tbl, cpe_dn_var, 6, row, 4)
            panel._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

            for j, env in enumerate(("uplift", "downward")):
                lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                               fg=COLORS["warning"], bg=COLORS["bg_panel"],
                               width=6, anchor="e")
                lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
                panel._pe_labels[f"roof_{key}_{env}"] = lbl
            for j, env in enumerate(("uplift", "downward")):
                lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                               fg=COLORS["success"], bg=COLORS["bg_panel"],
                               width=6, anchor="e")
                lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
                panel._pnet_labels[f"roof_{key}_{env}"] = lbl

            ka_var.trace_add("write", panel._schedule_recalc)
            cpe_up_var.trace_add("write", panel._schedule_recalc)
            cpe_dn_var.trace_add("write", panel._schedule_recalc)
            row += 1

        else:
            side_lower = side.lower()
            for i, (s_mult, e_mult, cpe_up, cpe_dn) in enumerate(TABLE_5_3A_ZONES):
                zone_label = f"{s_mult:.0f}h" + (
                    "-end" if e_mult is None else f"-{e_mult:.0f}h")
                key = f"roof_{side_lower}_{i}"

                if i == 0:
                    tk.Label(tbl, text=surface_label, font=FONT_MONO,
                             fg=COLORS["fg"], bg=COLORS["bg_panel"],
                             width=14, anchor="w"
                             ).grid(row=row, column=0, padx=1, sticky="w")

                dist_lbl = tk.Label(tbl, text=zone_label, font=FONT_MONO,
                                    fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                                    width=12, anchor="w")
                dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
                panel._dist_labels[f"roof_{key}_dist"] = dist_lbl

                ka_var = tk.StringVar(value="1.0")
                styled_entry(tbl, ka_var, 5, row, 2)
                panel._roof_vars[f"{key}_ka"] = ka_var

                cpe_up_var = tk.StringVar(value=str(cpe_up))
                styled_entry(tbl, cpe_up_var, 6, row, 3)
                panel._roof_vars[f"{key}_cpe_up"] = cpe_up_var

                cpe_dn_var = tk.StringVar(value=str(cpe_dn))
                styled_entry(tbl, cpe_dn_var, 6, row, 4)
                panel._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

                for j, env in enumerate(("uplift", "downward")):
                    lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                   fg=COLORS["warning"], bg=COLORS["bg_panel"],
                                   width=6, anchor="e")
                    lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
                    panel._pe_labels[f"roof_{key}_{env}"] = lbl
                for j, env in enumerate(("uplift", "downward")):
                    lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                   fg=COLORS["success"], bg=COLORS["bg_panel"],
                                   width=6, anchor="e")
                    lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
                    panel._pnet_labels[f"roof_{key}_{env}"] = lbl

                ka_var.trace_add("write", panel._schedule_recalc)
                cpe_up_var.trace_add("write", panel._schedule_recalc)
                cpe_dn_var.trace_add("write", panel._schedule_recalc)
                row += 1


def build_roof_transverse(panel, tbl):
    """Build Table 5.3B/C uniform roof rows for transverse wind."""
    build_roof_header_row(tbl)
    row = 2

    left_uni = panel._roof_uniform.get("left_uniform")
    right_uni = panel._roof_uniform.get("right_uniform")

    upwind_up = left_uni[0] if left_uni and len(left_uni) >= 1 else -0.9
    upwind_dn = left_uni[1] if left_uni and len(left_uni) >= 2 else -0.4
    downwind_cpe = right_uni[0] if right_uni else -0.5

    surfaces = [
        ("roof_upwind", "Upwind (5.3B)", "0-span", upwind_up, upwind_dn),
        ("roof_downwind", "Downwind (5.3C)", "0-span", downwind_cpe, downwind_cpe),
    ]

    for key, surface_name, dist_text, cpe_up_val, cpe_dn_val in surfaces:
        tk.Label(tbl, text=surface_name, font=FONT_MONO,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"],
                 width=14, anchor="w"
                 ).grid(row=row, column=0, padx=1, sticky="w")

        dist_lbl = tk.Label(tbl, text=dist_text, font=FONT_MONO,
                            fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                            width=12, anchor="w")
        dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
        panel._dist_labels[f"roof_{key}_dist"] = dist_lbl

        ka_var = tk.StringVar(value="1.0")
        styled_entry(tbl, ka_var, 5, row, 2)
        panel._roof_vars[f"{key}_ka"] = ka_var

        cpe_up_var = tk.StringVar(value=str(cpe_up_val))
        styled_entry(tbl, cpe_up_var, 6, row, 3)
        panel._roof_vars[f"{key}_cpe_up"] = cpe_up_var

        cpe_dn_var = tk.StringVar(value=str(cpe_dn_val))
        styled_entry(tbl, cpe_dn_var, 6, row, 4)
        panel._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

        for j, env in enumerate(("uplift", "downward")):
            lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                           fg=COLORS["warning"], bg=COLORS["bg_panel"],
                           width=6, anchor="e")
            lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
            panel._pe_labels[f"roof_{key}_{env}"] = lbl

        for j, env in enumerate(("uplift", "downward")):
            lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                           fg=COLORS["success"], bg=COLORS["bg_panel"],
                           width=6, anchor="e")
            lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
            panel._pnet_labels[f"roof_{key}_{env}"] = lbl

        ka_var.trace_add("write", panel._schedule_recalc)
        cpe_up_var.trace_add("write", panel._schedule_recalc)
        cpe_dn_var.trace_add("write", panel._schedule_recalc)
        row += 1
