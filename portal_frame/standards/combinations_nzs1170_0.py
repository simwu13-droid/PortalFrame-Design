"""AS/NZS 1170.0:2002 Load Combinations (incl Amdt 1-5).

Clause 4.2.2 Strength + Table 4.1
For "All other roofs": psi_s=0.7, psi_l=0.0, psi_c=0.0
"""

from dataclasses import dataclass


@dataclass
class LoadCombination:
    """A single load combination with name, description, factors, and output case number."""
    name: str             # e.g., "ULS-1"
    description: str      # e.g., "1.35G"
    factors: dict         # e.g., {"G": 1.35}
    case_number: int      # Output case number (101+, 201+)


def build_combinations(
    wind_case_names: list[str],
    ws_factor: float = 1.0,
    eq_case_names: list[str] | None = None,
    eq_sls_factor: float = 1.0,
    crane_gc_name: str | None = None,
    crane_qc_name: str | None = None,
    crane_hc_uls_names: list[str] | None = None,
    crane_hc_sls_names: list[str] | None = None,
):
    """Build full combo list including wind, earthquake and crane cases per AS/NZS 1170.0:2002.

    ULS combos are numbered sequentially (ULS-1, ULS-2, ...).
    SLS combos are numbered sequentially (SLS-1, SLS-2, ...) and start
    at combo number 201 in the output.

    Returns (uls_combos, sls_combos, groups) where uls/sls are lists of
    tuples (name, description, factors_dict), and groups is a dict mapping
    group names to (start_idx, end_idx) 0-based index ranges.

    Args:
        wind_case_names: List of wind case names (e.g. ["W1", "W2", ...])
        ws_factor: SLS wind scaling factor (qs/qu). Wind cases store Wu
            pressures; SLS combos scale by this factor to get Ws effect.
            Default 1.0 (conservative -- uses Wu for SLS).
        eq_case_names: List of earthquake case names (e.g. ["E+", "E-"]).
            EQ ULS uses G factor = 1.0 (not 1.2); Q drops out (psi_c=0 for
            roofs). EQ SLS uses eq_sls_factor on the earthquake case.
            Default None (no earthquake combos).
        eq_sls_factor: SLS scaling factor applied to earthquake cases.
            Default 1.0.
        crane_gc_name: Crane dead load case name (e.g. "Gc"). If None,
            no crane combos are generated.
        crane_qc_name: Crane live load case name (e.g. "Qc").
        crane_hc_uls_names: Crane transverse ULS case names (pre-factored).
        crane_hc_sls_names: Crane transverse SLS case names.
    """
    if eq_case_names is None:
        eq_case_names = []

    groups = {}

    uls = []
    uls_n = 1
    # Static ULS combos
    uls_gq_start = uls_n - 1  # 0-based index
    uls.append((f"ULS-{uls_n}", "1.35G", {"G": 1.35})); uls_n += 1
    uls.append((f"ULS-{uls_n}", "1.2G + 1.5Q", {"G": 1.2, "Q": 1.5})); uls_n += 1
    groups["uls_gq"] = (uls_gq_start, uls_n - 2)  # 0-based end index

    # Wind ULS combos
    if wind_case_names:
        uls_wind_start = uls_n - 1
        for wname in wind_case_names:
            uls.append((f"ULS-{uls_n}", f"1.2G + {wname}", {"G": 1.2, wname: 1.0})); uls_n += 1
            uls.append((f"ULS-{uls_n}", f"0.9G + {wname}", {"G": 0.9, wname: 1.0})); uls_n += 1
        groups["uls_wind"] = (uls_wind_start, uls_n - 2)

    # Earthquake ULS combos: 1.0G + E
    if eq_case_names:
        uls_eq_start = uls_n - 1
        for ename in eq_case_names:
            uls.append((f"ULS-{uls_n}", f"1.0G + {ename}", {"G": 1.0, ename: 1.0})); uls_n += 1
        groups["uls_eq"] = (uls_eq_start, uls_n - 2)

    sls = []
    sls_n = 1
    # Static SLS combos
    sls.append((f"SLS-{sls_n}", "G + 0.7Q", {"G": 1.0, "Q": 0.7})); sls_n += 1
    sls.append((f"SLS-{sls_n}", "G", {"G": 1.0})); sls_n += 1
    # Wind SLS combos
    if wind_case_names:
        sls_wind_start = sls_n - 1
        for wname in wind_case_names:
            sls.append((f"SLS-{sls_n}", f"G + {wname}(s)", {"G": 1.0, wname: ws_factor})); sls_n += 1
        groups["sls_wind"] = (sls_wind_start, sls_n - 2)

    # Earthquake SLS combos: G + E(s)
    if eq_case_names:
        sls_eq_start = sls_n - 1
        for ename in eq_case_names:
            sls.append((f"SLS-{sls_n}", f"G + {ename}(s)", {"G": 1.0, ename: eq_sls_factor})); sls_n += 1
        groups["sls_eq"] = (sls_eq_start, sls_n - 2)

    # --- Crane combinations (when crane IS at this frame) ---
    if crane_gc_name is not None:
        gc = crane_gc_name
        qc = crane_qc_name
        hc_uls = crane_hc_uls_names or []
        hc_sls = crane_hc_sls_names or []

        # ULS with crane
        uls.append((f"ULS-{uls_n}", f"1.35(G+{gc})", {"G": 1.35, gc: 1.35})); uls_n += 1
        uls.append((f"ULS-{uls_n}", f"1.2(G+{gc}) + 1.5Q", {"G": 1.2, gc: 1.2, "Q": 1.5})); uls_n += 1
        if qc:
            uls.append((f"ULS-{uls_n}", f"1.2(G+{gc}) + 1.5{qc}", {"G": 1.2, gc: 1.2, qc: 1.5})); uls_n += 1
            for hname in hc_uls:
                uls.append((f"ULS-{uls_n}", f"1.2(G+{gc}) + 1.5{qc} + {hname}",
                            {"G": 1.2, gc: 1.2, qc: 1.5, hname: 1.0})); uls_n += 1
        for hname in hc_uls:
            uls.append((f"ULS-{uls_n}", f"0.9(G+{gc}) + {hname}",
                        {"G": 0.9, gc: 0.9, hname: 1.0})); uls_n += 1
        for wname in wind_case_names:
            uls.append((f"ULS-{uls_n}", f"1.2(G+{gc}) + {wname}",
                        {"G": 1.2, gc: 1.2, wname: 1.0})); uls_n += 1
            uls.append((f"ULS-{uls_n}", f"0.9(G+{gc}) + {wname}",
                        {"G": 0.9, gc: 0.9, wname: 1.0})); uls_n += 1
        for ename in eq_case_names:
            uls.append((f"ULS-{uls_n}", f"1.0(G+{gc}) + {ename}",
                        {"G": 1.0, gc: 1.0, ename: 1.0})); uls_n += 1

        # SLS with crane
        sls.append((f"SLS-{sls_n}", f"(G+{gc}) + 0.7Q", {"G": 1.0, gc: 1.0, "Q": 0.7})); sls_n += 1
        sls.append((f"SLS-{sls_n}", f"(G+{gc})", {"G": 1.0, gc: 1.0})); sls_n += 1
        for wname in wind_case_names:
            sls.append((f"SLS-{sls_n}", f"(G+{gc}) + {wname}(s)",
                        {"G": 1.0, gc: 1.0, wname: ws_factor})); sls_n += 1
        for ename in eq_case_names:
            sls.append((f"SLS-{sls_n}", f"(G+{gc}) + {ename}(s)",
                        {"G": 1.0, gc: 1.0, ename: eq_sls_factor})); sls_n += 1
        if qc:
            sls.append((f"SLS-{sls_n}", f"(G+{gc}) + {qc}(s)",
                        {"G": 1.0, gc: 1.0, qc: 1.0})); sls_n += 1
        for hname in hc_sls:
            sls.append((f"SLS-{sls_n}", f"(G+{gc}) + {hname}",
                        {"G": 1.0, gc: 1.0, hname: 1.0})); sls_n += 1

    # Wind-only SLS: pure Ws per wind case (no G)
    if wind_case_names:
        sls_wo_start = sls_n - 1  # 0-based index
        for wname in wind_case_names:
            sls.append((f"SLS-{sls_n}", f"{wname}(s) wind only", {wname: ws_factor}))
            sls_n += 1
        groups["sls_wind_only"] = (sls_wo_start, sls_n - 2)

    return uls, sls, groups
