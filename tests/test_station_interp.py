"""Unit tests for analysis.station_interp."""
import pytest

from portal_frame.analysis.results import MemberStationResult
from portal_frame.analysis.station_interp import interpolate_station, STATION_FIELDS


def _stations():
    """Three-station sample: position 0.0, 1.0, 2.0 m with simple linear values."""
    return [
        MemberStationResult(position=0.0, position_pct=0.0,
                            axial=-10.0, shear=5.0, moment=0.0, dy_local=0.0),
        MemberStationResult(position=1.0, position_pct=50.0,
                            axial=-10.0, shear=5.0, moment=10.0, dy_local=2.0),
        MemberStationResult(position=2.0, position_pct=100.0,
                            axial=-10.0, shear=5.0, moment=20.0, dy_local=4.0),
    ]


def test_interpolate_at_exact_station():
    result = interpolate_station(_stations(), 1.0)
    assert result == {"moment": 10.0, "shear": 5.0, "axial": -10.0, "dy_local": 2.0}


def test_interpolate_at_midpoint():
    result = interpolate_station(_stations(), 0.5)
    assert result["moment"] == pytest.approx(5.0)
    assert result["dy_local"] == pytest.approx(1.0)
    assert result["axial"] == -10.0


def test_interpolate_below_range_clamps_to_start():
    result = interpolate_station(_stations(), -0.5)
    assert result["moment"] == 0.0
    assert result["dy_local"] == 0.0


def test_interpolate_above_range_clamps_to_end():
    result = interpolate_station(_stations(), 3.0)
    assert result["moment"] == 20.0
    assert result["dy_local"] == 4.0


def test_empty_stations_raises():
    with pytest.raises(ValueError, match="stations is empty"):
        interpolate_station([], 0.5)


def test_return_keys_match_station_fields():
    result = interpolate_station(_stations(), 1.0)
    assert set(result.keys()) == set(STATION_FIELDS)
