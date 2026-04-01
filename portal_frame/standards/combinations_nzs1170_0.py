"""AS/NZS 1170.0:2002 Load Combinations (incl Amdt 1-5).

Clause 4.2.2 Strength + Table 4.1
For "All other roofs": psi_s=0.7, psi_l=0.0, psi_c=0.0
"""

from dataclasses import dataclass


@dataclass
class LoadCombination:
    """A single load combination with name, description, factors, and output case number."""
    name: str             # e.g., "ULS-1"
    description: str      # e.g., "1.35G"
    factors: dict         # e.g., {"G": 1.35}
    case_number: int      # Output case number (101+, 201+)


def build_combinations(wind_case_names: list[str], ws_factor: float = 1.0):
    """Build full combo list including wind cases per AS/NZS 1170.0:2002.

    ULS combos are numbered sequentially (ULS-1, ULS-2, ...).
    SLS combos are numbered sequentially (SLS-1, SLS-2, ...) and start
    at combo number 201 in the output.

    Returns (uls_combos, sls_combos) as two lists of tuples for backward
    compatibility. Each tuple is (name, description, factors_dict).

    Args:
        wind_case_names: List of wind case names (e.g. ["W1", "W2", ...])
        ws_factor: SLS wind scaling factor (qs/qu). Wind cases store Wu
            pressures; SLS combos scale by this factor to get Ws effect.
            Default 1.0 (conservative -- uses Wu for SLS).
    """
    uls = []
    uls_n = 1
    # Static ULS combos
    uls.append((f"ULS-{uls_n}", "1.35G", {"G": 1.35})); uls_n += 1
    uls.append((f"ULS-{uls_n}", "1.2G + 1.5Q", {"G": 1.2, "Q": 1.5})); uls_n += 1
    # Wind ULS combos
    for wname in wind_case_names:
        uls.append((f"ULS-{uls_n}", f"1.2G + {wname}", {"G": 1.2, wname: 1.0})); uls_n += 1
        uls.append((f"ULS-{uls_n}", f"0.9G + {wname}", {"G": 0.9, wname: 1.0})); uls_n += 1

    sls = []
    sls_n = 1
    # Static SLS combos
    sls.append((f"SLS-{sls_n}", "G + 0.7Q", {"G": 1.0, "Q": 0.7})); sls_n += 1
    sls.append((f"SLS-{sls_n}", "G", {"G": 1.0})); sls_n += 1
    # Wind SLS combos
    for wname in wind_case_names:
        sls.append((f"SLS-{sls_n}", f"G + {wname}(s)", {"G": 1.0, wname: ws_factor})); sls_n += 1

    return uls, sls
