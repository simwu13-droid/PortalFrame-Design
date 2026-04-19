"""Write a CSV of support reactions from an AnalysisOutput."""

import csv


def _combo_sort_key(name):
    """Sort combos by prefix (ULS before SLS) then numeric suffix."""
    prefix = 0 if name.startswith("ULS") else 1
    try:
        num = int(name.split("-")[1])
    except (IndexError, ValueError):
        num = 0
    return (prefix, num)


def write_reactions_csv(path, analysis_output):
    """Write reactions as CSV to `path`.

    Row order:
      1. Header
      2. All base cases in case_results insertion order, each with one row
         per support node (sorted by node_id).
      3. All combos in combo_results, sorted ULS-N then SLS-N.

    Values formatted to 2 decimal places.
    """
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Case", "Node", "FX (kN)", "FY (kN)", "MZ (kNm)"])

        for case_name, cr in analysis_output.case_results.items():
            _write_case(w, case_name, cr)

        for combo_name in sorted(
                analysis_output.combo_results.keys(), key=_combo_sort_key):
            _write_case(w, combo_name, analysis_output.combo_results[combo_name])


def _write_case(w, name, cr):
    for nid in sorted(cr.reactions.keys()):
        r = cr.reactions[nid]
        w.writerow([
            name, str(nid),
            f"{r.fx:.2f}", f"{r.fy:.2f}", f"{r.mz:.2f}",
        ])
