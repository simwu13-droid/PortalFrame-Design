"""Post-processing: linear combination and envelope computation."""

from portal_frame.analysis.results import (
    CaseResult, MemberResult, MemberStationResult,
    NodeResult, ReactionResult, AnalysisOutput, EnvelopeEntry,
)

_STATION_FIELDS = ("axial", "shear", "moment", "dy_local", "dx_local")
_NODE_FIELDS = ("dx", "dy", "rz")
_REACTION_FIELDS = ("fx", "fy", "mz")


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
            acc = {f: 0.0 for f in _STATION_FIELDS}
            for cname, factor in factors.items():
                if cname in case_results and mid in case_results[cname].members:
                    st = case_results[cname].members[mid].stations[j]
                    for f in _STATION_FIELDS:
                        acc[f] += factor * getattr(st, f)
            stations.append(MemberStationResult(
                ref_st.position, ref_st.position_pct, **acc,
            ))
        mr = MemberResult(mid, stations)
        mr.compute_extremes()
        members[mid] = mr

    deflections = {}
    for nid in ref_case.deflections:
        acc = {f: 0.0 for f in _NODE_FIELDS}
        for cname, factor in factors.items():
            if cname in case_results and nid in case_results[cname].deflections:
                nd = case_results[cname].deflections[nid]
                for f in _NODE_FIELDS:
                    acc[f] += factor * getattr(nd, f)
        deflections[nid] = NodeResult(nid, **acc)

    reactions = {}
    for nid in ref_case.reactions:
        acc = {f: 0.0 for f in _REACTION_FIELDS}
        for cname, factor in factors.items():
            if cname in case_results and nid in case_results[cname].reactions:
                rx = case_results[cname].reactions[nid]
                for f in _REACTION_FIELDS:
                    acc[f] += factor * getattr(rx, f)
        reactions[nid] = ReactionResult(nid, **acc)

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
    """Compute per-station envelope curves for ULS, SLS, and SLS-Wind-Only.

    For each combo set, produces two synthetic CaseResult objects:
    - envelope_max: max of each attribute at each station across all combos
    - envelope_min: min of each attribute at each station across all combos

    Note: envelope max moment at station j is taken over all ULS combos
    independently of max shear at station j. The resulting CaseResult is
    a display-only construct — it does not represent any single physical
    state — but shows the bounding curves that the member must survive.

    Mutates output in place.
    """
    output.uls_envelope_curves = _build_envelope_pair(
        output.combo_results, prefix="ULS")
    output.sls_envelope_curves = _build_envelope_pair(
        output.combo_results, prefix="SLS")

    # Wind-only SLS envelope — filter by description substring
    wind_only_names = {
        name for name, desc in output.combo_descriptions.items()
        if name.startswith("SLS") and "wind only" in desc.lower()
    }
    if wind_only_names:
        output.sls_wind_only_envelope_curves = _build_envelope_pair(
            output.combo_results, prefix="SLS",
            name_filter=lambda n: n in wind_only_names)
    else:
        output.sls_wind_only_envelope_curves = None


def _build_envelope_pair(
    combo_results: dict[str, CaseResult],
    prefix: str,
    name_filter: callable = None,
) -> tuple | None:
    """Build (max, min) CaseResult pair from all combos matching the prefix.

    If name_filter is supplied, combos must also pass the filter.
    Returns None if no combos match.
    """
    matching = {name: cr for name, cr in combo_results.items()
                if name.startswith(prefix)
                and (name_filter is None or name_filter(name))}
    if not matching:
        return None

    # Use the first combo as a structural template for members/nodes
    ref_cr = next(iter(matching.values()))

    def _make_extreme_station(ref_st, init):
        return MemberStationResult(
            position=ref_st.position,
            position_pct=ref_st.position_pct,
            **{f: init for f in _STATION_FIELDS},
        )

    # Build max and min CaseResults by walking every station of every combo
    max_members = {}
    min_members = {}
    for mid, ref_mr in ref_cr.members.items():
        n_stations = len(ref_mr.stations)
        max_stations = [_make_extreme_station(ref_mr.stations[j], float("-inf"))
                        for j in range(n_stations)]
        min_stations = [_make_extreme_station(ref_mr.stations[j], float("inf"))
                        for j in range(n_stations)]
        for cr in matching.values():
            if mid not in cr.members:
                continue
            for j, st in enumerate(cr.members[mid].stations):
                if j >= n_stations:
                    break
                ms = max_stations[j]
                mn = min_stations[j]
                for f in _STATION_FIELDS:
                    v = getattr(st, f)
                    if v > getattr(ms, f):
                        setattr(ms, f, v)
                    if v < getattr(mn, f):
                        setattr(mn, f, v)

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
