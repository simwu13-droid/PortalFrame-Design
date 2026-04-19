"""Linear interpolation of MemberStationResult at an arbitrary position."""

from portal_frame.standards.utils import lerp


STATION_FIELDS = ("moment", "shear", "axial", "dy_local")


def interpolate_station(stations, x_query):
    """Linear interp of station fields at x_query (m along the member).

    Returns a dict with keys STATION_FIELDS. Clamps x_query to the
    [first.position, last.position] range (no extrapolation).

    Raises ValueError if stations is empty.
    """
    if not stations:
        raise ValueError("stations is empty")
    sorted_st = sorted(stations, key=lambda s: s.position)
    if x_query <= sorted_st[0].position:
        s = sorted_st[0]
        return {f: getattr(s, f) for f in STATION_FIELDS}
    if x_query >= sorted_st[-1].position:
        s = sorted_st[-1]
        return {f: getattr(s, f) for f in STATION_FIELDS}
    for a, b in zip(sorted_st, sorted_st[1:]):
        if a.position <= x_query <= b.position:
            return {
                f: lerp(x_query, a.position, b.position,
                        getattr(a, f), getattr(b, f))
                for f in STATION_FIELDS
            }
    raise RuntimeError("unreachable: POI inside range but no bracket found")
