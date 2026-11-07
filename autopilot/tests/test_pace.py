import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pace import DEFAULTS, decide, target_utilisation  # noqa: E402

H = 3600
RESET = 1_794_092_400  # Sat 2026-11-07 15:00 PST


def run(u7, u5, hours_left, **kw):
    return decide(u7, u5, RESET, RESET - hours_left * H, dict(DEFAULTS), **kw)


class Pace(unittest.TestCase):
    def test_curve_linear_then_final_sweep(self):
        self.assertAlmostEqual(target_utilisation(168, DEFAULTS), 0.0)
        self.assertAlmostEqual(target_utilisation(84, DEFAULTS), 0.46)
        self.assertAlmostEqual(target_utilisation(10, DEFAULTS), 0.92)

    def test_on_pace_does_nothing(self):
        r = run(0.45, 0.1, 84)
        self.assertEqual(r["workers"], 0)
        self.assertEqual(r["reason"], "on pace")

    def test_behind_pace_dispatches_up_to_max(self):
        r = run(0.24, 0.04, 10)  # today's real numbers
        self.assertEqual(r["workers"], DEFAULTS["max_workers"])

    def test_five_hour_window_guard(self):
        self.assertEqual(run(0.10, 0.75, 10)["workers"], 0)
        # 0.55 used -> room for one worker at 0.15 each under 0.70
        self.assertEqual(run(0.10, 0.55, 10)["workers"], 1)

    def test_in_flight_and_user_active(self):
        self.assertEqual(run(0.24, 0.04, 10, in_flight=2)["workers"], 1)
        self.assertEqual(run(0.24, 0.04, 10, user_active=True)["workers"], 1)

    def test_target_reached_and_stale(self):
        self.assertEqual(run(0.93, 0.0, 10)["workers"], 0)
        self.assertEqual(run(0.10, 0.0, -1)["workers"], 0)


if __name__ == "__main__":
    unittest.main()
