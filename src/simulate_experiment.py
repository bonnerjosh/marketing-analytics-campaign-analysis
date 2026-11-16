"""Simulate two outcome scenarios with the same frozen history and assignment."""
import argparse
from contextlib import ExitStack
from datetime import timedelta
import json
from pathlib import Path
from random import Random

from experiment_plan import BASELINES, EXPERIMENT_ID, LIFT, build_plan, frozen_population
from generate_data import CUTOFF, between, digest

END = CUTOFF + timedelta(days=59)
TABLES = ("experiments", "marketing_events", "transactions", "ga4_events")
LATE = {"A": .048, "B": .035, "C": .022}
REPEAT = {"A": .40, "B": .32, "C": .22}
ENGAGEMENT = {"A": .70, "B": .39, "C": .22}
CLICK = {"A": .19, "B": .11, "C": .065}


def potential_activation(profile, uniform, lift):
    return uniform < BASELINES[profile], uniform < BASELINES[profile] + lift


def simulate(population, directory, scenario, seed, snapshot_sha):
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "scenario_manifest.json"
    manifest.unlink(missing_ok=True)
    lift = LIFT if scenario == "nonzero" else 0.0
    assign, potential, journey, marketing, app = (Random(f"{seed}:{label}") for label in
                                                  ("assignment", "potential", "journey", "marketing", "app"))
    counts = dict.fromkeys(TABLES, 0)
    with ExitStack() as stack:
        files = {table: stack.enter_context((directory / f"{table}.ndjson").open("w")) for table in TABLES}

        def emit(table, **record):
            counts[table] += 1
            files[table].write(json.dumps(record, separators=(",", ":")) + "\n")

        for row in population:
            customer = row["customer_id"]
            profile = row["profile"]
            treatment = assign.random() < .5
            arm = "treatment" if treatment else "control"
            early = potential_activation(profile, potential.random(), lift)[int(treatment)]
            emit("experiments", experiment_id=EXPERIMENT_ID, customer_id=customer,
                 assigned_variant=arm, assignment_timestamp=CUTOFF.isoformat(), eligibility_status="ELIGIBLE")
            for index, day in enumerate((0, 3), 1):
                campaign = "ny_savings_index" if index == 1 else "ny_savings_reminder"
                variant = arm if index == 1 else "common"
                message = f"{customer}-M{index}"
                sent = CUTOFF + timedelta(days=day)
                delivered = sent + timedelta(minutes=marketing.randint(1, 90))
                clicked = delivered + timedelta(minutes=marketing.randint(1, 5 * 24 * 60))
                delivery_draw, click_draw = marketing.random(), marketing.random()

                def marketing_event(kind, timestamp):
                    emit("marketing_events", event_id=f"M{counts['marketing_events'] + 1:09d}",
                         customer_id=customer, message_id=message, campaign_id=campaign,
                         event_timestamp=timestamp.isoformat(), event_type=kind,
                         channel="email", message_variant=variant)

                marketing_event("sent", sent)
                if delivery_draw < .965:
                    marketing_event("delivered", delivered)
                    if click_draw < CLICK[profile] * (1 if index == 1 else .8):
                        marketing_event("clicked", clicked)

            late = journey.random() < LATE[profile]
            early_at = between(journey, CUTOFF + timedelta(seconds=20), CUTOFF + timedelta(days=14))
            late_at = between(journey, CUTOFF + timedelta(days=14), CUTOFF + timedelta(days=30))
            repeat = journey.random() < REPEAT[profile]
            repeat_after = timedelta(days=journey.randint(2, 29), minutes=journey.randint(0, 120))
            amount_scale = {"A": 1.3, "B": 1.15, "C": 1.0}[profile]
            cents_first = round(amount_scale * journey.randint(500, 30_000))
            cents_repeat = round(amount_scale * journey.randint(500, 25_000))
            first = early_at if early else late_at if late else None

            def deposit(timestamp, cents):
                emit("transactions", transaction_id=f"X{counts['transactions'] + 1:09d}",
                     account_id=row["open_savings_account_id"], transaction_timestamp=timestamp.isoformat(),
                     transaction_type="DEPOSIT", transaction_status="COMPLETED", amount=f"{cents // 100}.{cents % 100:02d}")

            if first is not None:
                deposit(first, cents_first)
                if repeat and first + repeat_after < END:
                    deposit(first + repeat_after, cents_repeat)

            background = app.random() < ENGAGEMENT[profile]
            initiative = app.random() < .26
            app_posting = app.random() < .62
            app_at = between(app, CUTOFF, CUTOFF + timedelta(days=30) - timedelta(seconds=20))

            def session(at, actions):
                session_id = 10_000_000 + counts["ga4_events"]
                for index, event in enumerate(("session_start", "app_open", *actions)):
                    timestamp = at + timedelta(seconds=2 * index)
                    emit("ga4_events", event_id=f"X{counts['ga4_events'] + 1:09d}", user_id=customer,
                         user_pseudo_id="P" + customer[1:], event_name=event,
                         event_timestamp=int(timestamp.timestamp()) * 1_000_000,
                         event_date=timestamp.strftime("%Y%m%d"),
                         platform="ANDROID" if int(customer[1:]) % 2 else "IOS",
                         event_params=[
                             {"key": "ga_session_id", "value": {"int_value": session_id}},
                             {"key": "screen_name", "value": {"string_value": "savings" if index > 1 else "home"}},
                         ])

            if background:
                actions = ["savings_account_view"]
                if initiative:
                    actions.append("deposit_initiated")
                session(app_at, actions)
            if first is not None and app_posting:
                session(first - timedelta(seconds=7),
                        ["savings_account_view", "deposit_initiated", "deposit_confirmation_view"])

    manifest.write_text(json.dumps({
        "synthetic": True, "scenario": scenario, "seed": seed, "scenario_lift": lift,
        "eligible_snapshot_sha256": snapshot_sha,
        "coverage_end_exclusive": END.isoformat(),
        "tables": {name: {"rows": count, "sha256": digest(directory / f"{name}.ndjson")}
                   for name, count in counts.items()},
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=20270101)
    args = parser.parse_args()
    people, receipt = frozen_population(args.history)
    plan = json.loads((args.output / "power_plan.json").read_text())
    if plan != build_plan(args.history):
        parser.error("Generate the matching power plan before simulating outcomes")
    for scenario in ("null", "nonzero"):
        simulate(people, args.output / scenario, scenario, args.seed, receipt["eligible_snapshot_sha256"])
