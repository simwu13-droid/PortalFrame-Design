"""Reusable GUI widgets — LabeledEntry, LabeledCombo."""

import tkinter as tk
from tkinter import ttk

from portal_frame.gui.theme import COLORS, FONT, FONT_BOLD, FONT_SMALL, FONT_MONO


def _filter_substring(master: list[str], text: str) -> list[str]:
    """Case-insensitive substring filter. Preserves master order.

    Empty/whitespace-only text returns the full list.
    """
    needle = text.strip().lower()
    if not needle:
        return list(master)
    return [item for item in master if needle in item.lower()]


class LabeledEntry(tk.Frame):
    """A label + entry pair with units."""

    def __init__(self, parent, label, default="", unit="", width=8, **kw):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.columnconfigure(1, weight=1)

        tk.Label(self, text=label, font=FONT, fg=COLORS["fg"], bg=COLORS["bg_panel"],
                 anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6))

        self.var = tk.StringVar(value=str(default))
        self.entry = tk.Entry(self, textvariable=self.var, font=FONT_MONO, width=width,
                              bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                              insertbackground=COLORS["fg_bright"],
                              relief="flat", borderwidth=0,
                              highlightthickness=1, highlightcolor=COLORS["accent"],
                              highlightbackground=COLORS["border"])
        self.entry.grid(row=0, column=1, sticky="ew", padx=2)

        if unit:
            tk.Label(self, text=unit, font=FONT_SMALL, fg=COLORS["fg_dim"],
                     bg=COLORS["bg_panel"]).grid(row=0, column=2, padx=(4, 0))

    def get(self) -> float:
        try:
            return float(self.var.get())
        except ValueError:
            return 0.0

    def set(self, value):
        self.var.set(str(value))

    def bind_change(self, callback):
        self.var.trace_add("write", lambda *_: callback())


class LabeledCombo(tk.Frame):
    """A label + combobox pair."""

    def __init__(self, parent, label, values=None, default="", width=20):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.columnconfigure(1, weight=1)

        tk.Label(self, text=label, font=FONT, fg=COLORS["fg"], bg=COLORS["bg_panel"],
                 anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6))

        self.var = tk.StringVar(value=default)
        self.combo = ttk.Combobox(self, textvariable=self.var, values=values or [],
                                  width=width, state="readonly", font=FONT_MONO)
        self.combo.grid(row=0, column=1, sticky="ew", padx=2)

    def get(self) -> str:
        return self.var.get()

    def set(self, value):
        self.var.set(value)

    def set_values(self, values):
        self.combo["values"] = values

    def bind_change(self, callback):
        self.combo.bind("<<ComboboxSelected>>", lambda _: callback())
