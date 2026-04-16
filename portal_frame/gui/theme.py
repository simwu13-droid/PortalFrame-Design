"""Shared theme constants for the GUI."""

COLORS = {
    "bg":           "#1e1e1e",
    "bg_panel":     "#252526",
    "bg_input":     "#2d2d30",
    "bg_header":    "#007acc",
    "fg":           "#cccccc",
    "fg_dim":       "#808080",
    "fg_bright":    "#ffffff",
    "accent":       "#007acc",
    "accent_hover": "#1a8ad4",
    "success":      "#4ec9b0",
    "warning":      "#dcdcaa",
    "error":        "#f44747",
    "border":       "#3e3e42",
    "canvas_bg":    "#1a1a2e",
    "canvas_grid":  "#2a2a3e",
    "hud_bg":       "#2d2d30",
    "hud_bg_hover": "#3e3e42",
    "frame_col":        "#4ec9b0",
    "frame_col_dim":    "#2a5c54",  # Dimmed teal for deflection overlay
    "frame_raf":        "#569cd6",
    "frame_raf_dim":    "#2c4e6a",  # Dimmed blue for deflection overlay
    "frame_load":   "#dcdcaa",
    "frame_node":   "#ffffff",
    "frame_support":"#ce9178",
    "diagram_moment":    "#e06c75",
    "diagram_shear":     "#c678dd",
    "diagram_axial":     "#e5c07b",
    "analyse_btn":       "#2d7d46",
    "analyse_btn_hover": "#38a055",
    # Design check overlay colours
    "dc_pass":           "#4ec9b0",   # green: util <= 0.85
    "dc_warn":           "#dcdcaa",   # amber: 0.85 < util <= 1.0
    "dc_fail":           "#f44747",   # red:   util > 1.0
    "dc_nodata":         "#808080",   # grey: section has no span table data
}

FONT_FAMILY = "Segoe UI"
FONT = (FONT_FAMILY, 9)
FONT_BOLD = (FONT_FAMILY, 9, "bold")
FONT_HEADER = (FONT_FAMILY, 11, "bold")
FONT_TITLE = (FONT_FAMILY, 14, "bold")
FONT_SMALL = (FONT_FAMILY, 8)
FONT_MONO = ("Consolas", 9)
