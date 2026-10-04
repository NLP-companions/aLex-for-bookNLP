"""Statistics, checked against SciPy where an independent reference exists."""
from __future__ import annotations

import math

import pytest
from scipy import stats as sp

from alex.core import stats


@pytest.mark.parametrize("x", [0.0, 0.5, 1.0, 3.84, 10.0, 27.0, 200.0])
def test_p_chi1_matches_scipy(x):
    assert stats.p_chi1(x) == pytest.approx(sp.chi2.sf(x, 1), rel=1e-9, abs=1e-15)


@pytest.mark.parametrize("df", [1, 2, 3, 7, 30])
@pytest.mark.parametrize("x", [0.1, 1.0, 5.0, 12.0, 40.0, 150.0])
def test_p_chi_matches_scipy(x, df):
    assert stats.p_chi(x, df) == pytest.approx(sp.chi2.sf(x, df), rel=1e-6, abs=1e-14)


def test_p_chi_edge_cases():
    assert stats.p_chi(0, 3) == 1.0 and stats.p_chi(5, 0) == 1.0 and stats.p_chi1(-1) == 1.0


def test_compare_log_likelihood_matches_scipy():
    a, b, c, d = 30, 10, 1000, 2000
    r = stats.compare(a, b, c, d)
    expected, _, _, _ = sp.chi2_contingency([[a, c - a], [b, d - b]], correction=False)
    assert r["chi2"] == pytest.approx(expected, rel=1e-9)
    # G² as corpus linguists use it (Rayson & Garside 2000): the item's two cells only, not the four of a full G-test
    e1, e2 = c * (a + b) / (c + d), d * (a + b) / (c + d)
    g = 2 * (a * math.log(a / e1) + b * math.log(b / e2))
    assert r["ll"] == pytest.approx(g, rel=1e-12)
    assert r["p_ll"] == pytest.approx(sp.chi2.sf(g, 1), rel=1e-6)


def test_compare_signs_and_effect_sizes():
    up, down = stats.compare(30, 10, 1000, 1000), stats.compare(10, 30, 1000, 1000)
    assert up["ll"] > 0 > down["ll"] and up["chi2"] > 0 > down["chi2"]
    assert up["ll"] == pytest.approx(-down["ll"])
    assert up["lr"] == pytest.approx(math.log2(3)) and up["or"] > 1 > down["or"]
    assert up["or_lo"] < up["or"] < up["or_hi"]
    assert up["pdiff"] == pytest.approx(200.0)


def test_compare_with_zero_counts_uses_half_counts_and_does_not_fail():
    r = stats.compare(5, 0, 100, 100)
    assert math.isfinite(r["lr"]) and math.isfinite(r["or"]) and r["ll"] > 0
    empty = stats.compare(1, 1, 0, 10)
    assert empty["ll"] == 0 and empty["p_ll"] == 1


def test_across_matches_scipy_chi2():
    counts, totals = [20, 5, 8], [1000, 900, 1200]
    r = stats.across(counts, totals)
    table = [counts, [t - c for c, t in zip(counts, totals)]]
    chi2, p, df, _ = sp.chi2_contingency(table, correction=False)
    assert r["chi2"] == pytest.approx(chi2, rel=1e-9) and r["df"] == df and r["p"] == pytest.approx(p, rel=1e-6)
    assert r["v"] == pytest.approx(math.sqrt(chi2 / sum(totals)))
    assert r["resid"][0] > 1.96 > r["resid"][1]


def test_across_degenerate_inputs():
    assert stats.across([0, 0], [10, 10])["chi2"] == 0
    assert stats.across([5], [10])["df"] == 0
    r = stats.across([3, 0], [10, 0])
    assert r["resid"][1] is None or r["df"] == 0


def test_keyness_ranks_and_filters():
    target = {"moor": 40, "the": 100, "rare": 1}
    reference = {"moor": 2, "the": 105, "goose": 30}
    rows, summary = stats.keyness(target, reference, min_freq=3)
    assert [r["item"] for r in rows] == ["moor"] and summary["tested"] == 2
    both, _ = stats.keyness(target, reference, min_freq=3, direction="both")
    assert {r["item"] for r in both} == {"moor", "goose"}
    # "the" is a little *less* frequent in the target, so it only appears with both directions and non-significant items shown
    everything, _ = stats.keyness(target, reference, min_freq=3, direction="both", show_all=True)
    assert "the" not in {r["item"] for r in both} and "the" in {r["item"] for r in everything}


def test_keyness_bonferroni_tightens_the_threshold():
    target = {f"w{i}": 12 for i in range(50)}
    reference = {f"w{i}": 6 for i in range(50)}
    loose, s1 = stats.keyness(target, reference, alpha=0.05)
    strict, s2 = stats.keyness(target, reference, alpha=0.05, bonferroni=True)
    assert s2["threshold"] == pytest.approx(0.05 / 50) and len(strict) <= len(loose)
