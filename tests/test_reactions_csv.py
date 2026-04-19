"""Unit tests for io.reactions_csv."""
import csv

from portal_frame.analysis.results import (
    AnalysisOutput, CaseResult, ReactionResult,
)
from portal_frame.io.reactions_csv import write_reactions_csv


def _make_case(name, rx_1=(0.0, -10.0, 0.0), rx_5=(0.0, -10.0, 0.0)):
    return CaseResult(
        case_name=name, members={}, deflections={},
        reactions={
            1: ReactionResult(node_id=1, fx=rx_1[0], fy=rx_1[1], mz=rx_1[2]),
            5: ReactionResult(node_id=5, fx=rx_5[0], fy=rx_5[1], mz=rx_5[2]),
        },
    )


def test_writes_header_and_case_rows(tmp_path):
    out = AnalysisOutput(
        case_results={"G": _make_case("G"), "Q": _make_case("Q", rx_1=(0.0, -5.0, 0.0), rx_5=(0.0, -5.0, 0.0))},
        combo_results={},
    )
    path = tmp_path / "rx.csv"
    write_reactions_csv(str(path), out)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))

    assert rows[0] == ["Case", "Node", "FX (kN)", "FY (kN)", "MZ (kNm)"]
    # 2 cases × 2 nodes = 4 data rows
    assert len(rows) == 5  # header + 4


def test_combo_rows_included_after_cases(tmp_path):
    out = AnalysisOutput(
        case_results={"G": _make_case("G")},
        combo_results={"ULS-1": _make_case("ULS-1", rx_1=(1.2, -20.3, 0.5))},
    )
    path = tmp_path / "rx.csv"
    write_reactions_csv(str(path), out)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))

    data_rows = rows[1:]
    # First rows = base cases, later rows = combos
    assert data_rows[0][0] == "G"
    uls_rows = [r for r in data_rows if r[0] == "ULS-1"]
    assert len(uls_rows) == 2
    assert uls_rows[0][1] == "1"
    assert uls_rows[0][2] == "1.20"
    assert uls_rows[0][3] == "-20.30"
    assert uls_rows[0][4] == "0.50"


def test_values_formatted_two_decimals(tmp_path):
    out = AnalysisOutput(
        case_results={"G": _make_case("G", rx_1=(1.234, -5.678, 0.9012))},
        combo_results={},
    )
    path = tmp_path / "rx.csv"
    write_reactions_csv(str(path), out)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))

    # Node 1 row is the first data row
    assert rows[1][2] == "1.23"
    assert rows[1][3] == "-5.68"
    assert rows[1][4] == "0.90"
