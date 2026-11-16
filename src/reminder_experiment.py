"""Simulate the frozen reminder design, reconcile customer rows and export aggregates."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from random import Random

import pandas as pd

from analyze_experiment import risk_difference
from experiment_plan import BASELINES, build_plan, frozen_population
from generate_data import CUTOFF
from run_sql import ROOT, load, query

SCHEMA = [
    {"name": name, "type": kind}
    for name, kind in (
        ("event_id", "STRING"), ("customer_id", "STRING"), ("kind", "STRING"),
        ("occurred_at", "TIMESTAMP"), ("arm", "STRING"), ("account_id", "STRING"),
        ("amount", "NUMERIC"),
    )
]


def simulate(population):
    rng = Random(20270102)
    assigned = list(population)
    rng.shuffle(assigned)
    for index, person in enumerate(assigned):
        customer_id = person["customer_id"]
        arm = "control" if index < len(assigned) // 2 else "treatment"
        account_id = person["open_savings_account_id"]

        def event(kind, day=0, hours=0, **fields):
            return dict(event_id=f"{customer_id}-{kind}", customer_id=customer_id,
                        kind=kind, occurred_at=(CUTOFF + timedelta(days=day, hours=hours)).isoformat(),
                        **fields)

        yield event("assignment", arm=arm, account_id=account_id)
        delivered, visited, funds, early, prompted = [rng.random() for _ in range(5)]
        if delivered < .97:
            yield event("email_delivery", 1, 1)
        baseline = funds < BASELINES[person["profile"]]
        shown = arm == "treatment" and visited < .55 and not (baseline and early < .25)
        if shown:
            yield event("in_app_impression", 4)
        if baseline or (shown and prompted < .04):
            day = (2 if early < .25 else 8) if baseline else 7
            yield event("posted_savings_deposit", day, account_id=account_id, amount="25.00")


def reference_rows(events):
    by_customer = defaultdict(dict)
    for event in events:
        seen = by_customer[event["customer_id"]]
        key = event["event_id"]
        if key in seen and seen[key] != event:
            raise ValueError(f"Conflicting event ID {key}")
        if key in seen and event["kind"] == "assignment":
            raise ValueError(f"Repeated assignment {key}")
        seen[key] = event

    for customer_id, indexed in sorted(by_customer.items()):
        rows = list(indexed.values())
        assignment, = [row for row in rows if row["kind"] == "assignment"]
        start = datetime.fromisoformat(assignment["occurred_at"])
        end = start + timedelta(days=14)
        in_window = [
            (datetime.fromisoformat(row["occurred_at"]), row)
            for row in rows if start <= datetime.fromisoformat(row["occurred_at"]) < end
        ]
        deposit = min((when for when, row in in_window
                       if row["kind"] == "posted_savings_deposit"
                       and row["account_id"] == assignment["account_id"]
                       and float(row["amount"]) > 0), default=None)
        touches = [(when, row["event_id"], row["kind"]) for when, row in in_window
                   if row["kind"] in ("email_delivery", "in_app_impression")]
        credit = sorted(touch for touch in touches if deposit and
                        touch[0] < deposit < touch[0] + timedelta(days=7))
        impressions = sum(touch[2] == "in_app_impression" for touch in touches)
        if assignment["arm"] == "control" and impressions:
            raise ValueError("Control received an in-app reminder")
        yield dict(customer_id=customer_id, arm=assignment["arm"], funded=deposit is not None,
                   impressions=impressions, first_touch=credit[0][2] if credit else None,
                   last_touch=credit[-1][2] if credit else None)


def summary(rows, plan, warehouse_verified):
    frame = pd.DataFrame(rows).rename(columns={"arm": "assigned_variant"})
    primary = risk_difference(frame, "funded", test_primary=True)
    credit = {rule: Counter((row[rule] or "unattributed") for row in rows if row["funded"])
              for rule in ("first_touch", "last_touch")}
    assert all(sum(counts.values()) == int(frame["funded"].sum()) for counts in credit.values())
    return dict(synthetic=True, warehouse_verified=warehouse_verified, primary=primary,
                mde=plan["profile_mixture"]["mde_absolute"],
                shown=sum(row["impressions"] > 0 for row in rows), credit=credit)


def run(history, directory, output, warehouse=False):
    people, receipt = frozen_population(history)
    plan = build_plan(history)
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "reminder_events.ndjson"
    with source.open("w") as handle:
        for event in simulate(people):
            handle.write(json.dumps(event) + "\n")
    with source.open() as handle:
        expected = list(reference_rows(map(json.loads, handle)))
    if len(expected) != len(people):
        raise ValueError("Customer rows do not match assignment population")
    if warehouse:
        project, dataset = receipt["destination"].split(".")
        config = project, dataset, "US"
        load(config, "raw_reminder_events", source, SCHEMA)
        body = (ROOT / "sql/marts/mart_reminder_customers.sql").read_text()
        records = query(config, body.replace("{{dataset}}", receipt["destination"]) +
                        "\nORDER BY customer_id", rows=len(people) + 1)
        records = [dict(row, impressions=int(row["impressions"]),
                        funded=str(row["funded"]).lower() == "true") for row in records]
        if records != expected:
            raise ValueError("BigQuery customer results differ from independent reconciliation")
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(summary(expected, plan, warehouse), indent=2) + "\n")
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--warehouse", action="store_true")
    args = parser.parse_args()
    run(args.history, args.directory, args.output, args.warehouse)
