"""Unit tests for standards modules — proves they're independently importable and testable."""

import math
import pytest

from portal_frame.standards.utils import lerp
from portal_frame.standards.earthquake_nzs1170_5 import (
    NZ_HAZARD_FACTORS,
    spectral_shape_factor,
    calculate_earthquake_forces,
)
from portal_frame.models.loads import EarthquakeInputs
from portal_frame.models.geometry import PortalFrameGeometry
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


class TestMonoRoofWindCases:
    """Tests for monoslope wind cases using Tables 5.3(B) and 5.3(C)."""

    def test_mono_steep_produces_8_cases(self):
        """Mono roof >= 10 deg still produces 8 wind cases."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 15.0, 50.0, cp, roof_type="mono",
        )
        assert len(cases) == 8

    def test_mono_steep_crosswind_uniform(self):
        """Mono >= 10 deg: W1-W4 crosswind are UNIFORM (not zone-based)."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 15.0, 50.0, cp, roof_type="mono",
        )
        for case in cases[:4]:
            assert not case.is_crosswind  # uniform, not zone-based
            assert case.left_rafter != 0

    def test_mono_steep_upslope_vs_downslope(self):
        """Upslope (W1-W2) and downslope (W3-W4) use different Cp,e tables."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 15.0, 50.0, cp, roof_type="mono",
        )
        # W1 = upslope uplift, W3 = downslope uplift
        w1_rafter = cases[0].left_rafter
        w3_rafter = cases[2].left_rafter
        # Different tables → different pressures
        assert w1_rafter != w3_rafter

    def test_mono_steep_wall_directions(self):
        """Upslope: left wall = windward. Downslope: right wall = windward."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 15.0, 50.0, cp, roof_type="mono",
        )
        # W1 upslope: wind from left (low side)
        assert cases[0].left_wall > 0  # windward = positive pressure
        # W3 downslope: wind from right (high side)
        assert cases[2].right_wall > 0  # windward = positive pressure

    def test_mono_shallow_uses_zones(self):
        """Mono roof < 10 deg falls back to Table 5.3(A) zone-based."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 5.0, 50.0, cp, roof_type="mono",
        )
        # W1-W4 should be zone-based (same as gable for < 10 deg)
        for case in cases[:4]:
            assert case.is_crosswind

    def test_mono_transverse_same_as_gable(self):
        """W5-W8 transverse cases are the same logic for mono."""
        cp = WindCpInputs()
        cases = generate_standard_wind_cases(
            12.0, 4.5, 15.0, 50.0, cp, roof_type="mono",
        )
        for case in cases[4:]:
            assert not case.is_crosswind
            assert case.left_rafter != 0


class TestTable53BLookup:
    """Tests for Table 5.3(B) upwind slope interpolation."""

    def test_exact_values(self):
        """Check exact table values at known points."""
        from portal_frame.standards.wind_nzs1170_2 import _interp_53b
        up, dn = _interp_53b(0.5, 15.0)
        assert up == pytest.approx(-0.7, abs=0.01)
        assert dn == pytest.approx(-0.3, abs=0.01)

    def test_high_pitch(self):
        """Alpha >= 45 deg uses 0.8*sin(alpha)."""
        from portal_frame.standards.wind_nzs1170_2 import _interp_53b
        up, dn = _interp_53b(0.5, 45.0)
        expected = 0.8 * math.sin(math.radians(45.0))
        assert up == pytest.approx(expected, abs=0.01)


class TestTable53CLookup:
    """Tests for Table 5.3(C) downwind slope interpolation."""

    def test_exact_values(self):
        from portal_frame.standards.wind_nzs1170_2 import _interp_53c
        assert _interp_53c(0.5, 15.0) == pytest.approx(-0.5, abs=0.01)

    def test_high_pitch_bd_low(self):
        """Alpha >= 25, b/d <= 3 returns -0.6."""
        from portal_frame.standards.wind_nzs1170_2 import _interp_53c
        assert _interp_53c(0.5, 30.0, b_over_d=2.0) == pytest.approx(-0.6)

    def test_high_pitch_bd_high(self):
        """Alpha >= 25, b/d >= 8 returns -0.9."""
        from portal_frame.standards.wind_nzs1170_2 import _interp_53c
        assert _interp_53c(0.5, 30.0, b_over_d=10.0) == pytest.approx(-0.9)

    def test_high_pitch_bd_mid(self):
        """Alpha >= 25, 3 < b/d < 8 uses formula -0.06*(7+b/d)."""
        from portal_frame.standards.wind_nzs1170_2 import _interp_53c
        result = _interp_53c(0.5, 30.0, b_over_d=5.0)
        expected = -0.06 * (7 + 5.0)
        assert result == pytest.approx(expected, abs=0.01)


class TestEarthquakeCombinations:
    def test_eq_uls_combos(self):
        uls, sls = build_combinations(["W1"], eq_case_names=["E+", "E-"])
        eq_uls = [c for c in uls if "E+" in c[1] or "E-" in c[1]]
        assert len(eq_uls) == 2

    def test_eq_sls_combos(self):
        uls, sls = build_combinations(["W1"], eq_case_names=["E+", "E-"])
        eq_sls = [c for c in sls if "E+" in c[1] or "E-" in c[1]]
        assert len(eq_sls) == 2

    def test_eq_uls_factor_on_G(self):
        uls, sls = build_combinations([], eq_case_names=["E+", "E-"])
        eq_combo = [c for c in uls if "E+" in c[1]][0]
        assert eq_combo[2]["G"] == 1.0

    def test_no_eq_when_empty(self):
        uls, sls = build_combinations(["W1"], eq_case_names=[])
        for c in uls:
            assert "E+" not in c[1]

    def test_default_no_eq(self):
        uls, sls = build_combinations(["W1"])
        for c in uls:
            assert "E+" not in c[1]

    def test_eq_combo_numbering(self):
        uls, sls = build_combinations(["W1", "W2"], eq_case_names=["E+", "E-"])
        names = [c[0] for c in uls]
        assert len(names) == 8
        assert names[-2] == "ULS-7"
        assert names[-1] == "ULS-8"


class TestNZHazardFactors:
    def test_wellington_z(self):
        assert NZ_HAZARD_FACTORS["Wellington"] == 0.40

    def test_auckland_z(self):
        assert NZ_HAZARD_FACTORS["Auckland"] == 0.13

    def test_christchurch_z(self):
        assert NZ_HAZARD_FACTORS["Christchurch"] == 0.30


class TestSpectralShapeFactor:
    def test_soil_c_at_0s(self):
        ch = spectral_shape_factor(0.0, "C")
        assert ch == pytest.approx(1.33, rel=0.05)

    def test_soil_c_at_0_5s(self):
        ch = spectral_shape_factor(0.5, "C")
        assert ch == pytest.approx(2.36, rel=0.05)

    def test_soil_a_at_0s(self):
        ch = spectral_shape_factor(0.0, "A")
        assert ch == pytest.approx(1.89, rel=0.05)

    def test_interpolation(self):
        ch = spectral_shape_factor(0.25, "C")
        assert 1.0 < ch < 3.0

    def test_long_period_decay(self):
        ch_short = spectral_shape_factor(0.3, "C")
        ch_long = spectral_shape_factor(2.0, "C")
        assert ch_long < ch_short


class TestCalculateEarthquakeForces:
    def test_basic_portal_frame(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(
            Z=0.40, soil_class="C", R_uls=1.0, R_sls=0.25,
            mu=1.0, Sp=1.0, near_fault=1.0, extra_seismic_mass=0.0,
        )
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        assert result["T1"] > 0
        assert result["Ch"] > 0
        assert result["k_mu"] == pytest.approx(1.0)
        assert result["Wt"] > 0
        assert result["V_uls"] > 0
        assert result["V_sls"] > 0
        assert result["V_sls"] < result["V_uls"]
        assert result["F_node"] == pytest.approx(result["V_uls"] / 2.0)

    def test_period_calculation(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C")
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        h_n = geom.ridge_height
        expected_T1 = 1.25 * 0.085 * h_n ** 0.75
        assert result["T1"] == pytest.approx(expected_T1, rel=1e-3)

    def test_seismic_weight(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", extra_seismic_mass=10.0)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        expected_Wt = (0.15 * 12.0 + 0.10 * 2 * 6.0 / 2.0) * 8.0 + 10.0
        assert result["Wt"] == pytest.approx(expected_Wt, rel=1e-3)

    def test_k_mu_short_period(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=4.0, roof_pitch=5.0, bay_spacing=6.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", mu=4.0, Sp=0.7)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        T1 = result["T1"]
        if T1 < 0.7:
            expected_k_mu = (4.0 - 1) * T1 / 0.7 + 1
            assert result["k_mu"] == pytest.approx(expected_k_mu, rel=1e-3)

    def test_cd_floor(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", R_uls=1.0)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        cd_floor = max(0.03, 0.40 * 1.0 * 0.02)
        assert result["Cd_uls"] >= cd_floor

    def test_f_node_sls(self):
        geom = PortalFrameGeometry(
            span=12.0, eave_height=6.0, roof_pitch=5.0, bay_spacing=8.0,
        )
        eq = EarthquakeInputs(Z=0.40, soil_class="C", R_sls=0.25)
        result = calculate_earthquake_forces(geom, 0.15, 0.10, eq)
        assert result["F_node_sls"] == pytest.approx(result["V_sls"] / 2.0)
