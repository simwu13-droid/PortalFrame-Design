"""Modal dialogs — CrosswindZoneDialog, WindCaseTable."""

import tkinter as tk
from tkinter import messagebox

from portal_frame.gui.theme import COLORS, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO
from portal_frame.models.loads import RafterZoneLoad
from portal_frame.standards.wind_nzs1170_2 import TABLE_5_3A_ZONES


class CrosswindZoneDialog(tk.Toplevel):
    """Modal dialog to edit crosswind zone pressures per Table 5.3(A)."""

    def __init__(self, parent, h, building_depth, existing_zones=None):
        super().__init__(parent)
        self.title("Crosswind Zones - Table 5.3(A)")
        self.configure(bg=COLORS["bg_panel"])
        self.geometry("520x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None
        self.h = h
        self.building_depth = building_depth

        # Header info
        info = tk.Frame(self, bg=COLORS["bg"])
        info.pack(fill="x", padx=10, pady=(10, 6))
        tk.Label(info, text=f"h = {h:.2f} m (avg roof height)    d = {building_depth:.1f} m (building depth)",
                 font=FONT_MONO, fg=COLORS["fg_dim"], bg=COLORS["bg"]).pack(padx=8, pady=4)

        # Zone table
        tbl = tk.Frame(self, bg=COLORS["bg_panel"])
        tbl.pack(fill="x", padx=10, pady=6)

        headers = ["Zone", "Start", "End", "Start %", "End %", "Cp,e"]
        for j, hdr_text in enumerate(headers):
            tk.Label(tbl, text=hdr_text, font=FONT_BOLD, fg=COLORS["fg_dim"],
                     bg=COLORS["bg_panel"], width=8, anchor="w"
                     ).grid(row=0, column=j, padx=3, pady=2)

        self.zone_vars = []
        for i, (s_mult, e_mult, cp_max, cp_alt) in enumerate(TABLE_5_3A_ZONES):
            start_m = s_mult * h
            end_m = building_depth if e_mult is None else min(e_mult * h, building_depth)
            if start_m >= building_depth:
                break
            start_pct = round((start_m / building_depth) * 100.0, 1)
            end_pct = round((end_m / building_depth) * 100.0, 1)

            zone_label = f"{s_mult}h-{'end' if e_mult is None else str(e_mult)+'h'}"
            tk.Label(tbl, text=zone_label, font=FONT_MONO, fg=COLORS["fg"],
                     bg=COLORS["bg_panel"], width=8, anchor="w").grid(row=i+1, column=0, padx=3)
            tk.Label(tbl, text=f"{start_m:.1f}m", font=FONT_MONO, fg=COLORS["fg_dim"],
                     bg=COLORS["bg_panel"], width=8).grid(row=i+1, column=1, padx=3)
            tk.Label(tbl, text=f"{end_m:.1f}m", font=FONT_MONO, fg=COLORS["fg_dim"],
                     bg=COLORS["bg_panel"], width=8).grid(row=i+1, column=2, padx=3)
            tk.Label(tbl, text=f"{start_pct:.1f}%", font=FONT_MONO, fg=COLORS["fg_dim"],
                     bg=COLORS["bg_panel"], width=8).grid(row=i+1, column=3, padx=3)
            tk.Label(tbl, text=f"{end_pct:.1f}%", font=FONT_MONO, fg=COLORS["fg_dim"],
                     bg=COLORS["bg_panel"], width=8).grid(row=i+1, column=4, padx=3)

            default_cp = cp_max
            if existing_zones and i < len(existing_zones):
                default_cp = existing_zones[i].pressure
            var = tk.StringVar(value=str(default_cp))
            e = tk.Entry(tbl, textvariable=var, font=FONT_MONO, width=8,
                         bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                         insertbackground=COLORS["fg_bright"], relief="flat",
                         highlightthickness=1, highlightcolor=COLORS["accent"],
                         highlightbackground=COLORS["border"])
            e.grid(row=i+1, column=5, padx=3, pady=1)
            self.zone_vars.append((start_pct, end_pct, var))

        # Reference
        ref = tk.Label(self, text=(
            "Table 5.3(A) Cp,e values for roof pitch < 10 deg:\n"
            "  Max suction:  -0.9,  -0.5,  -0.3,  -0.2\n"
            "  Alternative:   -0.4,   0.0,  +0.1,  +0.2"
        ), font=FONT_MONO, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
            anchor="w", justify="left")
        ref.pack(fill="x", padx=10, pady=(4, 8))

        # Buttons
        btn_frame = tk.Frame(self, bg=COLORS["bg_panel"])
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        tk.Button(btn_frame, text="OK", font=FONT_BOLD, fg=COLORS["fg_bright"],
                  bg=COLORS["accent"], activebackground=COLORS["accent_hover"],
                  relief="flat", padx=16, pady=4, cursor="hand2",
                  command=self._ok).pack(side="left")
        tk.Button(btn_frame, text="Cancel", font=FONT, fg=COLORS["fg"],
                  bg=COLORS["bg_input"], relief="flat", padx=16, pady=4,
                  cursor="hand2", command=self.destroy).pack(side="left", padx=(8, 0))

        self.wait_window()

    def _ok(self):
        zones = []
        for start_pct, end_pct, var in self.zone_vars:
            try:
                pressure = float(var.get())
            except ValueError:
                pressure = 0.0
            zones.append(RafterZoneLoad(start_pct=start_pct, end_pct=end_pct, pressure=pressure))
        self.result = zones
        self.destroy()


class WindCaseTable(tk.Frame):
    """Editable table for wind load cases — supports transverse and crosswind types."""

    TRANS_COLUMNS = [
        ("Name", 6),
        ("Description", 18),
        ("Left Wall", 8),
        ("Right Wall", 8),
        ("Left Rafter", 8),
        ("Right Rafter", 8),
    ]

    def __init__(self, parent, get_geometry_fn=None):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.rows = []
        self.get_geometry_fn = get_geometry_fn

        # Header
        hdr = tk.Frame(self, bg=COLORS["bg"])
        hdr.pack(fill="x")
        for i, (col_name, col_w) in enumerate(self.TRANS_COLUMNS):
            tk.Label(hdr, text=col_name, font=FONT_BOLD, fg=COLORS["fg_dim"],
                     bg=COLORS["bg"], width=col_w, anchor="w"
                     ).grid(row=0, column=i, padx=2, pady=2)

        self.table_frame = tk.Frame(self, bg=COLORS["bg_panel"])
        self.table_frame.pack(fill="x")

        # Buttons
        btn_frame = tk.Frame(self, bg=COLORS["bg_panel"])
        btn_frame.pack(fill="x", pady=(4, 0))

        tk.Button(
            btn_frame, text="+ Transverse", font=FONT, fg=COLORS["fg_bright"],
            bg=COLORS["bg_input"], activebackground=COLORS["accent"],
            activeforeground=COLORS["fg_bright"], relief="flat", cursor="hand2",
            command=self.add_row, padx=8, pady=2
        ).pack(side="left")

        tk.Button(
            btn_frame, text="+ Crosswind (5.3A)", font=FONT, fg=COLORS["fg_bright"],
            bg=COLORS["bg_input"], activebackground=COLORS["accent"],
            activeforeground=COLORS["fg_bright"], relief="flat", cursor="hand2",
            command=self._add_crosswind_row, padx=8, pady=2
        ).pack(side="left", padx=(4, 0))

        tk.Button(
            btn_frame, text="- Remove Last", font=FONT, fg=COLORS["fg"],
            bg=COLORS["bg_input"], activebackground=COLORS["error"],
            activeforeground=COLORS["fg_bright"], relief="flat", cursor="hand2",
            command=self.remove_row, padx=8, pady=2
        ).pack(side="left", padx=(4, 0))

    def add_row(self, values=None):
        idx = len(self.rows) + 1
        if values is None:
            values = [f"W{idx}", "", "0", "0", "0", "0"]

        row_frame = tk.Frame(self.table_frame, bg=COLORS["bg_panel"])
        row_frame.pack(fill="x")

        entries = []
        for i, (col_name, col_w) in enumerate(self.TRANS_COLUMNS):
            var = tk.StringVar(value=str(values[i]))
            e = tk.Entry(row_frame, textvariable=var, font=FONT_MONO, width=col_w,
                         bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                         insertbackground=COLORS["fg_bright"], relief="flat",
                         highlightthickness=1, highlightcolor=COLORS["accent"],
                         highlightbackground=COLORS["border"])
            e.grid(row=0, column=i, padx=2, pady=1)
            entries.append(var)

        self.rows.append((row_frame, entries, {"type": "transverse"}))

    def add_crosswind_row(self, name, desc, left_wall, right_wall, zones,
                          right_zones=None):
        row_frame = tk.Frame(self.table_frame, bg=COLORS["bg_panel"])
        row_frame.pack(fill="x")

        row_data = {
            "type": "crosswind",
            "zones": zones,
            "right_zones": right_zones if right_zones is not None else zones,
        }

        v_name = tk.StringVar(value=name)
        tk.Entry(row_frame, textvariable=v_name, font=FONT_MONO, width=6,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"]).grid(row=0, column=0, padx=2, pady=1)
        v_desc = tk.StringVar(value=desc)
        tk.Entry(row_frame, textvariable=v_desc, font=FONT_MONO, width=18,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"]).grid(row=0, column=1, padx=2, pady=1)
        v_lw = tk.StringVar(value=str(left_wall))
        tk.Entry(row_frame, textvariable=v_lw, font=FONT_MONO, width=8,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"]).grid(row=0, column=2, padx=2, pady=1)
        v_rw = tk.StringVar(value=str(right_wall))
        tk.Entry(row_frame, textvariable=v_rw, font=FONT_MONO, width=8,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"]).grid(row=0, column=3, padx=2, pady=1)

        l_text = " ".join(f"{z.pressure:+.2f}" for z in zones)
        r_zones = right_zones if right_zones is not None else zones
        r_text = " ".join(f"{z.pressure:+.2f}" for z in r_zones)
        zone_text = f"L[{l_text}] R[{r_text}]"
        zone_label = tk.Label(row_frame, text=zone_text, font=FONT_SMALL,
                              fg=COLORS["warning"], bg=COLORS["bg_panel"], anchor="w")
        zone_label.grid(row=0, column=4, columnspan=2, padx=2, sticky="w")
        row_data["zone_label"] = zone_label

        edit_btn = tk.Button(row_frame, text="Edit", font=FONT_SMALL,
                             fg=COLORS["fg_bright"], bg=COLORS["accent"],
                             relief="flat", padx=4, cursor="hand2",
                             command=lambda rd=row_data, lbl=zone_label: self._edit_zones(rd, lbl))
        edit_btn.grid(row=0, column=6, padx=2)

        entries = [v_name, v_desc, v_lw, v_rw]
        self.rows.append((row_frame, entries, row_data))

    def _add_crosswind_row(self):
        if self.get_geometry_fn:
            h, depth = self.get_geometry_fn()
        else:
            h, depth = 4.75, 24.0
        if depth <= 0 or h <= 0:
            messagebox.showwarning("Warning", "Set valid Building Depth and geometry first.")
            return

        dlg = CrosswindZoneDialog(self, h, depth)
        if dlg.result:
            idx = len(self.rows) + 1
            self.add_crosswind_row(
                name=f"CW{idx}", desc="Crosswind Table 5.3(A)",
                left_wall="-0.65", right_wall="-0.50",
                zones=dlg.result,
            )

    def _edit_zones(self, row_data, zone_label):
        if self.get_geometry_fn:
            h, depth = self.get_geometry_fn()
        else:
            h, depth = 4.75, 24.0
        dlg = CrosswindZoneDialog(self, h, depth, existing_zones=row_data.get("zones"))
        if dlg.result:
            row_data["zones"] = dlg.result
            zone_text = "  ".join(f"{z.pressure:+.1f}" for z in dlg.result)
            zone_label.config(text=f"Zones: {zone_text}")

    def remove_row(self):
        if self.rows:
            frame, _, _ = self.rows.pop()
            frame.destroy()

    def get_wind_cases(self) -> list[dict]:
        cases = []
        for _, entries, row_data in self.rows:
            vals = [e.get() for e in entries]
            try:
                if row_data["type"] == "crosswind":
                    left_z = row_data.get("zones", [])
                    right_z = row_data.get("right_zones", left_z)
                    left_dicts = [{"start_pct": z.start_pct, "end_pct": z.end_pct,
                                   "pressure": z.pressure} for z in left_z]
                    right_dicts = [{"start_pct": z.start_pct, "end_pct": z.end_pct,
                                    "pressure": z.pressure} for z in right_z]
                    cases.append({
                        "name": vals[0].strip() or f"CW{len(cases)+1}",
                        "description": vals[1].strip(),
                        "is_crosswind": True,
                        "left_wall": float(vals[2] or 0),
                        "right_wall": float(vals[3] or 0),
                        "left_rafter_zones": left_dicts,
                        "right_rafter_zones": right_dicts,
                    })
                else:
                    cases.append({
                        "name": vals[0].strip() or f"W{len(cases)+1}",
                        "description": vals[1].strip(),
                        "left_wall": float(vals[2] or 0),
                        "right_wall": float(vals[3] or 0),
                        "left_rafter": float(vals[4] or 0),
                        "right_rafter": float(vals[5] or 0),
                    })
            except ValueError:
                pass
        return cases

    def load_defaults(self):
        defaults = [
            ["W1", "Crosswind L-R - max uplift", "0.56", "-0.40", "-0.72", "-0.40"],
            ["W2", "Crosswind L-R - max downward", "0.56", "-0.40", "0.16", "-0.40"],
            ["W3", "Crosswind R-L - max uplift", "-0.40", "0.56", "-0.40", "-0.72"],
            ["W4", "Crosswind R-L - max downward", "-0.40", "0.56", "-0.40", "0.16"],
        ]
        for vals in defaults:
            self.add_row(vals)
