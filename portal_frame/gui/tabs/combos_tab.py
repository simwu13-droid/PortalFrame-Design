"""Combos tab — read-only display of NZ load-combination rules."""

import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_MONO


def build_combos_tab(app, parent):
    app._section_header(parent, "LOAD COMBINATIONS  (AS/NZS 1170.0:2002)")

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
