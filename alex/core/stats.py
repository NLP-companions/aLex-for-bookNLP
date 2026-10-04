"""Comparison statistics for a 2x2 table, as used in corpus linguistics.

a = item count in the target, c = all items in the target
b = item count in the reference, d = all items in the reference
"""
import math

MEASURES = {
    "ll": "Log-likelihood (G²)",
    "chi2": "Chi-squared",
    "lr": "Log ratio",
    "pdiff": "%DIFF",
    "or": "Odds ratio",
}
TESTS = {"ll": "Log-likelihood (G²)", "chi2": "Chi-squared"}

NOTES = {
    "ll": "G² = 2 Σ O ln(O/E) over the target and reference cells, with expected E from the combined proportion (Rayson & Garside 2000). Signed + when the item is relatively more frequent in the target. p from χ² with 1 degree of freedom.",
    "chi2": "Pearson's χ² for the 2×2 table (item vs other items, target vs reference), without Yates' correction. Signed like G². p from χ² with 1 degree of freedom.",
    "lr": "Log ratio = log₂ of (relative frequency in target ÷ relative frequency in reference) (Hardie 2014). 1 means twice as frequent, −1 half as frequent. Zero counts are replaced by 0.5.",
    "pdiff": "%DIFF = (relative frequency in target − in reference) ÷ in reference × 100 (Gabrielatos & Marchi 2012). Zero counts are replaced by 0.5.",
    "or": "Odds ratio = (a ÷ (c − a)) ÷ (b ÷ (d − b)), with a 95% confidence interval from the log odds ratio's standard error. When any cell is zero, 0.5 is added to every cell (Haldane–Anscombe).",
}


def p_chi1(x):
    """Upper-tail p-value of the chi-squared distribution with 1 degree of freedom."""
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2))


def _gammq(a, x):
    """Regularised upper incomplete gamma Q(a, x) (Numerical Recipes)."""
    if x <= 0:
        return 1.0
    if x < a + 1:
        ap, total, delta = a, 1 / a, 1 / a
        for _ in range(1000):
            ap += 1
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-12:
                break
        return max(0.0, 1 - total * math.exp(-x + a * math.log(x) - math.lgamma(a)))
    b, c, d = x + 1 - a, 1 / 1e-300, 1 / (x + 1 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - math.lgamma(a)) * h)


def p_chi(x, df):
    """Upper-tail p-value of chi-squared with df degrees of freedom."""
    return _gammq(df / 2, x / 2) if df > 0 else 1.0


def across(counts, totals):
    """How one item is spread over several parts (books), against how big each part is.
    counts, totals: lists, one per part. Returns chi-squared (item vs rest x parts),
    its p, Cramér's V and each part's adjusted standardised residual."""
    A, N = sum(counts), sum(totals)
    k = sum(1 for t in totals if t > 0)
    if A == 0 or N == 0 or k < 2 or A == N:
        return {"chi2": 0.0, "df": max(0, k - 1), "p": 1.0, "v": 0.0, "resid": [0.0] * len(counts)}
    chi2, resid = 0.0, []
    for o, t in zip(counts, totals):
        if t == 0:
            resid.append(None)
            continue
        e1, e2 = t * A / N, t * (N - A) / N
        chi2 += (o - e1) ** 2 / e1 + ((t - o) - e2) ** 2 / e2
        var = e1 * (1 - t / N) * (1 - A / N)
        resid.append((o - e1) / math.sqrt(var) if var > 0 else 0.0)
    return {"chi2": chi2, "df": k - 1, "p": p_chi(chi2, k - 1), "v": math.sqrt(chi2 / N), "resid": resid}


ACROSS_NOTE = ("For each item, a table of this item against all other items, by book, is tested with Pearson's χ² "
               "(degrees of freedom = books − 1). A small p means the item's share of the list changes between books "
               "more than chance would explain. Cramér's V (0–1) is the size of that change. In each book's column, the "
               "cell is shaded when its adjusted standardised residual is beyond ±1.96: blue when the item is more "
               "frequent in that book than expected from the other books, red when less. With a Bonferroni correction, "
               "the threshold for p is divided by the number of items tested.")


