"""
Survival analysis engine: Kaplan-Meier estimation and median survival.
Pure numpy.
"""

import numpy as np


def kaplan_meier(times, events):
    """Return (times, survival, at_risk) step-function arrays."""
    t = np.asarray(times, dtype=float)
    e = np.asarray(events, dtype=float)
    mask = ~np.isnan(t) & ~np.isnan(e) & (t >= 0)
    t, e = t[mask], e[mask]
    if len(t) == 0:
        return np.array([0.0]), np.array([1.0]), np.array([0])
    order = np.argsort(t)
    t, e = t[order], e[order]
    uniq = np.unique(t)
    S, n = 1.0, len(t)
    out_t, out_s, out_risk = [0.0], [1.0], [n]
    start = 0
    for ti in uniq:
        j = np.searchsorted(t, ti, side="right")
        d = e[start:j].sum()
        at_risk = n - start
        if d > 0 and at_risk > 0:
            S *= 1.0 - d / at_risk
        out_t.append(float(ti))
        out_s.append(float(S))
        out_risk.append(int(at_risk))
        start = j
    return np.array(out_t), np.array(out_s), np.array(out_risk)


def median_survival(times, events):
    t, s, _ = kaplan_meier(times, events)
    below = np.where(s <= 0.5)[0]
    return float(t[below[0]]) if len(below) else None
