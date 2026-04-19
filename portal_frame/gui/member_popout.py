"""Member detail popout window. Full implementation in Tasks 8-11."""
import tkinter as tk


class MemberPopout(tk.Toplevel):
    def __init__(self, parent, mid, analysis_output, topology):
        super().__init__(parent)
        self.title(f"Member {mid}")
        self.geometry("820x620")
        tk.Label(self, text=f"Member {mid} popout (stub)").pack(padx=20, pady=20)
