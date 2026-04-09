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
            axial = shear = moment = 0.0
            for cname, factor in factors.items():
                if cname in case_results and mid in case_results[cname].members:
                    st = case_results[cname].members[mid].stations[j]
                    axial += factor * st.axial
                    shear += factor * st.shear
                    moment += factor * st.moment
            stations.append(MemberStationResult(
                ref_st.position, ref_st.position_pct,
                axial, shear, moment,
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
