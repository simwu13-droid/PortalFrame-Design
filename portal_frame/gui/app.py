"""Main application window — tab orchestration and generate flow."""

import tkinter as tk
from tkinter import ttk

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
from portal_frame.gui.diagram_controller import (
    update_preview, on_diagram_type_changed, draw_preview, update_section_info,
    update_diagram_dropdowns,
    refresh_load_case_list as _refresh_load_case_list_fn,
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
            values=["M", "V", "N", "δ", "Reactions"], state="readonly", font=FONT_MONO, width=10)
        self.diagram_type_combo.pack(side="left", padx=4)
        self.diagram_type_combo.bind("<<ComboboxSelected>>",
                                      lambda _: self._on_diagram_type_changed())

        right.rowconfigure(1, weight=1)

        self.preview = FramePreview(right, width=400, height=300)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.preview.set_member_dblclick_handler(self._open_member_popout)
        self._open_popouts = []

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

        self.export_reactions_btn = tk.Button(
            btn_row, text="  EXPORT REACTIONS  ", font=FONT_BOLD,
            fg=COLORS["fg_bright"], bg="#555555",
            activebackground="#666666", activeforeground=COLORS["fg_bright"],
            relief="flat", cursor="hand2", padx=10, pady=8,
            command=self._export_reactions,
            state="disabled",
        )
        self.export_reactions_btn.pack(side="left", padx=(8, 0))

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

    def _update_preview(self, *args):
        update_preview(self, *args)

    def _on_diagram_type_changed(self):
        on_diagram_type_changed(self)

    def _draw_preview(self, *args):
        draw_preview(self, *args)

    def refresh_load_case_list(self):
        _refresh_load_case_list_fn(self)

    def _update_section_info(self, *args):
        update_section_info(self, *args)

    def _generate(self):
        generate(self)

    def _analyse(self):
        analyse(self)

    def _export_reactions(self):
        from portal_frame.gui.analysis_runner import export_reactions
        export_reactions(self)

    def _invalidate_analysis(self):
        invalidate_analysis(self)
        if hasattr(self, "export_reactions_btn"):
            self.export_reactions_btn.config(state="disabled")

    def _group_design_checks_by_member(self) -> dict | None:
        return group_design_checks_by_member(self)

    def _update_diagram_dropdowns(self):
        update_diagram_dropdowns(self)

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

    def _open_member_popout(self, mid):
        """Open a MemberPopout for the given member id."""
        if self._analysis_output is None:
            from tkinter import messagebox
            messagebox.showinfo("No analysis",
                                "Run Analyse (PyNite) before inspecting members.")
            return
        # Guard: topology may have replaced original member IDs with sub-members
        # (e.g. crane brackets split column 1 into sub-members 6+7)
        if (self._analysis_topology is None or
                mid not in self._analysis_topology.members):
            from tkinter import messagebox
            messagebox.showinfo("Member unavailable",
                                f"Member {mid} is not in the current topology "
                                f"(crane brackets may have split this member).")
            return
        from portal_frame.gui.member_popout import MemberPopout
        popout = MemberPopout(self, mid, self._analysis_output,
                              self._analysis_topology)
        self._open_popouts.append(popout)
        popout.bind("<Destroy>",
                    lambda e, p=popout: self._open_popouts.remove(p)
                    if p in self._open_popouts else None)
