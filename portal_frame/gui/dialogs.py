"""Wind surface panel -- WindSurfacePanel for surface-based Cp,e editing."""

import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.standards.wind_nzs1170_2 import (
    TABLE_5_3A_ZONES, SIDE_WALL_CPE_ZONES,
)


def _styled_entry(parent, var, width, row, col, padx=1, pady=1):
    """Create a consistently-styled Entry widget and grid it."""
    e = tk.Entry(parent, textvariable=var, font=FONT_MONO, width=width,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"])
    e.grid(row=row, column=col, padx=padx, pady=pady)
    return e


# ══════════════════════════════════════════════════════════════════════
# WindSurfacePanel — surface-based wind coefficient table with Walls/Roof tabs
# ══════════════════════════════════════════════════════════════════════

class WindSurfacePanel(tk.Frame):
    """Surface-based wind coefficient table with Walls/Roof sub-tabs.

    Displays Cp,e and Ka per surface with auto-calculated pe and pnet columns.
    Includes wind case tabs (W1-W8) for preview selection.
    """

    # Wind case metadata for tab display
    _CASE_INFO = [
        ("W1", "L-R", "uplift",   "crosswind"),
        ("W2", "L-R", "downward", "crosswind"),
        ("W3", "R-L", "uplift",   "crosswind"),
        ("W4", "R-L", "downward", "crosswind"),
        ("W5", "90",  "uplift",   "transverse"),
        ("W6", "90",  "downward", "transverse"),
        ("W7", "270", "uplift",   "transverse"),
        ("W8", "270", "downward", "transverse"),
    ]

    def __init__(self, parent, get_geometry_fn=None, get_wind_params_fn=None,
                 on_change_fn=None, on_case_select_fn=None):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.get_geometry_fn = get_geometry_fn
        self.get_wind_params_fn = get_wind_params_fn
        self.on_change_fn = on_change_fn
        self.on_case_select_fn = on_case_select_fn

        # Data storage — StringVars for editable cells
        self._wall_vars = {}   # key -> StringVar for walls (ka, cpe)
        self._roof_vars = {}   # key -> StringVar for roof (ka, cpe_up, cpe_dn)
        self._pe_labels = {}   # key -> tk.Label for auto-calculated pe
        self._pnet_labels = {} # key -> tk.Label for auto-calculated pnet
        self._dist_labels = {} # key -> tk.Label for distance labels
        self._recalc_scheduled = False
        # Uniform roof overrides for steep pitch (set by populate, not editable)
        self._roof_uniform = {
            "type": "zones",
            "left_uniform": None,
            "right_uniform": None,
        }

        # ── Wind Case Tab Strip ──
        self._active_case = None
        self._case_btns = {}

        case_strip = tk.Frame(self, bg=COLORS["bg_panel"])
        case_strip.pack(fill="x", padx=2, pady=(4, 0))

        # Crosswind group
        cw_frame = tk.Frame(case_strip, bg=COLORS["bg_panel"])
        cw_frame.pack(side="left", padx=(0, 6))
        tk.Label(cw_frame, text="CROSSWIND", font=("Segoe UI", 7),
                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"]
                 ).pack(side="left", padx=(0, 3))
        for name, direction, envelope, group in self._CASE_INFO[:4]:
            self._build_case_tab(cw_frame, name, direction, envelope)

        # Separator
        sep = tk.Frame(case_strip, bg=COLORS["border"], width=1)
        sep.pack(side="left", fill="y", padx=4, pady=2)

        # Transverse group
        tr_frame = tk.Frame(case_strip, bg=COLORS["bg_panel"])
        tr_frame.pack(side="left", padx=(0, 4))
        tk.Label(tr_frame, text="TRANSVERSE", font=("Segoe UI", 7),
                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"]
                 ).pack(side="left", padx=(0, 3))
        for name, direction, envelope, group in self._CASE_INFO[4:]:
            self._build_case_tab(tr_frame, name, direction, envelope)

        # Case description label
        self._case_desc = tk.Label(
            self, text="", font=FONT_SMALL,
            fg=COLORS["fg_dim"], bg=COLORS["bg_panel"], anchor="w")
        self._case_desc.pack(fill="x", padx=4, pady=(0, 2))

        # ── Surface Sub-tab bar (Walls / Roof) ──
        tab_bar = tk.Frame(self, bg=COLORS["bg"])
        tab_bar.pack(fill="x")

        self._sub_tabs = {}
        self._sub_tab_btns = {}
        self._active_sub = None

        for name in ("Walls", "Roof"):
            btn = tk.Label(tab_bar, text=f"  {name}  ", font=FONT_BOLD,
                           fg=COLORS["fg_dim"], bg=COLORS["bg"],
                           cursor="hand2", padx=8, pady=4)
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, n=name: self._select_sub(n))
            self._sub_tab_btns[name] = btn

            page = tk.Frame(self, bg=COLORS["bg_panel"])
            self._sub_tabs[name] = page

        self._build_walls_page(self._sub_tabs["Walls"])
        self._build_roof_page(self._sub_tabs["Roof"])
        self._select_sub("Walls")

    def _build_case_tab(self, parent, name, direction, envelope):
        """Build a single wind case tab button."""
        # Color-code by envelope: uplift = cyan accent, downward = warm
        if envelope == "uplift":
            active_bg = "#1b5e7a"
            active_fg = "#7fdbff"
        else:
            active_bg = "#5e3a1b"
            active_fg = "#ffbd7f"

        # Arrow indicator for direction
        if direction == "L-R":
            arrow = "\u2192"
        elif direction == "R-L":
            arrow = "\u2190"
        elif direction == "90":
            arrow = "\u2191"
        else:
            arrow = "\u2193"

        btn = tk.Label(
            parent, text=f"{name}", font=("Consolas", 8, "bold"),
            fg=COLORS["fg_dim"], bg=COLORS["bg"],
            cursor="hand2", padx=4, pady=2,
            relief="flat", borderwidth=0,
        )
        btn.pack(side="left", padx=1)
        btn.bind("<Button-1>", lambda e, n=name: self._select_case(n))
        btn.bind("<Enter>", lambda e, b=btn, n=name:
                 b.config(bg=COLORS["bg_input"]) if n != self._active_case else None)
        btn.bind("<Leave>", lambda e, b=btn, n=name:
                 b.config(bg=COLORS["bg"] if n != self._active_case
                          else self._case_btns[n]["active_bg"]))

        self._case_btns[name] = {
            "widget": btn,
            "direction": direction,
            "envelope": envelope,
            "arrow": arrow,
            "active_bg": active_bg,
            "active_fg": active_fg,
        }

    def _select_case(self, name):
        """Select a wind case tab and notify the app for preview."""
        # Deselect previous
        if self._active_case and self._active_case in self._case_btns:
            prev = self._case_btns[self._active_case]
            prev["widget"].config(bg=COLORS["bg"], fg=COLORS["fg_dim"])

        if self._active_case == name:
            # Toggle off
            self._active_case = None
            self._case_desc.config(text="")
            if self.on_case_select_fn:
                self.on_case_select_fn(None)
            return

        self._active_case = name
        info = self._case_btns[name]
        info["widget"].config(bg=info["active_bg"], fg=info["active_fg"])

        # Build description
        direction = info["direction"]
        envelope = info["envelope"]
        arrow = info["arrow"]
        if direction in ("L-R", "R-L"):
            desc = f"{arrow}  {name}: Crosswind {direction} - max {envelope}"
        else:
            desc = f"{arrow}  {name}: Transverse {direction}\u00b0 - max {envelope}"
        self._case_desc.config(text=desc)

        # Always rebuild roof table when case changes — the per-rafter
        # roles (upwind/downwind) and table references depend on direction
        case_group = next(
            (g for n, d, e, g in self._CASE_INFO if n == name), "crosswind")
        self._rebuild_roof_table(case_group, case_name=name)

        if self.on_case_select_fn:
            self.on_case_select_fn(name)

    def _select_sub(self, name):
        if self._active_sub == name:
            return
        for n, page in self._sub_tabs.items():
            page.pack_forget()
            self._sub_tab_btns[n].config(
                bg=COLORS["bg"], fg=COLORS["fg_dim"])
        self._sub_tabs[name].pack(fill="x", expand=False)
        self._sub_tab_btns[name].config(
            bg=COLORS["accent"], fg=COLORS["fg_bright"])
        self._active_sub = name

    # ── Walls Page ──

    def _build_walls_page(self, parent):
        # Section label
        tk.Label(parent, text="EXTERNAL", font=FONT_BOLD,
                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                 anchor="w").pack(fill="x", padx=4, pady=(4, 0))

        tbl = tk.Frame(parent, bg=COLORS["bg_panel"])
        tbl.pack(fill="x", padx=2, pady=2)

        # Multi-level header
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

        # Sub-headers for pe and pnet
        sub_cols = [(4, "uplift", 6), (5, "downward", 6),
                    (6, "uplift", 6), (7, "downward", 6)]
        for c, text, w in sub_cols:
            tk.Label(tbl, text=text, font=FONT_SMALL, fg=COLORS["fg_dim"],
                     bg=COLORS["bg"], width=w, anchor="center"
                     ).grid(row=1, column=c, padx=1, pady=(0, 2), sticky="ew")

        # Data rows
        row = 2
        wall_rows = [
            ("windward", "Windward", "All"),
            ("leeward", "Leeward", ""),
        ]
        for key, surface, dist_text in wall_rows:
            self._add_wall_row(tbl, row, key, surface, dist_text)
            row += 1

        # Side wall separator
        tk.Label(tbl, text="Side", font=FONT_BOLD, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"], width=10, anchor="w"
                 ).grid(row=row, column=0, padx=1, pady=(4, 0), sticky="w")
        row += 1

        for i, (s_mult, e_mult, cpe) in enumerate(SIDE_WALL_CPE_ZONES):
            zone_label = f"{s_mult:.0f}h" + ("-end" if e_mult is None else f"-{e_mult:.0f}h")
            key = f"side_{i}"
            self._add_wall_row(tbl, row, key, "", zone_label,
                               default_cpe=cpe, is_side=True)
            row += 1

        self._walls_table = tbl

    def _add_wall_row(self, tbl, row, key, surface, dist_text,
                      default_cpe=0.0, is_side=False):
        if surface:
            tk.Label(tbl, text=surface, font=FONT_MONO, fg=COLORS["fg"],
                     bg=COLORS["bg_panel"], width=10, anchor="w"
                     ).grid(row=row, column=0, padx=1, sticky="w")

        dist_lbl = tk.Label(tbl, text=dist_text, font=FONT_MONO,
                            fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                            width=12, anchor="w")
        dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
        self._dist_labels[f"wall_{key}_dist"] = dist_lbl

        # Ka entry
        ka_var = tk.StringVar(value="1.0")
        _styled_entry(tbl, ka_var, 5, row, 2)
        self._wall_vars[f"{key}_ka"] = ka_var

        # Cp,e entry
        cpe_var = tk.StringVar(value=str(default_cpe))
        _styled_entry(tbl, cpe_var, 6, row, 3)
        self._wall_vars[f"{key}_cpe"] = cpe_var

        # pe labels (uplift, downward)
        for j, env in enumerate(("uplift", "downward")):
            lbl = tk.Label(tbl, text="—", font=FONT_MONO, fg=COLORS["warning"],
                           bg=COLORS["bg_panel"], width=6, anchor="e")
            lbl.grid(row=row, column=4 + j, padx=1, sticky="e")
            self._pe_labels[f"wall_{key}_{env}"] = lbl

        # pnet labels (uplift, downward)
        for j, env in enumerate(("uplift", "downward")):
            lbl = tk.Label(tbl, text="—", font=FONT_MONO, fg=COLORS["success"],
                           bg=COLORS["bg_panel"], width=6, anchor="e")
            lbl.grid(row=row, column=6 + j, padx=1, sticky="e")
            self._pnet_labels[f"wall_{key}_{env}"] = lbl

        # Trace for auto-recalc
        ka_var.trace_add("write", self._schedule_recalc)
        cpe_var.trace_add("write", self._schedule_recalc)

    # ── Roof Page ──

    def _build_roof_page(self, parent):
        self._roof_header_lbl = tk.Label(
            parent, text="EXTERNAL — Crosswind Slope (Table 5.3A)",
            font=FONT_BOLD, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
            anchor="w")
        self._roof_header_lbl.pack(fill="x", padx=4, pady=(4, 0))

        # Container that gets rebuilt when wind direction changes
        self._roof_container = tk.Frame(parent, bg=COLORS["bg_panel"])
        self._roof_container.pack(fill="x", padx=2, pady=2)
        self._roof_direction = "crosswind"  # "crosswind" or "transverse"

        self._rebuild_roof_table("crosswind")

    def _rebuild_roof_table(self, direction, case_name=None):
        """Rebuild the roof table based on wind direction and selected case.

        For crosswind (W1-W4), shows per-rafter Cp,e based on each rafter's
        pitch and role (upwind/downwind). Pitch < 10 deg uses Table 5.3(A) zones,
        pitch >= 10 deg upwind uses Table 5.3(B), downwind uses Table 5.3(C).

        For transverse (W5-W8), shows worst-case uniform roof Cp,e.
        """
        # Clear existing roof vars/labels
        for key in list(self._roof_vars.keys()):
            del self._roof_vars[key]
        for key in list(self._pe_labels.keys()):
            if key.startswith("roof_"):
                del self._pe_labels[key]
        for key in list(self._pnet_labels.keys()):
            if key.startswith("roof_"):
                del self._pnet_labels[key]
        for key in list(self._dist_labels.keys()):
            if key.startswith("roof_"):
                del self._dist_labels[key]

        for child in self._roof_container.winfo_children():
            child.destroy()

        self._roof_direction = direction
        tbl = tk.Frame(self._roof_container, bg=COLORS["bg_panel"])
        tbl.pack(fill="x")

        if direction == "crosswind":
            # Determine wind direction from case name
            is_LR = True
            if case_name in ("W3", "W4"):
                is_LR = False
            self._build_roof_crosswind_per_rafter(tbl, is_LR)
        else:
            self._roof_header_lbl.config(
                text="EXTERNAL — Transverse (Tables 5.3B / 5.3C)")
            self._build_roof_transverse(tbl)

        self._roof_table = tbl
        self._recalc_pressures()

    def _build_roof_header_row(self, tbl):
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

    def _build_roof_crosswind_per_rafter(self, tbl, is_LR=True):
        """Build crosswind roof rows per-rafter based on pitch and wind direction.

        Each rafter independently uses the correct table:
        - pitch < 10 deg: Table 5.3(A) zone-based
        - pitch >= 10 deg, upwind: Table 5.3(B) uniform
        - pitch >= 10 deg, downwind: Table 5.3(C) uniform
        """
        self._build_roof_header_row(tbl)
        row = 2

        # Get pitches from geometry callback
        left_pitch = 5.0
        right_pitch = 5.0
        if self.get_geometry_fn:
            try:
                h, depth = self.get_geometry_fn()
            except Exception:
                pass

        # Get pitches from stored surface data
        left_uni = self._roof_uniform.get("left_uniform")
        right_uni = self._roof_uniform.get("right_uniform")
        roof_type = self._roof_uniform.get("type", "zones")

        if is_LR:
            left_role, right_role = "upwind", "downwind"
            dir_desc = "L\u2192R"
        else:
            left_role, right_role = "downwind", "upwind"
            dir_desc = "R\u2192L"

        self._roof_header_lbl.config(
            text=f"EXTERNAL \u2014 Crosswind ({dir_desc})")

        # Determine table for each rafter
        # left_uni = (cpe_up_uplift, cpe_up_downward, cpe_downwind) for mixed
        rafter_configs = []

        for side, role, uni_data in [
            ("Left", left_role, left_uni),
            ("Right", right_role, right_uni),
        ]:
            has_uniform = uni_data is not None
            if has_uniform and role == "upwind":
                # Table 5.3(B): uniform, 2 values (uplift, downward)
                cpe_up_val = uni_data[0] if len(uni_data) >= 1 else -0.9
                cpe_dn_val = uni_data[1] if len(uni_data) >= 2 else -0.4
                table_ref = "5.3(B)"
                rafter_configs.append((side, role, "uniform", table_ref,
                                       cpe_up_val, cpe_dn_val))
            elif has_uniform and role == "downwind":
                # Table 5.3(C): uniform, single value
                cpe_val = uni_data[2] if len(uni_data) >= 3 else uni_data[0]
                table_ref = "5.3(C)"
                rafter_configs.append((side, role, "uniform", table_ref,
                                       cpe_val, cpe_val))
            else:
                # Table 5.3(A): zone-based
                table_ref = "5.3(A)"
                rafter_configs.append((side, role, "zones", table_ref,
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
                _styled_entry(tbl, ka_var, 5, row, 2)
                self._roof_vars[f"{key}_ka"] = ka_var

                cpe_up_var = tk.StringVar(value=str(cpe_up_val))
                _styled_entry(tbl, cpe_up_var, 6, row, 3)
                self._roof_vars[f"{key}_cpe_up"] = cpe_up_var

                cpe_dn_var = tk.StringVar(value=str(cpe_dn_val))
                _styled_entry(tbl, cpe_dn_var, 6, row, 4)
                self._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

                for j, env in enumerate(("uplift", "downward")):
                    lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                   fg=COLORS["warning"], bg=COLORS["bg_panel"],
                                   width=6, anchor="e")
                    lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
                    self._pe_labels[f"roof_{key}_{env}"] = lbl
                for j, env in enumerate(("uplift", "downward")):
                    lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                   fg=COLORS["success"], bg=COLORS["bg_panel"],
                                   width=6, anchor="e")
                    lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
                    self._pnet_labels[f"roof_{key}_{env}"] = lbl

                ka_var.trace_add("write", self._schedule_recalc)
                cpe_up_var.trace_add("write", self._schedule_recalc)
                cpe_dn_var.trace_add("write", self._schedule_recalc)
                row += 1
            else:
                # Zone-based: Table 5.3(A)
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
                                        fg=COLORS["fg_dim"],
                                        bg=COLORS["bg_panel"],
                                        width=12, anchor="w")
                    dist_lbl.grid(row=row, column=1, padx=1, sticky="w")
                    self._dist_labels[f"roof_{key}_dist"] = dist_lbl

                    ka_var = tk.StringVar(value="1.0")
                    _styled_entry(tbl, ka_var, 5, row, 2)
                    self._roof_vars[f"{key}_ka"] = ka_var

                    cpe_up_var = tk.StringVar(value=str(cpe_up))
                    _styled_entry(tbl, cpe_up_var, 6, row, 3)
                    self._roof_vars[f"{key}_cpe_up"] = cpe_up_var

                    cpe_dn_var = tk.StringVar(value=str(cpe_dn))
                    _styled_entry(tbl, cpe_dn_var, 6, row, 4)
                    self._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

                    for j, env in enumerate(("uplift", "downward")):
                        lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                       fg=COLORS["warning"],
                                       bg=COLORS["bg_panel"],
                                       width=6, anchor="e")
                        lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
                        self._pe_labels[f"roof_{key}_{env}"] = lbl
                    for j, env in enumerate(("uplift", "downward")):
                        lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                                       fg=COLORS["success"],
                                       bg=COLORS["bg_panel"],
                                       width=6, anchor="e")
                        lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
                        self._pnet_labels[f"roof_{key}_{env}"] = lbl

                    ka_var.trace_add("write", self._schedule_recalc)
                    cpe_up_var.trace_add("write", self._schedule_recalc)
                    cpe_dn_var.trace_add("write", self._schedule_recalc)
                    row += 1

    def _build_roof_transverse(self, tbl):
        """Build Table 5.3B/C uniform roof rows for transverse wind."""
        self._build_roof_header_row(tbl)
        row = 2

        # Get uniform values from stored data (set by populate)
        left_uni = self._roof_uniform.get("left_uniform")
        right_uni = self._roof_uniform.get("right_uniform")

        # For transverse, the 2D frame sees worst-case uniform pressure
        # Show the roof zones Cp,e as used for the worst-case envelope
        # Upwind Slope — Table 5.3(B)
        upwind_up = left_uni[0] if left_uni and len(left_uni) >= 1 else -0.9
        upwind_dn = left_uni[1] if left_uni and len(left_uni) >= 2 else -0.4
        # Downwind Slope — Table 5.3(C)
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
            self._dist_labels[f"roof_{key}_dist"] = dist_lbl

            ka_var = tk.StringVar(value="1.0")
            _styled_entry(tbl, ka_var, 5, row, 2)
            self._roof_vars[f"{key}_ka"] = ka_var

            cpe_up_var = tk.StringVar(value=str(cpe_up_val))
            _styled_entry(tbl, cpe_up_var, 6, row, 3)
            self._roof_vars[f"{key}_cpe_up"] = cpe_up_var

            cpe_dn_var = tk.StringVar(value=str(cpe_dn_val))
            _styled_entry(tbl, cpe_dn_var, 6, row, 4)
            self._roof_vars[f"{key}_cpe_dn"] = cpe_dn_var

            for j, env in enumerate(("uplift", "downward")):
                lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                               fg=COLORS["warning"], bg=COLORS["bg_panel"],
                               width=6, anchor="e")
                lbl.grid(row=row, column=5 + j, padx=1, sticky="e")
                self._pe_labels[f"roof_{key}_{env}"] = lbl

            for j, env in enumerate(("uplift", "downward")):
                lbl = tk.Label(tbl, text="--", font=FONT_MONO,
                               fg=COLORS["success"], bg=COLORS["bg_panel"],
                               width=6, anchor="e")
                lbl.grid(row=row, column=7 + j, padx=1, sticky="e")
                self._pnet_labels[f"roof_{key}_{env}"] = lbl

            ka_var.trace_add("write", self._schedule_recalc)
            cpe_up_var.trace_add("write", self._schedule_recalc)
            cpe_dn_var.trace_add("write", self._schedule_recalc)
            row += 1

    # ── Recalculation ──

    def _schedule_recalc(self, *_):
        if not self._recalc_scheduled:
            self._recalc_scheduled = True
            self.after_idle(self._recalc_pressures)

    def _recalc_pressures(self):
        self._recalc_scheduled = False
        if not self.get_wind_params_fn:
            return
        try:
            p = self.get_wind_params_fn()
        except Exception:
            return

        qu = p.get("qu", 0)
        kc_i = p.get("kc_i", 1.0)
        cpi_up = p.get("cpi_uplift", 0.2)
        cpi_dn = p.get("cpi_downward", -0.3)

        def _fmt(val):
            return f"{val:+.2f}" if val != 0 else "0.00"

        # Walls
        wall_keys = ["windward", "leeward"] + [f"side_{i}" for i in range(4)]
        for key in wall_keys:
            ka_var = self._wall_vars.get(f"{key}_ka")
            cpe_var = self._wall_vars.get(f"{key}_cpe")
            if not ka_var or not cpe_var:
                continue
            try:
                ka = float(ka_var.get())
                cpe = float(cpe_var.get())
            except ValueError:
                continue

            for env, cpi in [("uplift", cpi_up), ("downward", cpi_dn)]:
                pe = round(cpe * ka * qu, 4)
                pnet = round((cpe * ka - cpi * kc_i) * qu, 4)

                pe_lbl = self._pe_labels.get(f"wall_{key}_{env}")
                pnet_lbl = self._pnet_labels.get(f"wall_{key}_{env}")
                if pe_lbl:
                    pe_lbl.config(text=_fmt(pe))
                if pnet_lbl:
                    pnet_lbl.config(text=_fmt(pnet))

        # Roof — find all roof keys dynamically (works for both crosswind and transverse)
        roof_keys = set()
        for var_key in self._roof_vars:
            if var_key.endswith("_ka"):
                roof_keys.add(var_key[:-3])  # strip "_ka" suffix
        for key in sorted(roof_keys):
            ka_var = self._roof_vars.get(f"{key}_ka")
            cpe_up_var = self._roof_vars.get(f"{key}_cpe_up")
            cpe_dn_var = self._roof_vars.get(f"{key}_cpe_dn")
            if not ka_var or not cpe_up_var or not cpe_dn_var:
                continue
            try:
                ka = float(ka_var.get())
                cpe_uplift = float(cpe_up_var.get())
                cpe_downward = float(cpe_dn_var.get())
            except ValueError:
                continue

            for env, cpi, cpe in [("uplift", cpi_up, cpe_uplift),
                                   ("downward", cpi_dn, cpe_downward)]:
                pe = round(cpe * ka * qu, 4)
                pnet = round((cpe * ka - cpi * kc_i) * qu, 4)

                pe_lbl = self._pe_labels.get(f"roof_{key}_{env}")
                pnet_lbl = self._pnet_labels.get(f"roof_{key}_{env}")
                if pe_lbl:
                    pe_lbl.config(text=_fmt(pe))
                if pnet_lbl:
                    pnet_lbl.config(text=_fmt(pnet))

        # Notify parent of change (for preview updates)
        if self.on_change_fn:
            self.on_change_fn()

    # ── Populate from auto-generate ──

    def populate(self, surface_data):
        """Fill the table from get_surface_coefficients() output."""
        walls = surface_data.get("walls", {})
        roof = surface_data.get("roof", {})
        h = surface_data.get("h", 0)

        # Store uniform roof overrides for steep pitch
        self._roof_uniform = {
            "type": roof.get("type", "zones"),
            "left_uniform": roof.get("left_uniform"),
            "right_uniform": roof.get("right_uniform"),
        }

        # Walls
        ww_var = self._wall_vars.get("windward_cpe")
        if ww_var:
            ww_var.set(str(walls.get("windward_cpe", 0.7)))
        lw_var = self._wall_vars.get("leeward_cpe")
        if lw_var:
            lw_var.set(str(walls.get("leeward_cpe", -0.5)))

        # Leeward distance label
        depth = surface_data.get("building_depth", 0)
        lw_dist = self._dist_labels.get("wall_leeward_dist")
        if lw_dist and depth:
            lw_dist.config(text=f"{depth:.1f} m")

        # Side wall zones
        for i, zone_data in enumerate(walls.get("side_zones", [])):
            s_mult, e_mult, cpe, start_m, end_m = zone_data
            cpe_var = self._wall_vars.get(f"side_{i}_cpe")
            if cpe_var:
                cpe_var.set(str(cpe))
            dist_lbl = self._dist_labels.get(f"wall_side_{i}_dist")
            if dist_lbl:
                zone_text = f"{start_m:.1f}-{end_m:.1f} m"
                dist_lbl.config(text=zone_text)

        # Roof — rebuild to pick up new uniform/zone data
        # Always rebuild since zone keys are per-rafter and direction-dependent
        if self._active_case:
            case_group = next(
                (g for n, d, e, g in self._CASE_INFO if n == self._active_case),
                "crosswind")
            self._rebuild_roof_table(case_group, case_name=self._active_case)
        else:
            self._rebuild_roof_table("crosswind")

        self._recalc_pressures()

    # ── Case Synthesis ──

    def _get_var_float(self, var_dict, key, default=0.0):
        var = var_dict.get(key)
        if not var:
            return default
        try:
            return float(var.get())
        except ValueError:
            return default

    def get_surface_data(self) -> dict:
        """Return raw surface Cp,e data for case synthesis by the app.

        Returns dict with effective Cp,e (= Cp,e * Ka) per surface:
        {
            "windward_cpe": float,
            "leeward_cpe": float,
            "side_cpes": [float, ...],  # per zone
            "roof_zones_up": [float, ...],  # per zone, uplift
            "roof_zones_dn": [float, ...],  # per zone, downward
        }
        """
        ww_cpe = (self._get_var_float(self._wall_vars, "windward_cpe")
                  * self._get_var_float(self._wall_vars, "windward_ka", 1.0))
        lw_cpe = (self._get_var_float(self._wall_vars, "leeward_cpe")
                  * self._get_var_float(self._wall_vars, "leeward_ka", 1.0))

        side_cpes = []
        for i in range(4):
            cpe = self._get_var_float(self._wall_vars, f"side_{i}_cpe")
            ka = self._get_var_float(self._wall_vars, f"side_{i}_ka", 1.0)
            side_cpes.append(cpe * ka)

        # Roof — dynamically read all roof keys from _roof_vars
        roof_zones_up = []
        roof_zones_dn = []
        roof_keys = sorted(
            k[:-3] for k in self._roof_vars if k.endswith("_ka"))
        for key in roof_keys:
            ka = self._get_var_float(self._roof_vars, f"{key}_ka", 1.0)
            cpe_up = self._get_var_float(self._roof_vars, f"{key}_cpe_up") * ka
            cpe_dn = self._get_var_float(self._roof_vars, f"{key}_cpe_dn") * ka
            roof_zones_up.append(cpe_up)
            roof_zones_dn.append(cpe_dn)

        return {
            "windward_cpe": ww_cpe,
            "leeward_cpe": lw_cpe,
            "side_cpes": side_cpes,
            "roof_zones_up": roof_zones_up,
            "roof_zones_dn": roof_zones_dn,
            "roof_uniform": self._roof_uniform,
        }
