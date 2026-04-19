"""Member detail popout window.

A Toplevel that shows a single-member X-Y diagram (M/V/N/delta) with a
Point-of-Interest input and a summary table. Multiple popouts may be open
simultaneously — each is independent.
"""
import tkinter as tk
from tkinter import ttk

from portal_frame.gui.theme import COLORS, FONT_MONO, FONT_SMALL


DIAGRAM_TYPES = ["M", "V", "N", "\u03b4"]
DIAGRAM_UNITS = {"M": "kNm", "V": "kN", "N": "kN", "\u03b4": "mm"}
DIAGRAM_ATTRS = {"M": "moment", "V": "shear", "N": "axial", "\u03b4": "dy_local"}


class MemberPopout(tk.Toplevel):
    """One member x one case x one diagram type, with POI table."""

    def __init__(self, parent, mid, analysis_output, topology):
        super().__init__(parent)
        self._mid = mid
        self._out = analysis_output
        self._topology = topology
        self._member = topology.members[mid]
        self._length = self._compute_length()
        # Get section name from member if available
        section_name = getattr(self._member, "section_name", str(mid))
        self.title(f"Member {mid} \u2014 {section_name} "
                   f"(L={self._length:.2f} m)")
        self.geometry("820x620")
        self.configure(bg=COLORS["bg_panel"])
        self.resizable(True, True)

        self._build_controls()
        self._build_chart()
        self._build_poi_input()
        self._build_table()

        self._refresh_case_list()
        self._on_case_changed()

    # ── layout ──────────────────────────────────────────────────────────

    def _build_controls(self):
        top = tk.Frame(self, bg=COLORS["bg_panel"])
        top.pack(fill="x", padx=12, pady=(12, 4))

        tk.Label(top, text="Load Case", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")
        self._case_var = tk.StringVar()
        self._case_combo = ttk.Combobox(
            top, textvariable=self._case_var, state="readonly",
            font=FONT_MONO, width=28)
        self._case_combo.pack(side="left", padx=(6, 16))
        self._case_combo.bind("<<ComboboxSelected>>",
                              lambda _: self._on_case_changed())

        tk.Label(top, text="Diagram", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")
        self._dtype_var = tk.StringVar(value="M")
        self._dtype_combo = ttk.Combobox(
            top, textvariable=self._dtype_var, state="readonly",
            values=DIAGRAM_TYPES, font=FONT_MONO, width=4)
        self._dtype_combo.pack(side="left", padx=(6, 0))
        self._dtype_combo.bind("<<ComboboxSelected>>",
                               lambda _: self._redraw_chart())

    def _build_chart(self):
        self._chart = tk.Canvas(
            self, bg=COLORS["canvas_bg"], highlightthickness=0,
            height=360)
        self._chart.pack(fill="both", expand=True, padx=12, pady=4)
        self._chart.bind("<Motion>", self._on_chart_motion)
        self._chart.bind("<Leave>", lambda _: self._clear_hover())

    def _build_poi_input(self):
        row = tk.Frame(self, bg=COLORS["bg_panel"])
        row.pack(fill="x", padx=12, pady=(4, 4))
        tk.Label(row, text="Point of interest", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")
        self._poi_var = tk.StringVar()
        self._poi_entry = tk.Entry(
            row, textvariable=self._poi_var, font=FONT_MONO, width=24,
            bg=COLORS["bg_input"], fg=COLORS["fg_bright"], relief="flat",
            highlightthickness=1, highlightcolor=COLORS["accent"],
            highlightbackground=COLORS["border"])
        self._poi_entry.pack(side="left", padx=(6, 4))
        self._poi_entry.bind("<Return>", lambda _: self._refresh_table())
        self._poi_entry.bind("<FocusOut>", lambda _: self._refresh_table())
        tk.Label(row, text="m", font=FONT_SMALL,
                 fg=COLORS["fg"], bg=COLORS["bg_panel"]).pack(side="left")

    def _build_table(self):
        cols = ("position", "moment", "shear", "axial", "deflection")
        self._table = ttk.Treeview(self, columns=cols, show="headings",
                                   height=6)
        headings = {
            "position": "Position (m)", "moment": "Moment (kNm)",
            "shear": "Shear (kN)", "axial": "Axial (kN)",
            "deflection": "Deflection (mm)",
        }
        for c in cols:
            self._table.heading(c, text=headings[c])
            self._table.column(c, width=140, anchor="center")
        self._table.pack(fill="x", padx=12, pady=(4, 12))

    # ── helpers ─────────────────────────────────────────────────────────

    def _compute_length(self):
        ns = self._topology.nodes[self._member.node_start]
        ne = self._topology.nodes[self._member.node_end]
        return ((ne.x - ns.x) ** 2 + (ne.y - ns.y) ** 2) ** 0.5

    def _refresh_case_list(self):
        values = list(self._out.case_results.keys())
        values.extend(sorted(self._out.combo_results.keys(),
                             key=lambda n: (0 if n.startswith("ULS") else 1,
                                            self._combo_num(n))))
        if self._out.uls_envelope_curves is not None:
            values.append("ULS Envelope")
        if self._out.sls_envelope_curves is not None:
            values.append("SLS Envelope")
        if self._out.sls_wind_only_envelope_curves is not None:
            values.append("SLS Wind Only Envelope")
        self._case_combo["values"] = values
        if values and not self._case_var.get():
            self._case_var.set(values[0])

    @staticmethod
    def _combo_num(name):
        try:
            return int(name.split("-")[1])
        except (IndexError, ValueError):
            return 0

    # ── callbacks (stubs — filled in Tasks 9-11) ────────────────────────

    def _on_case_changed(self):
        self._redraw_chart()
        self._refresh_table()

    def _redraw_chart(self):
        self._chart.delete("all")
        self._chart.create_text(
            400, 180,
            text=f"Chart: {self._dtype_var.get()} @ {self._case_var.get()}",
            fill=COLORS["fg"], font=FONT_MONO)

    def _refresh_table(self):
        for row in self._table.get_children():
            self._table.delete(row)

    def _on_chart_motion(self, event):
        pass

    def _clear_hover(self):
        self._chart.delete("hover_marker")
