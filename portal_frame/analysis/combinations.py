"""Post-processing: linear combination and envelope computation."""

from portal_frame.analysis.results import (
    CaseResult, MemberResult, MemberStationResult,
    NodeResult, ReactionResult, AnalysisOutput, EnvelopeEntry,
)


def combine_case_results(
    case_results: dict[str, CaseResult],
    factors: dict[str, float],
    combo_name: str,
) -> CaseResult:
    """Linearly combine per-case results: combo = sum(factor_i * case_i)."""
    ref_case = next(iter(case_results.values()))

    members = {}
    for mid, ref_mr in ref_case.members.items():
        stations = []
        for j, ref_st in enumerate(ref_mr.stations):
            axial = shear = moment = dy_local = dx_local = 0.0
            for cname, factor in factors.items():
                if cname in case_results and mid in case_results[cname].members:
                    st = case_results[cname].members[mid].stations[j]
                    axial += factor * st.axial
                    shear += factor * st.shear
                    moment += factor * st.moment
                    dy_local += factor * st.dy_local
                    dx_local += factor * st.dx_local
            stations.append(MemberStationResult(
                ref_st.position, ref_st.position_pct,
                axial, shear, moment, dy_local, dx_local,
            ))
        mr = MemberResult(mid, stations)
        mr.compute_extremes()
        members[mid] = mr

    deflections = {}
    for nid, ref_nd in ref_case.deflections.items():
        dx = dy = rz = 0.0
        for cname, factor in factors.items():
            if cname in case_results and nid in case_results[cname].deflections:
                nd = case_results[cname].deflections[nid]
                dx += factor * nd.dx
                dy += factor * nd.dy
                rz += factor * nd.rz
        deflections[nid] = NodeResult(nid, dx, dy, rz)

    reactions = {}
    for nid, ref_rx in ref_case.reactions.items():
        fx = fy = mz = 0.0
        for cname, factor in factors.items():
            if cname in case_results and nid in case_results[cname].reactions:
                rx = case_results[cname].reactions[nid]
                fx += factor * rx.fx
                fy += factor * rx.fy
                mz += factor * rx.mz
        reactions[nid] = ReactionResult(nid, fx, fy, mz)

    return CaseResult(combo_name, members, deflections, reactions)


def compute_envelopes(output: AnalysisOutput) -> None:
    """Compute ULS and SLS envelopes across all combinations. Mutates output in-place."""
    output.uls_envelope = {}
    output.sls_envelope = {}

    for combo_name, cr in output.combo_results.items():
        is_uls = combo_name.startswith("ULS")
        env = output.uls_envelope if is_uls else output.sls_envelope

        for mid, mr in cr.members.items():
            for st in mr.stations:
                _update_max(env, "max_moment", st.moment, combo_name, mid, st.position_pct)
                _update_min(env, "min_moment", st.moment, combo_name, mid, st.position_pct)
                _update_abs_max(env, "max_shear", st.shear, combo_name, mid, st.position_pct)
                _update_max(env, "max_axial", st.axial, combo_name, mid, st.position_pct)
                _update_min(env, "min_axial", st.axial, combo_name, mid, st.position_pct)

        for nid, nd in cr.deflections.items():
            _update_abs_max(env, "max_dx", nd.dx, combo_name)
            _update_abs_max(env, "max_dy", nd.dy, combo_name)

        for nid, rx in cr.reactions.items():
            _update_abs_max(env, "max_reaction_fy", rx.fy, combo_name)


def _update_max(env, key, value, combo_name, mid=0, pct=0.0):
    if key not in env or value > env[key].value:
        env[key] = EnvelopeEntry(value, combo_name, mid, pct)


def _update_min(env, key, value, combo_name, mid=0, pct=0.0):
    if key not in env or value < env[key].value:
        env[key] = EnvelopeEntry(value, combo_name, mid, pct)


def _update_abs_max(env, key, value, combo_name, mid=0, pct=0.0):
    if key not in env or abs(value) > abs(env[key].value):
        env[key] = EnvelopeEntry(value, combo_name, mid, pct)


