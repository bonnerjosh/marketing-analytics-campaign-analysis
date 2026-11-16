"""Check planning arithmetic, outcome boundaries, and treatment simulation."""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import sys
from random import Random
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyze_experiment import local_outcomes
from experiment_plan import BASELINES, LIFT, design_row
from generate_data import CUTOFF
from simulate_experiment import potential_activation


class ExperimentTests(unittest.TestCase):
    def test_planning_reference(self):
        plan = design_row(.08, 5350)
        self.assertEqual(plan["n_required_per_arm"], 3213)
        self.assertAlmostEqual(plan["mde_absolute"], .01531684)
        self.assertGreater(plan["power_at_target"], .95)

    def test_exact_cutoffs(self):
        first = CUTOFF + timedelta(seconds=1)
        day14 = CUTOFF + timedelta(days=14)
        day30 = CUTOFF + timedelta(days=30)
        amount = Decimal("10.05")
        self.assertEqual(local_outcomes([(day14, amount)], False)["activated_14d"], 0)
        self.assertEqual(local_outcomes([(day30, amount)], False)["activated_30d"], 0)
        self.assertEqual(local_outcomes([(day30, amount)], False)["deposit_amount_30d"], 0)
        self.assertEqual(local_outcomes([(first, amount), (first + timedelta(days=30), amount)],
                                        False)["sustained_saving"], 0)
        self.assertEqual(local_outcomes([(first, amount), (day30, amount)], True)["sustained_saving"], 1)
        self.assertEqual(local_outcomes([(first, amount), (day30, amount)], True)["deposit_amount_30d"], amount)

    def test_null_potential_outcomes_and_common_draw(self):
        uniform = Random(17)
        for profile, p0 in BASELINES.items():
            for _ in range(200):
                draw = uniform.random()
                c, t = potential_activation(profile, draw, 0)
                self.assertEqual(c, t)
                self.assertEqual(c, potential_activation(profile, draw, LIFT)[0])
            self.assertEqual(potential_activation(profile, p0 + LIFT / 2, LIFT), (False, True))
