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
    """A label + combobox pair with type-to-filter support.

    Typing filters the dropdown by case-insensitive substring. Commits
    only happen on list-item click, Enter (when filter is unique or a
    row is highlighted), or programmatic set(). Invalid typed text
    reverts on Escape or focus-out. Public API unchanged.
    """

    _NAV_KEYSYMS = {
        "Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next",
        "Tab", "ISO_Left_Tab",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        "Caps_Lock", "Return", "Escape",
    }

    def __init__(self, parent, label, values=None, default="", width=20):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.columnconfigure(1, weight=1)

        tk.Label(self, text=label, font=FONT, fg=COLORS["fg"], bg=COLORS["bg_panel"],
                 anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 6))

        self._all_values: list[str] = list(values or [])
        self._last_valid: str = default if default in self._all_values else ""
        self._filtering: bool = False
        self._change_callback = None

        self.var = tk.StringVar(value=default)
        self.combo = ttk.Combobox(self, textvariable=self.var, values=self._all_values,
                                  width=width, state="normal", font=FONT_MONO)
        self.combo.grid(row=0, column=1, sticky="ew", padx=2)

        self.combo.bind("<KeyRelease>", self._on_key_release)
        self.combo.bind("<Return>", self._on_return)
        self.combo.bind("<Escape>", self._on_escape)
        self.combo.bind("<FocusOut>", self._on_focus_out)
        self.combo.bind("<<ComboboxSelected>>", self._on_selected)

    # Public API — signatures unchanged.

    def get(self) -> str:
        return self.var.get()

    def set(self, value):
        self.var.set(value)
        if value in self._all_values:
            self._last_valid = value

    def set_values(self, values):
        self._all_values = list(values)
        self.combo["values"] = self._all_values
        if self.var.get() not in self._all_values:
            self.var.set("")
            self._last_valid = ""

    def bind_change(self, callback):
        self._change_callback = callback
