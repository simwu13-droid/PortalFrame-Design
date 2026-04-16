"""AS/NZS 4600 cold-formed steel member capacity checks.

Capacity values for compression and major-axis bending are looked up from
Formsteel's pre-computed span table (`docs/CFS_Span_Table.xlsx`). Tension
capacity is computed directly from Eq 3.2.2(2):

    Nt = 0.85 * kt * An * fu

with kt=1, An=Ag, fu=550 MPa for G550 sheet steel.

The combined check uses the simple linear interaction:

    util_combined = |N*|/φN + |M*|/φM_bx ≤ 1.0

This is conservative — the more accurate AS/NZS 4600 Cl 3.5.1 with moment
amplification factor αn is intentionally omitted for v1.

Shear is deferred until Formsteel provides the corresponding table.
"""

from portal_frame.analysis.results import MemberDesignCheck
from portal_frame.models.geometry import FrameTopology
from portal_frame.models.sections import CFS_Section
from portal_frame.standards.cfs_span_table import phi_Mbx, phi_Nc, phi_Vy

G550_FU_MPA = 550.0
TENSION_K = 0.85   # 0.85 coefficient in Eq 3.2.2(2)


def phi_Nt(section: CFS_Section) -> float:
    """Tension capacity Nt (kN) per AS/NZS 4600 Eq 3.2.2(2).

    Nt = 0.85 * kt * An * fu  with kt=1, An=Ag, fu=550 MPa.
    Section.Ax is in mm², so result in N is divided by 1000 to give kN.
    """
    return TENSION_K * section.Ax * G550_FU_MPA / 1000.0


def check_member(
    member_id: int,
    member_role: str,
    section: CFS_Section,
    L_eff: float,
    N_max_compression: float,
    N_max_tension: float,
    M_max: float,
    V_max: float = 0.0,
    controlling_combo_n: str = "",
    controlling_combo_m: str = "",
    controlling_combo_v: str = "",
) -> MemberDesignCheck:
    """Run bending, axial, shear, and combined checks on one member.

    Args:
        member_id: topology member id (for display)
        member_role: "col" or "raf"
        section: the CFS section assigned to this member
        L_eff: effective length (m) used for compression buckling and
            lateral-torsional bending lookups (shear is L-independent)
        N_max_compression: largest compressive force in member (kN, ≥ 0)
        N_max_tension: largest tensile force in member (kN, ≥ 0)
        M_max: largest |moment| (kNm)
        V_max: largest |shear| (kN)
        controlling_combo_*: combo names for display
    """
    pNc = phi_Nc(section.name, L_eff)
    pNt = phi_Nt(section)
    pMbx = phi_Mbx(section.name, L_eff)
    pVy = phi_Vy(section.name)

    # NO_DATA path: if any of the three span-table-sourced capacities is
    # missing, mark NO_DATA. Tension is always computable.
    if pNc is None or pMbx is None or pVy is None:
        return MemberDesignCheck(
            member_id=member_id,
            member_role=member_role,
            section_name=section.name,
            L_eff=L_eff,
            phi_Nc=pNc,
            phi_Nt=pNt,
            phi_Mbx=pMbx,
            phi_Vy=pVy,
            N_compression=N_max_compression,
            N_tension=N_max_tension,
            M_max=M_max,
            V_max=V_max,
            util_axial=0.0,
            util_bending=0.0,
            util_shear=0.0,
            util_combined=0.0,
            status="NO_DATA",
            controlling_combo_n=controlling_combo_n,
            controlling_combo_m=controlling_combo_m,
            controlling_combo_v=controlling_combo_v,
        )

    # Axial: pick the worst of (compression / φNc) and (tension / φNt)
    util_c = N_max_compression / pNc if pNc > 0 else 0.0
    util_t = N_max_tension / pNt if pNt > 0 else 0.0
    util_axial = max(util_c, util_t)

    # Bending
    util_bending = M_max / pMbx if pMbx > 0 else 0.0

    # Shear — separate check, not part of linear interaction (per AS/NZS 4600,
    # shear is checked independently against φVy; combined shear+moment is
    # Cl 3.3.5 but the simpler separate check is common practice for
    # CFS members where shear rarely governs)
    util_shear = V_max / pVy if pVy > 0 else 0.0

    # Combined: simple linear interaction for axial + bending
    util_combined = util_axial + util_bending

    # Status FAILs if ANY check fails
    fails = (util_combined > 1.0) or (util_shear > 1.0)
    status = "FAIL" if fails else "PASS"

    return MemberDesignCheck(
        member_id=member_id,
        member_role=member_role,
        section_name=section.name,
        L_eff=L_eff,
        phi_Nc=pNc,
        phi_Nt=pNt,
        phi_Mbx=pMbx,
        phi_Vy=pVy,
        N_compression=N_max_compression,
        N_tension=N_max_tension,
        M_max=M_max,
        V_max=V_max,
        util_axial=util_axial,
        util_bending=util_bending,
        util_shear=util_shear,
        util_combined=util_combined,
        status=status,
        controlling_combo_n=controlling_combo_n,
        controlling_combo_m=controlling_combo_m,
        controlling_combo_v=controlling_combo_v,
    )


