"""Main application window — tab orchestration and generate flow."""

import tkinter as tk
from tkinter import ttk
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
from portal_frame.models.loads import EarthquakeInputs
from portal_frame.standards.earthquake_nzs1170_5 import calculate_earthquake_forces
from portal_frame.gui.wind_generator import (
    auto_generate_wind_cases, synthesize_wind_cases,
    get_h_and_depth, get_wind_params,
)
from portal_frame.gui.persistence import (
    save_config, load_config, open_recent, update_recent_menu,
    on_close, auto_restore,
)
from portal_frame.gui.analysis_runner import (
    generate, analyse, invalidate_analysis, group_design_checks_by_member,
)


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

    def _on_wind_table_change(self):
        on_wind_table_change(self)

    def _on_wind_case_select(self, case_name):
        on_wind_case_select(self, case_name)

    def _auto_generate_wind_cases(self):
        auto_generate_wind_cases(self)

    def _synthesize_wind_cases(self):
        return synthesize_wind_cases(self)

    def _get_h_and_depth(self):
        return get_h_and_depth(self)

    def _get_wind_params(self):
        return get_wind_params(self)

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

        self.preview.set_design_checks(self._group_design_checks_by_member())
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

    def _generate(self):
        generate(self)

    def _analyse(self):
        analyse(self)

    def _invalidate_analysis(self):
        invalidate_analysis(self)

    def _group_design_checks_by_member(self) -> dict | None:
        return group_design_checks_by_member(self)

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

    def _save_config(self):
        save_config(self)

    def _load_config(self):
        load_config(self)

    def _open_recent(self, path):
        open_recent(self, path)

    def _update_recent_menu(self):
        update_recent_menu(self)

    def _on_close(self):
        on_close(self)

    def _auto_restore(self):
        auto_restore(self)
