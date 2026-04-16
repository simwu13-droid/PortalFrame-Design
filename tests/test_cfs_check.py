"""Unit tests for AS/NZS 4600 CFS member capacity checks."""

import pytest

from portal_frame.io.section_library import load_all_sections
from portal_frame.models.sections import CFS_Section
from portal_frame.standards.cfs_check import (
    G550_FU_MPA, TENSION_K, check_member, phi_Nt,
)
from portal_frame.standards.cfs_span_table import (
    LIBRARY_TO_SPANTABLE, has_data, phi_Mbx, phi_Nc, phi_Vy,
)


# ─── Span table data integrity ───────────────────────────────────────

def test_every_mapping_resolves_to_real_row():
    """Every entry in LIBRARY_TO_SPANTABLE must exist in all three sheets."""
    for lib_name in LIBRARY_TO_SPANTABLE:
        assert has_data(lib_name), f"{lib_name} missing from span table"
        assert phi_Nc(lib_name, 5.0) is not None
        assert phi_Mbx(lib_name, 5.0) is not None
        assert phi_Vy(lib_name) is not None, f"{lib_name} missing from Vy sheet"


def test_unmapped_section_returns_none():
    assert phi_Nc("100x1", 5.0) is None
    assert phi_Mbx("100x1", 5.0) is None
    assert phi_Vy("100x1") is None
    assert has_data("100x1") is False


def test_known_vy_value_63020s2():
    """63020S2 shear capacity = 429.6 kN per span table."""
    assert phi_Vy("63020S2") == pytest.approx(429.6, rel=1e-4)


def test_vy_is_L_independent():
    """phi_Vy takes no L argument — one value per section."""
    v1 = phi_Vy("63020S2")
    v2 = phi_Vy("63020S2")
    assert v1 == v2 == 429.6


def test_known_value_63020s2_at_5m():
    """63020S2 at L=5m: from xlsx, Nc=1032.3 kN, Mbx=387.1 kNm."""
    assert phi_Nc("63020S2", 5.0) == pytest.approx(1032.3, rel=1e-4)
    assert phi_Mbx("63020S2", 5.0) == pytest.approx(387.1, rel=1e-4)


def test_known_value_50020_at_3m():
    """50020 at L=3m: from xlsx, Nc=249.86 kN, Mbx=57.424 kNm."""
    assert phi_Nc("50020", 3.0) == pytest.approx(249.86, rel=1e-4)
    assert phi_Mbx("50020", 3.0) == pytest.approx(57.424, rel=1e-4)


def test_interpolation_midpoint():
    """Nc at L=4.5m must equal the average of Nc(4) and Nc(5)."""
    nc4 = phi_Nc("63020S2", 4.0)
    nc5 = phi_Nc("63020S2", 5.0)
    assert phi_Nc("63020S2", 4.5) == pytest.approx((nc4 + nc5) / 2.0)


def test_clamp_below_min():
    """L < 1m is clamped to the 1m value."""
    assert phi_Nc("63020S2", 0.5) == phi_Nc("63020S2", 1.0)
    assert phi_Mbx("63020S2", 0.0) == phi_Mbx("63020S2", 1.0)


def test_clamp_above_max():
    """L > 25m is clamped to the 25m value."""
    assert phi_Nc("63020S2", 30.0) == phi_Nc("63020S2", 25.0)
    assert phi_Mbx("63020S2", 50.0) == phi_Mbx("63020S2", 25.0)


# ─── Tension formula ─────────────────────────────────────────────────

def _fake_section(name="TEST", Ax=1000.0) -> CFS_Section:
    return CFS_Section(
        name=name, library="test", library_name="TEST", group="",
        Ax=Ax, J=0.0, Iy=0.0, Iz=0.0, Iw=0.0, Sy=0.0, Sz=0.0,
    )


def test_phi_Nt_matches_formula():
    """phi_Nt = 0.85 * Ag * 550 / 1000 (kN)."""
    sec = _fake_section(Ax=1000.0)
    expected = TENSION_K * 1000.0 * G550_FU_MPA / 1000.0
    assert phi_Nt(sec) == pytest.approx(expected)


def test_phi_Nt_real_section():
    secs = load_all_sections()
    sec = secs["63020S2"]
    expected = 0.85 * sec.Ax * 550.0 / 1000.0
    assert phi_Nt(sec) == pytest.approx(expected)


# ─── check_member ────────────────────────────────────────────────────

def test_pure_compression_check():
    secs = load_all_sections()
    sec = secs["63020S2"]
    pNc = phi_Nc("63020S2", 5.0)  # 1032.3 kN

    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=pNc / 2,  # exactly 50% util
        N_max_tension=0.0,
        M_max=0.0,
    )
    assert chk.status == "PASS"
    assert chk.util_axial == pytest.approx(0.5)
    assert chk.util_bending == 0.0
    assert chk.util_combined == pytest.approx(0.5)


