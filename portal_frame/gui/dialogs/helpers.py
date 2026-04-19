"""Shared widget helpers for the dialogs package."""
import tkinter as tk

from portal_frame.gui.theme import COLORS, FONT_MONO


def styled_entry(parent, var, width, row, col, padx=1, pady=1):
    """Create a consistently-styled Entry widget and grid it."""
    e = tk.Entry(parent, textvariable=var, font=FONT_MONO, width=width,
                 bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                 insertbackground=COLORS["fg_bright"], relief="flat",
                 highlightthickness=1, highlightcolor=COLORS["accent"],
                 highlightbackground=COLORS["border"])
    e.grid(row=row, column=col, padx=padx, pady=pady)
    return e
