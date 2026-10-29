"""
Tests for scripts/startup/constant_mass_core.py. No bpy - run directly with
`uv run python tests/constant_mass_core_test.py`.

Main property: k emitted spheres x mass-per-sphere matches the input total
mass to within one sphere, and the emission times are a valid, monotone
inversion of the cumulative-mass curve.
"""

import importlib.util
import os

import numpy as np

_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "startup", "constant_mass_core.py")
_spec = importlib.util.spec_from_file_location("constant_mass_core", _path)
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

# Irregular years, unsorted, with a zero-mass plateau in the middle.
X = np.array([2003, 2000, 2001, 2007, 2004, 2002, 2010], dtype=float)
Y = np.array([5.0, 12.0, 0.0, 30.0, 0.0, 7.5, 1.25])
TOTAL = Y.sum()


def _report(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    return ok


def test_emitted_mass_matches_total_mass_interval():
    ok = True
    for mass_interval in (0.37, 1.0, 2.5, 9.0):
        times, targets, pm = core.compute_emission_times(X, Y, mass_interval, 0)
        emitted = len(times) * pm
        if not (0 <= TOTAL - emitted < pm):
            ok = False
    return _report("emitted mass within one sphere of total (Mass Per Sphere mode)", ok)


def test_emitted_mass_matches_total_num_spheres():
    ok = True
    for n in (1, 3, 7, 49, 100, 1000):
        times, targets, pm = core.compute_emission_times(X, Y, 0.0, n)
        if len(times) != n or not np.isclose(len(times) * pm, TOTAL):
            ok = False
    return _report("exact sphere count and total mass (Total Spheres mode)", ok)


def test_targets_are_midpoint_centred():
    times, targets, pm = core.compute_emission_times(X, Y, 2.5, 0)
    expected = (np.arange(1, len(times) + 1) - 0.5) * pm
    return _report("target masses are (k - 1/2) x mass per sphere", np.allclose(targets, expected))


def test_times_monotone_and_in_domain():
    times, _, _ = core.compute_emission_times(X, Y, 0.5, 0)
    order = np.sort(X)
    t_start = 2 * order[0] - order[1]
    ok = bool(np.all(np.diff(times) >= 0) and times[0] >= t_start and times[-1] <= order[-1])
    return _report("emission times non-decreasing and inside [anchor, last year]", ok)


def test_times_invert_cumulative_curve():
    from scipy.interpolate import PchipInterpolator

    times, targets, _ = core.compute_emission_times(X, Y, 0.5, 0)
    order = np.argsort(X)
    xs = np.sort(X)
    t_nodes = np.concatenate(([2 * xs[0] - xs[1]], xs))
    m_nodes = np.concatenate(([0.0], np.cumsum(Y[order])))
    m = PchipInterpolator(t_nodes, m_nodes)
    err = float(np.max(np.abs(m(times) - targets)))
    return _report("M(emission_time) reproduces each target mass", err < 1e-8, f"max error {err:.2e}")


def test_rejects_bad_input():
    cases = [
        ("negative mass", lambda: core.compute_emission_times([0, 1], [1, -1], 1.0, 0)),
        ("duplicate times", lambda: core.compute_emission_times([0, 0, 1], [1, 1, 1], 1.0, 0)),
        ("single point", lambda: core.compute_emission_times([0], [1], 1.0, 0)),
        ("mass per sphere > total", lambda: core.compute_emission_times(X, Y, TOTAL * 2, 0)),
        ("over safety cap", lambda: core.compute_emission_times(X, Y, 1e-6, 0, max_spheres=100)),
    ]
    ok = True
    for label, fn in cases:
        try:
            fn()
        except ValueError:
            continue
        print(f"    did not raise for {label}")
        ok = False
    return _report("invalid inputs raise ValueError", ok)


if __name__ == "__main__":
    results = [
        test_emitted_mass_matches_total_mass_interval(),
        test_emitted_mass_matches_total_num_spheres(),
        test_targets_are_midpoint_centred(),
        test_times_monotone_and_in_domain(),
        test_times_invert_cumulative_curve(),
        test_rejects_bad_input(),
    ]
    print(f"\n{sum(results)}/{len(results)} tests passed")
    raise SystemExit(0 if all(results) else 1)
