"""WindSurfacePanel -- surface-based wind coefficient table with Walls/Roof tabs."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_BOLD, FONT_SMALL
from portal_frame.gui.dialogs.wall_builders import build_walls_page
from portal_frame.gui.dialogs.roof_builders import build_roof_page, rebuild_roof_table


class WindSurfacePanel(tk.Frame):
    """Surface-based wind coefficient table with Walls/Roof sub-tabs.

    Displays Cp,e and Ka per surface with auto-calculated pe and pnet columns.
    Includes wind case tabs (W1-W8) for preview selection.
    """

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
        self._wall_vars = {}
        self._roof_vars = {}
        self._pe_labels = {}
        self._pnet_labels = {}
        self._dist_labels = {}
        self._recalc_scheduled = False
        # Uniform roof overrides for steep pitch (set by populate, not editable)
        self._roof_uniform = {
            "type": "zones",
            "left_uniform": None,
            "right_uniform": None,
        }

        self._active_case = None
        self._case_btns = {}

        case_strip = tk.Frame(self, bg=COLORS["bg_panel"])
        case_strip.pack(fill="x", padx=2, pady=(4, 0))

        cw_frame = tk.Frame(case_strip, bg=COLORS["bg_panel"])
        cw_frame.pack(side="left", padx=(0, 6))
        tk.Label(cw_frame, text="CROSSWIND", font=("Segoe UI", 7),
                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"]
                 ).pack(side="left", padx=(0, 3))
        for name, direction, envelope, group in self._CASE_INFO[:4]:
            self._build_case_tab(cw_frame, name, direction, envelope)

        sep = tk.Frame(case_strip, bg=COLORS["border"], width=1)
        sep.pack(side="left", fill="y", padx=4, pady=2)

        tr_frame = tk.Frame(case_strip, bg=COLORS["bg_panel"])
        tr_frame.pack(side="left", padx=(0, 4))
        tk.Label(tr_frame, text="TRANSVERSE", font=("Segoe UI", 7),
                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"]
                 ).pack(side="left", padx=(0, 3))
        for name, direction, envelope, group in self._CASE_INFO[4:]:
            self._build_case_tab(tr_frame, name, direction, envelope)

        self._case_desc = tk.Label(
            self, text="", font=FONT_SMALL,
            fg=COLORS["fg_dim"], bg=COLORS["bg_panel"], anchor="w")
        self._case_desc.pack(fill="x", padx=4, pady=(0, 2))

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

        build_walls_page(self, self._sub_tabs["Walls"])
        build_roof_page(self, self._sub_tabs["Roof"])
        self._select_sub("Walls")

    def _build_case_tab(self, parent, name, direction, envelope):
        """Build a single wind case tab button.

        Stays on the class because its lambda closures reference self._active_case
        and self._case_btns directly — extracting would give no size benefit.
        """
        if envelope == "uplift":
            active_bg = "#1b5e7a"
            active_fg = "#7fdbff"
        else:
            active_bg = "#5e3a1b"
            active_fg = "#ffbd7f"

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
        if self._active_case and self._active_case in self._case_btns:
            prev = self._case_btns[self._active_case]
            prev["widget"].config(bg=COLORS["bg"], fg=COLORS["fg_dim"])

        if self._active_case == name:
            self._active_case = None
            self._case_desc.config(text="")
            if self.on_case_select_fn:
                self.on_case_select_fn(None)
            return

        self._active_case = name
        info = self._case_btns[name]
        info["widget"].config(bg=info["active_bg"], fg=info["active_fg"])

        direction = info["direction"]
        envelope = info["envelope"]
        arrow = info["arrow"]
        if direction in ("L-R", "R-L"):
            desc = f"{arrow}  {name}: Crosswind {direction} - max {envelope}"
        else:
            desc = f"{arrow}  {name}: Transverse {direction}\u00b0 - max {envelope}"
        self._case_desc.config(text=desc)

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

    def _rebuild_roof_table(self, direction, case_name=None):
        rebuild_roof_table(self, direction, case_name=case_name)

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

        roof_keys = set()
        for var_key in self._roof_vars:
            if var_key.endswith("_ka"):
                roof_keys.add(var_key[:-3])
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

        if self.on_change_fn:
            self.on_change_fn()

    def populate(self, surface_data):
        """Fill the table from get_surface_coefficients() output."""
        walls = surface_data.get("walls", {})
        roof = surface_data.get("roof", {})

        self._roof_uniform = {
            "type": roof.get("type", "zones"),
            "left_uniform": roof.get("left_uniform"),
            "right_uniform": roof.get("right_uniform"),
        }

        ww_var = self._wall_vars.get("windward_cpe")
        if ww_var:
            ww_var.set(str(walls.get("windward_cpe", 0.7)))
        lw_var = self._wall_vars.get("leeward_cpe")
        if lw_var:
            lw_var.set(str(walls.get("leeward_cpe", -0.5)))

        depth = surface_data.get("building_depth", 0)
        lw_dist = self._dist_labels.get("wall_leeward_dist")
        if lw_dist and depth:
            lw_dist.config(text=f"{depth:.1f} m")

        for i, zone_data in enumerate(walls.get("side_zones", [])):
            s_mult, e_mult, cpe, start_m, end_m = zone_data
            cpe_var = self._wall_vars.get(f"side_{i}_cpe")
            if cpe_var:
                cpe_var.set(str(cpe))
            dist_lbl = self._dist_labels.get(f"wall_side_{i}_dist")
            if dist_lbl:
                zone_text = f"{start_m:.1f}-{end_m:.1f} m"
                dist_lbl.config(text=zone_text)

        if self._active_case:
            case_group = next(
                (g for n, d, e, g in self._CASE_INFO if n == self._active_case),
                "crosswind")
            self._rebuild_roof_table(case_group, case_name=self._active_case)
        else:
            self._rebuild_roof_table("crosswind")

        self._recalc_pressures()

    def _get_var_float(self, var_dict, key, default=0.0):
        var = var_dict.get(key)
        if not var:
            return default
        try:
            return float(var.get())
        except ValueError:
            return default

    def get_surface_data(self) -> dict:
        """Return raw surface Cp,e data for case synthesis by the app."""
        ww_cpe = (self._get_var_float(self._wall_vars, "windward_cpe")
                  * self._get_var_float(self._wall_vars, "windward_ka", 1.0))
        lw_cpe = (self._get_var_float(self._wall_vars, "leeward_cpe")
                  * self._get_var_float(self._wall_vars, "leeward_ka", 1.0))

        side_cpes = []
        for i in range(4):
            cpe = self._get_var_float(self._wall_vars, f"side_{i}_cpe")
            ka = self._get_var_float(self._wall_vars, f"side_{i}_ka", 1.0)
            side_cpes.append(cpe * ka)

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
