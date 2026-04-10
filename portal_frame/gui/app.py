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

from portal_frame.io.section_library import load_all_sections
from portal_frame.models.geometry import PortalFrameGeometry
from portal_frame.models.loads import RafterZoneLoad, WindCase, LoadInput, EarthquakeInputs
from portal_frame.standards.earthquake_nzs1170_5 import (
    NZ_HAZARD_FACTORS, calculate_earthquake_forces,
)
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

        self._build_frame_tab(self._tab_pages["Frame"])
        self._build_wind_tab(self._tab_pages["Wind"])
        self._build_earthquake_tab(self._tab_pages["Earthquake"])
        self._build_crane_tab(self._tab_pages["Crane"])
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
                                      lambda _: self._draw_preview())

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
        self.span.bind_change(self._on_frame_change)

        self.eave = LabeledEntry(parent, "Eave Height", 4.5, "m")
        self.eave.pack(fill="x", **pad)
        self.eave.bind_change(self._on_frame_change)

        self.pitch = LabeledEntry(parent, "Roof Pitch 1 (a1)", 5.0, "deg")
        self.pitch.pack(fill="x", **pad)
        self.pitch.bind_change(self._on_pitch_change)

        self.pitch2_frame = tk.Frame(parent, bg=COLORS["bg_panel"])
        self.pitch2_frame.pack(fill="x", **pad)
        self.pitch2 = LabeledEntry(self.pitch2_frame, "Roof Pitch 2 (a2)", 5.0, "deg")
        self.pitch2.pack(fill="x")
        self.pitch2.bind_change(self._on_pitch_change)

        self.pitch_warning_label = tk.Label(
            parent, text="", font=FONT_SMALL, fg=COLORS["warning"],
            bg=COLORS["bg_panel"], anchor="w", justify="left",
        )
        self.pitch_warning_label.pack(fill="x", padx=10, pady=(0, 2))

        self.bay = LabeledEntry(parent, "Bay Spacing", 6.0, "m")
        self.bay.pack(fill="x", **pad)
        self.bay.bind_change(self._on_frame_change)

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

        self.col_section.bind_change(self._on_section_change)
        self.raf_section.bind_change(self._on_section_change)
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
        self.dead_roof.bind_change(self._on_frame_change)

        self.dead_wall = LabeledEntry(parent, "Dead Load - Wall", 0.10, "kPa")
        self.dead_wall.pack(fill="x", **pad)
        self.dead_wall.bind_change(self._on_frame_change)

        self.live_roof = LabeledEntry(parent, "Live Load - Roof (Q)", 0.25, "kPa")
        self.live_roof.pack(fill="x", **pad)
        self.live_roof.bind_change(self._on_frame_change)

        self.self_weight_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            parent, text="Include self-weight in Dead Load case",
            variable=self.self_weight_var, font=FONT,
            fg=COLORS["fg"], bg=COLORS["bg_panel"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["fg"],
            command=self._on_frame_change
        ).pack(fill="x", padx=10, pady=(0, 4))

    def _on_frame_change(self, *_):
        """Geometry or dead load changed — update preview and EQ results."""
        self._update_preview()
        self._update_eq_results()

    def _on_section_change(self, *_):
        """Section selection changed — update info display and EQ results."""
        self._invalidate_analysis()
        self._update_section_info()
        self._update_eq_results()

    def _on_roof_type_change(self, *_):
        if self.roof_type_var.get() == "mono":
            self.pitch2_frame.pack_forget()
            self.pitch_warning_label.pack_forget()
        else:
            # Re-pack after pitch1 widget to maintain correct order
            self.pitch2_frame.pack(fill="x", padx=10, pady=(0, 2), after=self.pitch)
            self.pitch_warning_label.pack(fill="x", padx=10, pady=(0, 2), after=self.pitch2_frame)
        self._check_pitch_warnings()
        self._update_preview()
        self._update_eq_results()

    def _on_pitch_change(self, *_):
        self._check_pitch_warnings()
        self._update_preview()
        self._update_eq_results()

    def _check_pitch_warnings(self):
        from portal_frame.models.validation import validate_geometry_pitch
        geom = self._build_geometry()
        warnings = validate_geometry_pitch(geom)
        if warnings:
            self.pitch_warning_label.config(text="\n".join(warnings))
        else:
            self.pitch_warning_label.config(text="")

    def _build_geometry(self) -> PortalFrameGeometry:
        crane_rail_height = None
        if hasattr(self, 'crane_enabled_var') and self.crane_enabled_var.get():
            crane_rail_height = self.crane_rail_height.get()

        if self.roof_type_var.get() == "mono":
            return PortalFrameGeometry(
                span=self.span.get(),
                eave_height=self.eave.get(),
                roof_pitch=self.pitch.get(),
                bay_spacing=self.bay.get(),
                roof_type="mono",
                crane_rail_height=crane_rail_height,
            )
        return PortalFrameGeometry(
            span=self.span.get(),
            eave_height=self.eave.get(),
            roof_pitch=self.pitch.get(),
            bay_spacing=self.bay.get(),
            roof_type="gable",
            roof_pitch_2=self.pitch2.get(),
            crane_rail_height=crane_rail_height,
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

        self.wind_ratios_label = tk.Label(
            wind_param_frame, text="", font=FONT_MONO,
            fg=COLORS["fg"], bg=COLORS["bg_panel"],
            anchor="w", justify="left",
        )
        self.wind_ratios_label.pack(fill="x", pady=(0, 4))

        tk.Button(
            wind_param_frame, text="  AUTO GENERATE 8 CASES  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg="#2d7d46",
            activebackground="#3a9d5a", activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=12, pady=4,
            command=self._auto_generate_wind_cases
        ).pack(fill="x", pady=(6, 4))

        self._section_header(parent, "WIND COEFFICIENTS  (Cp,e per surface)")

        self.wind_table = WindSurfacePanel(
            parent,
            get_geometry_fn=self._get_h_and_depth,
            get_wind_params_fn=self._get_wind_params,
            on_change_fn=self._on_wind_table_change,
            on_case_select_fn=self._on_wind_case_select,
        )
        self.wind_table.pack(fill="x", padx=10, pady=(0, 8))

        # Trace wind params so pe/pnet update when qu/kc/cpi change
        def _trigger_recalc():
            self.wind_table._schedule_recalc()
        for widget in [self.qu, self.qs, self.kc_e, self.kc_i]:
            widget.bind_change(_trigger_recalc)
        self.cpi_uplift_var.trace_add("write", lambda *_: _trigger_recalc())
        self.cpi_downward_var.trace_add("write", lambda *_: _trigger_recalc())

    # ── Earthquake Tab ──

    def _build_earthquake_tab(self, parent):
        pad = {"padx": 10, "pady": (0, 2)}

        self._section_header(parent, "EARTHQUAKE  (NZS 1170.5:2004)")

        self.eq_enabled_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parent, text="Include earthquake loading",
            variable=self.eq_enabled_var, font=FONT_BOLD,
            fg=COLORS["fg"], bg=COLORS["bg_panel"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["fg"],
            command=self._on_eq_toggle,
        ).pack(fill="x", padx=10, pady=(0, 6))

        self.eq_content = tk.Frame(parent, bg=COLORS["bg_panel"])
        # Initially hidden — shown on toggle

        self._section_header(self.eq_content, "SEISMIC HAZARD")
        locations = sorted(NZ_HAZARD_FACTORS.keys())
        self.eq_location = LabeledCombo(
            self.eq_content, "Location", values=locations, default="Wellington", width=20,
        )
        self.eq_location.pack(fill="x", **pad)
        self.eq_location.bind_change(self._on_eq_location_change)

        self.eq_Z = LabeledEntry(self.eq_content, "Z (hazard factor)", 0.40, "")
        self.eq_Z.pack(fill="x", **pad)
        self.eq_Z.bind_change(self._update_eq_results)

        self.eq_soil = LabeledCombo(
            self.eq_content, "Soil Class", values=["A", "B", "C", "D", "E"],
            default="C", width=6,
        )
        self.eq_soil.pack(fill="x", **pad)
        self.eq_soil.bind_change(self._update_eq_results)

        self._section_header(self.eq_content, "DUCTILITY & IMPORTANCE")

        duct_presets = [
            "Nominally ductile (mu=1.25, Sp=0.925)",
            "Limited ductile (mu=2.0, Sp=0.7)",
            "Ductile (mu=4.0, Sp=0.7)",
            "Elastic (mu=1.0, Sp=1.0)",
            "Custom",
        ]
        self.eq_ductility = LabeledCombo(
            self.eq_content, "Ductility Preset", values=duct_presets,
            default=duct_presets[0], width=36,
        )
        self.eq_ductility.pack(fill="x", **pad)
        self.eq_ductility.bind_change(self._on_ductility_change)

        self.eq_mu = LabeledEntry(self.eq_content, "mu (ductility)", 1.25, "")
        self.eq_mu.pack(fill="x", **pad)
        self.eq_mu.bind_change(self._update_eq_results)

        self.eq_Sp = LabeledEntry(self.eq_content, "Sp ULS (structural perf.)", 0.925, "")
        self.eq_Sp.pack(fill="x", **pad)
        self.eq_Sp.bind_change(self._update_eq_results)

        self.eq_Sp_sls = LabeledEntry(self.eq_content, "Sp SLS (Cl 4.4.4)", 0.7, "")
        self.eq_Sp_sls.pack(fill="x", **pad)
        self.eq_Sp_sls.bind_change(self._update_eq_results)

        self.eq_R_uls = LabeledEntry(self.eq_content, "R (ULS return period)", 1.0, "")
        self.eq_R_uls.pack(fill="x", **pad)
        self.eq_R_uls.bind_change(self._update_eq_results)

        self.eq_R_sls = LabeledEntry(self.eq_content, "R (SLS return period)", 0.25, "")
        self.eq_R_sls.pack(fill="x", **pad)
        self.eq_R_sls.bind_change(self._update_eq_results)

        self.eq_near_fault = LabeledEntry(self.eq_content, "N(T,D) near-fault", 1.0, "")
        self.eq_near_fault.pack(fill="x", **pad)
        self.eq_near_fault.bind_change(self._update_eq_results)

        self.eq_extra_mass = LabeledEntry(self.eq_content, "Extra seismic mass", 0.0, "kN")
        self.eq_extra_mass.pack(fill="x", **pad)
        self.eq_extra_mass.bind_change(self._update_eq_results)

        self.eq_T1_override = LabeledEntry(self.eq_content, "T1 override (0=auto)", 0.0, "s")
        self.eq_T1_override.pack(fill="x", **pad)
        self.eq_T1_override.bind_change(self._update_eq_results)

        self._section_header(self.eq_content, "CALCULATED VALUES")

        self.eq_results_label = tk.Label(
            self.eq_content, text="(enable earthquake loading to see results)",
            font=FONT_MONO, fg=COLORS["fg_dim"], bg=COLORS["bg_panel"],
            anchor="w", justify="left",
        )
        self.eq_results_label.pack(fill="x", padx=10, pady=(0, 8))

    def _on_eq_toggle(self, *_):
        if self.eq_enabled_var.get():
            self.eq_content.pack(fill="x")
            self._update_eq_results()
        else:
            self.eq_content.pack_forget()
        self.refresh_load_case_list()

    def _on_eq_location_change(self, *_):
        loc = self.eq_location.get()
        if loc in NZ_HAZARD_FACTORS:
            self.eq_Z.set(NZ_HAZARD_FACTORS[loc])
        self._update_eq_results()

    def _on_ductility_change(self, *_):
        preset = self.eq_ductility.get()
        if "Nominally" in preset:
            self.eq_mu.set(1.25); self.eq_Sp.set(0.925)
        elif "Limited" in preset:
            self.eq_mu.set(2.0); self.eq_Sp.set(0.7)
        elif preset.startswith("Ductile"):
            self.eq_mu.set(4.0); self.eq_Sp.set(0.7)
        elif "Elastic" in preset:
            self.eq_mu.set(1.0); self.eq_Sp.set(1.0)
        self._update_eq_results()

    def _estimate_member_self_weight(self, geom) -> float:
        """Estimate steel self-weight tributary to knee level (kN).

        Only the top half of columns and full rafters contribute to
        the seismic mass lumped at the knee nodes.
        """
        STEEL_DENSITY = 7850  # kg/m3
        G = 9.81 / 1000  # kN per kg

        col_name = self.col_section.get()
        raf_name = self.raf_section.get()
        col_ax = 0.0  # m2
        raf_ax = 0.0
        if col_name in self.section_library:
            col_ax = self.section_library[col_name].Ax * 1e-6
        if raf_name in self.section_library:
            raf_ax = self.section_library[raf_name].Ax * 1e-6

        # Top half of columns only (bottom half goes to foundation)
        left_col_len = geom.eave_height / 2.0
        if geom.roof_type == "mono":
            right_col_len = geom.ridge_height / 2.0
        else:
            right_col_len = geom.eave_height / 2.0

        # Full rafter length
        rise = geom.ridge_height - geom.eave_height
        if geom.roof_type == "mono":
            raf_len = math.hypot(geom.span, rise)
        else:
            left_run = geom.apex_x
            right_run = geom.span - geom.apex_x
            raf_len = math.hypot(left_run, rise) + math.hypot(right_run, rise)

        col_wt = col_ax * (left_col_len + right_col_len) * STEEL_DENSITY * G
        raf_wt = raf_ax * raf_len * STEEL_DENSITY * G
        return col_wt + raf_wt

    def _update_eq_results(self, *_):
        self._invalidate_analysis()
        if not self.eq_enabled_var.get():
            return
        try:
            geom = self._build_geometry()
            sw_kn = self._estimate_member_self_weight(geom)

            t1_val = self.eq_T1_override.get()
            eq = EarthquakeInputs(
                Z=self.eq_Z.get(),
                soil_class=self.eq_soil.get(),
                R_uls=self.eq_R_uls.get(),
                R_sls=self.eq_R_sls.get(),
                mu=self.eq_mu.get(),
                Sp=self.eq_Sp.get(),
                Sp_sls=self.eq_Sp_sls.get(),
                near_fault=self.eq_near_fault.get(),
                extra_seismic_mass=self.eq_extra_mass.get() + sw_kn,
                T1_override=t1_val if t1_val > 0 else 0.0,
            )
            result = calculate_earthquake_forces(
                geom, self.dead_roof.get(), self.dead_wall.get(), eq,
            )
            t1_val = self.eq_T1_override.get()
            t1_label = f"T1 = {result['T1']:.3f} s"
            if t1_val > 0:
                t1_label += " (user override)"
            else:
                t1_label += " (auto)"
            text = (
                f"{t1_label}\n"
                f"Ch(T1) = {result['Ch']:.3f}\n"
                f"k_mu = {result['k_mu']:.3f}\n"
                f"Cd(T1) ULS = {result['Cd_uls']:.4f}\n"
                f"Cd(T1) SLS = {result['Cd_sls']:.4f}\n"
                f"Wt = {result['Wt']:.2f} kN  "
                f"(SDL={result['Wt'] - eq.extra_seismic_mass:.2f} "
                f"+ SW={sw_kn:.2f} "
                f"+ extra={self.eq_extra_mass.get():.2f})\n"
                f"V_uls = {result['V_uls']:.2f} kN\n"
                f"V_sls = {result['V_sls']:.2f} kN\n"
                f"F_node ULS = {result['F_node']:.2f} kN (per knee)\n"
                f"F_node SLS = {result['F_node_sls']:.2f} kN (per knee)"
            )
            # Show crane seismic contribution if crane is enabled
            if hasattr(self, 'crane_enabled_var') and self.crane_enabled_var.get():
                gc_total = self.crane_gc_left.get() + self.crane_gc_right.get()
                qc_total = self.crane_qc_left.get() + self.crane_qc_right.get()
                crane_wt = gc_total + 0.6 * qc_total
                if crane_wt > 0:
                    F_crane_uls = result['Cd_uls'] * crane_wt / 2.0
                    F_crane_sls = result['Cd_sls'] * crane_wt / 2.0
                    text += (
                        f"\n--- Crane seismic (at bracket nodes) ---\n"
                        f"Wt_crane = Gc + 0.6Qc = {gc_total:.1f} + 0.6x{qc_total:.1f}"
                        f" = {crane_wt:.2f} kN\n"
                        f"F_crane ULS = {F_crane_uls:.2f} kN (per bracket)\n"
                        f"F_crane SLS = {F_crane_sls:.2f} kN (per bracket)"
                    )
            self.eq_results_label.config(text=text)
        except Exception as e:
            self.eq_results_label.config(text=f"Error: {e}")

    # ── Crane Tab ──

    def _build_crane_tab(self, parent):
        pad = {"padx": 10, "pady": (0, 2)}

        self._section_header(parent, "GANTRY CRANE LOADING")

        self.crane_enabled_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parent, text="Enable Gantry Crane Loading",
            variable=self.crane_enabled_var, font=FONT_BOLD,
            fg=COLORS["fg"], bg=COLORS["bg_panel"],
            selectcolor=COLORS["bg_input"],
            activebackground=COLORS["bg_panel"],
            activeforeground=COLORS["fg"],
            command=self._on_crane_toggle,
        ).pack(fill="x", padx=10, pady=(0, 6))

        self.crane_content = tk.Frame(parent, bg=COLORS["bg_panel"])
        # Initially hidden — shown on toggle

        self._section_header(self.crane_content, "CRANE PARAMETERS")
        self.crane_rail_height = LabeledEntry(
            self.crane_content, "Rail Height", 3.0, "m")
        self.crane_rail_height.pack(fill="x", **pad)
        self.crane_rail_height.bind_change(self._on_crane_param_change)

        self._section_header(self.crane_content, "CRANE DEAD LOAD (Gc) -- unfactored")
        self.crane_gc_left = LabeledEntry(
            self.crane_content, "Gc Left Bracket", 0.0, "kN")
        self.crane_gc_left.pack(fill="x", **pad)
        self.crane_gc_right = LabeledEntry(
            self.crane_content, "Gc Right Bracket", 0.0, "kN")
        self.crane_gc_right.pack(fill="x", **pad)

        self._section_header(self.crane_content, "CRANE LIVE LOAD (Qc) -- unfactored")
        self.crane_qc_left = LabeledEntry(
            self.crane_content, "Qc Left Bracket", 0.0, "kN")
        self.crane_qc_left.pack(fill="x", **pad)
        self.crane_qc_right = LabeledEntry(
            self.crane_content, "Qc Right Bracket", 0.0, "kN")
        self.crane_qc_right.pack(fill="x", **pad)

        # Transverse ULS
        self._section_header(
            self.crane_content,
            "TRANSVERSE ULS (Hc) -- pre-factored from manufacturer")
        self.crane_hc_uls_frame = tk.Frame(
            self.crane_content, bg=COLORS["bg_panel"])
        self.crane_hc_uls_frame.pack(fill="x", padx=10, pady=(0, 4))
        self.crane_hc_uls_rows = []

        uls_btn_row = tk.Frame(self.crane_content, bg=COLORS["bg_panel"])
        uls_btn_row.pack(fill="x", padx=10, pady=(0, 6))
        tk.Button(
            uls_btn_row, text="+ Add ULS Row", font=FONT_SMALL,
            fg=COLORS["fg_bright"], bg=COLORS["accent"],
            activebackground=COLORS["accent_hover"],
            relief="flat", cursor="hand2", padx=6, pady=2,
            command=lambda: self._add_crane_hc_row(
                self.crane_hc_uls_frame, self.crane_hc_uls_rows,
                "Hc", len(self.crane_hc_uls_rows) + 1),
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            uls_btn_row, text="- Remove Last", font=FONT_SMALL,
            fg=COLORS["fg_bright"], bg=COLORS["border"],
            activebackground=COLORS["fg_dim"],
            relief="flat", cursor="hand2", padx=6, pady=2,
            command=lambda: self._remove_crane_hc_row(self.crane_hc_uls_rows),
        ).pack(side="left")

        # Transverse SLS
        self._section_header(
            self.crane_content,
            "TRANSVERSE SLS (Hc) -- pre-factored from manufacturer")
        self.crane_hc_sls_frame = tk.Frame(
            self.crane_content, bg=COLORS["bg_panel"])
        self.crane_hc_sls_frame.pack(fill="x", padx=10, pady=(0, 4))
        self.crane_hc_sls_rows = []

        sls_btn_row = tk.Frame(self.crane_content, bg=COLORS["bg_panel"])
        sls_btn_row.pack(fill="x", padx=10, pady=(0, 6))
        tk.Button(
            sls_btn_row, text="+ Add SLS Row", font=FONT_SMALL,
            fg=COLORS["fg_bright"], bg=COLORS["accent"],
            activebackground=COLORS["accent_hover"],
            relief="flat", cursor="hand2", padx=6, pady=2,
            command=lambda: self._add_crane_hc_row(
                self.crane_hc_sls_frame, self.crane_hc_sls_rows,
                "Hcs", len(self.crane_hc_sls_rows) + 1),
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            sls_btn_row, text="- Remove Last", font=FONT_SMALL,
            fg=COLORS["fg_bright"], bg=COLORS["border"],
            activebackground=COLORS["fg_dim"],
            relief="flat", cursor="hand2", padx=6, pady=2,
            command=lambda: self._remove_crane_hc_row(self.crane_hc_sls_rows),
        ).pack(side="left")

    def _on_crane_toggle(self, *_):
        if self.crane_enabled_var.get():
            self.crane_content.pack(fill="x", padx=10)
        else:
            self.crane_content.pack_forget()
        self.refresh_load_case_list()
        self._update_preview()

    def _on_crane_param_change(self, *_):
        """Called when crane rail height or loads change."""
        self.refresh_load_case_list()
        self._update_preview()

    def _add_crane_hc_row(self, frame, rows_list, prefix, idx):
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

    def _remove_crane_hc_row(self, rows_list):
        """Remove the last transverse combo row."""
        if rows_list:
            row_frame, _, _, _ = rows_list.pop()
            row_frame.destroy()

    # ── Combos Tab ──

    def _build_combos_tab(self, parent):
        self._section_header(parent, "LOAD COMBINATIONS  (AS/NZS 1170.0:2002)")

        combo_text = (
            "ULS-1: 1.35G              (101+)\n"
            "ULS-2: 1.2G + 1.5Q\n"
            "ULS-n: 1.2G + Wu  (per wind case)\n"
            "ULS-n: 0.9G + Wu  (per wind case)\n"
            "ULS-n: 1.0G + E+  (if EQ enabled)\n"
            "ULS-n: 1.0G + E-  (if EQ enabled)\n"
            "SLS-1: G + 0.7Q           (201+)\n"
            "SLS-2: G\n"
            "SLS-n: G + Ws  (per wind case)\n"
            "SLS-n: G + E(s)  (if EQ enabled)\n\n"
            "Table 4.1 roof factors: psi_s=0.7, psi_l=0.0, psi_c=0.0\n"
            "EQ combo: G factor = 1.0 (not 1.2), Q drops out (psi_c=0)"
        )
        tk.Label(parent, text=combo_text, font=FONT_MONO, fg=COLORS["fg_dim"],
                 bg=COLORS["bg_panel"], anchor="w", justify="left"
                 ).pack(fill="x", padx=10, pady=(0, 12))

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
        """Called when user edits any Cp,e or Ka value in the surface table."""
        if not hasattr(self, 'load_case_var'):
            return  # still building UI
        self.refresh_load_case_list()
        self._update_preview()

    def _on_wind_case_select(self, case_name):
        """Called when user clicks a W1-W8 tab in the surface panel."""
        if case_name is None:
            self.load_case_var.set("(none)")
        else:
            # Find the matching entry in the load case dropdown
            try:
                cases = self._synthesize_wind_cases()
                for wc in cases:
                    if wc.name == case_name:
                        self.load_case_var.set(f"{wc.name} - {wc.description}"[:50])
                        break
            except Exception:
                pass
        self._draw_preview()

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
        """Display envelope results in the summary text widget."""
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

        self._results_text.config(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.insert("1.0", "\n".join(lines))
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
        name = self._diagram_display_to_name.get(display) if hasattr(
            self, '_diagram_display_to_name') else display
        if name is None:
            return None

        attr = {"M": "moment", "V": "shear", "N": "axial", "δ": "dy_local"}[dtype]

        # Envelope selections return both max and min curves
        if name == "ULS Envelope" and out.uls_envelope_curves is not None:
            env_max, env_min = out.uls_envelope_curves
        elif name == "SLS Envelope" and out.sls_envelope_curves is not None:
            env_max, env_min = out.sls_envelope_curves
        else:
            env_max = env_min = None

        def _extract(cr):
            return {
                mid: [(s.position_pct, getattr(s, attr)) for s in mr.stations]
                for mid, mr in cr.members.items()
            }

        def _extract_dx(cr):
            """For δ diagrams, extract dx_local values parallel to main attr."""
            return {
                mid: [(s.position_pct, s.dx_local) for s in mr.stations]
                for mid, mr in cr.members.items()
            }

        members_map = {}
        if self._analysis_topology:
            for mid, mem in self._analysis_topology.members.items():
                members_map[mid] = (mem.node_start, mem.node_end)

        if env_max is not None:
            result = {
                "data": _extract(env_max),
                "data_min": _extract(env_min),
                "type": dtype,
                "members": members_map,
                "is_envelope": True,
            }
            if dtype == "δ":
                result["data_dx"] = _extract_dx(env_max)
                result["data_min_dx"] = _extract_dx(env_min)
            return result

        # Normal case/combo lookup
        if name in out.case_results:
            cr = out.case_results[name]
        elif name in out.combo_results:
            cr = out.combo_results[name]
        else:
            return None

        result = {
            "data": _extract(cr),
            "type": dtype,
            "members": members_map,
        }
        if dtype == "δ":
            result["data_dx"] = _extract_dx(cr)
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
            "Z": self.eq_Z.get(),
            "soil_class": self.eq_soil.get(),
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
        self._update_section_info()

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
        self.eq_Z.set(eq.get("Z", 0.40))
        self.eq_soil.set(eq.get("soil_class", "C"))
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
