"""Main application window — tab orchestration and generate flow."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import math
import os

from portal_frame.gui.theme import COLORS, FONT, FONT_BOLD, FONT_TITLE, FONT_SMALL, FONT_MONO
from portal_frame.gui.widgets import LabeledEntry, LabeledCombo
from portal_frame.gui.preview import FramePreview
from portal_frame.gui.dialogs import WindCaseTable

from portal_frame.io.section_library import load_all_sections
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import RafterZoneLoad, WindCase, LoadInput
from portal_frame.models.supports import SupportCondition
from portal_frame.standards.wind_nzs1170_2 import WindCpInputs, generate_standard_wind_cases
from portal_frame.solvers.base import AnalysisRequest
from portal_frame.solvers.spacegass import SpaceGassSolver


class PortalFrameApp(tk.Tk):

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

        # Auto-generate default wind cases
        self._auto_generate_wind_cases()
        self._update_preview()

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

        tab_names = ["Frame", "Wind", "Combos"]
        for name in tab_names:
            self._create_tab_page(name)

        self._build_frame_tab(self._tab_pages["Frame"])
        self._build_wind_tab(self._tab_pages["Wind"])
        self._build_combos_tab(self._tab_pages["Combos"])

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
        self.load_case_combo.bind("<<ComboboxSelected>>", lambda _: self._update_preview())
        self.load_case_combo.bind("<Button-1>", lambda _: self.refresh_load_case_list())

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

    # ── Frame Tab ──

    def _build_frame_tab(self, parent):
        pad = {"padx": 10, "pady": (0, 2)}

        self._section_header(parent, "GEOMETRY")

        # Roof type selector
        roof_type_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        roof_type_frame.pack(fill="x", **pad)

        tk.Label(roof_type_frame, text="Roof Type", font=FONT, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"], width=14, anchor="w").pack(side="left")
        self.roof_type_var = tk.StringVar(value="gable")
        for text, val in [("Gable", "gable"), ("Mono", "mono")]:
            tk.Radiobutton(
                roof_type_frame, text=text, variable=self.roof_type_var,
                value=val, font=FONT, fg=COLORS["fg"],
                bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                activebackground=COLORS["bg_panel"],
                activeforeground=COLORS["fg"],
                command=self._on_roof_type_change,
            ).pack(side="left", padx=(4, 8))

        self.span = LabeledEntry(parent, "Span", 12.0, "m")
        self.span.pack(fill="x", **pad)
        self.span.bind_change(self._update_preview)

        self.eave = LabeledEntry(parent, "Eave Height", 4.5, "m")
        self.eave.pack(fill="x", **pad)
        self.eave.bind_change(self._update_preview)

        self.pitch = LabeledEntry(parent, "Roof Pitch", 5.0, "deg")
        self.pitch.pack(fill="x", **pad)
        self.pitch.bind_change(self._update_preview)

        self.apex_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        self.apex_frame.pack(fill="x", **pad)
        self.apex_position = LabeledEntry(self.apex_frame, "Apex Position", 50.0, "% of span")
        self.apex_position.pack(fill="x")
        self.apex_position.bind_change(self._on_apex_change)

        self.pitch_warning_label = tk.Label(
            parent, text="", font=FONT_SMALL, fg=COLORS["warning"],
            bg=COLORS["bg_panel"], anchor="w", justify="left",
        )
        self.pitch_warning_label.pack(fill="x", padx=10, pady=(0, 2))

        self.bay = LabeledEntry(parent, "Bay Spacing", 6.0, "m")
        self.bay.pack(fill="x", **pad)

        self.building_depth = LabeledEntry(parent, "Building Depth (d)", 24.0, "m")
        self.building_depth.pack(fill="x", **pad)

        self._section_header(parent, "SECTIONS  (from SpaceGass Library)")

        self.col_section = LabeledCombo(
            parent, "Column", values=self.section_names, default="63020S2", width=24
        )
        self.col_section.pack(fill="x", **pad)

        self.raf_section = LabeledCombo(
            parent, "Rafter", values=self.section_names, default="650180295S2", width=24
        )
        self.raf_section.pack(fill="x", **pad)

        self.sec_info = tk.Label(parent, text="", font=FONT_SMALL,
                                 fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                                 anchor="w", justify="left")
        self.sec_info.pack(fill="x", padx=10, pady=(0, 4))

        self.col_section.bind_change(self._update_section_info)
        self.raf_section.bind_change(self._update_section_info)
        self._update_section_info()

        self._section_header(parent, "SUPPORTS")

        sup_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        sup_frame.pack(fill="x", **pad)

        tk.Label(sup_frame, text="Left Base", font=FONT, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"]).grid(row=0, column=0, sticky="w")
        self.left_support = tk.StringVar(value="pinned")
        tk.Radiobutton(sup_frame, text="Pinned", variable=self.left_support,
                        value="pinned", font=FONT, fg=COLORS["fg"],
                        bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                        activebackground=COLORS["bg_panel"],
                        activeforeground=COLORS["fg"],
                        command=self._update_preview
                        ).grid(row=0, column=1, padx=(10, 4))
        tk.Radiobutton(sup_frame, text="Fixed", variable=self.left_support,
                        value="fixed", font=FONT, fg=COLORS["fg"],
                        bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                        activebackground=COLORS["bg_panel"],
                        activeforeground=COLORS["fg"],
                        command=self._update_preview
                        ).grid(row=0, column=2)

        tk.Label(sup_frame, text="Right Base", font=FONT, fg=COLORS["fg"],
                 bg=COLORS["bg_panel"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.right_support = tk.StringVar(value="pinned")
        tk.Radiobutton(sup_frame, text="Pinned", variable=self.right_support,
                        value="pinned", font=FONT, fg=COLORS["fg"],
                        bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                        activebackground=COLORS["bg_panel"],
                        activeforeground=COLORS["fg"],
                        command=self._update_preview
                        ).grid(row=1, column=1, padx=(10, 4), pady=(4, 0))
        tk.Radiobutton(sup_frame, text="Fixed", variable=self.right_support,
                        value="fixed", font=FONT, fg=COLORS["fg"],
                        bg=COLORS["bg_panel"], selectcolor=COLORS["bg_input"],
                        activebackground=COLORS["bg_panel"],
                        activeforeground=COLORS["fg"],
                        command=self._update_preview
                        ).grid(row=1, column=2, pady=(4, 0))

        self._section_header(parent, "LOADS  (unfactored, kPa)")

        self.dead_roof = LabeledEntry(parent, "Dead Load - Roof (SDL)", 0.15, "kPa")
        self.dead_roof.pack(fill="x", **pad)

        self.dead_wall = LabeledEntry(parent, "Dead Load - Wall", 0.10, "kPa")
        self.dead_wall.pack(fill="x", **pad)

        self.live_roof = LabeledEntry(parent, "Live Load - Roof (Q)", 0.25, "kPa")
        self.live_roof.pack(fill="x", **pad)

        self.self_weight_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            parent, text="Include self-weight in Dead Load case",
            variable=self.self_weight_var, font=FONT,
            fg=COLORS["fg"], bg=COLORS["bg_panel"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["fg"]
        ).pack(fill="x", padx=10, pady=(0, 4))

    def _on_roof_type_change(self, *_):
        if self.roof_type_var.get() == "mono":
            self.apex_frame.pack_forget()
            self.pitch_warning_label.pack_forget()
        else:
            # Show apex frame and warning label
            self.apex_frame.pack(fill="x", padx=10, pady=(0, 2))
            self.pitch_warning_label.pack(fill="x", padx=10, pady=(0, 2))
        self._check_pitch_warnings()
        self._update_preview()

    def _on_apex_change(self, *_):
        self._check_pitch_warnings()
        self._update_preview()

    def _check_pitch_warnings(self):
        from portal_frame.models.validation import validate_geometry_pitch
        geom = self._build_geometry()
        warnings = validate_geometry_pitch(geom)
        if warnings:
            self.pitch_warning_label.config(text="\n".join(warnings))
        else:
            self.pitch_warning_label.config(text="")

    def _build_geometry(self) -> PortalFrameGeometry:
        return PortalFrameGeometry(
            span=self.span.get(),
            eave_height=self.eave.get(),
            roof_pitch=self.pitch.get(),
            bay_spacing=self.bay.get(),
            roof_type=self.roof_type_var.get(),
            apex_position_pct=self.apex_position.get() if self.roof_type_var.get() == "gable" else 50.0,
        )

    # ── Wind Tab ──

    def _build_wind_tab(self, parent):
        pad = {"padx": 10, "pady": (0, 2)}

        self._section_header(parent, "WIND PARAMETERS  (NZS 1170.2:2021)")

        wind_param_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        wind_param_frame.pack(fill="x", padx=10, pady=(0, 4))

        self.qu = LabeledEntry(wind_param_frame, "qu (ULS pressure)", 1.2, "kPa", width=6)
        self.qu.pack(fill="x", pady=(0, 2))

        self.qs = LabeledEntry(wind_param_frame, "qs (SLS pressure)", 0.9, "kPa", width=6)
        self.qs.pack(fill="x", pady=(0, 2))

        self.kc_e = LabeledEntry(wind_param_frame, "Kc,e (external)", 0.8, "", width=6)
        self.kc_e.pack(fill="x", pady=(0, 2))

        self.kc_i = LabeledEntry(wind_param_frame, "Kc,i (internal)", 1.0, "", width=6)
        self.kc_i.pack(fill="x", pady=(0, 2))

        tk.Label(wind_param_frame, text="Cp,i  (internal pressure - Table 5.1)",
                 font=FONT_BOLD, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                 anchor="w").pack(fill="x", pady=(4, 2))

        cpi_grid = tk.Frame(wind_param_frame, bg=COLORS["bg_panel"])
        cpi_grid.pack(fill="x", pady=(0, 4))

        self.cpi_uplift_var = tk.StringVar(value="0.2")
        self.cpi_downward_var = tk.StringVar(value="-0.3")

        for i, (label, var) in enumerate([
            ("Cp,i (max uplift)", self.cpi_uplift_var),
            ("Cp,i (max downward)", self.cpi_downward_var),
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

        self.cp_vars = {}
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
            self.cp_vars[key] = var

        tk.Label(wind_param_frame,
                 text="Leeward Cp,e from Table 5.2(B) by d/b ratio\n"
                      "Roof zones from Table 5.3(A) by h/d ratio\n"
                      "Side wall zones from Table 5.2(C)",
                 font=FONT_SMALL, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
                 anchor="w", justify="left").pack(fill="x", pady=(2, 4))

        tk.Button(
            wind_param_frame, text="  AUTO GENERATE 8 CASES  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg="#2d7d46",
            activebackground="#3a9d5a", activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=12, pady=4,
            command=self._auto_generate_wind_cases
        ).pack(fill="x", pady=(6, 4))

        self._section_header(parent, "WIND LOAD CASES  (net pressure kPa: +ve = into surface)")

        self.wind_table = WindCaseTable(parent, get_geometry_fn=self._get_h_and_depth)
        self.wind_table.pack(fill="x", padx=10, pady=(0, 8))

    # ── Combos Tab ──

    def _build_combos_tab(self, parent):
        self._section_header(parent, "LOAD COMBINATIONS  (AS/NZS 1170.0:2002)")

        combo_text = (
            "ULS-1: 1.35G              (101+)\n"
            "ULS-2: 1.2G + 1.5Q\n"
            "ULS-n: 1.2G + Wu  (per wind case)\n"
            "ULS-n: 0.9G + Wu  (per wind case)\n"
            "SLS-1: G + 0.7Q           (201+)\n"
            "SLS-2: G\n"
            "SLS-n: G + Ws  (per wind case)\n\n"
            "Table 4.1 roof factors: psi_s=0.7, psi_l=0.0, psi_c=0.0"
        )
        tk.Label(parent, text=combo_text, font=FONT_MONO, fg=COLORS["fg_dim"],
                 bg=COLORS["bg_panel"], anchor="w", justify="left"
                 ).pack(fill="x", padx=10, pady=(0, 12))

    # ── Helpers ──

    def _get_h_and_depth(self):
        eave = self.eave.get()
        span = self.span.get()
        pitch = self.pitch.get()
        ridge = eave + (span / 2) * math.tan(math.radians(pitch)) if pitch else eave
        h = (eave + ridge) / 2.0
        depth = self.building_depth.get()
        return h, depth

    def _auto_generate_wind_cases(self):
        try:
            qu_val = self.qu.get()
            qs_val = self.qs.get()
            kc_e_val = self.kc_e.get()
            kc_i_val = self.kc_i.get()
            if qu_val <= 0 or kc_e_val <= 0:
                messagebox.showwarning("Warning", "qu and Kc,e must be positive.")
                return

            def cpf(key):
                try:
                    return float(self.cp_vars[key].get())
                except ValueError:
                    return 0.0

            try:
                cpi_up = float(self.cpi_uplift_var.get())
            except ValueError:
                cpi_up = 0.2
            try:
                cpi_dn = float(self.cpi_downward_var.get())
            except ValueError:
                cpi_dn = -0.3

            cp = WindCpInputs(
                qu=qu_val, qs=qs_val,
                kc_e=kc_e_val, kc_i=kc_i_val,
                cpi_uplift=cpi_up, cpi_downward=cpi_dn,
                windward_wall_cpe=cpf("cp_ww"),
            )

            span = self.span.get()
            eave = self.eave.get()
            pitch = self.pitch.get()
            depth = self.building_depth.get()

            split_pct = self.apex_position.get() if self.roof_type_var.get() == "gable" else 50.0
            cases = generate_standard_wind_cases(
                span=span, eave_height=eave, roof_pitch=pitch,
                building_depth=depth, cp=cp, split_pct=split_pct,
            )

            while self.wind_table.rows:
                self.wind_table.remove_row()

            for wc in cases:
                if wc.is_crosswind and (wc.left_rafter_zones or wc.right_rafter_zones):
                    self.wind_table.add_crosswind_row(
                        name=wc.name, desc=wc.description,
                        left_wall=str(wc.left_wall),
                        right_wall=str(wc.right_wall),
                        zones=wc.left_rafter_zones,
                        right_zones=wc.right_rafter_zones,
                    )
                else:
                    self.wind_table.add_row([
                        wc.name, wc.description,
                        str(wc.left_wall), str(wc.right_wall),
                        str(wc.left_rafter), str(wc.right_rafter),
                    ])

            self.refresh_load_case_list()
            self._update_preview()

        except Exception as e:
            messagebox.showerror("Wind Generation Error", str(e))

    def _update_preview(self, *_):
        geom = {
            "span": self.span.get(),
            "eave_height": self.eave.get(),
            "roof_pitch": self.pitch.get(),
            "roof_type": self.roof_type_var.get(),
            "apex_position_pct": self.apex_position.get(),
        }
        supports = (self.left_support.get(), self.right_support.get())
        loads = self._build_preview_loads()
        self.preview.update_frame(geom, supports, loads)
        self._update_summary()

    def refresh_load_case_list(self):
        choices = ["(none)", "G - Dead Load", "Q - Live Load"]
        wc_list = self.wind_table.get_wind_cases()
        for wc in wc_list:
            choices.append(f"{wc['name']} - {wc.get('description', '')}"[:50])
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

        else:
            wc_name = selected.split(" - ")[0].strip()
            wc_list = self.wind_table.get_wind_cases()
            wc = None
            for w in wc_list:
                if w["name"] == wc_name:
                    wc = w
                    break
            if not wc:
                return None

            left_col = (1, 2)
            right_col = (4, 3) if is_mono else (5, 4)

            if wc.get("left_wall", 0) != 0:
                members.append({"from": left_col[0], "to": left_col[1], "segments": [
                    {"start_pct": 0, "end_pct": 100,
                     "w_kn": wc["left_wall"] * bay,
                     "direction": "global_x"}]})
            if wc.get("right_wall", 0) != 0:
                members.append({"from": right_col[0], "to": right_col[1], "segments": [
                    {"start_pct": 0, "end_pct": 100,
                     "w_kn": -wc["right_wall"] * bay,
                     "direction": "global_x"}]})

            if is_mono:
                # Single rafter for mono roof
                val = wc.get("left_rafter", 0)
                if val != 0:
                    members.append({"from": 2, "to": 3, "segments": [
                        {"start_pct": 0, "end_pct": 100,
                         "w_kn": val * bay,
                         "direction": "normal"}]})
            elif wc.get("is_crosswind") and wc.get("left_rafter_zones"):
                for nf, nt, zone_key in [(2, 3, "left_rafter_zones"),
                                          (3, 4, "right_rafter_zones")]:
                    segs = []
                    for z in wc.get(zone_key, []):
                        if z["pressure"] != 0:
                            segs.append({
                                "start_pct": z["start_pct"],
                                "end_pct": z["end_pct"],
                                "w_kn": z["pressure"] * bay,
                                "direction": "normal"})
                    if segs:
                        members.append({"from": nf, "to": nt, "segments": segs})
            else:
                for nf, nt, key in [(2, 3, "left_rafter"),
                                     (3, 4, "right_rafter")]:
                    val = wc.get(key, 0)
                    if val != 0:
                        members.append({"from": nf, "to": nt, "segments": [
                            {"start_pct": 0, "end_pct": 100,
                             "w_kn": val * bay,
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
        apex_info = ""
        if geom.roof_type == "gable" and geom.apex_position_pct != 50.0:
            apex_info = f"  |  Apex: {geom.apex_position_pct:.0f}%"
        self.summary_label.config(
            text=f"{roof_label}  |  Span: {geom.span:.1f}m  |  Eave: {geom.eave_height:.1f}m  |  "
                 f"Ridge: {ridge:.2f}m  |  Pitch: {geom.roof_pitch:.1f} deg{apex_info}"
        )

    def _generate(self):
        """Collect all inputs and generate the SpaceGass file via solver interface."""
        try:
            col_name = self.col_section.get()
            raf_name = self.raf_section.get()

            if not col_name or col_name not in self.section_library:
                messagebox.showerror("Error", "Please select a valid column section.")
                return
            if not raf_name or raf_name not in self.section_library:
                messagebox.showerror("Error", "Please select a valid rafter section.")
                return

            col_sec = self.section_library[col_name]
            raf_sec = self.section_library[raf_name]

            geom = self._build_geometry()

            supports = SupportCondition(
                left_base=self.left_support.get(),
                right_base=self.right_support.get(),
            )

            wind_dicts = self.wind_table.get_wind_cases()
            wind_cases = []
            for wc_dict in wind_dicts:
                zones_left = [RafterZoneLoad(**z) for z in wc_dict.pop("left_rafter_zones", [])]
                zones_right = [RafterZoneLoad(**z) for z in wc_dict.pop("right_rafter_zones", [])]
                wind_cases.append(WindCase(
                    **wc_dict,
                    left_rafter_zones=zones_left,
                    right_rafter_zones=zones_right,
                ))

            qu_val = self.qu.get()
            qs_val = self.qs.get()
            ws_factor = qs_val / qu_val if qu_val > 0 else 0.75

            loads = LoadInput(
                dead_load_roof=self.dead_roof.get(),
                dead_load_wall=self.dead_wall.get(),
                live_load_roof=self.live_roof.get(),
                wind_cases=wind_cases,
                include_self_weight=self.self_weight_var.get(),
                ws_factor=ws_factor,
            )

            topology = geom.to_topology()

            request = AnalysisRequest(
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
