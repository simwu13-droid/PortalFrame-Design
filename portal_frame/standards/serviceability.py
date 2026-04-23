"""Serviceability Limit State (SLS) deflection checks.

Two metrics are supported:

1. **Apex vertical deflection (`apex_dy`)** — the worst |dy| at the ridge
   node, compared against a user-supplied `span/X` limit (typically
   `L/180` for wind and `L/360` for earthquake per NZ practice).

2. **Eave horizontal drift (`drift`)** — the worst |dx| at an eave node
   (top of a column), compared against an `h/X` limit (typically `h/150`
   for wind and `h/300` for earthquake).

Each metric is split into two categories (`wind` / `eq`) by scanning
the combo description substring — an `E+` or `E-` in the description
classifies the combo as earthquake, anything else is wind (or gravity,
bucketed with wind because that's the stricter daily limit).

Rafter midspan, minor-axis deflections, and relative drift between
columns are intentionally out of scope.
"""

from portal_frame.analysis.results import CaseResult, SLSCheck
from portal_frame.models.geometry import FrameTopology


_MAX_REPORTED_RATIO = 9999   # cap for actual_ratio when deflection ~0


def _apex_node_id(topology: FrameTopology) -> int:
    """Highest-y node in the topology. Works for gable, mono, and crane."""
    return max(topology.nodes.values(), key=lambda n: n.y).id


def _eave_node_ids(topology: FrameTopology) -> list[int]:
    """Node IDs at the top of each column (= eave level).

    Uses the existing `get_eave_nodes()` helper which identifies nodes
    connected to both a column member and a rafter member — the natural
    definition of an eave regardless of crane brackets or other
    sub-members.
    """
    return [n.id for n in topology.get_eave_nodes()]


def _topology_span_m(topology: FrameTopology) -> float:
    """Total node x-extent of the topology (max x − min x).

    Used as the source of truth for SLS span/X ratios so the check can
    never get out of sync with the FEM model. For the current gable,
    mono, and crane topologies this equals the engineering clear span
    because no nodes lie outside the column lines. If that assumption
    is ever broken (e.g. cantilever, offset support), revisit this.
    """
    xs = [n.x for n in topology.nodes.values()]
    return max(xs) - min(xs)


def _classify(description: str) -> str:
    """Classify an SLS combo by description substring.

    'E+' or 'E-' in the description -> 'eq'
    Anything else (G, G+0.7Q, G+W*(s), W*(s) wind only) -> 'wind'
    """
    if "E+" in description or "E-" in description:
        return "eq"
    return "wind"


def _actual_ratio(ref_length_mm: float, deflection_mm: float) -> int:
    """The 'X' such that ref_length / X == |deflection|. Capped at 9999.

    i.e. if a 12m span deflected 40mm, the actual ratio is 300 (L/300).
    """
    abs_def = abs(deflection_mm)
    if abs_def < 1e-6 or ref_length_mm <= 0:
        return _MAX_REPORTED_RATIO
    ratio = ref_length_mm / abs_def
    return int(round(min(ratio, _MAX_REPORTED_RATIO)))


def _build_check(
    metric: str,
    category: str,
    deflection_mm: float,
    ratio: int,
    ref_length_m: float,
    ref_symbol: str,
    combo_name: str,
) -> SLSCheck:
    ref_length_mm = ref_length_m * 1000.0
    limit_mm = ref_length_mm / ratio
    util = abs(deflection_mm) / limit_mm if limit_mm > 0 else 0.0
    return SLSCheck(
        metric=metric,
        category=category,
        deflection_mm=deflection_mm,
        limit_mm=limit_mm,
        ratio=ratio,
        actual_ratio=_actual_ratio(ref_length_mm, deflection_mm),
        util=util,
        status="PASS" if util <= 1.0 else "FAIL",
        controlling_combo=combo_name,
        reference_length_m=ref_length_m,
        reference_symbol=ref_symbol,
    )


def _worst_per_category(
    combo_results: dict[str, CaseResult],
    combo_descriptions: dict[str, str],
    extract: callable,   # takes CaseResult -> float | None (signed deflection)
) -> dict[str, tuple[float, str]]:
    """Walk SLS combos, apply `extract` to each, and return
    `{category: (worst_signed_deflection, combo_name)}`.

    Combos that don't contribute (extract returns None) are skipped.
    """
    worst: dict[str, tuple[float, str]] = {}
    for cname, cr in combo_results.items():
        if not cname.startswith("SLS"):
            continue
        val = extract(cr)
        if val is None:
            continue
        cat = _classify(combo_descriptions.get(cname, cname))
        if cat not in worst or abs(val) > abs(worst[cat][0]):
            worst[cat] = (val, cname)
    return worst


def _dead_only_combo(
    combo_results: dict[str, CaseResult],
    combo_descriptions: dict[str, str],
) -> tuple[str, CaseResult] | None:
    """Find the SLS combo whose description is exactly 'G' (dead only).

    Returns (name, case_result) or None if no such combo exists.
    """
    for name, cr in combo_results.items():
        if not name.startswith("SLS"):
            continue
        if combo_descriptions.get(name, "").strip() == "G":
            return name, cr
    return None


