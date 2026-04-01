"""Unit tests for standards modules — proves they're independently importable and testable."""

import pytest

from portal_frame.standards.utils import lerp
from portal_frame.standards.wind_nzs1170_2 import (
    cfig, leeward_cpe_lookup, roof_cpe_zones,
    generate_standard_wind_cases, WindCpInputs, _split_zones_to_rafters,
)
from portal_frame.standards.combinations_nzs1170_0 import build_combinations


class TestLerp:
    def test_midpoint(self):
        assert lerp(0.5, 0, 1, 0, 10) == 5.0

    def test_at_start(self):
        assert lerp(0, 0, 1, 0, 10) == 0.0

    def test_at_end(self):
        assert lerp(1, 0, 1, 0, 10) == 10.0

    def test_equal_x(self):
        assert lerp(5, 5, 5, 3, 7) == 3.0


class TestCfig:
    def test_basic(self):
        # Cfig = Cp,e * Kc,e - Cp,i * Kc,i
        result = cfig(0.7, 0.2, 0.8, 1.0)
        assert result == pytest.approx(0.7 * 0.8 - 0.2 * 1.0)

    def test_negative_cpe(self):
        result = cfig(-0.9, 0.2, 0.8, 1.0)
        assert result == pytest.approx(-0.9 * 0.8 - 0.2 * 1.0)

    def test_zero_cpi(self):
        result = cfig(0.7, 0.0, 0.8, 1.0)
        assert result == pytest.approx(0.7 * 0.8)


class TestLeewardCpeLookup:
    def test_low_pitch_low_db(self):
        assert leeward_cpe_lookup(0.5, 5.0) == -0.5

    def test_low_pitch_mid_db(self):
        result = leeward_cpe_lookup(1.5, 5.0)
        assert result == pytest.approx(-0.4)  # interpolated between -0.5 and -0.3

    def test_alpha_15(self):
        assert leeward_cpe_lookup(1.0, 15.0) == -0.3


class TestRoofCpeZones:
    def test_low_hd(self):
        zones = roof_cpe_zones(0.3)
        assert len(zones) == 5  # h/d <= 0.5 table has 5 zones

    def test_high_hd(self):
        zones = roof_cpe_zones(1.5)
        assert len(zones) == 3  # h/d >= 1.0 table has 3 zones

    def test_mid_hd_interpolation(self):
        zones = roof_cpe_zones(0.75)
        # Should have interpolated zones
        assert len(zones) >= 3


class TestBuildCombinations:
    def test_no_wind(self):
        uls, sls = build_combinations([])
        assert len(uls) == 2  # 1.35G and 1.2G+1.5Q
        assert len(sls) == 2  # G+0.7Q and G

    def test_with_wind(self):
        uls, sls = build_combinations(["W1", "W2"])
        # 2 static + 2 per wind case (1.2G+W, 0.9G+W) * 2 cases = 6
        assert len(uls) == 6
        # 2 static + 1 per wind case = 4
        assert len(sls) == 4

    def test_combo_names_sequential(self):
        uls, sls = build_combinations(["W1"])
        assert uls[0][0] == "ULS-1"
        assert uls[1][0] == "ULS-2"
        assert uls[2][0] == "ULS-3"
        assert sls[0][0] == "SLS-1"


class TestGenerateStandardWindCases:
    def test_produces_8_cases(self):
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp)
        assert len(cases) == 8

    def test_case_names(self):
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp)
        names = [c.name for c in cases]
        assert names == ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"]

    def test_crosswind_has_zones(self):
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp)
        # W1-W4 are crosswind with zone-based loading
        for case in cases[:4]:
            assert case.is_crosswind
            assert len(case.left_rafter_zones) > 0

    def test_transverse_is_uniform(self):
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp)
        # W5-W8 are transverse with uniform loading
        for case in cases[4:]:
            assert not case.is_crosswind
            assert case.left_rafter != 0


class TestVariableApexWindSplit:
    def test_split_at_50_matches_default(self):
        """50% split should match existing behavior."""
        from portal_frame.models.loads import RafterZoneLoad
        zones = [
            RafterZoneLoad(0.0, 50.0, -1.0),
            RafterZoneLoad(50.0, 100.0, -0.5),
        ]
        left, right = _split_zones_to_rafters(zones, 50.0)
        assert len(left) == 1
        assert left[0].start_pct == pytest.approx(0.0)
        assert left[0].end_pct == pytest.approx(100.0)
        assert left[0].pressure == pytest.approx(-1.0)
        assert len(right) == 1
        assert right[0].pressure == pytest.approx(-0.5)

    def test_split_at_33(self):
        """33% split: left rafter is shorter, gets fewer zones."""
        from portal_frame.models.loads import RafterZoneLoad
        zones = [
            RafterZoneLoad(0.0, 33.3, -1.0),
            RafterZoneLoad(33.3, 66.7, -0.7),
            RafterZoneLoad(66.7, 100.0, -0.3),
        ]
        left, right = _split_zones_to_rafters(zones, 33.3)
        assert len(left) == 1
        assert left[0].start_pct == pytest.approx(0.0)
        assert left[0].end_pct == pytest.approx(100.0)
        assert len(right) == 2


class TestGenerateWindCasesWithApex:
    def test_custom_split_pct(self):
        """generate_standard_wind_cases accepts split_pct parameter."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 5.0, 50.0, cp, split_pct=33.0,
        )
        assert len(cases) == 8
        w1 = cases[0]
        assert w1.is_crosswind

    def test_default_split_is_50(self):
        """Without split_pct, behavior is unchanged."""
        cp = WindCpInputs()
        cases_default = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp)
        cases_explicit = generate_standard_wind_cases(12.0, 4.5, 5.0, 50.0, cp, split_pct=50.0)
        for a, b in zip(cases_default, cases_explicit):
            assert a.left_wall == b.left_wall
            assert a.right_wall == b.right_wall
