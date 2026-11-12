"""
SUS scoring and usability summary (analysis/usability.py).
"""

import pandas as pd
import pytest

from analysis.usability import analyse, mean_ci, sus_score, wilson


def test_sus_extremes_and_neutral():
    assert sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100
    assert sus_score([1, 5, 1, 5, 1, 5, 1, 5, 1, 5]) == 0
    assert sus_score([3] * 10) == 50


def test_sus_known_example():
    # odd: 4,5,4,4,3 -> 3+4+3+3+2 = 15 ; even: 2,1,2,2,1 -> 3+4+3+3+4 = 17 ; (15+17)*2.5 = 80
    assert sus_score([4, 2, 5, 1, 4, 2, 4, 2, 3, 1]) == 80


@pytest.mark.parametrize("bad", [[3] * 9, [0, 3, 3, 3, 3, 3, 3, 3, 3, 3], [6] * 10])
def test_sus_rejects_invalid_answers(bad):
    with pytest.raises(ValueError):
        sus_score(bad)


def test_mean_ci_and_wilson():
    ci = mean_ci([70, 80, 90])
    assert ci["mean"] == 80 and ci["ci95"][0] < 80 < ci["ci95"][1]
    lo, hi = wilson(9, 10)
    assert 0.5 < lo < 0.9 < hi <= 1


def test_analyse_summary():
    rows = []
    for i, answers in enumerate([[4, 2, 5, 1, 4, 2, 4, 2, 3, 1], [3] * 10]):
        row = {"participant_id": i, "group": "student" if i == 0 else "clinician", "language": "ar"}
        row.update({f"sus_{k + 1}": v for k, v in enumerate(answers)})
        row.update({f"task_{k}": 1 for k in range(1, 6)})
        row.update({f"time_{k}": 60 for k in range(1, 6)})
        rows.append(row)
    summary = analyse(pd.DataFrame(rows))
    assert summary["participants"] == 2
    assert summary["sus"]["mean"] == 65
    assert summary["tasks"]["task_1"]["completion_rate"] == 1
    assert set(summary["by_group"]) == {"student", "clinician"}
