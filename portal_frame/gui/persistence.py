"""Config persistence -- save/load config, recent files, auto-restore."""

import json
import os
from tkinter import filedialog, messagebox

from portal_frame.gui.theme import COLORS


_APP_DIR = os.path.join(os.path.expanduser("~"), ".portal_frame")
_RECENT_FILE = os.path.join(_APP_DIR, "recent.json")
_LAST_SESSION = os.path.join(_APP_DIR, "last_session.json")


def collect_config(app) -> dict:
    """Serialize all GUI state to a config dict."""
    cfg = {"version": 1}

    cfg["geometry"] = {
        "span": app.span.get(),
        "eave_height": app.eave.get(),
        "roof_pitch": app.pitch.get(),
        "roof_pitch_2": app.pitch2.get(),
        "bay_spacing": app.bay.get(),
        "roof_type": app.roof_type_var.get(),
        "building_depth": app.building_depth.get(),
    }
    cfg["sections"] = {
        "column": app.col_section.get(),
        "rafter": app.raf_section.get(),
        "col_Le": app.col_Le.get(),
        "raf_Le": app.raf_Le.get(),
    }
    cfg["serviceability"] = {
        "apex_wind_ratio": int(round(app.apex_limit_wind.get())),
        "apex_eq_ratio": int(round(app.apex_limit_eq.get())),
        "apex_dead_ratio": int(round(app.apex_limit_dead.get())),
        "drift_wind_ratio": int(round(app.drift_limit_wind.get())),
        "drift_eq_ratio": int(round(app.drift_limit_eq.get())),
        "drift_eq_uls_ratio": int(round(app.drift_limit_eq_uls.get())),
        "drift_kdm": float(app.drift_kdm.get()),
    }
    cfg["supports"] = {
        "left_base": app.left_support.get(),
        "right_base": app.right_support.get(),
        "fixity_percent": float(app.fixity_pct.get() or "0"),
        "sls_partial_only": bool(app.sls_partial_only.get())
        if hasattr(app, "sls_partial_only") else True,
    }
    cfg["loads"] = {
        "dead_load_roof": app.dead_roof.get(),
        "dead_load_wall": app.dead_wall.get(),
        "live_load_roof": app.live_roof.get(),
        "include_self_weight": app.self_weight_var.get(),
    }
    cfg["wind"] = {
        "qu": app.qu.get(),
        "qs": app.qs.get(),
        "kc_e": app.kc_e.get(),
        "kc_i": app.kc_i.get(),
        "cpi_uplift": float(app.cpi_uplift_var.get()),
        "cpi_downward": float(app.cpi_downward_var.get()),
        "windward_wall_cpe": float(app.cp_vars["cp_ww"].get()),
    }
    cfg["earthquake"] = {
        "enabled": app.eq_enabled_var.get(),
        "location": app.eq_location.get(),
        "Z": app.eq_Z.get(),
        "soil_class": app.eq_soil.get(),
        "ductility": app.eq_ductility.get(),
        "mu": app.eq_mu.get(),
        "Sp": app.eq_Sp.get(),
        "Sp_sls": app.eq_Sp_sls.get(),
        "R_uls": app.eq_R_uls.get(),
        "R_sls": app.eq_R_sls.get(),
        "near_fault": app.eq_near_fault.get(),
        "extra_mass": app.eq_extra_mass.get(),
        "T1_override": app.eq_T1_override.get(),
    }
    cfg["crane"] = {
        "enabled": app.crane_enabled_var.get(),
        "rail_height": app.crane_rail_height.get(),
        "gc_left": app.crane_gc_left.get(),
        "gc_right": app.crane_gc_right.get(),
        "qc_left": app.crane_qc_left.get(),
        "qc_right": app.crane_qc_right.get(),
        "transverse_uls": [],
        "transverse_sls": [],
    }
    for _, nv, lv, rv in app.crane_hc_uls_rows:
        try:
            cfg["crane"]["transverse_uls"].append({
                "name": nv.get(),
                "left": float(lv.get()),
                "right": float(rv.get()),
            })
        except ValueError:
            pass
    for _, nv, lv, rv in app.crane_hc_sls_rows:
        try:
            cfg["crane"]["transverse_sls"].append({
                "name": nv.get(),
                "left": float(lv.get()),
                "right": float(rv.get()),
            })
        except ValueError:
            pass
    return cfg


