"""Local contract and deterministic generator tests (Python standard library only)."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import groupby
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_data import CUTOFF, START, STATE_REGION, digest, generate
from schema import SCHEMAS


def rows(directory, name):
    with (directory / f"{name}.ndjson").open() as stream:
        yield from map(json.loads, stream)


def validate_history(test, directory):
    manifest = json.loads((directory / "history_manifest.json").read_text())
    test.assertTrue(manifest["synthetic"])
    for name, table in manifest["tables"].items():
        test.assertEqual(table["sha256"], digest(directory / f"{name}.ndjson"))

    customers = {}
    for customer in rows(directory, "customers"):
        key = customer["customer_id"]
        signup = datetime.fromisoformat(customer["signup_timestamp"])
        test.assertNotIn(key, customers)
        test.assertTrue(START <= signup < CUTOFF)
        test.assertEqual(STATE_REGION[customer["state"]], customer["region"])
        customers[key] = signup
    test.assertEqual(len(customers), manifest["customer_count"])

    accounts = {}
    open_savings = {}
    for account in rows(directory, "accounts"):
        key = account["account_id"]
        customer = account["customer_id"]
        opened = datetime.fromisoformat(account["account_open_timestamp"])
        closed = account["account_close_timestamp"]
        end = datetime.fromisoformat(closed) if closed else CUTOFF
        test.assertNotIn(key, accounts)
        test.assertTrue(customers[customer] <= opened < end <= CUTOFF)
        test.assertEqual("CLOSED" if closed else "OPEN", account["account_status"])
        accounts[key] = customer, opened, end, account["account_type"]
        if not closed and account["account_type"] == "SAVINGS":
            candidate = opened, key
            if customer not in open_savings or candidate < open_savings[customer]:
                open_savings[customer] = candidate
    test.assertEqual(len(accounts), manifest["tables"]["accounts"]["row_count"])

    funded = set()
    postings = defaultdict(set)
    checking = Counter()
    cutoff_feature = CUTOFF - timedelta(days=30)
    transaction_count = 0
    for transaction_count, txn in enumerate(rows(directory, "transactions"), 1):
        test.assertEqual(txn["transaction_id"], f"T{transaction_count:09d}")
        customer, opened, end, kind = accounts[txn["account_id"]]
        when = datetime.fromisoformat(txn["transaction_timestamp"])
        test.assertTrue(opened <= when < end)
        test.assertGreater(Decimal(txn["amount"]), 0)
        test.assertIn(txn["transaction_status"], {"COMPLETED", "PENDING", "FAILED", "REVERSED"})
        test.assertIn(txn["transaction_type"], {"DEPOSIT"} if kind == "SAVINGS" else {"DEBIT", "CREDIT"})
        if txn["transaction_status"] == "COMPLETED":
            if kind == "SAVINGS":
                funded.add(customer)
                postings[customer].add(int(when.timestamp()))
            elif when >= cutoff_feature:
                checking[customer] += 1
    test.assertEqual(transaction_count, manifest["tables"]["transactions"]["row_count"])

    def session_key(event):
        return event["user_pseudo_id"], event["event_params"][0]["value"]["int_value"]

    event_count = 0
    sessions = Counter()
    savings = Counter()
    event_feature = int(cutoff_feature.timestamp()) * 1_000_000
    for _, session in groupby(rows(directory, "ga4_events"), session_key):
        start = None
        seen = set()
        for event in session:
            event_count += 1
            test.assertEqual(event["event_id"], f"E{event_count:09d}")
            customer = event["user_id"]
            test.assertEqual(event["user_pseudo_id"], "P" + customer[1:])
            when = event["event_timestamp"]
            name = event["event_name"]
            test.assertTrue(int(customers[customer].timestamp()) * 1_000_000
                            <= when < int(CUTOFF.timestamp()) * 1_000_000)
            test.assertEqual(START.fromtimestamp(when / 1_000_000, START.tzinfo).strftime("%Y%m%d"),
                             event["event_date"])
            keys = {param["key"] for param in event["event_params"]}
            test.assertEqual(len(keys), len(event["event_params"]))
            if start is None:
                test.assertEqual(name, "session_start")
                test.assertEqual(session_key(event)[1], event_count)
                start = when
            else:
                test.assertNotEqual(name, "session_start")
                test.assertGreater(when, previous)
            if name == "deposit_confirmation_view":
                test.assertIn("deposit_initiated", seen)
                test.assertIn(when // 1_000_000 - 1, postings[customer])
            if name == "savings_goal_completed":
                test.assertIn("savings_goal_started", seen)
            previous = when
            seen.add(name)
        if start >= event_feature:
            sessions[customer] += 1
            if seen & {"savings_account_view", "savings_goal_started", "savings_goal_completed", "deposit_initiated"}:
                savings[customer] += 1

    test.assertEqual(event_count, manifest["tables"]["ga4_events"]["row_count"])
    for name in ("experiments", "marketing_events"):
        test.assertEqual(manifest["tables"][name]["row_count"], 0)
        test.assertEqual(list(rows(directory, name)), [])
    eligible = open_savings.keys() - funded
    expected_snapshot = {}
    for customer in eligible:
        s, g, c = sessions[customer], savings[customer], checking[customer]
        if s >= 6 and g >= 2 and c >= 4:
            profile = "A"
        elif c >= 6 and s >= 2 and g <= 1:
            profile = "B"
        else:
            profile = "C"
        expected_snapshot[customer] = profile, open_savings[customer][1]
    if (directory / "eligible.ndjson").exists():
        receipt = json.loads((directory / "warehouse_validation.json").read_text())
        test.assertEqual(receipt["history_manifest_sha256"], digest(directory / "history_manifest.json"))
        test.assertEqual(receipt["eligible_snapshot_sha256"], digest(directory / "eligible.ndjson"))
        observed = {}
        for record in rows(directory, "eligible"):
            customer = record["customer_id"]
            test.assertNotIn(customer, observed)
            observed[customer] = record["profile"], record["open_savings_account_id"]
        test.assertEqual(observed, expected_snapshot)
        print(f"Compared all {len(observed):,} warehouse customer, account and profile rows with local history")
    return Counter(profile for profile, _ in expected_snapshot.values())


class HistoricalDataTests(unittest.TestCase):
    def test_seeded_history(self):
        with TemporaryDirectory() as left, TemporaryDirectory() as right:
            left, right = Path(left), Path(right)
            generate(left, 180, 17)
            generate(right, 180, 17)
            self.assertEqual((left / "history_manifest.json").read_bytes(),
                             (right / "history_manifest.json").read_bytes())
            self.assertEqual(set(SCHEMAS), {"customers", "accounts", "transactions",
                                           "ga4_events", "experiments", "marketing_events"})
            self.assertEqual(len(STATE_REGION), 51)
            self.assertGreater(sum(validate_history(self, left).values()), 0)

    @unittest.skipUnless(os.environ.get("HISTORY_DIR"), "set HISTORY_DIR to validate a full run")
    def test_full_history(self):
        counts = validate_history(self, Path(os.environ["HISTORY_DIR"]))
        self.assertEqual(set(counts), {"A", "B", "C"})
        print(f"Local diagnostic eligibility: {sum(counts.values())}; profiles: {dict(sorted(counts.items()))}")
