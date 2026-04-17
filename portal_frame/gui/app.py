"""Main application window — tab orchestration and generate flow."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import math
import os

from portal_frame.gui.theme import COLORS, FONT, FONT_BOLD, FONT_TITLE, FONT_SMALL, FONT_MONO
from portal_frame.gui.widgets import LabeledEntry, LabeledCombo
from portal_frame.gui.preview import FramePreview
from portal_frame.gui.dialogs import WindSurfacePanel
from portal_frame.gui.tabs.combos_tab import build_combos_tab
from portal_frame.gui.tabs.crane_tab import (
    build_crane_tab, on_crane_toggle, on_crane_param_change,
    add_crane_hc_row, remove_crane_hc_row,
)
from portal_frame.gui.tabs.frame_tab import (
    build_frame_tab, build_geometry, on_frame_change, on_section_change,
    on_design_input_change, on_roof_type_change, on_pitch_change,
)
from portal_frame.gui.tabs.wind_tab import (
    build_wind_tab, on_wind_table_change, on_wind_case_select,
)
from portal_frame.gui.tabs.earthquake_tab import (
    build_earthquake_tab, on_eq_toggle, on_eq_location_change,
    on_ductility_change, update_eq_results,
)

from portal_frame.io.section_library import load_all_sections
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import RafterZoneLoad, WindCase, LoadInput, EarthquakeInputs
from portal_frame.standards.earthquake_nzs1170_5 import calculate_earthquake_forces
from portal_frame.models.supports import SupportCondition
from portal_frame.standards.wind_nzs1170_2 import (
    get_surface_coefficients, cfig, roof_cpe_zones, mirror_zones,
)
from portal_frame.solvers.base import AnalysisRequest
from portal_frame.solvers.spacegass import SpaceGassSolver


class PortalFrameApp(tk.Tk):

    _APP_DIR = os.path.join(os.path.expanduser("~"), ".portal_frame")
    _RECENT_FILE = os.path.join(_APP_DIR, "recent.json")
    _LAST_SESSION = os.path.join(_APP_DIR, "last_session.json")

    def __init__(self):
        super().__init__()
        self.title("Portal Frame Generator  |  SpaceGass v14  |  AS/NZS 1170")
        self.configure(bg=COLORS["bg"])
        self.geometry("1050x740")
        self.minsize(900, 600)

        # Load section library
        self.section_library = load_all_sections()
        self.section_names = sorted(self.section_library.keys())

        # Style ttk widgets
        self._configure_styles()

        # Build UI
        self._build_ui()

        self._analysis_output = None
        self._analysis_topology = None
        self._diagram_display_to_name = {"(none)": None}

        # Auto-generate default wind cases
        self._auto_generate_wind_cases()
        self._update_preview()

        # Auto-restore last session and handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._auto_restore()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TCombobox",
                        fieldbackground=COLORS["bg_input"],
                        background=COLORS["bg_input"],
                        foreground=COLORS["fg_bright"],
                        borderwidth=0,
                        relief="flat")
        style.map("TCombobox",
                  fieldbackground=[("readonly", COLORS["bg_input"])],
                  selectbackground=[("readonly", COLORS["bg_input"])],
                  selectforeground=[("readonly", COLORS["fg_bright"])])

        style.configure("TCheckbutton",
                        background=COLORS["bg_panel"],
                        foreground=COLORS["fg"],
                        font=FONT)

    def _build_ui(self):
        # Title bar
        title_bar = tk.Frame(self, bg=COLORS["bg_header"], height=36)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="  PORTAL FRAME GENERATOR", font=FONT_TITLE,
                 fg=COLORS["fg_bright"], bg=COLORS["bg_header"],
                 anchor="w").pack(side="left", padx=8, fill="y")
        tk.Label(title_bar, text="SpaceGass v14  |  AS/NZS 1170.0:2002  ",
                 font=FONT_SMALL, fg="#cccccc", bg=COLORS["bg_header"],
                 anchor="e").pack(side="right", padx=8, fill="y")

        # Main content
        paned = tk.PanedWindow(self, orient="horizontal", bg=COLORS["border"],
                               sashwidth=5, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        # Left panel with tabs
        left_outer = tk.Frame(paned, bg=COLORS["bg_panel"])

        self._tab_bar = tk.Frame(left_outer, bg=COLORS["bg"])
        self._tab_bar.pack(fill="x")

        self._tab_buttons = []
        self._tab_pages = {}
        self._tab_canvases = {}
        self._active_tab = None

        self._tab_container = tk.Frame(left_outer, bg=COLORS["bg_panel"])
        self._tab_container.pack(fill="both", expand=True)

        tab_names = ["Frame", "Wind", "Earthquake", "Crane", "Combos"]
        for name in tab_names:
            self._create_tab_page(name)

        build_frame_tab(self, self._tab_pages["Frame"])
        build_wind_tab(self, self._tab_pages["Wind"])
        build_earthquake_tab(self, self._tab_pages["Earthquake"])
        build_crane_tab(self, self._tab_pages["Crane"])
        build_combos_tab(self, self._tab_pages["Combos"])

        self._select_tab("Frame")

        paned.add(left_outer, minsize=380, stretch="always")

        # Right panel (preview + generate)
        right = tk.Frame(paned, bg=COLORS["bg"])
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        load_bar = tk.Frame(right, bg=COLORS["bg_panel"])
        load_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        tk.Label(load_bar, text="Show Load Case:", font=FONT, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"]).pack(side="left", padx=(8, 4))
        self.load_case_var = tk.StringVar(value="(none)")
        self.load_case_combo = ttk.Combobox(
            load_bar, textvariable=self.load_case_var,
            values=["(none)"], state="readonly", font=FONT_MONO, width=30)
        self.load_case_combo.pack(side="left", padx=4)
        self.load_case_combo.bind("<<ComboboxSelected>>", lambda _: self._draw_preview())
        self.load_case_combo.bind("<Button-1>", lambda _: self.refresh_load_case_list())

        tk.Label(load_bar, text="  Diagram:", font=FONT, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"]).pack(side="left", padx=(16, 4))

        self.diagram_case_var = tk.StringVar(value="(none)")
        self.diagram_case_combo = ttk.Combobox(
            load_bar, textvariable=self.diagram_case_var,
            values=["(none)"], state="readonly", font=FONT_MONO, width=22)
        self.diagram_case_combo.pack(side="left", padx=4)
        self.diagram_case_combo.bind("<<ComboboxSelected>>",
                                      lambda _: self._draw_preview())

        self.diagram_type_var = tk.StringVar(value="M")
        self.diagram_type_combo = ttk.Combobox(
            load_bar, textvariable=self.diagram_type_var,
            values=["M", "V", "N", "δ"], state="readonly", font=FONT_MONO, width=4)
        self.diagram_type_combo.pack(side="left", padx=4)
        self.diagram_type_combo.bind("<<ComboboxSelected>>",
                                      lambda _: self._on_diagram_type_changed())

        right.rowconfigure(1, weight=1)

        self.preview = FramePreview(right, width=400, height=300)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        bottom = tk.Frame(right, bg=COLORS["bg_panel"])
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))

        self.summary_label = tk.Label(
            bottom, text="", font=FONT_MONO, fg=COLORS["fg_dim"],
            bg=COLORS["bg_panel"], anchor="w", justify="left"
        )
        self.summary_label.pack(fill="x", padx=8, pady=(8, 4))

        self._results_text = tk.Text(
            bottom, font=FONT_MONO, fg=COLORS["fg"],
            bg=COLORS["bg_input"], height=8, width=60,
            relief="flat", state="disabled", wrap="none",
        )
        self._results_text.pack(fill="x", padx=8, pady=(0, 4))

        btn_row = tk.Frame(bottom, bg=COLORS["bg_panel"])
        btn_row.pack(fill="x", padx=8, pady=(0, 8))

        self.generate_btn = tk.Button(
            btn_row, text="  GENERATE SPACEGASS FILE  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg=COLORS["accent"],
            activebackground=COLORS["accent_hover"],
            activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=self._generate
        )
        self.generate_btn.pack(side="left")

        self.analyse_btn = tk.Button(
            btn_row, text="  ANALYSE (PyNite)  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg=COLORS["analyse_btn"],
            activebackground=COLORS["analyse_btn_hover"],
            activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=16, pady=8,
            command=self._analyse
        )
        self.analyse_btn.pack(side="left", padx=(8, 0))

        tk.Button(
            btn_row, text="  SAVE  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg="#555555",
            activebackground="#666666",
            activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=8, pady=8,
            command=self._save_config
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_row, text="  LOAD  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg="#555555",
            activebackground="#666666",
            activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=8, pady=8,
            command=self._load_config
        ).pack(side="left", padx=(4, 0))

        self._recent_menu_btn = tk.Menubutton(
            btn_row, text="  Recent  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg="#555555",
            activebackground="#666666",
            activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=8, pady=8,
        )
        self._recent_menu_btn.pack(side="left", padx=(4, 0))
        self._recent_menu = tk.Menu(
            self._recent_menu_btn, tearoff=0, font=FONT,
            bg=COLORS["bg_panel"], fg=COLORS["fg"],
            activebackground=COLORS["accent"],
            activeforeground=COLORS["fg_bright"],
        )
        self._recent_menu_btn["menu"] = self._recent_menu
        self._update_recent_menu()

        self.status_label = tk.Label(
            btn_row, text="", font=FONT, fg=COLORS["success"],
            bg=COLORS["bg_panel"], anchor="w"
        )
        self.status_label.pack(side="left", padx=(12, 0))

        paned.add(right, minsize=300, stretch="always")

    def _create_tab_page(self, name):
        btn = tk.Label(
            self._tab_bar, text=f"  {name}  ", font=FONT_BOLD,
            fg=COLORS["fg_dim"], bg=COLORS["bg"],
            padx=14, pady=6, cursor="hand2",
        )
        btn.pack(side="left", padx=(1, 0))
        btn.bind("<Button-1>", lambda e, n=name: self._select_tab(n))
        self._tab_buttons.append((name, btn))

        page_outer = tk.Frame(self._tab_container, bg=COLORS["bg_panel"])

        canvas = tk.Canvas(page_outer, bg=COLORS["bg_panel"],
                           highlightthickness=0, borderwidth=0)
        vscroll = ttk.Scrollbar(page_outer, orient="vertical",
                                command=canvas.yview)
        hscroll = ttk.Scrollbar(page_outer, orient="horizontal",
                                command=canvas.xview)
        inner = tk.Frame(canvas, bg=COLORS["bg_panel"])

        inner.bind(
            "<Configure>",
            lambda e, c=canvas: c.configure(scrollregion=c.bbox("all"))
        )
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set,
                         xscrollcommand=hscroll.set)

        vscroll.pack(side="right", fill="y")
        hscroll.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)

        def _sync_width(event, c=canvas, w=win_id, f=inner):
            c.itemconfigure(w, width=max(event.width, f.winfo_reqwidth()))
        canvas.bind("<Configure>", _sync_width)

        def _on_mousewheel(event, c=canvas):
            if event.state & 0x1:
                c.xview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                c.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)

        self._tab_pages[name] = inner
        self._tab_canvases[name] = (page_outer, canvas)

    def _select_tab(self, name):
        if self._active_tab == name:
            return
        for n, (page_outer, _) in self._tab_canvases.items():
            page_outer.pack_forget()
        page_outer, canvas = self._tab_canvases[name]
        page_outer.pack(fill="both", expand=True)
        for btn_name, btn in self._tab_buttons:
            if btn_name == name:
                btn.configure(bg=COLORS["bg_panel"], fg=COLORS["fg_bright"])
            else:
                btn.configure(bg=COLORS["bg"], fg=COLORS["fg_dim"])
        self._active_tab = name

    def _section_header(self, parent, text):
        hdr = tk.Frame(parent, bg=COLORS["border"])
        hdr.pack(fill="x", pady=(10, 6), padx=6)
        tk.Label(hdr, text=f"  {text}", font=FONT_BOLD, fg=COLORS["accent"],
                 bg=COLORS["border"], anchor="w", pady=3).pack(fill="x")

    def _on_frame_change(self, *args):
        on_frame_change(self, *args)

    def _on_section_change(self, *args):
        on_section_change(self, *args)

    def _on_design_input_change(self, *args):
        on_design_input_change(self, *args)

    def _on_roof_type_change(self, *args):
        on_roof_type_change(self, *args)

    def _on_pitch_change(self, *args):
        on_pitch_change(self, *args)

    def _build_geometry(self):
        return build_geometry(self)

    # ── Wind Tab ──

    def _on_eq_toggle(self, *args):
        on_eq_toggle(self, *args)

    def _on_eq_location_change(self, *args):
        on_eq_location_change(self, *args)

    def _on_ductility_change(self, *args):
        on_ductility_change(self, *args)

    def _update_eq_results(self, *args):
        update_eq_results(self, *args)

    def _on_crane_toggle(self, *args):
        on_crane_toggle(self, *args)

    def _on_crane_param_change(self, *args):
        on_crane_param_change(self, *args)

    def _add_crane_hc_row(self, frame, rows_list, prefix, idx):
        add_crane_hc_row(self, frame, rows_list, prefix, idx)

    def _remove_crane_hc_row(self, rows_list):
        remove_crane_hc_row(self, rows_list)

    # ── Helpers ──

    def _get_h_and_depth(self):
        geom = self._build_geometry()
        h = (geom.eave_height + geom.ridge_height) / 2.0
        depth = self.building_depth.get()
        return h, depth

    def _get_wind_params(self):
        """Return current wind parameters for WindSurfacePanel recalculation."""
        try:
            cpi_up = float(self.cpi_uplift_var.get())
        except ValueError:
            cpi_up = 0.2
        try:
            cpi_dn = float(self.cpi_downward_var.get())
        except ValueError:
            cpi_dn = -0.3
        return {
            "qu": self.qu.get(),
            "qs": self.qs.get(),
            "kc_e": self.kc_e.get(),
            "kc_i": self.kc_i.get(),
            "cpi_uplift": cpi_up,
            "cpi_downward": cpi_dn,
        }

    def _on_wind_table_change(self):
        on_wind_table_change(self)

    def _on_wind_case_select(self, case_name):
        on_wind_case_select(self, case_name)

    def _auto_generate_wind_cases(self):
        """Populate the surface table with Cp,e values from NZS 1170.2 lookup."""
        try:
            span = self.span.get()
            eave = self.eave.get()
            pitch = self.pitch.get()
            depth = self.building_depth.get()

            def cpf(key):
                try:
                    return float(self.cp_vars[key].get())
                except ValueError:
                    return 0.0

            geom = self._build_geometry()
            pitch_2 = geom.right_pitch if geom.roof_type == "gable" else None

            surface_data = get_surface_coefficients(
                span=span, eave_height=eave, roof_pitch=pitch,
                building_depth=depth,
                windward_wall_cpe=cpf("cp_ww"),
                roof_type=self.roof_type_var.get(),
                roof_pitch_2=pitch_2,
            )
            h = surface_data["h"]
            d_over_b = surface_data["d_over_b"]
            h_over_d = surface_data["h_over_d"]
            lw_cpe = surface_data["walls"]["leeward_cpe"]

            self.wind_ratios_label.config(
                text=f"h={h:.2f}m  d/b={d_over_b:.3f}  h/d={h_over_d:.3f}  "
                     f"Leeward Cp,e={lw_cpe:.2f}"
            )

            self.wind_table.populate(surface_data)
            self.refresh_load_case_list()
            self._update_preview()

        except Exception as e:
            messagebox.showerror("Wind Generation Error", str(e))

    def _synthesize_wind_cases(self):
        """Synthesize 8 wind cases from the surface table Cp,e values.

        Uses the current geometry and wind parameters to build zone-based
        crosswind cases (W1-W4) and uniform transverse cases (W5-W8).
        Returns list of WindCase objects with Wu pressures (kPa).
        """
        p = self._get_wind_params()
        qu = p["qu"]
        kc_e = p["kc_e"]
        kc_i = p["kc_i"]
        cpi_up = p["cpi_uplift"]
        cpi_dn = p["cpi_downward"]

        sd = self.wind_table.get_surface_data()
        ww_cpe = sd["windward_cpe"]
        lw_cpe = sd["leeward_cpe"]
        side_cpes = sd["side_cpes"]
        roof_up = sd["roof_zones_up"]
        roof_dn = sd["roof_zones_dn"]
        roof_uniform = sd.get("roof_uniform", {})

        side_worst = min(side_cpes) if side_cpes else -0.65

        def wu(cpe, cpi):
            return round(cfig(cpe, cpi, kc_e, kc_i) * qu, 4)

        # Get geometry for zone splitting
        geom = self._build_geometry()
        span = geom.span
        h = (geom.eave_height + geom.ridge_height) / 2.0
        h_over_d = h / span if span > 0 else 0.5
        split_pct = (geom.apex_x / span * 100.0) if span > 0 else 50.0

        # Standard Table 5.3(A) zone lookup (NOT from GUI which may show per-rafter data)
        zone_table = roof_cpe_zones(h_over_d)
        # Transverse uses first zone (0-0.5h) as worst-case — matches reference
        roof_worst_up = zone_table[0][2]
        roof_worst_dn = zone_table[0][3]

        def _build_full_zones(cpi_val, use_uplift):
            """Build full-span RafterZoneLoad list from Table 5.3(A) Cp,e values."""
            zones = []
            for s_mult, e_mult, cpe_up, cpe_dn in zone_table:
                start_m = s_mult * h
                if start_m >= span:
                    break
                end_m = span if e_mult is None else min(e_mult * h, span)
                start_pct = (start_m / span) * 100.0
                end_pct = (end_m / span) * 100.0
                cpe = cpe_up if use_uplift else cpe_dn
                zones.append(RafterZoneLoad(
                    start_pct=round(start_pct, 1),
                    end_pct=round(end_pct, 1),
                    pressure=wu(cpe, cpi_val),
                ))
            return zones

        def _split_zones(full_zones, split_pct):
            """Split full-span zones at the ridge into left/right rafter zones.

            NOTE: Not consolidated with wind_nzs1170_2._split_zones_to_rafters
            which has micro-zone filtering (<0.05%) that would change output.
            """
            left, right = [], []
            for z in full_zones:
                if z.end_pct <= split_pct:
                    # Entirely on left rafter
                    new_start = z.start_pct / split_pct * 100.0
                    new_end = z.end_pct / split_pct * 100.0
                    left.append(RafterZoneLoad(round(new_start, 1),
                                               round(new_end, 1), z.pressure))
                elif z.start_pct >= split_pct:
                    # Entirely on right rafter
                    r_span = 100.0 - split_pct
                    new_start = (z.start_pct - split_pct) / r_span * 100.0
                    new_end = (z.end_pct - split_pct) / r_span * 100.0
                    right.append(RafterZoneLoad(round(new_start, 1),
                                                round(new_end, 1), z.pressure))
                else:
                    # Straddles the ridge — split into two
                    new_end_l = 100.0
                    new_start_l = z.start_pct / split_pct * 100.0
                    left.append(RafterZoneLoad(round(new_start_l, 1),
                                               round(new_end_l, 1), z.pressure))
                    r_span = 100.0 - split_pct
                    new_start_r = 0.0
                    new_end_r = (z.end_pct - split_pct) / r_span * 100.0
                    right.append(RafterZoneLoad(round(new_start_r, 1),
                                                round(new_end_r, 1), z.pressure))
            return left, right

        cases = []
        is_mono = self.roof_type_var.get() == "mono"
        left_pitch = geom.left_pitch if hasattr(geom, 'left_pitch') else geom.roof_pitch
        right_pitch = geom.right_pitch if hasattr(geom, 'right_pitch') else geom.roof_pitch
        roof_type = roof_uniform.get("type", "zones")
        left_uni = roof_uniform.get("left_uniform")
        right_uni = roof_uniform.get("right_uniform")

        # W1-W4: Crosswind (wind across ridge)
        if is_mono and roof_type == "uniform" and left_uni:
            # Mono >= 10 deg: Table 5.3(B) upwind, 5.3(C) downwind — uniform
            for case_num, is_upslope, cpi_val, envelope, desc_env in [
                (1, True,  cpi_up,  "max_uplift",   "max uplift"),
                (2, False, cpi_up,  "max_uplift",   "max uplift"),
                (3, True,  cpi_dn,  "max_downward", "max downward"),
                (4, False, cpi_dn,  "max_downward", "max downward"),
            ]:
                ww_p = wu(ww_cpe, cpi_val)
                lw_p = wu(lw_cpe, cpi_val)
                if is_upslope:
                    left_wall, right_wall = ww_p, lw_p
                    use_uplift = (envelope == "max_uplift")
                    roof_cpe = left_uni[0] if use_uplift else left_uni[1]
                else:
                    left_wall, right_wall = lw_p, ww_p
                    roof_cpe = right_uni[0] if right_uni else left_uni[0]
                roof_p = wu(roof_cpe, cpi_val)
                dir_label = "Upslope" if is_upslope else "Downslope"
                cases.append(WindCase(
                    name=f"W{case_num}",
                    description=f"{dir_label} - {desc_env}",
                    direction=f"crosswind_{'LR' if is_upslope else 'RL'}",
                    envelope=envelope, is_crosswind=False,
                    left_wall=left_wall, right_wall=right_wall,
                    left_rafter=roof_p, right_rafter=0.0,
                ))
        else:
            # Zone-based crosswind (gable or mono < 10 deg)
            for case_num, is_LR, envelope in [
                (1, True,  "max_uplift"),
                (2, False, "max_uplift"),
                (3, True,  "max_downward"),
                (4, False, "max_downward"),
            ]:
                desc_env = "max uplift" if envelope == "max_uplift" else "max downward"
                dir_label = "L-R" if is_LR else "R-L"
                cpi_val = cpi_up if envelope == "max_uplift" else cpi_dn
                use_uplift = (envelope == "max_uplift")

                ww_p = wu(ww_cpe, cpi_val)
                lw_p = wu(lw_cpe, cpi_val)

                if is_LR:
                    left_wall, right_wall = ww_p, lw_p
                else:
                    left_wall, right_wall = lw_p, ww_p

                full_zones = _build_full_zones(cpi_val, use_uplift)

                if is_mono:
                    rafter_zones = full_zones if is_LR else mirror_zones(full_zones)
                    cases.append(WindCase(
                        name=f"W{case_num}",
                        description=f"Crosswind {dir_label} - {desc_env}",
                        direction=f"crosswind_{'LR' if is_LR else 'RL'}",
                        envelope=envelope, is_crosswind=True,
                        left_wall=left_wall, right_wall=right_wall,
                        left_rafter_zones=rafter_zones, right_rafter_zones=[],
                    ))
                else:
                    # Gable: split zones at ridge, then override per-rafter
                    # if that rafter's pitch >= 10 deg
                    if is_LR:
                        l_zones, r_zones = _split_zones(full_zones, split_pct)
                        left_role, right_role = "upwind", "downwind"
                    else:
                        mirrored = mirror_zones(full_zones)
                        l_zones, r_zones = _split_zones(mirrored, split_pct)
                        left_role, right_role = "downwind", "upwind"

                    l_uniform = 0.0
                    r_uniform = 0.0

                    # Override left rafter if pitch >= 10 deg
                    if left_pitch >= 10.0 and left_uni:
                        if left_role == "upwind":
                            cpe = left_uni[0] if use_uplift else left_uni[1]
                        else:
                            # left_uni has (up, dn, downwind) for gable mixed
                            cpe = left_uni[2] if len(left_uni) >= 3 else left_uni[0]
                        l_uniform = wu(cpe, cpi_val)
                        l_zones = []

                    # Override right rafter if pitch >= 10 deg
                    if right_pitch >= 10.0 and right_uni:
                        if right_role == "upwind":
                            cpe = right_uni[0] if use_uplift else right_uni[1]
                        else:
                            cpe = right_uni[2] if len(right_uni) >= 3 else right_uni[0]
                        r_uniform = wu(cpe, cpi_val)
                        r_zones = []

                    has_zones = bool(l_zones or r_zones)
                    cases.append(WindCase(
                        name=f"W{case_num}",
                        description=f"Crosswind {dir_label} - {desc_env}",
                        direction=f"crosswind_{'LR' if is_LR else 'RL'}",
                        envelope=envelope, is_crosswind=has_zones,
                        left_wall=left_wall, right_wall=right_wall,
                        left_rafter_zones=l_zones, right_rafter_zones=r_zones,
                        left_rafter=l_uniform, right_rafter=r_uniform,
                    ))

        # W5-W8: Transverse (wind along ridge — uniform roof pressure)
        for case_num, is_mirrored, envelope in [
            (5, False, "max_uplift"),
            (6, False, "max_downward"),
            (7, True,  "max_uplift"),
            (8, True,  "max_downward"),
        ]:
            desc_env = "max uplift" if envelope == "max_uplift" else "max downward"
            mir_label = " (mirrored)" if is_mirrored else ""
            cpi_val = cpi_up if envelope == "max_uplift" else cpi_dn
            roof_cpe = roof_worst_up if envelope == "max_uplift" else roof_worst_dn

            sw_p = wu(side_worst, cpi_val)
            roof_p = wu(roof_cpe, cpi_val)

            cases.append(WindCase(
                name=f"W{case_num}",
                description=f"Transverse{mir_label} - {desc_env}",
                direction="transverse_mirrored" if is_mirrored else "transverse",
                envelope=envelope,
                is_crosswind=False,
                left_wall=sw_p, right_wall=sw_p,
                left_rafter=roof_p, right_rafter=roof_p,
            ))

        return cases

    def _update_preview(self, *_):
        """Called when inputs change — invalidates stale analysis and redraws.

        Use this from input-change callbacks only. For display-only refresh
        (load case dropdown, diagram selection), call _draw_preview() directly.
        """
        self._invalidate_analysis()
        self._draw_preview()

    def _on_diagram_type_changed(self):
        """Handle diagram type combobox change — notify preview and redraw."""
        dtype = self.diagram_type_var.get()
        # Map combobox values to scale keys used by _diagram_scales
        # "delta" (Unicode δ) maps to "D"; M/V/N pass through unchanged
        scale_key = {"M": "M", "V": "V", "N": "N", "\u03b4": "D"}.get(dtype, dtype)
        self.preview.set_diagram_type(scale_key)
        self._draw_preview()

    def _draw_preview(self, *_):
        """Redraw the preview canvas without touching analysis state.

        Use this for display-only refresh (combo selection). Does not invalidate.
        """
        geom_obj = self._build_geometry()
        geom = {
            "span": geom_obj.span,
            "eave_height": geom_obj.eave_height,
            "roof_pitch": geom_obj.roof_pitch,
            "roof_pitch_2": geom_obj.right_pitch,
            "roof_type": geom_obj.roof_type,
            "apex_x": geom_obj.apex_x,
            "ridge_height": geom_obj.ridge_height,
        }
        if geom_obj.crane_rail_height is not None:
            geom["crane_rail_height"] = geom_obj.crane_rail_height
        supports = (self.left_support.get(), self.right_support.get())
        loads = self._build_preview_loads()

        diagram = None
        if (self._analysis_output is not None and
                hasattr(self, 'diagram_case_var') and
                self.diagram_case_var.get() != "(none)"):
            diagram = self._build_diagram_data()

        self.preview.set_design_checks(self._bucket_design_checks())
        self.preview.set_sls_checks(
            self._analysis_output.sls_checks if self._analysis_output else None
        )
        self.preview.update_frame(geom, supports, loads, diagram)
        self._update_summary()

    def refresh_load_case_list(self):
        if not hasattr(self, 'load_case_combo'):
            return
        choices = ["(none)", "G - Dead Load", "Q - Live Load"]
        try:
            wc_list = self._synthesize_wind_cases()
            for wc in wc_list:
                choices.append(f"{wc.name} - {wc.description}"[:50])
        except Exception:
            pass
        if hasattr(self, 'eq_enabled_var') and self.eq_enabled_var.get():
            choices.append("E+ - Earthquake positive")
            choices.append("E- - Earthquake negative")
        if hasattr(self, 'crane_enabled_var') and self.crane_enabled_var.get():
            choices.append("Gc - Crane Dead")
            choices.append("Qc - Crane Live")
            for _, name_var, _, _ in self.crane_hc_uls_rows:
                choices.append(f"{name_var.get()} - Crane Transverse ULS")
            for _, name_var, _, _ in self.crane_hc_sls_rows:
                choices.append(f"{name_var.get()} - Crane Transverse SLS")
        self.load_case_combo["values"] = choices

    def _build_preview_loads(self) -> dict:
        selected = self.load_case_var.get()
        if selected == "(none)":
            return None

        bay = self.bay.get()
        if bay <= 0:
            return None

        is_mono = self.roof_type_var.get() == "mono"
        members = []

        if selected.startswith("G "):
            w_roof = self.dead_roof.get() * bay
            w_wall = self.dead_wall.get() * bay
            if w_roof > 0:
                rafter_pairs = [(2, 3)] if is_mono else [(2, 3), (3, 4)]
                for nf, nt in rafter_pairs:
                    members.append({"from": nf, "to": nt, "segments": [
                        {"start_pct": 0, "end_pct": 100, "w_kn": w_roof,
                         "direction": "global_y"}]})
            if w_wall > 0:
                col_pairs = [(1, 2), (4, 3)] if is_mono else [(1, 2), (5, 4)]
                for nf, nt in col_pairs:
                    members.append({"from": nf, "to": nt, "segments": [
                        {"start_pct": 0, "end_pct": 100, "w_kn": w_wall,
                         "direction": "global_y"}]})

        elif selected.startswith("Q "):
            w_live = self.live_roof.get() * bay
            if w_live > 0:
                rafter_pairs = [(2, 3)] if is_mono else [(2, 3), (3, 4)]
                for nf, nt in rafter_pairs:
                    members.append({"from": nf, "to": nt, "segments": [
                        {"start_pct": 0, "end_pct": 100, "w_kn": w_live,
                         "direction": "global_y"}]})

        elif selected.startswith("E"):
            try:
                geom_obj = self._build_geometry()
                t1_val = self.eq_T1_override.get() if hasattr(self, 'eq_T1_override') else 0
                eq = EarthquakeInputs(
                    Z=self.eq_Z.get(), soil_class=self.eq_soil.get(),
                    R_uls=self.eq_R_uls.get(), R_sls=self.eq_R_sls.get(),
                    mu=self.eq_mu.get(), Sp=self.eq_Sp.get(),
                    Sp_sls=self.eq_Sp_sls.get(),
                    near_fault=self.eq_near_fault.get(),
                    extra_seismic_mass=self.eq_extra_mass.get(),
                    T1_override=t1_val if t1_val > 0 else 0.0,
                )
                result = calculate_earthquake_forces(
                    geom_obj, self.dead_roof.get(), self.dead_wall.get(), eq,
                )
                F = result["F_node"]
                is_negative = "E-" in selected
                if is_negative:
                    F = -F
                # Point loads at eave/knee nodes
                eave_nodes = [2, 3] if is_mono else [2, 4]
                point_loads = []
                for nid in eave_nodes:
                    point_loads.append({"node": nid, "fx": F, "label": f"E={'−' if is_negative else '+'}"})
                return {"members": [], "point_loads": point_loads}
            except Exception:
                pass

        elif selected.startswith("Gc ") or selected.startswith("Qc "):
            # Crane vertical loads at bracket nodes
            try:
                geom_obj = self._build_geometry()
                h = geom_obj.crane_rail_height
                if h is not None and 0 < h < geom_obj.eave_height:
                    # Bracket nodes: left at (0, h), right at (span, h)
                    # Use node IDs 6 and 7 for bracket nodes in the preview
                    if selected.startswith("Gc"):
                        left_kn = self.crane_gc_left.get()
                        right_kn = self.crane_gc_right.get()
                    else:
                        left_kn = self.crane_qc_left.get()
                        right_kn = self.crane_qc_right.get()
                    point_loads = []
                    if left_kn != 0:
                        point_loads.append({"node": "bracket_left", "fx": 0, "fy": -left_kn})
                    if right_kn != 0:
                        point_loads.append({"node": "bracket_right", "fx": 0, "fy": -right_kn})
                    return {"members": [], "point_loads": point_loads}
            except Exception:
                pass

        elif "Crane Transverse" in selected:
            # Crane horizontal loads at bracket nodes
            try:
                geom_obj = self._build_geometry()
                h = geom_obj.crane_rail_height
                if h is not None and 0 < h < geom_obj.eave_height:
                    case_name = selected.split(" - ")[0].strip()
                    left_kn = 0.0
                    right_kn = 0.0
                    rows = (self.crane_hc_uls_rows if "ULS" in selected
                            else self.crane_hc_sls_rows)
                    for _, name_var, left_var, right_var in rows:
                        if name_var.get() == case_name:
                            try:
                                left_kn = float(left_var.get())
                            except ValueError:
                                left_kn = 0.0
                            try:
                                right_kn = float(right_var.get())
                            except ValueError:
                                right_kn = 0.0
                            break
                    point_loads = []
                    if left_kn != 0:
                        point_loads.append({"node": "bracket_left", "fx": left_kn, "fy": 0})
                    if right_kn != 0:
                        point_loads.append({"node": "bracket_right", "fx": right_kn, "fy": 0})
                    return {"members": [], "point_loads": point_loads}
            except Exception:
                pass

        else:
            wc_name = selected.split(" - ")[0].strip()
            try:
                wc_list = self._synthesize_wind_cases()
            except Exception:
                return None
            wc = None
            for w in wc_list:
                if w.name == wc_name:
                    wc = w
                    break
            if not wc:
                return None

            left_col = (1, 2)
            right_col = (4, 3) if is_mono else (5, 4)

            if wc.left_wall != 0:
                members.append({"from": left_col[0], "to": left_col[1], "segments": [
                    {"start_pct": 0, "end_pct": 100,
                     "w_kn": wc.left_wall * bay,
                     "direction": "global_x"}]})
            if wc.right_wall != 0:
                members.append({"from": right_col[0], "to": right_col[1], "segments": [
                    {"start_pct": 0, "end_pct": 100,
                     "w_kn": -wc.right_wall * bay,
                     "direction": "global_x"}]})

            if is_mono:
                if wc.is_crosswind and wc.left_rafter_zones:
                    segs = []
                    for z in wc.left_rafter_zones:
                        if z.pressure != 0:
                            segs.append({
                                "start_pct": z.start_pct,
                                "end_pct": z.end_pct,
                                "w_kn": z.pressure * bay,
                                "direction": "normal"})
                    if segs:
                        members.append({"from": 2, "to": 3, "segments": segs})
                else:
                    val = wc.left_rafter
                    if val != 0:
                        members.append({"from": 2, "to": 3, "segments": [
                            {"start_pct": 0, "end_pct": 100,
                             "w_kn": val * bay,
                             "direction": "normal"}]})
            else:
                for nf, nt, zones, uni_val in [
                    (2, 3, wc.left_rafter_zones, wc.left_rafter),
                    (3, 4, wc.right_rafter_zones, wc.right_rafter),
                ]:
                    if zones:
                        segs = []
                        for z in zones:
                            if z.pressure != 0:
                                segs.append({
                                    "start_pct": z.start_pct,
                                    "end_pct": z.end_pct,
                                    "w_kn": z.pressure * bay,
                                    "direction": "normal"})
                        if segs:
                            members.append({"from": nf, "to": nt, "segments": segs})
                    elif uni_val != 0:
                        members.append({"from": nf, "to": nt, "segments": [
                            {"start_pct": 0, "end_pct": 100,
                             "w_kn": uni_val * bay,
                             "direction": "normal"}]})

        if not members:
            return None
        return {"members": members}

    def _update_section_info(self, *_):
        lines = []
        for label, name in [("Col", self.col_section.get()),
                             ("Raf", self.raf_section.get())]:
            if name in self.section_library:
                s = self.section_library[name]
                lines.append(
                    f"{label}: A={s.Ax:.0f} mm2  Iy={s.Iy:.0f} mm4  "
                    f"Iz={s.Iz:.0f} mm4  J={s.J:.0f} mm4"
                )
        self.sec_info.config(text="\n".join(lines))

    def _update_summary(self):
        geom = self._build_geometry()
        roof_label = "Gable" if geom.roof_type == "gable" else "Mono"
        ridge = geom.ridge_height
        pitch_info = f"a1={geom.left_pitch:.1f} a2={geom.right_pitch:.1f}" if geom.roof_type == "gable" else f"{geom.roof_pitch:.1f} deg"
        self.summary_label.config(
            text=f"{roof_label}  |  Span: {geom.span:.1f}m  |  Eave: {geom.eave_height:.1f}m  |  "
                 f"Ridge: {ridge:.2f}m  |  {pitch_info}"
        )

    def _build_analysis_request(self):
        """Collect all GUI inputs and return an AnalysisRequest."""
        col_name = self.col_section.get()
        raf_name = self.raf_section.get()

        if not col_name or col_name not in self.section_library:
            raise ValueError("Please select a valid column section.")
        if not raf_name or raf_name not in self.section_library:
            raise ValueError("Please select a valid rafter section.")

        col_sec = self.section_library[col_name]
        raf_sec = self.section_library[raf_name]

        geom = self._build_geometry()

        supports = SupportCondition(
            left_base=self.left_support.get(),
            right_base=self.right_support.get(),
        )

        wind_cases = self._synthesize_wind_cases()

        qu_val = self.qu.get()
        qs_val = self.qs.get()
        ws_factor = qs_val / qu_val if qu_val > 0 else 0.75

        earthquake = None
        if self.eq_enabled_var.get():
            t1_val = self.eq_T1_override.get()
            earthquake = EarthquakeInputs(
                Z=self.eq_Z.get(),
                soil_class=self.eq_soil.get(),
                R_uls=self.eq_R_uls.get(),
                R_sls=self.eq_R_sls.get(),
                mu=self.eq_mu.get(),
                Sp=self.eq_Sp.get(),
                Sp_sls=self.eq_Sp_sls.get(),
                near_fault=self.eq_near_fault.get(),
                extra_seismic_mass=self.eq_extra_mass.get(),
                T1_override=t1_val if t1_val > 0 else 0.0,
            )

        crane_inputs = None
        if self.crane_enabled_var.get():
            from portal_frame.models.crane import CraneTransverseCombo, CraneInputs
            hc_uls = []
            for _, name_var, left_var, right_var in self.crane_hc_uls_rows:
                try:
                    hc_uls.append(CraneTransverseCombo(
                        name=name_var.get(),
                        left=float(left_var.get()),
                        right=float(right_var.get()),
                    ))
                except ValueError:
                    pass
            hc_sls = []
            for _, name_var, left_var, right_var in self.crane_hc_sls_rows:
                try:
                    hc_sls.append(CraneTransverseCombo(
                        name=name_var.get(),
                        left=float(left_var.get()),
                        right=float(right_var.get()),
                    ))
                except ValueError:
                    pass
            crane_inputs = CraneInputs(
                rail_height=self.crane_rail_height.get(),
                dead_left=self.crane_gc_left.get(),
                dead_right=self.crane_gc_right.get(),
                live_left=self.crane_qc_left.get(),
                live_right=self.crane_qc_right.get(),
                transverse_uls=hc_uls,
                transverse_sls=hc_sls,
            )

        loads = LoadInput(
            dead_load_roof=self.dead_roof.get(),
            dead_load_wall=self.dead_wall.get(),
            live_load_roof=self.live_roof.get(),
            wind_cases=wind_cases,
            include_self_weight=self.self_weight_var.get(),
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

    def _generate(self):
        """Collect all inputs and generate the SpaceGass file via solver interface."""
        try:
            request = self._build_analysis_request()
            geom = self._build_geometry()

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
                self.status_label.config(
                    text=f"Saved: {os.path.basename(filepath)}",
                    fg=COLORS["success"]
                )

        except Exception as e:
            messagebox.showerror("Generation Error", str(e))
            self.status_label.config(text=f"Error: {e}", fg=COLORS["error"])

    def _analyse(self):
        """Run PyNite analysis on current inputs."""
        try:
            # Clear any stale results first — if solve fails mid-way, we won't
            # leave old results visible.
            self._invalidate_analysis()
            request = self._build_analysis_request()
            self._analysis_topology = request.topology

            from portal_frame.solvers.pynite_solver import PyNiteSolver
            solver = PyNiteSolver()
            solver.build_model(request)

            self.status_label.config(text="Analysing...", fg=COLORS["warning"])
            self.update_idletasks()

            solver.solve()

            self._analysis_output = solver.output
            self._run_design_checks()
            self._update_results_panel()
            self._update_diagram_dropdowns()
            self._draw_preview()

            self.status_label.config(
                text="Analysis complete", fg=COLORS["success"]
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Analysis Error", str(e))
            self.status_label.config(text=f"Analysis error: {e}", fg=COLORS["error"])

    def _bucket_design_checks(self) -> dict | None:
        """Group design checks into canvas-line buckets for the preview overlay.

        Returns a dict with keys "col_L", "col_R", "raf_L", "raf_R" (mono
        omits "raf_R") whose values are the worst-utilisation
        MemberDesignCheck for each canvas line, or None if no checks exist.

        Crane-bracket sub-members and any other split members are collapsed
        into the parent line via worst-case utilisation.
        """
        out = self._analysis_output
        if out is None or not out.design_checks:
            return None
        topo = self._analysis_topology
        if topo is None:
            return None

        # Resolve span to determine which side each member belongs to
        try:
            span = self.span.get()
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
                # Left rafter: starts at left eave (x≈0), ends at apex (x<span)
                # Right rafter: starts at apex, ends at right eave (x≈span)
                # Mono: single rafter spanning x=0 to x=span -> "raf_L"
                if x_min <= eps and x_max < span - eps:
                    _consider("raf_L", chk)
                elif x_min > eps and x_max >= span - eps:
                    _consider("raf_R", chk)
                else:
                    # Mono full-span rafter, or unusual case — bucket as raf_L
                    _consider("raf_L", chk)

        return groups

    def _run_design_checks(self):
        """Run AS/NZS 4600 capacity checks on the current analysis output.

        Looks up section capacities from the Formsteel span table at the
        user-supplied effective lengths, then writes a list of
        MemberDesignCheck onto self._analysis_output.design_checks.
        """
        out = self._analysis_output
        if out is None or out.uls_envelope_curves is None:
            return
        if self._analysis_topology is None:
            return

        from portal_frame.standards.cfs_check import check_all_members
        from portal_frame.standards.serviceability import (
            check_apex_deflection, check_eave_drift,
        )

        col_name = self.col_section.get()
        raf_name = self.raf_section.get()
        col_sec = self.section_library.get(col_name)
        raf_sec = self.section_library.get(raf_name)
        if col_sec is None or raf_sec is None:
            return

        out.design_checks = check_all_members(
            topology=self._analysis_topology,
            envelope_curves=out.uls_envelope_curves,
            column_section=col_sec,
            rafter_section=raf_sec,
            L_col=self.col_Le.get(),
            L_raf=self.raf_Le.get(),
            combo_results=out.combo_results,
        )

        apex_checks = check_apex_deflection(
            topology=self._analysis_topology,
            combo_results=out.combo_results,
            combo_descriptions=out.combo_descriptions,
            limit_ratio_wind=int(round(self.apex_limit_wind.get())),
            limit_ratio_eq=int(round(self.apex_limit_eq.get())),
        )
        drift_checks = check_eave_drift(
            topology=self._analysis_topology,
            combo_results=out.combo_results,
            combo_descriptions=out.combo_descriptions,
            limit_ratio_wind=int(round(self.drift_limit_wind.get())),
            limit_ratio_eq=int(round(self.drift_limit_eq.get())),
        )
        out.sls_checks = apex_checks + drift_checks

    def _invalidate_analysis(self):
        """Clear stale analysis results when inputs change.

        Called from input change callbacks to prevent the user from mistakenly
        applying outdated analysis results to design.
        """
        self._analysis_output = None
        self._analysis_topology = None
        if hasattr(self, '_results_text'):
            self._results_text.config(state="normal")
            self._results_text.delete("1.0", "end")
            self._results_text.config(state="disabled")
        if hasattr(self, 'diagram_case_var'):
            self.diagram_case_var.set("(none)")
        if hasattr(self, 'diagram_case_combo'):
            self.diagram_case_combo["values"] = ["(none)"]
        if hasattr(self, '_diagram_display_to_name'):
            self._diagram_display_to_name = {"(none)": None}
        # Clear the green "Analysis complete" status message
        if hasattr(self, 'status_label'):
            self.status_label.config(text="", fg=COLORS["fg_dim"])

    def _update_results_panel(self):
        """Display envelope results and design checks in the summary widget."""
        out = self._analysis_output
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
        if int(self._results_text.cget("height")) != new_height:
            self._results_text.config(height=new_height)

        self._results_text.config(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.insert("1.0", "\n".join(lines))

        # Tag FAIL rows red and NO_DATA rows dim
        self._results_text.tag_configure("dc_fail", foreground=COLORS["error"])
        self._results_text.tag_configure("dc_nodata", foreground=COLORS["fg_dim"])
        for ln in fail_lines:
            self._results_text.tag_add("dc_fail", f"{ln+1}.0", f"{ln+1}.end")
        for ln in nodata_lines:
            self._results_text.tag_add("dc_nodata", f"{ln+1}.0", f"{ln+1}.end")

        self._results_text.config(state="disabled")

    def _update_diagram_dropdowns(self):
        """Populate diagram case dropdown with analysis cases and combos.

        Builds human-friendly display strings for combos (e.g., 'ULS-1: 1.35G')
        while maintaining a display_to_name map for reverse lookup.
        """
        out = self._analysis_output
        self._diagram_display_to_name = {"(none)": None}

        if out is None:
            self.diagram_case_combo["values"] = ["(none)"]
            return

        values = ["(none)"]

        # Individual unfactored cases — name only
        for name in sorted(out.case_results.keys()):
            values.append(name)
            self._diagram_display_to_name[name] = name

        # Combinations — "name: description"
        def _combo_sort_key(n):
            # ULS first, then SLS; numeric order within each
            prefix = 0 if n.startswith("ULS") else 1
            try:
                num = int(n.split("-")[1])
            except (IndexError, ValueError):
                num = 0
            return (prefix, num)

        for name in sorted(out.combo_results.keys(), key=_combo_sort_key):
            desc = out.combo_descriptions.get(name, "")
            display = f"{name}: {desc}" if desc else name
            values.append(display)
            self._diagram_display_to_name[display] = name

        # Envelope entries (last in the dropdown)
        if out.uls_envelope_curves is not None:
            values.append("ULS Envelope")
            self._diagram_display_to_name["ULS Envelope"] = "ULS Envelope"
        if out.sls_envelope_curves is not None:
            values.append("SLS Envelope")
            self._diagram_display_to_name["SLS Envelope"] = "SLS Envelope"
        if out.sls_wind_only_envelope_curves is not None:
            values.append("SLS Wind Only Envelope")
            self._diagram_display_to_name["SLS Wind Only Envelope"] = "SLS Wind Only Envelope"

        self.diagram_case_combo["values"] = values

    def _build_diagram_data(self):
        """Build diagram data dict for the preview canvas.

        For normal cases/combos, returns {'data': {mid: [(pct, val), ...]},
        'type': dtype, 'members': {mid: (n1, n2)}}.

        For envelopes, also includes 'data_min' with the min curve.

        For the δ diagram type, also includes 'data_dx' (and 'data_min_dx'
        for envelopes) — per-station dx_local values needed by the renderer
        to reconstruct the global deformation vector and guarantee diagram
        continuity at shared nodes.
        """
        display = self.diagram_case_var.get()
        dtype = self.diagram_type_var.get()
        out = self._analysis_output

        # Translate display string back to actual case/combo name
        name = self._diagram_display_to_name.get(display)
        if name is None:
            return None

        attr = {"M": "moment", "V": "shear", "N": "axial", "δ": "dy_local"}[dtype]

        def _extract(cr, field):
            return {
                mid: [(s.position_pct, getattr(s, field)) for s in mr.stations]
                for mid, mr in cr.members.items()
            }

        # Pass ALL topology node world coords so the preview can resolve
        # non-hardcoded nodes (e.g. crane bracket nodes added by
        # _insert_crane_brackets) when drawing per-member diagrams.
        members_map = {}
        topology_nodes = {}
        if self._analysis_topology:
            members_map = {
                mid: (mem.node_start, mem.node_end)
                for mid, mem in self._analysis_topology.members.items()
            }
            topology_nodes = {
                nid: (node.x, node.y)
                for nid, node in self._analysis_topology.nodes.items()
            }

        base = {
            "type": dtype,
            "members": members_map,
            "topology_nodes": topology_nodes,
        }

        # Envelope selections return both max and min curves
        envelope_curves = None
        if name == "ULS Envelope":
            envelope_curves = out.uls_envelope_curves
        elif name == "SLS Envelope":
            envelope_curves = out.sls_envelope_curves
        elif name == "SLS Wind Only Envelope":
            envelope_curves = out.sls_wind_only_envelope_curves

        if envelope_curves is not None:
            env_max, env_min = envelope_curves
            result = {
                **base,
                "data": _extract(env_max, attr),
                "data_min": _extract(env_min, attr),
                "is_envelope": True,
            }
            if dtype == "δ":
                result["data_dx"] = _extract(env_max, "dx_local")
                result["data_min_dx"] = _extract(env_min, "dx_local")
            return result

        # Normal case/combo lookup
        cr = out.case_results.get(name) or out.combo_results.get(name)
        if cr is None:
            return None

        result = {**base, "data": _extract(cr, attr)}
        if dtype == "δ":
            result["data_dx"] = _extract(cr, "dx_local")
        return result

    # ── Save / Load / Recent ──

    def _collect_config(self) -> dict:
        """Serialize all GUI state to a config dict."""
        cfg = {"version": 1}

        cfg["geometry"] = {
            "span": self.span.get(),
            "eave_height": self.eave.get(),
            "roof_pitch": self.pitch.get(),
            "roof_pitch_2": self.pitch2.get(),
            "bay_spacing": self.bay.get(),
            "roof_type": self.roof_type_var.get(),
            "building_depth": self.building_depth.get(),
        }
        cfg["sections"] = {
            "column": self.col_section.get(),
            "rafter": self.raf_section.get(),
            "col_Le": self.col_Le.get(),
            "raf_Le": self.raf_Le.get(),
        }
        cfg["serviceability"] = {
            "apex_wind_ratio": int(round(self.apex_limit_wind.get())),
            "apex_eq_ratio": int(round(self.apex_limit_eq.get())),
            "drift_wind_ratio": int(round(self.drift_limit_wind.get())),
            "drift_eq_ratio": int(round(self.drift_limit_eq.get())),
        }
        cfg["supports"] = {
            "left_base": self.left_support.get(),
            "right_base": self.right_support.get(),
        }
        cfg["loads"] = {
            "dead_load_roof": self.dead_roof.get(),
            "dead_load_wall": self.dead_wall.get(),
            "live_load_roof": self.live_roof.get(),
            "include_self_weight": self.self_weight_var.get(),
        }
        cfg["wind"] = {
            "qu": self.qu.get(),
            "qs": self.qs.get(),
            "kc_e": self.kc_e.get(),
            "kc_i": self.kc_i.get(),
            "cpi_uplift": float(self.cpi_uplift_var.get()),
            "cpi_downward": float(self.cpi_downward_var.get()),
            "windward_wall_cpe": float(self.cp_vars["cp_ww"].get()),
        }
        cfg["earthquake"] = {
            "enabled": self.eq_enabled_var.get(),
            "location": self.eq_location.get(),
            "Z": self.eq_Z.get(),
            "soil_class": self.eq_soil.get(),
            "ductility": self.eq_ductility.get(),
            "mu": self.eq_mu.get(),
            "Sp": self.eq_Sp.get(),
            "Sp_sls": self.eq_Sp_sls.get(),
            "R_uls": self.eq_R_uls.get(),
            "R_sls": self.eq_R_sls.get(),
            "near_fault": self.eq_near_fault.get(),
            "extra_mass": self.eq_extra_mass.get(),
            "T1_override": self.eq_T1_override.get(),
        }
        cfg["crane"] = {
            "enabled": self.crane_enabled_var.get(),
            "rail_height": self.crane_rail_height.get(),
            "gc_left": self.crane_gc_left.get(),
            "gc_right": self.crane_gc_right.get(),
            "qc_left": self.crane_qc_left.get(),
            "qc_right": self.crane_qc_right.get(),
            "transverse_uls": [],
            "transverse_sls": [],
        }
        for _, nv, lv, rv in self.crane_hc_uls_rows:
            try:
                cfg["crane"]["transverse_uls"].append({
                    "name": nv.get(),
                    "left": float(lv.get()),
                    "right": float(rv.get()),
                })
            except ValueError:
                pass
        for _, nv, lv, rv in self.crane_hc_sls_rows:
            try:
                cfg["crane"]["transverse_sls"].append({
                    "name": nv.get(),
                    "left": float(lv.get()),
                    "right": float(rv.get()),
                })
            except ValueError:
                pass
        return cfg

    def _apply_config(self, cfg: dict):
        """Populate all GUI fields from a config dict."""
        # Geometry — set roof type first (affects pitch2 visibility)
        geo = cfg.get("geometry", {})
        rt = geo.get("roof_type", "gable")
        self.roof_type_var.set(rt)
        self._on_roof_type_change()

        self.span.set(geo.get("span", 12.0))
        self.eave.set(geo.get("eave_height", 4.5))
        self.pitch.set(geo.get("roof_pitch", 5.0))
        self.pitch2.set(geo.get("roof_pitch_2", 5.0))
        self.bay.set(geo.get("bay_spacing", 6.0))
        self.building_depth.set(geo.get("building_depth", 24.0))

        # Sections
        sec = cfg.get("sections", {})
        col = sec.get("column", "63020S2")
        raf = sec.get("rafter", "650180295S2")
        self.col_section.set(col)
        self.raf_section.set(raf)
        self.col_Le.set(sec.get("col_Le", 4.5))
        self.raf_Le.set(sec.get("raf_Le", 6.0))
        self._update_section_info()

        # Serviceability limits
        slsc = cfg.get("serviceability", {})
        self.apex_limit_wind.set(slsc.get("apex_wind_ratio", 180))
        self.apex_limit_eq.set(slsc.get("apex_eq_ratio", 360))
        self.drift_limit_wind.set(slsc.get("drift_wind_ratio", 150))
        self.drift_limit_eq.set(slsc.get("drift_eq_ratio", 300))

        # Supports
        sup = cfg.get("supports", {})
        self.left_support.set(sup.get("left_base", "pinned"))
        self.right_support.set(sup.get("right_base", "pinned"))

        # Loads
        ld = cfg.get("loads", {})
        self.dead_roof.set(ld.get("dead_load_roof", 0.15))
        self.dead_wall.set(ld.get("dead_load_wall", 0.10))
        self.live_roof.set(ld.get("live_load_roof", 0.25))
        self.self_weight_var.set(ld.get("include_self_weight", True))

        # Wind
        w = cfg.get("wind", {})
        self.qu.set(w.get("qu", 1.2))
        self.qs.set(w.get("qs", 0.9))
        self.kc_e.set(w.get("kc_e", 0.8))
        self.kc_i.set(w.get("kc_i", 1.0))
        self.cpi_uplift_var.set(str(w.get("cpi_uplift", 0.2)))
        self.cpi_downward_var.set(str(w.get("cpi_downward", -0.3)))
        self.cp_vars["cp_ww"].set(str(w.get("windward_wall_cpe", 0.7)))

        # Earthquake
        eq = cfg.get("earthquake", {})
        self.eq_enabled_var.set(eq.get("enabled", False))
        # Set location first; trigger the callback so the fault-distance
        # label + Z auto-fill run. We then override Z with the explicit
        # saved value so an engineer's manual Z edits are preserved.
        self.eq_location.set(eq.get("location", "Wellington"))
        self._on_eq_location_change()
        self.eq_Z.set(eq.get("Z", 0.40))
        self.eq_soil.set(eq.get("soil_class", "C"))
        # Same pattern for ductility: set preset, fire auto-fill, then
        # override mu/Sp with the explicit saved values.
        self.eq_ductility.set(eq.get(
            "ductility", "Nominally ductile (mu=1.25, Sp=0.925)"))
        self._on_ductility_change()
        self.eq_mu.set(eq.get("mu", 1.25))
        self.eq_Sp.set(eq.get("Sp", 0.925))
        self.eq_Sp_sls.set(eq.get("Sp_sls", 0.7))
        self.eq_R_uls.set(eq.get("R_uls", 1.0))
        self.eq_R_sls.set(eq.get("R_sls", 0.25))
        self.eq_near_fault.set(eq.get("near_fault", 1.0))
        self.eq_extra_mass.set(eq.get("extra_mass", 0.0))
        self.eq_T1_override.set(eq.get("T1_override", 0.0))
        self._on_eq_toggle()

        # Crane
        cr = cfg.get("crane", {})
        self.crane_enabled_var.set(cr.get("enabled", False))
        self.crane_rail_height.set(cr.get("rail_height", 3.0))
        self.crane_gc_left.set(cr.get("gc_left", 0.0))
        self.crane_gc_right.set(cr.get("gc_right", 0.0))
        self.crane_qc_left.set(cr.get("qc_left", 0.0))
        self.crane_qc_right.set(cr.get("qc_right", 0.0))

        # Clear existing transverse rows and rebuild
        while self.crane_hc_uls_rows:
            self._remove_crane_hc_row(self.crane_hc_uls_rows)
        while self.crane_hc_sls_rows:
            self._remove_crane_hc_row(self.crane_hc_sls_rows)

        for row_data in cr.get("transverse_uls", []):
            self._add_crane_hc_row(
                self.crane_hc_uls_frame, self.crane_hc_uls_rows,
                "Hc", len(self.crane_hc_uls_rows) + 1)
            _, nv, lv, rv = self.crane_hc_uls_rows[-1]
            nv.set(row_data.get("name", ""))
            lv.set(str(row_data.get("left", 0.0)))
            rv.set(str(row_data.get("right", 0.0)))

        for row_data in cr.get("transverse_sls", []):
            self._add_crane_hc_row(
                self.crane_hc_sls_frame, self.crane_hc_sls_rows,
                "Hcs", len(self.crane_hc_sls_rows) + 1)
            _, nv, lv, rv = self.crane_hc_sls_rows[-1]
            nv.set(row_data.get("name", ""))
            lv.set(str(row_data.get("left", 0.0)))
            rv.set(str(row_data.get("right", 0.0)))

        self._on_crane_toggle()

        # Regenerate wind cases and update preview
        self._auto_generate_wind_cases()
        self._update_preview()

    def _save_config(self):
        """Save current configuration to a JSON file."""
        try:
            cfg = self._collect_config()
            filepath = filedialog.asksaveasfilename(
                title="Save Configuration",
                defaultextension=".json",
                filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")],
                initialfile="portal_config.json",
            )
            if filepath:
                with open(filepath, "w") as f:
                    json.dump(cfg, f, indent=2)
                self._add_recent(filepath)
                self.status_label.config(
                    text=f"Config saved: {os.path.basename(filepath)}",
                    fg=COLORS["success"]
                )
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _load_config(self):
        """Load configuration from a JSON file."""
        filepath = filedialog.askopenfilename(
            title="Load Configuration",
            filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")],
        )
        if filepath:
            self._open_recent(filepath)

    def _open_recent(self, path):
        """Load a specific config file by path."""
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
            self._apply_config(cfg)
            self._add_recent(path)
            self.status_label.config(
                text=f"Loaded: {os.path.basename(path)}",
                fg=COLORS["success"]
            )
        except FileNotFoundError:
            messagebox.showerror("Load Error", f"File not found:\n{path}")
            # Remove from recent list if file no longer exists
            recent = self._load_recent_list()
            recent = [p for p in recent if p != path]
            self._save_recent_list(recent)
            self._update_recent_menu()
        except (json.JSONDecodeError, Exception) as e:
            messagebox.showerror("Load Error", str(e))

    def _load_recent_list(self) -> list:
        """Read the recent files list from disk."""
        try:
            with open(self._RECENT_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return []

    def _save_recent_list(self, recent: list):
        """Write the recent files list to disk."""
        try:
            os.makedirs(self._APP_DIR, exist_ok=True)
            with open(self._RECENT_FILE, "w") as f:
                json.dump(recent, f, indent=2)
        except Exception:
            pass

    def _add_recent(self, path):
        """Add a path to the recent list, trim to 10, save, and update menu."""
        path = os.path.abspath(path)
        recent = self._load_recent_list()
        # Remove if already present, then prepend
        recent = [p for p in recent if p != path]
        recent.insert(0, path)
        recent = recent[:10]
        self._save_recent_list(recent)
        self._update_recent_menu()

    def _update_recent_menu(self):
        """Rebuild the Recent dropdown menu from the recent files list."""
        self._recent_menu.delete(0, "end")
        recent = self._load_recent_list()
        if not recent:
            self._recent_menu.add_command(label="(no recent files)", state="disabled")
            return
        for path in recent:
            display = os.path.basename(path)
            self._recent_menu.add_command(
                label=display,
                command=lambda p=path: self._open_recent(p),
            )

    def _on_close(self):
        """Auto-save session state on window close."""
        try:
            cfg = self._collect_config()
            os.makedirs(self._APP_DIR, exist_ok=True)
            with open(self._LAST_SESSION, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
        self.destroy()

    def _auto_restore(self):
        """Restore last session state on startup."""
        try:
            with open(self._LAST_SESSION, "r") as f:
                cfg = json.load(f)
            self._apply_config(cfg)
        except (FileNotFoundError, json.JSONDecodeError, Exception):
            pass