def test_pure_bending_check():
    secs = load_all_sections()
    sec = secs["63020S2"]
    pMbx = phi_Mbx("63020S2", 5.0)  # 387.1 kNm

    chk = check_member(
        member_id=1, member_role="raf", section=sec, L_eff=5.0,
        N_max_compression=0.0, N_max_tension=0.0,
        M_max=pMbx / 2,
    )
    assert chk.status == "PASS"
    assert chk.util_bending == pytest.approx(0.5)
    assert chk.util_combined == pytest.approx(0.5)


def test_combined_pass_at_unity():
    secs = load_all_sections()
    sec = secs["63020S2"]
    pNc = phi_Nc("63020S2", 5.0)
    pMbx = phi_Mbx("63020S2", 5.0)

    # 0.4 axial + 0.6 bending = 1.0 exactly
    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=0.4 * pNc,
        N_max_tension=0.0,
        M_max=0.6 * pMbx,
    )
    assert chk.util_combined == pytest.approx(1.0)
    assert chk.status == "PASS"


def test_combined_fail_above_unity():
    secs = load_all_sections()
    sec = secs["63020S2"]
    pNc = phi_Nc("63020S2", 5.0)
    pMbx = phi_Mbx("63020S2", 5.0)

    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=0.5 * pNc,
        N_max_tension=0.0,
        M_max=0.6 * pMbx,
    )
    assert chk.util_combined == pytest.approx(1.1)
    assert chk.status == "FAIL"


def test_no_data_path():
    """Section without span table mapping returns NO_DATA."""
    sec = _fake_section(name="100x1", Ax=500.0)
    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=10.0, N_max_tension=0.0, M_max=2.0,
    )
    assert chk.status == "NO_DATA"
    assert chk.phi_Nc is None
    assert chk.phi_Mbx is None
    # Tension capacity is still computed even with no span table data
    assert chk.phi_Nt > 0


def test_tension_governs_when_larger():
    """When tension util > compression util, tension governs the axial term."""
    secs = load_all_sections()
    sec = secs["63020S2"]
    pNc = phi_Nc("63020S2", 5.0)
    pNt = phi_Nt(sec)

    # Compression util = 100/Nc, Tension util = (0.5*Nt)/Nt = 0.5
    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=100.0,
        N_max_tension=0.5 * pNt,
        M_max=0.0,
    )
    assert chk.util_axial == pytest.approx(0.5)
    assert chk.util_axial > 100.0 / pNc  # tension is the governing term


# ─── Shear check ─────────────────────────────────────────────────────

def test_shear_check_pass():
    secs = load_all_sections()
    sec = secs["63020S2"]
    pVy = phi_Vy("63020S2")   # 429.6 kN

    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=0.0, N_max_tension=0.0, M_max=0.0,
        V_max=pVy / 2,   # exactly 50% util
    )
    assert chk.util_shear == pytest.approx(0.5)
    assert chk.status == "PASS"


def test_shear_check_fail():
    secs = load_all_sections()
    sec = secs["63020S2"]
    pVy = phi_Vy("63020S2")

    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=0.0, N_max_tension=0.0, M_max=0.0,
        V_max=pVy * 1.1,   # 10% over
    )
    assert chk.util_shear == pytest.approx(1.1)
    assert chk.status == "FAIL"


def test_shear_fail_overrides_combined_pass():
    """If combined passes but shear fails, overall status is FAIL."""
    secs = load_all_sections()
    sec = secs["63020S2"]
    pVy = phi_Vy("63020S2")
    pMbx = phi_Mbx("63020S2", 5.0)

    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=0.0, N_max_tension=0.0,
        M_max=0.3 * pMbx,   # util_bending = 0.3
        V_max=1.2 * pVy,    # util_shear = 1.2 (FAIL)
    )
    assert chk.util_combined == pytest.approx(0.3)   # combined passes
    assert chk.util_shear == pytest.approx(1.2)      # shear fails
    assert chk.status == "FAIL"


def test_shear_and_combined_both_pass():
    secs = load_all_sections()
    sec = secs["63020S2"]
    pVy = phi_Vy("63020S2")
    pMbx = phi_Mbx("63020S2", 5.0)

    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=0.0, N_max_tension=0.0,
        M_max=0.4 * pMbx,
        V_max=0.6 * pVy,
    )
    assert chk.status == "PASS"


def test_no_data_path_preserves_shear_capacity_field():
    """Even for NO_DATA sections, phi_Vy is reported (or None if missing)."""
    sec = _fake_section(name="100x1", Ax=500.0)
    chk = check_member(
        member_id=1, member_role="col", section=sec, L_eff=5.0,
        N_max_compression=10.0, N_max_tension=0.0, M_max=2.0, V_max=5.0,
    )
    assert chk.status == "NO_DATA"
    assert chk.phi_Vy is None
    assert chk.V_max == 5.0   # force is still reported