def check_apex_deflection(
    topology: FrameTopology,
    combo_results: dict[str, CaseResult],
    combo_descriptions: dict[str, str],
    limit_ratio_wind: int,
    limit_ratio_eq: int,
    limit_ratio_dead: int = 0,
) -> list[SLSCheck]:
    """Apex vertical deflection check.

    Returns up to 3 SLSCheck entries — one per category that has
    matching combos. Span is derived from the topology.

    - wind: worst |dy| across SLS combos classified as wind/gravity.
    - eq:   worst |dy| across SLS combos with E+/E- in description.
    - dead: dy from the SLS combo whose description is exactly 'G'
            (i.e. SLS-2). Skipped if limit_ratio_dead <= 0.
    """
    apex_id = _apex_node_id(topology)
    span_m = _topology_span_m(topology)

    def extract(cr: CaseResult) -> float | None:
        if apex_id not in cr.deflections:
            return None
        return cr.deflections[apex_id].dy

    worst = _worst_per_category(combo_results, combo_descriptions, extract)

    checks: list[SLSCheck] = []
    for cat in ("wind", "eq"):
        if cat not in worst:
            continue
        ratio = limit_ratio_wind if cat == "wind" else limit_ratio_eq
        if ratio <= 0:
            continue
        dy, combo_name = worst[cat]
        checks.append(_build_check(
            metric="apex_dy",
            category=cat,
            deflection_mm=dy,
            ratio=ratio,
            ref_length_m=span_m,
            ref_symbol="L",
            combo_name=combo_name,
        ))

    if limit_ratio_dead > 0:
        dead = _dead_only_combo(combo_results, combo_descriptions)
        if dead is not None:
            name, cr = dead
            dy = extract(cr)
            if dy is not None:
                checks.append(_build_check(
                    metric="apex_dy",
                    category="dead",
                    deflection_mm=dy,
                    ratio=limit_ratio_dead,
                    ref_length_m=span_m,
                    ref_symbol="L",
                    combo_name=name,
                ))
    return checks


def check_eave_drift(
    topology: FrameTopology,
    combo_results: dict[str, CaseResult],
    combo_descriptions: dict[str, str],
    limit_ratio_wind: int,
    limit_ratio_eq: int,
    limit_ratio_eq_uls: int = 0,
    k_dm: float = 1.2,
) -> list[SLSCheck]:
    """Horizontal drift at the eave nodes.

    For each SLS combo, finds the worst |dx| across all eave nodes,
    then reduces per category. Reference length is the eave height
    (column height above ground).

    Categories:
    - wind:   worst |dx| across SLS wind/gravity combos.
    - eq:     worst |dx| across SLS combos with E+/E- in description.
    - eq_uls: worst |dx| across ULS combos with E+/E- in description,
              scaled by k_dm (drift modification factor, per NZS
              1170.5 Cl 7.2). Skipped if limit_ratio_eq_uls <= 0.
    """
    eave_ids = _eave_node_ids(topology)
    if not eave_ids:
        return []
    # All eave nodes are assumed to be at the same height for a simple
    # portal. Use the first one's y as the reference (matches the
    # column height above ground).
    eave_height_m = topology.nodes[eave_ids[0]].y
    if eave_height_m <= 0:
        return []

    def extract(cr: CaseResult) -> float | None:
        worst_dx = 0.0
        found = False
        for nid in eave_ids:
            if nid not in cr.deflections:
                continue
            dx = cr.deflections[nid].dx
            if abs(dx) > abs(worst_dx):
                worst_dx = dx
            found = True
        return worst_dx if found else None

    worst = _worst_per_category(combo_results, combo_descriptions, extract)

    checks: list[SLSCheck] = []
    for cat in ("wind", "eq"):
        if cat not in worst:
            continue
        ratio = limit_ratio_wind if cat == "wind" else limit_ratio_eq
        if ratio <= 0:
            continue
        dx, combo_name = worst[cat]
        checks.append(_build_check(
            metric="drift",
            category=cat,
            deflection_mm=dx,
            ratio=ratio,
            ref_length_m=eave_height_m,
            ref_symbol="h",
            combo_name=combo_name,
        ))

    if limit_ratio_eq_uls > 0:
        worst_dx = 0.0
        worst_name = None
        for name, cr in combo_results.items():
            if not name.startswith("ULS"):
                continue
            desc = combo_descriptions.get(name, "")
            if "E+" not in desc and "E-" not in desc:
                continue
            dx = extract(cr)
            if dx is None:
                continue
            if abs(dx) > abs(worst_dx):
                worst_dx = dx
                worst_name = name
        if worst_name is not None:
            checks.append(_build_check(
                metric="drift",
                category="eq_uls",
                deflection_mm=worst_dx * k_dm,
                ratio=limit_ratio_eq_uls,
                ref_length_m=eave_height_m,
                ref_symbol="h",
                combo_name=worst_name,
            ))
    return checks