def check_all_members(
    topology: FrameTopology,
    envelope_curves: tuple | None,
    column_section: CFS_Section,
    rafter_section: CFS_Section,
    L_col: float,
    L_raf: float,
    combo_results: dict | None = None,
) -> list[MemberDesignCheck]:
    """Run design checks for every member in the topology.

    Forces are taken from the ULS envelope curves (max and min CaseResult
    pair). For each member, the worst N (max +ve / min -ve) and worst |M|
    across all stations are extracted and fed to `check_member`.

    Section assignment: Member.section_id 1 = column, 2 = rafter.
    L_col is used for column members, L_raf for rafters.

    `combo_results` is optional and used only to back out which named combo
    drives each extreme (for display). When omitted the controlling combo
    fields are left empty.
    """
    if envelope_curves is None:
        return []
    max_cr, min_cr = envelope_curves

    checks: list[MemberDesignCheck] = []
    for mid, member in topology.members.items():
        is_column = member.section_id == 1
        section = column_section if is_column else rafter_section
        role = "col" if is_column else "raf"
        L_eff = L_col if is_column else L_raf

        if mid not in max_cr.members or mid not in min_cr.members:
            continue

        max_stations = max_cr.members[mid].stations
        min_stations = min_cr.members[mid].stations

        # Extract envelope extremes from the max/min station pairs
        N_max_pos = max(st.axial for st in max_stations)   # most tensile
        N_max_neg = min(st.axial for st in min_stations)   # most compressive
        M_extreme = max(
            max(abs(st.moment) for st in max_stations),
            max(abs(st.moment) for st in min_stations),
        )
        V_extreme = max(
            max(abs(st.shear) for st in max_stations),
            max(abs(st.shear) for st in min_stations),
        )

        N_compression = abs(min(N_max_neg, 0.0))
        N_tension = max(N_max_pos, 0.0)

        combo_n = ""
        combo_m = ""
        combo_v = ""
        if combo_results:
            combo_n, combo_m, combo_v = _find_controlling_combos(
                mid, combo_results, N_max_neg, N_max_pos, M_extreme, V_extreme,
            )

        checks.append(check_member(
            member_id=mid,
            member_role=role,
            section=section,
            L_eff=L_eff,
            N_max_compression=N_compression,
            N_max_tension=N_tension,
            M_max=M_extreme,
            V_max=V_extreme,
            controlling_combo_n=combo_n,
            controlling_combo_m=combo_m,
            controlling_combo_v=combo_v,
        ))

    return checks


def _find_controlling_combos(
    mid: int,
    combo_results: dict,
    N_compression_extreme: float,
    N_tension_extreme: float,
    M_abs_extreme: float,
    V_abs_extreme: float = 0.0,
    tol: float = 1e-3,
) -> tuple[str, str, str]:
    """Walk per-combo results to find which combo set the envelope extremes.

    Returns (axial_combo, moment_combo, shear_combo). Empty strings if not
    found (e.g. only ULS combos present and the search found no match).
    """
    axial_combo = ""
    moment_combo = ""
    shear_combo = ""

    # Pick whichever axial sign is governing
    use_compression = abs(N_compression_extreme) >= abs(N_tension_extreme)
    target_n = N_compression_extreme if use_compression else N_tension_extreme

    for cname, cr in combo_results.items():
        if not cname.startswith("ULS"):
            continue
        if mid not in cr.members:
            continue
        mr = cr.members[mid]
        if not mr.stations:
            continue
        if use_compression:
            local_n = min(st.axial for st in mr.stations)
        else:
            local_n = max(st.axial for st in mr.stations)
        local_m = max(abs(st.moment) for st in mr.stations)
        local_v = max(abs(st.shear) for st in mr.stations)
        if not axial_combo and abs(local_n - target_n) < tol:
            axial_combo = cname
        if not moment_combo and abs(local_m - M_abs_extreme) < tol:
            moment_combo = cname
        if not shear_combo and abs(local_v - V_abs_extreme) < tol:
            shear_combo = cname
        if axial_combo and moment_combo and shear_combo:
            break
    return axial_combo, moment_combo, shear_combo