def compare(a, b, c, d):
    """Compare one item's frequency in two texts. a, b: its counts in the target and the reference; c, d: the sizes of each.
    Returns the log-likelihood (G², Rayson & Garside) and chi-squared (both signed + when relatively more frequent in the
    target) with their p-values, log ratio, %DIFF and odds ratio with a 95% interval. Zero counts are replaced by 0.5 where needed."""
    out = {"a": a, "b": b}
    if c <= 0 or d <= 0:
        return {**out, "ll": 0, "chi2": 0, "p_ll": 1, "p_chi2": 1, "lr": 0, "pdiff": 0, "or": 1, "or_lo": 1, "or_hi": 1}
    n = c + d
    e1, e2 = c * (a + b) / n, d * (a + b) / n
    ll = 2 * ((a * math.log(a / e1) if a else 0) + (b * math.log(b / e2) if b else 0))
    more = a / c > b / d
    k = a + b
    denom = k * (n - k) * c * d
    chi2 = n * (a * (d - b) - b * (c - a)) ** 2 / denom if denom else 0
    a5, b5 = (a or 0.5), (b or 0.5)
    lr = math.log2((a5 / c) / (b5 / d))
    pdiff = ((a5 / c) - (b5 / d)) / (b5 / d) * 100
    cells = [a, c - a, b, d - b]
    if min(cells) <= 0:
        cells = [x + 0.5 for x in cells]
    try:
        orr = (cells[0] / cells[1]) / (cells[2] / cells[3])
        se = math.sqrt(sum(1 / x for x in cells))
        lo, hi = math.exp(math.log(orr) - 1.96 * se), math.exp(math.log(orr) + 1.96 * se)
    except (ZeroDivisionError, ValueError):
        orr, lo, hi = 1, 1, 1
    sign = 1 if more else -1
    return {**out, "ll": sign * ll, "chi2": sign * chi2, "p_ll": p_chi1(ll), "p_chi2": p_chi1(chi2),
            "lr": lr, "pdiff": pdiff, "or": orr, "or_lo": lo, "or_hi": hi}


def keyness(target, reference, measure="ll", test="ll", min_freq=3, alpha=0.05,
            bonferroni=False, direction="target", show_all=False):
    """target, reference: Counter of item -> count. Returns rows and a summary."""
    c, d = sum(target.values()), sum(reference.values())
    keys = set(target) | set(reference)
    if direction == "target":
        keys = [k for k in keys if target.get(k, 0) >= min_freq]
    else:
        keys = [k for k in keys if max(target.get(k, 0), reference.get(k, 0)) >= min_freq]
    thresh = alpha / len(keys) if (bonferroni and keys) else alpha
    rows = []
    for k in keys:
        r = compare(target.get(k, 0), reference.get(k, 0), c, d)
        r["item"] = k
        r["pa"] = 100 * r["a"] / c if c else 0
        r["pb"] = 100 * r["b"] / d if d else 0
        r["p"] = r["p_" + test]
        r["sig"] = r["p"] < thresh
        up = r["lr"] > 0
        if direction == "target" and not up:
            continue
        if not show_all and not r["sig"]:
            continue
        rows.append(r)
    key = {"or": lambda r: math.log(r["or"]) if r["or"] > 0 else 0}.get(measure, lambda r: r[measure])
    if direction == "target":
        rows.sort(key=lambda r: (key(r), r["a"]), reverse=True)
    else:
        rows.sort(key=lambda r: (abs(key(r)), r["a"]), reverse=True)
    return rows, {"c": c, "d": d, "tested": len(keys), "alpha": alpha, "threshold": thresh,
                  "measure": measure, "test": test, "bonferroni": bonferroni, "min_freq": min_freq,
                  "direction": direction}
