import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from generate_data import CUTOFF
from reminder_experiment import reference_rows, simulate


def event(customer, kind, day, suffix="", **fields):
    return dict(customer_id=customer, event_id=f"{customer}-{kind}{suffix}", kind=kind,
                occurred_at=(CUTOFF + timedelta(days=day)).isoformat(), **fields)


class ReminderTests(unittest.TestCase):
    def test_assignment_and_touch_windows(self):
        a, b, c = "a", "b", "c"
        impression = event(a, "in_app_impression", 4)
        events = [
            event(a, "assignment", 0, arm="treatment", account_id=a),
            event(a, "email_delivery", 1), impression, dict(impression),
            event(a, "posted_savings_deposit", 6, account_id=a, amount="25"),
            event(b, "assignment", 0, arm="treatment", account_id=b),
            event(b, "email_delivery", 1),
            event(b, "posted_savings_deposit", 2, account_id=b, amount="25"),
            event(b, "in_app_impression", 4),
            event(c, "assignment", 0, arm="treatment", account_id=c),
            event(c, "posted_savings_deposit", 14, account_id=c, amount="25"),
        ]
        self.assertEqual(list(reference_rows(events)), [
            dict(customer_id=a, arm="treatment", funded=True, impressions=1,
                 first_touch="email_delivery", last_touch="in_app_impression"),
            dict(customer_id=b, arm="treatment", funded=True, impressions=1,
                 first_touch="email_delivery", last_touch="email_delivery"),
            dict(customer_id=c, arm="treatment", funded=False, impressions=0,
                 first_touch=None, last_touch=None),
        ])

    def test_randomization_is_balanced_and_reproducible(self):
        population = [
            dict(customer_id=str(i), profile="A", open_savings_account_id=f"account-{i}")
            for i in range(101)
        ]
        events = list(simulate(population))
        self.assertEqual(events, list(simulate(population)))
        rows = list(reference_rows(events))
        self.assertEqual(len(rows), 101)
        self.assertEqual(sum(row["arm"] == "control" for row in rows), 50)
        self.assertGreater(sum(row["impressions"] for row in rows), 0)
