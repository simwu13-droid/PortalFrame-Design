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
        self._popdown_opening: bool = False
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
        self.combo.bind("<FocusIn>", self._on_focus_in)

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

    # --- Internal event handlers ---------------------------------------

    def _on_focus_in(self, ev):
        """Select all entry text so typing replaces the current value.

        Skips the select-all when focus is returning from our own popdown
        (detected via _popdown_opening) — otherwise mid-typing focus bounces
        would clobber the text the user just typed.
        """
        if self._popdown_opening:
            return
        self.combo.select_range(0, "end")
        self.combo.icursor("end")

    def _on_key_release(self, ev):
        """Filter master list by substring of current entry text. Post the
        popdown so user sees matches, then reclaim focus to the entry.
        """
        if ev.keysym in self._NAV_KEYSYMS:
            return
        if self._filtering:
            return
        self._filtering = True
        try:
            filtered = _filter_substring(self._all_values, self.var.get())
            self.combo["values"] = filtered
            if filtered:
                self._popdown_opening = True
                try:
                    self.combo.event_generate("<Down>")
                    self.combo.focus_set()
                    self.combo.icursor("end")
                finally:
                    self.after_idle(self._clear_popdown_flag)
        finally:
            self._filtering = False

    def _clear_popdown_flag(self):
        self._popdown_opening = False

    def _on_return(self, ev):
        """Commit on Enter: exact match > unique filter match > no-op."""
        text = self.var.get()
        if text in self._all_values:
            self._commit(text)
            return "break"
        filtered = _filter_substring(self._all_values, text)
        if len(filtered) == 1:
            self._commit(filtered[0])
            return "break"
        # Otherwise let Tk's default Enter behaviour run (highlighted row
        # in popdown will fire <<ComboboxSelected>>, which commits).
        return None

    def _on_escape(self, ev):
        """Revert entry text to last-committed value."""
        self.var.set(self._last_valid)
        self.combo["values"] = self._all_values
        # Close the popdown if it is open.
        try:
            self.combo.tk.call("ttk::combobox::Unpost", self.combo._w)
        except tk.TclError:
            pass
        return "break"

    def _on_focus_out(self, ev):
        """If typed text is not valid, revert; if valid and uncommitted, commit.

        Ignored during our own popdown-opening moment — _<Down>_ transiently
        moves focus to the popdown listbox, and that must not be treated as
        a user-driven focus leave.
        """
        if self._popdown_opening:
            return
        text = self.var.get()
        if text in self._all_values:
            if text != self._last_valid:
                self._commit(text)
        else:
            self.var.set(self._last_valid)
            self.combo["values"] = self._all_values

    def _on_selected(self, ev):
        """List-item click or default Enter-on-highlighted-row commit."""
        self._commit(self.var.get())

    def _commit(self, value: str) -> None:
        """Update _last_valid and fire the change callback if the value changed."""
        changed = value != self._last_valid
        self.var.set(value)
        self._last_valid = value
        self.combo["values"] = self._all_values
        if changed and self._change_callback is not None:
            self._change_callback()