def apply_config(app, cfg: dict):
    """Populate all GUI fields from a config dict."""
    # Geometry -- set roof type first (affects pitch2 visibility)
    geo = cfg.get("geometry", {})
    rt = geo.get("roof_type", "gable")
    app.roof_type_var.set(rt)
    app._on_roof_type_change()

    app.span.set(geo.get("span", 12.0))
    app.eave.set(geo.get("eave_height", 4.5))
    app.pitch.set(geo.get("roof_pitch", 5.0))
    app.pitch2.set(geo.get("roof_pitch_2", 5.0))
    app.bay.set(geo.get("bay_spacing", 6.0))
    app.building_depth.set(geo.get("building_depth", 24.0))

    # Sections
    sec = cfg.get("sections", {})
    col = sec.get("column", "63020S2")
    raf = sec.get("rafter", "650180295S2")
    app.col_section.set(col)
    app.raf_section.set(raf)
    app.col_Le.set(sec.get("col_Le", 4.5))
    app.raf_Le.set(sec.get("raf_Le", 6.0))
    app._update_section_info()

    # Serviceability limits
    slsc = cfg.get("serviceability", {})
    app.apex_limit_wind.set(slsc.get("apex_wind_ratio", 180))
    app.apex_limit_eq.set(slsc.get("apex_eq_ratio", 360))
    app.apex_limit_dead.set(slsc.get("apex_dead_ratio", 360))
    app.drift_limit_wind.set(slsc.get("drift_wind_ratio", 150))
    app.drift_limit_eq.set(slsc.get("drift_eq_ratio", 200))
    app.drift_limit_eq_uls.set(slsc.get("drift_eq_uls_ratio", 40))
    app.drift_kdm.set(slsc.get("drift_kdm", 1.2))

    # Supports
    sup = cfg.get("supports", {})
    app.left_support.set(sup.get("left_base", "pinned"))
    app.right_support.set(sup.get("right_base", "pinned"))
    app.fixity_pct.set(f"{float(sup.get('fixity_percent', 0.0)):g}")
    if hasattr(app, "sls_partial_only"):
        app.sls_partial_only.set(bool(sup.get("sls_partial_only", True)))
    if hasattr(app, "_update_fixity_entry_state"):
        app._update_fixity_entry_state()

    # Loads
    ld = cfg.get("loads", {})
    app.dead_roof.set(ld.get("dead_load_roof", 0.15))
    app.dead_wall.set(ld.get("dead_load_wall", 0.10))
    app.live_roof.set(ld.get("live_load_roof", 0.25))
    app.self_weight_var.set(ld.get("include_self_weight", True))

    # Wind
    w = cfg.get("wind", {})
    app.qu.set(w.get("qu", 1.2))
    app.qs.set(w.get("qs", 0.9))
    app.kc_e.set(w.get("kc_e", 0.8))
    app.kc_i.set(w.get("kc_i", 1.0))
    app.cpi_uplift_var.set(str(w.get("cpi_uplift", 0.2)))
    app.cpi_downward_var.set(str(w.get("cpi_downward", -0.3)))
    app.cp_vars["cp_ww"].set(str(w.get("windward_wall_cpe", 0.7)))

    # Earthquake
    eq = cfg.get("earthquake", {})
    app.eq_enabled_var.set(eq.get("enabled", False))
    # Set location first; trigger the callback so the fault-distance
    # label + Z auto-fill run. We then override Z with the explicit
    # saved value so an engineer's manual Z edits are preserved.
    app.eq_location.set(eq.get("location", "Wellington"))
    app._on_eq_location_change()
    app.eq_Z.set(eq.get("Z", 0.40))
    app.eq_soil.set(eq.get("soil_class", "C"))
    # Same pattern for ductility: set preset, fire auto-fill, then
    # override mu/Sp with the explicit saved values.
    app.eq_ductility.set(eq.get(
        "ductility", "Nominally ductile (mu=1.25, Sp=0.925)"))
    app._on_ductility_change()
    app.eq_mu.set(eq.get("mu", 1.25))
    app.eq_Sp.set(eq.get("Sp", 0.925))
    app.eq_Sp_sls.set(eq.get("Sp_sls", 0.7))
    app.eq_R_uls.set(eq.get("R_uls", 1.0))
    app.eq_R_sls.set(eq.get("R_sls", 0.25))
    app.eq_near_fault.set(eq.get("near_fault", 1.0))
    app.eq_extra_mass.set(eq.get("extra_mass", 0.0))
    app.eq_T1_override.set(eq.get("T1_override", 0.0))
    app._on_eq_toggle()

    # Crane
    cr = cfg.get("crane", {})
    app.crane_enabled_var.set(cr.get("enabled", False))
    app.crane_rail_height.set(cr.get("rail_height", 3.0))
    app.crane_gc_left.set(cr.get("gc_left", 0.0))
    app.crane_gc_right.set(cr.get("gc_right", 0.0))
    app.crane_qc_left.set(cr.get("qc_left", 0.0))
    app.crane_qc_right.set(cr.get("qc_right", 0.0))

    # Clear existing transverse rows and rebuild
    while app.crane_hc_uls_rows:
        app._remove_crane_hc_row(app.crane_hc_uls_rows)
    while app.crane_hc_sls_rows:
        app._remove_crane_hc_row(app.crane_hc_sls_rows)

    for row_data in cr.get("transverse_uls", []):
        app._add_crane_hc_row(
            app.crane_hc_uls_frame, app.crane_hc_uls_rows,
            "Hc", len(app.crane_hc_uls_rows) + 1)
        _, nv, lv, rv = app.crane_hc_uls_rows[-1]
        nv.set(row_data.get("name", ""))
        lv.set(str(row_data.get("left", 0.0)))
        rv.set(str(row_data.get("right", 0.0)))

    for row_data in cr.get("transverse_sls", []):
        app._add_crane_hc_row(
            app.crane_hc_sls_frame, app.crane_hc_sls_rows,
            "Hcs", len(app.crane_hc_sls_rows) + 1)
        _, nv, lv, rv = app.crane_hc_sls_rows[-1]
        nv.set(row_data.get("name", ""))
        lv.set(str(row_data.get("left", 0.0)))
        rv.set(str(row_data.get("right", 0.0)))

    app._on_crane_toggle()

    # Regenerate wind cases and update preview
    app._auto_generate_wind_cases()
    app._update_preview()