def compute_envelope_curves(output: AnalysisOutput) -> None:
    """Compute per-station envelope curves for ULS and SLS combo sets.

    For each combo set (ULS, SLS), produces two synthetic CaseResult objects:
    - envelope_max: max of each attribute at each station across all combos
    - envelope_min: min of each attribute at each station across all combos

    Note: envelope max moment at station j is taken over all ULS combos
    independently of max shear at station j. The resulting CaseResult is
    a display-only construct — it does not represent any single physical
    state — but shows the bounding curves that the member must survive.

    Mutates output in place by setting output.uls_envelope_curves and
    output.sls_envelope_curves.
    """
    output.uls_envelope_curves = _build_envelope_pair(
        output.combo_results, prefix="ULS")
    output.sls_envelope_curves = _build_envelope_pair(
        output.combo_results, prefix="SLS")


def _build_envelope_pair(
    combo_results: dict[str, CaseResult],
    prefix: str,
) -> tuple | None:
    """Build (max, min) CaseResult pair from all combos matching the prefix.

    Returns None if no combos match the prefix.
    """
    matching = {name: cr for name, cr in combo_results.items()
                if name.startswith(prefix)}
    if not matching:
        return None

    # Use the first combo as a structural template for members/nodes
    ref_cr = next(iter(matching.values()))

    # Build max and min CaseResults by walking every station of every combo
    max_members = {}
    min_members = {}
    for mid, ref_mr in ref_cr.members.items():
        n_stations = len(ref_mr.stations)
        max_stations = [
            MemberStationResult(
                position=ref_mr.stations[j].position,
                position_pct=ref_mr.stations[j].position_pct,
                axial=float("-inf"),
                shear=float("-inf"),
                moment=float("-inf"),
                dy_local=float("-inf"),
                dx_local=float("-inf"),
            )
            for j in range(n_stations)
        ]
        min_stations = [
            MemberStationResult(
                position=ref_mr.stations[j].position,
                position_pct=ref_mr.stations[j].position_pct,
                axial=float("inf"),
                shear=float("inf"),
                moment=float("inf"),
                dy_local=float("inf"),
                dx_local=float("inf"),
            )
            for j in range(n_stations)
        ]
        for cr in matching.values():
            if mid not in cr.members:
                continue
            for j, st in enumerate(cr.members[mid].stations):
                if j >= n_stations:
                    break
                ms = max_stations[j]
                if st.axial > ms.axial:
                    ms.axial = st.axial
                if st.shear > ms.shear:
                    ms.shear = st.shear
                if st.moment > ms.moment:
                    ms.moment = st.moment
                if st.dy_local > ms.dy_local:
                    ms.dy_local = st.dy_local
                if st.dx_local > ms.dx_local:
                    ms.dx_local = st.dx_local
                mn = min_stations[j]
                if st.axial < mn.axial:
                    mn.axial = st.axial
                if st.shear < mn.shear:
                    mn.shear = st.shear
                if st.moment < mn.moment:
                    mn.moment = st.moment
                if st.dy_local < mn.dy_local:
                    mn.dy_local = st.dy_local
                if st.dx_local < mn.dx_local:
                    mn.dx_local = st.dx_local

        max_mr = MemberResult(member_id=mid, stations=max_stations)
        max_mr.compute_extremes()
        max_members[mid] = max_mr
        min_mr = MemberResult(member_id=mid, stations=min_stations)
        min_mr.compute_extremes()
        min_members[mid] = min_mr

    # Envelope CaseResults don't carry meaningful deflections/reactions at
    # the node level — those would need separate per-node envelopes. Leave
    # them empty; the renderer only uses members[].stations[] for curves.
    max_cr = CaseResult(
        case_name=f"{prefix} Envelope Max",
        members=max_members,
        deflections={},
        reactions={},
    )
    min_cr = CaseResult(
        case_name=f"{prefix} Envelope Min",
        members=min_members,
        deflections={},
        reactions={},
    )
    return (max_cr, min_cr)
