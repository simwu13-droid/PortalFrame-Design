"""Reusable GUI widgets — LabeledEntry, LabeledCombo."""

import tkinter as tk

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
    """A label + searchable combobox pair.

    Visual layout: label | entry | dropdown arrow. When the user types or
    clicks the arrow, a floating popup Toplevel appears below the entry
    containing a Listbox of case-insensitive substring matches. Click an
    item or press Enter to commit. Escape or click-elsewhere reverts.

    Public API (get/set/set_values/bind_change) is unchanged from the
    previous ttk.Combobox-based implementation, so existing call sites
    work without modification.
    """

    _MAX_POPUP_ROWS = 10      # cap the popup height
    _ROW_HEIGHT_PX = 20       # approximate row pixel height for sizing
    _ARROW_CHAR = "▼"

    def __init__(self, parent, label, values=None, default="", width=20):
        super().__init__(parent, bg=COLORS["bg_panel"])
        self.columnconfigure(1, weight=1)

        tk.Label(
            self, text=label, font=FONT, fg=COLORS["fg"], bg=COLORS["bg_panel"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))

        self._all_values: list[str] = list(values or [])
        self._last_valid: str = default if default in self._all_values else ""
        self._change_callback = None
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None

        # Container styled like a single input so entry + arrow share one border.
        container = tk.Frame(
            self, bg=COLORS["bg_input"], highlightthickness=1,
            highlightcolor=COLORS["accent"], highlightbackground=COLORS["border"],
        )
        container.grid(row=0, column=1, sticky="ew", padx=2)
        container.columnconfigure(0, weight=1)

        self.var = tk.StringVar(value=default)
        self.entry = tk.Entry(
            container, textvariable=self.var, width=width, font=FONT_MONO,
            bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
            insertbackground=COLORS["fg_bright"],
            relief="flat", borderwidth=0, highlightthickness=0,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(2, 0))

        self.arrow = tk.Label(
            container, text=self._ARROW_CHAR, font=FONT_SMALL,
            fg=COLORS["fg_dim"], bg=COLORS["bg_input"],
            cursor="hand2", padx=4,
        )
        self.arrow.grid(row=0, column=1, sticky="ns")
        self.arrow.bind("<Button-1>", self._on_arrow_click)

        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<Down>",       self._on_down)
        self.entry.bind("<Up>",         self._on_up)
        self.entry.bind("<Return>",     self._on_return)
        self.entry.bind("<Escape>",     self._on_escape)
        self.entry.bind("<FocusIn>",    self._on_focus_in)
        self.entry.bind("<FocusOut>",   self._on_focus_out)
        self.entry.bind("<Tab>",           self._on_tab)
        self.entry.bind("<Shift-Tab>",     self._on_tab)
        self.entry.bind("<ISO_Left_Tab>",  self._on_tab)

    # --- Public API (unchanged signatures) -------------------------------

    def get(self) -> str:
        return self.var.get()

    def set(self, value):
        self.var.set(value)
        if value in self._all_values:
            self._last_valid = value

    def set_values(self, values):
        self._all_values = list(values)
        if self.var.get() not in self._all_values:
            self.var.set("")
            self._last_valid = ""
        # If popup is open, refresh its contents.
        if self._popup_visible():
            self._refresh_popup(_filter_substring(self._all_values, self.var.get()))

    def bind_change(self, callback):
        self._change_callback = callback

    # --- Popup management ------------------------------------------------

    def _popup_visible(self) -> bool:
        return self._popup is not None and bool(self._popup.winfo_viewable())

    def _show_popup(self, items: list[str]) -> None:
        if not items:
            self._hide_popup()
            return
        if self._popup is None:
            self._popup = tk.Toplevel(self)
            self._popup.overrideredirect(True)
            self._popup.attributes("-topmost", True)
            self._listbox = tk.Listbox(
                self._popup, font=FONT_MONO,
                bg=COLORS["bg_input"], fg=COLORS["fg_bright"],
                selectbackground=COLORS["accent"], selectforeground=COLORS["fg_bright"],
                activestyle="none", exportselection=False, borderwidth=0,
                highlightthickness=1, highlightcolor=COLORS["accent"],
                highlightbackground=COLORS["border"],
            )
            self._listbox.pack(fill="both", expand=True)
            self._listbox.bind("<Button-1>", self._on_listbox_click)
            self._listbox.bind("<Motion>",   self._on_listbox_motion)
        self._refresh_popup(items)
        self._position_popup()
        self._popup.deiconify()
        self._popup.lift()

    def _refresh_popup(self, items: list[str]) -> None:
        if self._listbox is None:
            return
        self._listbox.delete(0, "end")
        for item in items:
            self._listbox.insert("end", item)
        # Pre-select the current value if it is in the filtered list; else row 0.
        current = self.var.get()
        if current in items:
            idx = items.index(current)
        else:
            idx = 0
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.activate(idx)
        self._listbox.see(idx)

    def _position_popup(self) -> None:
        if self._popup is None or self._listbox is None:
            return
        self.entry.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        w = self.entry.winfo_width() + self.arrow.winfo_width()
        n = max(1, min(self._listbox.size(), self._MAX_POPUP_ROWS))
        self._listbox.configure(height=n)
        self._popup.update_idletasks()
        self._popup.geometry(f"{w}x{self._listbox.winfo_reqheight()}+{x}+{y}")

    def _hide_popup(self) -> None:
        if self._popup is not None:
            self._popup.withdraw()

    def _destroy_popup(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
            self._listbox = None

    def destroy(self):
        # Ensure the floating popup is cleaned up with the widget.
        self._destroy_popup()
        super().destroy()

    # --- Event handlers --------------------------------------------------

    def _on_arrow_click(self, ev):
        if self._popup_visible():
            self._hide_popup()
            return "break"
        items = _filter_substring(self._all_values, self.var.get())
        if not items:
            items = list(self._all_values)
        self._show_popup(items)
        self.entry.focus_set()
        self.entry.icursor("end")
        return "break"

    def _on_focus_in(self, ev):
        # Select all so typing replaces the current value cleanly.
        self.entry.select_range(0, "end")
        self.entry.icursor("end")

    def _on_focus_out(self, ev):
        # If focus moved into our own popup, ignore.
        try:
            new_focus = self.focus_get()
        except (KeyError, tk.TclError):
            new_focus = None
        if new_focus is not None and self._listbox is not None and new_focus is self._listbox:
            return
        # Defer commit/revert so the listbox click (which fires FocusOut before
        # Button-1) has a chance to commit first.
        self.after_idle(self._finalize_focus_out)

    def _finalize_focus_out(self):
        # If focus has returned to our widget (popup click handled), do nothing.
        try:
            cur = self.focus_get()
        except (KeyError, tk.TclError):
            cur = None
        if cur is self.entry:
            return
        text = self.var.get()
        if text in self._all_values:
            if text != self._last_valid:
                self._commit(text)
        else:
            self.var.set(self._last_valid)
        self._hide_popup()

    def _on_tab(self, ev):
        """If the popup is open with a highlighted row, commit that row
        before Tab advances focus to the next widget. Do NOT return
        "break" — we want Tk's default Tab binding (focus traversal) to
        still run after we commit.
        """
        if self._popup_visible() and self._listbox is not None:
            cur = self._listbox.curselection()
            if cur:
                self._commit(self._listbox.get(cur[0]))
                self._hide_popup()
        return None

    def _on_key_release(self, ev):
        # Ignore nav/commit/modifier keys — their own handlers cover them.
        if ev.keysym in {
            "Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next",
            "Tab", "ISO_Left_Tab", "Return", "Escape",
            "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Caps_Lock",
        }:
            return
        items = _filter_substring(self._all_values, self.var.get())
        if items:
            self._show_popup(items)
        else:
            self._hide_popup()

    def _on_down(self, ev):
        if not self._popup_visible():
            items = _filter_substring(self._all_values, self.var.get())
            if not items:
                items = list(self._all_values)
            self._show_popup(items)
            return "break"
        if self._listbox is None or self._listbox.size() == 0:
            return "break"
        cur = self._listbox.curselection()
        idx = 0 if not cur else min(cur[0] + 1, self._listbox.size() - 1)
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.activate(idx)
        self._listbox.see(idx)
        return "break"

    def _on_up(self, ev):
        if not self._popup_visible() or self._listbox is None or self._listbox.size() == 0:
            return "break"
        cur = self._listbox.curselection()
        idx = 0 if not cur else max(cur[0] - 1, 0)
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.activate(idx)
        self._listbox.see(idx)
        return "break"

    def _on_return(self, ev):
        # Prefer the popup's highlighted row if open.
        if self._popup_visible() and self._listbox is not None:
            cur = self._listbox.curselection()
            if cur:
                self._commit(self._listbox.get(cur[0]))
                self._hide_popup()
                return "break"
        # Else: exact typed match.
        text = self.var.get()
        if text in self._all_values:
            self._commit(text)
            self._hide_popup()
            return "break"
        # Else: unique filter match.
        filtered = _filter_substring(self._all_values, text)
        if len(filtered) == 1:
            self._commit(filtered[0])
            self._hide_popup()
            return "break"
        return "break"

    def _on_escape(self, ev):
        self.var.set(self._last_valid)
        self._hide_popup()
        return "break"

    def _on_listbox_click(self, ev):
        if self._listbox is None:
            return "break"
        idx = self._listbox.nearest(ev.y)
        if idx >= 0:
            self._commit(self._listbox.get(idx))
            self._hide_popup()
            self.entry.focus_set()
        return "break"

    def _on_listbox_motion(self, ev):
        if self._listbox is None:
            return
        idx = self._listbox.nearest(ev.y)
        if idx >= 0:
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(idx)
            self._listbox.activate(idx)

    # --- Commit helper ---------------------------------------------------

    def _commit(self, value: str) -> None:
        changed = value != self._last_valid
        self.var.set(value)
        self._last_valid = value
        if changed and self._change_callback is not None:
            self._change_callback()