def save_config(app):
    """Save current configuration to a JSON file."""
    try:
        cfg = collect_config(app)
        filepath = filedialog.asksaveasfilename(
            title="Save Configuration",
            defaultextension=".json",
            filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")],
            initialfile="portal_config.json",
        )
        if filepath:
            with open(filepath, "w") as f:
                json.dump(cfg, f, indent=2)
            add_recent(app, filepath)
            app.status_label.config(
                text=f"Config saved: {os.path.basename(filepath)}",
                fg=COLORS["success"]
            )
    except Exception as e:
        messagebox.showerror("Save Error", str(e))


def load_config(app):
    """Load configuration from a JSON file."""
    filepath = filedialog.askopenfilename(
        title="Load Configuration",
        filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")],
    )
    if filepath:
        open_recent(app, filepath)


def open_recent(app, path):
    """Load a specific config file by path."""
    try:
        with open(path, "r") as f:
            cfg = json.load(f)
        apply_config(app, cfg)
        add_recent(app, path)
        app.status_label.config(
            text=f"Loaded: {os.path.basename(path)}",
            fg=COLORS["success"]
        )
    except FileNotFoundError:
        messagebox.showerror("Load Error", f"File not found:\n{path}")
        # Remove from recent list if file no longer exists
        recent = load_recent_list()
        recent = [p for p in recent if p != path]
        save_recent_list(recent)
        update_recent_menu(app)
    except (json.JSONDecodeError, Exception) as e:
        messagebox.showerror("Load Error", str(e))


def load_recent_list() -> list:
    """Read the recent files list from disk."""
    try:
        with open(_RECENT_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def save_recent_list(recent: list):
    """Write the recent files list to disk."""
    try:
        os.makedirs(_APP_DIR, exist_ok=True)
        with open(_RECENT_FILE, "w") as f:
            json.dump(recent, f, indent=2)
    except Exception:
        pass


def add_recent(app, path):
    """Add a path to the recent list, trim to 10, save, and update menu."""
    path = os.path.abspath(path)
    recent = load_recent_list()
    # Remove if already present, then prepend
    recent = [p for p in recent if p != path]
    recent.insert(0, path)
    recent = recent[:10]
    save_recent_list(recent)
    update_recent_menu(app)


def update_recent_menu(app):
    """Rebuild the Recent dropdown menu from the recent files list."""
    app._recent_menu.delete(0, "end")
    recent = load_recent_list()
    if not recent:
        app._recent_menu.add_command(label="(no recent files)", state="disabled")
        return
    for path in recent:
        display = os.path.basename(path)
        app._recent_menu.add_command(
            label=display,
            command=lambda p=path: app._open_recent(p),
        )


def on_close(app):
    """Auto-save session state on window close."""
    try:
        cfg = collect_config(app)
        os.makedirs(_APP_DIR, exist_ok=True)
        with open(_LAST_SESSION, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
    app.destroy()


def auto_restore(app):
    """Restore last session state on startup."""
    try:
        with open(_LAST_SESSION, "r") as f:
            cfg = json.load(f)
        apply_config(app, cfg)
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        pass
