"""Wind-case synthesis — generate 8 standard NZS 1170.2 wind cases from geometry."""

from tkinter import messagebox

from portal_frame.models.loads import WindCase, RafterZoneLoad
from portal_frame.standards.wind_nzs1170_2 import (
    get_surface_coefficients, cfig, roof_cpe_zones, mirror_zones,
)


def get_h_and_depth(app):
    geom = app._build_geometry()
    h = (geom.eave_height + geom.ridge_height) / 2.0
    depth = app.building_depth.get()
    return h, depth


def get_wind_params(app):
    """Return current wind parameters for WindSurfacePanel recalculation."""
    try:
        cpi_up = float(app.cpi_uplift_var.get())
    except ValueError:
        cpi_up = 0.2
    try:
        cpi_dn = float(app.cpi_downward_var.get())
    except ValueError:
        cpi_dn = -0.3
    return {
        "qu": app.qu.get(),
        "qs": app.qs.get(),
        "kc_e": app.kc_e.get(),
        "kc_i": app.kc_i.get(),
        "cpi_uplift": cpi_up,
        "cpi_downward": cpi_dn,
    }


def auto_generate_wind_cases(app):
    """Populate the surface table with Cp,e values from NZS 1170.2 lookup."""
    try:
        span = app.span.get()
        eave = app.eave.get()
        pitch = app.pitch.get()
        depth = app.building_depth.get()

        def cpf(key):
            try:
                return float(app.cp_vars[key].get())
            except ValueError:
                return 0.0

        geom = app._build_geometry()
        pitch_2 = geom.right_pitch if geom.roof_type == "gable" else None

        surface_data = get_surface_coefficients(
            span=span, eave_height=eave, roof_pitch=pitch,
            building_depth=depth,
            windward_wall_cpe=cpf("cp_ww"),
            roof_type=app.roof_type_var.get(),
            roof_pitch_2=pitch_2,
        )
        h = surface_data["h"]
        d_over_b = surface_data["d_over_b"]
        h_over_d = surface_data["h_over_d"]
        lw_cpe = surface_data["walls"]["leeward_cpe"]

        app.wind_ratios_label.config(
            text=f"h={h:.2f}m  d/b={d_over_b:.3f}  h/d={h_over_d:.3f}  "
                 f"Leeward Cp,e={lw_cpe:.2f}"
        )

        app.wind_table.populate(surface_data)
        app.refresh_load_case_list()
        app._update_preview()

    except Exception as e:
        messagebox.showerror("Wind Generation Error", str(e))


def synthesize_wind_cases(app):
    """Synthesize 8 wind cases from the surface table Cp,e values.

    Uses the current geometry and wind parameters to build zone-based
    crosswind cases (W1-W4) and uniform transverse cases (W5-W8).
    Returns list of WindCase objects with Wu pressures (kPa).
    """
    p = get_wind_params(app)
    qu = p["qu"]
    kc_e = p["kc_e"]
    kc_i = p["kc_i"]
    cpi_up = p["cpi_uplift"]
    cpi_dn = p["cpi_downward"]

    sd = app.wind_table.get_surface_data()
    ww_cpe = sd["windward_cpe"]
    lw_cpe = sd["leeward_cpe"]
    side_cpes = sd["side_cpes"]
    roof_up = sd["roof_zones_up"]
    roof_dn = sd["roof_zones_dn"]
    roof_uniform = sd.get("roof_uniform", {})

    side_worst = min(side_cpes) if side_cpes else -0.65

    def wu(cpe, cpi):
        return round(cfig(cpe, cpi, kc_e, kc_i) * qu, 4)

    # Get geometry for zone splitting
    geom = app._build_geometry()
    span = geom.span
    h = (geom.eave_height + geom.ridge_height) / 2.0
    h_over_d = h / span if span > 0 else 0.5
    split_pct = (geom.apex_x / span * 100.0) if span > 0 else 50.0

    # Standard Table 5.3(A) zone lookup (NOT from GUI which may show per-rafter data)
    zone_table = roof_cpe_zones(h_over_d)
    # Transverse uses first zone (0-0.5h) as worst-case — matches reference
    roof_worst_up = zone_table[0][2]
    roof_worst_dn = zone_table[0][3]

    def _build_full_zones(cpi_val, use_uplift):
        """Build full-span RafterZoneLoad list from Table 5.3(A) Cp,e values."""
        zones = []
        for s_mult, e_mult, cpe_up, cpe_dn in zone_table:
            start_m = s_mult * h
            if start_m >= span:
                break
            end_m = span if e_mult is None else min(e_mult * h, span)
            start_pct = (start_m / span) * 100.0
            end_pct = (end_m / span) * 100.0
            cpe = cpe_up if use_uplift else cpe_dn
            zones.append(RafterZoneLoad(
                start_pct=round(start_pct, 1),
                end_pct=round(end_pct, 1),
                pressure=wu(cpe, cpi_val),
            ))
        return zones

    def _split_zones(full_zones, split_pct):
        """Split full-span zones at the ridge into left/right rafter zones.

        NOTE: Not consolidated with wind_nzs1170_2._split_zones_to_rafters
        which has micro-zone filtering (<0.05%) that would change output.
        """
        left, right = [], []
        for z in full_zones:
            if z.end_pct <= split_pct:
                # Entirely on left rafter
                new_start = z.start_pct / split_pct * 100.0
                new_end = z.end_pct / split_pct * 100.0
                left.append(RafterZoneLoad(round(new_start, 1),
                                           round(new_end, 1), z.pressure))
            elif z.start_pct >= split_pct:
                # Entirely on right rafter
                r_span = 100.0 - split_pct
                new_start = (z.start_pct - split_pct) / r_span * 100.0
                new_end = (z.end_pct - split_pct) / r_span * 100.0
                right.append(RafterZoneLoad(round(new_start, 1),
                                            round(new_end, 1), z.pressure))
            else:
                # Straddles the ridge — split into two
                new_end_l = 100.0
                new_start_l = z.start_pct / split_pct * 100.0
                left.append(RafterZoneLoad(round(new_start_l, 1),
                                           round(new_end_l, 1), z.pressure))
                r_span = 100.0 - split_pct
                new_start_r = 0.0
                new_end_r = (z.end_pct - split_pct) / r_span * 100.0
                right.append(RafterZoneLoad(round(new_start_r, 1),
                                            round(new_end_r, 1), z.pressure))
        return left, right

    cases = []
    is_mono = app.roof_type_var.get() == "mono"
    left_pitch = geom.left_pitch if hasattr(geom, 'left_pitch') else geom.roof_pitch
    right_pitch = geom.right_pitch if hasattr(geom, 'right_pitch') else geom.roof_pitch
    roof_type = roof_uniform.get("type", "zones")
    left_uni = roof_uniform.get("left_uniform")
    right_uni = roof_uniform.get("right_uniform")

    # W1-W4: Crosswind (wind across ridge)
    if is_mono and roof_type == "uniform" and left_uni:
        # Mono >= 10 deg: Table 5.3(B) upwind, 5.3(C) downwind — uniform
        for case_num, is_upslope, cpi_val, envelope, desc_env in [
            (1, True,  cpi_up,  "max_uplift",   "max uplift"),
            (2, False, cpi_up,  "max_uplift",   "max uplift"),
            (3, True,  cpi_dn,  "max_downward", "max downward"),
            (4, False, cpi_dn,  "max_downward", "max downward"),
        ]:
            ww_p = wu(ww_cpe, cpi_val)
            lw_p = wu(lw_cpe, cpi_val)
            if is_upslope:
                left_wall, right_wall = ww_p, lw_p
                use_uplift = (envelope == "max_uplift")
                roof_cpe = left_uni[0] if use_uplift else left_uni[1]
            else:
                left_wall, right_wall = lw_p, ww_p
                roof_cpe = right_uni[0] if right_uni else left_uni[0]
            roof_p = wu(roof_cpe, cpi_val)
            dir_label = "Upslope" if is_upslope else "Downslope"
            cases.append(WindCase(
                name=f"W{case_num}",
                description=f"{dir_label} - {desc_env}",
                direction=f"crosswind_{'LR' if is_upslope else 'RL'}",
                envelope=envelope, is_crosswind=False,
                left_wall=left_wall, right_wall=right_wall,
                left_rafter=roof_p, right_rafter=0.0,
            ))
    else:
        # Zone-based crosswind (gable or mono < 10 deg)
        for case_num, is_LR, envelope in [
            (1, True,  "max_uplift"),
            (2, False, "max_uplift"),
            (3, True,  "max_downward"),
            (4, False, "max_downward"),
        ]:
            desc_env = "max uplift" if envelope == "max_uplift" else "max downward"
            dir_label = "L-R" if is_LR else "R-L"
            cpi_val = cpi_up if envelope == "max_uplift" else cpi_dn
            use_uplift = (envelope == "max_uplift")

            ww_p = wu(ww_cpe, cpi_val)
            lw_p = wu(lw_cpe, cpi_val)

            if is_LR:
                left_wall, right_wall = ww_p, lw_p
            else:
                left_wall, right_wall = lw_p, ww_p

            full_zones = _build_full_zones(cpi_val, use_uplift)

            if is_mono:
                rafter_zones = full_zones if is_LR else mirror_zones(full_zones)
                cases.append(WindCase(
                    name=f"W{case_num}",
                    description=f"Crosswind {dir_label} - {desc_env}",
                    direction=f"crosswind_{'LR' if is_LR else 'RL'}",
                    envelope=envelope, is_crosswind=True,
                    left_wall=left_wall, right_wall=right_wall,
                    left_rafter_zones=rafter_zones, right_rafter_zones=[],
                ))
            else:
                # Gable: split zones at ridge, then override per-rafter
                # if that rafter's pitch >= 10 deg
                if is_LR:
                    l_zones, r_zones = _split_zones(full_zones, split_pct)
                    left_role, right_role = "upwind", "downwind"
                else:
                    mirrored = mirror_zones(full_zones)
                    l_zones, r_zones = _split_zones(mirrored, split_pct)
                    left_role, right_role = "downwind", "upwind"

                l_uniform = 0.0
                r_uniform = 0.0

                # Override left rafter if pitch >= 10 deg
                if left_pitch >= 10.0 and left_uni:
                    if left_role == "upwind":
                        cpe = left_uni[0] if use_uplift else left_uni[1]
                    else:
                        # left_uni has (up, dn, downwind) for gable mixed
                        cpe = left_uni[2] if len(left_uni) >= 3 else left_uni[0]
                    l_uniform = wu(cpe, cpi_val)
                    l_zones = []

                # Override right rafter if pitch >= 10 deg
                if right_pitch >= 10.0 and right_uni:
                    if right_role == "upwind":
                        cpe = right_uni[0] if use_uplift else right_uni[1]
                    else:
                        cpe = right_uni[2] if len(right_uni) >= 3 else right_uni[0]
                    r_uniform = wu(cpe, cpi_val)
                    r_zones = []

                has_zones = bool(l_zones or r_zones)
                cases.append(WindCase(
                    name=f"W{case_num}",
                    description=f"Crosswind {dir_label} - {desc_env}",
                    direction=f"crosswind_{'LR' if is_LR else 'RL'}",
                    envelope=envelope, is_crosswind=has_zones,
                    left_wall=left_wall, right_wall=right_wall,
                    left_rafter_zones=l_zones, right_rafter_zones=r_zones,
                    left_rafter=l_uniform, right_rafter=r_uniform,
                ))

    # W5-W8: Transverse (wind along ridge — uniform roof pressure)
    for case_num, is_mirrored, envelope in [
        (5, False, "max_uplift"),
        (6, False, "max_downward"),
        (7, True,  "max_uplift"),
        (8, True,  "max_downward"),
    ]:
        desc_env = "max uplift" if envelope == "max_uplift" else "max downward"
        mir_label = " (mirrored)" if is_mirrored else ""
        cpi_val = cpi_up if envelope == "max_uplift" else cpi_dn
        roof_cpe = roof_worst_up if envelope == "max_uplift" else roof_worst_dn

        sw_p = wu(side_worst, cpi_val)
        roof_p = wu(roof_cpe, cpi_val)

        cases.append(WindCase(
            name=f"W{case_num}",
            description=f"Transverse{mir_label} - {desc_env}",
            direction="transverse_mirrored" if is_mirrored else "transverse",
            envelope=envelope,
            is_crosswind=False,
            left_wall=sw_p, right_wall=sw_p,
            left_rafter=roof_p, right_rafter=roof_p,
        ))

    return cases
