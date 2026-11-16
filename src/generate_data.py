"""Generate synthetic 2026 history as local BigQuery NDJSON."""
import argparse
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from hashlib import file_digest
import json
from pathlib import Path
from random import Random

from schema import SCHEMAS

START = datetime(2026, 1, 1, tzinfo=UTC)
CUTOFF = datetime(2027, 1, 1, tzinfo=UTC)
REGIONS = {
    "Northeast": "CT ME MA NH RI VT NJ NY PA",
    "Midwest": "IN IL MI OH WI IA KS MN MO NE ND SD",
    "South": "DE DC FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX",
    "West": "AZ CO ID MT NV NM UT WY AK CA HI OR WA",
}
STATE_REGION = {state: region for region, states in REGIONS.items() for state in states.split()}
STATE_WEIGHTS = {"CA": 9, "TX": 8, "FL": 6, "NY": 5, "PA": 3, "IL": 3, "OH": 3,
                 "GA": 3, "NC": 3, "DC": 0.2, "AK": 0.3, "HI": 0.4}
CHANNEL_ENGAGEMENT = {"organic": 0.10, "referral": 0.15, "paid_social": -0.12, "partner": -0.03}


def between(rng, start, stop):
    return start + timedelta(seconds=rng.randrange(int((stop - start).total_seconds())))


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def generate(directory, count, seed):
    rng = Random(seed)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "history_manifest.json"
    manifest.unlink(missing_ok=True)
    totals = dict.fromkeys(SCHEMAS, 0)

    with ExitStack() as stack:
        writers = {name: stack.enter_context((directory / f"{name}.ndjson").open("w"))
                   for name in SCHEMAS}

        def emit(table, **row):
            totals[table] += 1
            writers[table].write(json.dumps(row, separators=(",", ":")) + "\n")

        for index in range(1, count + 1):
            customer_id = f"C{index:06d}"
            pseudo_id = f"P{index:06d}"
            signup = between(rng, START, CUTOFF)
            channel = rng.choices(list(CHANNEL_ENGAGEMENT), [36, 25, 25, 14])[0]
            segment = rng.choices(["everyday_banking", "payments", "savings_interest"], [55, 23, 22])[0]
            state = rng.choices(list(STATE_REGION), [STATE_WEIGHTS.get(s, 1) for s in STATE_REGION])[0]
            market_weights = [48, 43, 9] if STATE_WEIGHTS.get(state, 1) >= 3 else [24, 43, 33]
            market = rng.choices(["urban", "suburban", "rural"], market_weights)[0]
            age = rng.choices(["18–24", "25–34", "35–44", "45–54", "55+"], [18, 33, 24, 15, 10])[0]
            engagement = min(1, max(0, rng.random() + CHANNEL_ENGAGEMENT[channel]))
            propensity = min(1, max(0, 0.55 * rng.random() + 0.35 * engagement
                                    + 0.13 * (segment == "savings_interest")
                                    + 0.025 * (STATE_REGION[state] == "West")
                                    - 0.025 * (market == "rural") - 0.02 * (age == "18–24")))
            platform = rng.choices(["ANDROID", "IOS"], [53, 47])[0]
            emit("customers", customer_id=customer_id, signup_timestamp=signup.isoformat(),
                 acquisition_channel=channel, acquisition_campaign=f"{channel}_2026",
                 customer_segment=segment, state=state, region=STATE_REGION[state],
                 market_type=market, age_band=age)

            def account(kind, suffix, opening, closing=None):
                account_id = f"{customer_id}_{suffix}"
                emit("accounts", account_id=account_id, customer_id=customer_id,
                     account_type=kind, account_open_timestamp=opening.isoformat(),
                     account_close_timestamp=closing.isoformat() if closing else None,
                     account_status="CLOSED" if closing else "OPEN")
                return account_id

            def transaction(account_id, when, kind, cents, status="COMPLETED"):
                emit("transactions", transaction_id=f"T{totals['transactions'] + 1:09d}",
                     account_id=account_id, transaction_timestamp=when.isoformat(),
                     transaction_type=kind, amount=f"{cents // 100}.{cents % 100:02d}",
                     transaction_status=status)

            def session(when, actions, campaign=None):
                session_id = totals["ga4_events"] + 1
                for sequence, (name, extra) in enumerate([("session_start", {}), ("app_open", {})] + actions):
                    event_time = when + timedelta(seconds=2 * sequence)
                    params = {"ga_session_id": session_id, "screen_name": "savings" if extra or name.startswith(("savings", "deposit")) else "home"}
                    params.update(extra)
                    if campaign:
                        params["campaign_id"] = campaign
                    emit("ga4_events", event_id=f"E{totals['ga4_events'] + 1:09d}",
                         event_date=event_time.strftime("%Y%m%d"),
                         event_timestamp=int(event_time.timestamp()) * 1_000_000,
                         user_pseudo_id=pseudo_id, user_id=customer_id, event_name=name, platform=platform,
                         event_params=[{"key": key, "value": {"int_value" if isinstance(value, int)
                                                               else "string_value": value}}
                                       for key, value in params.items()])

            checking = account("CHECKING", "CH1", signup)
            tenure = (CUTOFF - signup).total_seconds() / 86400
            for _ in range(round(tenure / 30 * (1 + 11 * engagement))):
                transaction(checking, between(rng, signup, CUTOFF),
                            rng.choice(["DEBIT", "CREDIT"]), rng.randint(100, 35_000))

            savings = []
            if tenure >= 1 and rng.random() < 0.26 + 0.52 * propensity:
                opened = signup + timedelta(hours=rng.randrange(min(24 * 65, int(tenure * 24))))
                has_second = CUTOFF - opened >= timedelta(days=25) and rng.random() < 0.13
                closing = opened + timedelta(days=20) if has_second and rng.random() < 0.5 else None
                first = account("SAVINGS", "SV1", opened, closing)
                savings.append((first, opened, closing or CUTOFF))
                if has_second:
                    second_opened = opened + timedelta(days=24)
                    second = account("SAVINGS", "SV2", second_opened)
                    savings.append((second, second_opened, CUTOFF))

            for account_id, opened, stop in savings:
                if (stop - opened).days >= 1 and rng.random() < 0.12 + 0.63 * propensity:
                    last = min(stop, opened + timedelta(days=60)) - timedelta(seconds=20)
                    posted = between(rng, opened + timedelta(seconds=20), last)
                    transaction(account_id, posted, "DEPOSIT", rng.randint(500, 80_000))
                    if rng.random() < 0.50:
                        session(posted - timedelta(seconds=7), [
                            ("savings_account_view", {}), ("deposit_initiated", {}),
                            ("deposit_confirmation_view", {}),
                        ])
                    for _ in range(rng.choices([0, 1, 2, 3], [47, 31, 16, 6])[0]):
                        posted += timedelta(days=rng.randint(4, 29))
                        if posted < stop:
                            transaction(account_id, posted, "DEPOSIT", rng.randint(500, 80_000))
                if rng.random() < 0.18:
                    transaction(account_id, between(rng, opened, stop), "DEPOSIT", rng.randint(500, 20_000),
                                rng.choice(["PENDING", "FAILED", "REVERSED"]))

            if tenure > 1:
                session(signup, [("onboarding_step_completed", {})], campaign=f"{channel}_2026")
                for _ in range(round(tenure / 30 * (0.35 + 9 * engagement))):
                    when = between(rng, signup, CUTOFF - timedelta(seconds=30))
                    actions = []
                    if any(opened <= when < stop for _, opened, stop in savings) and rng.random() < propensity * 0.85:
                        actions.append(("savings_account_view", {}))
                        if rng.random() < 0.4:
                            goal = {"savings_goal_type": rng.choice(["emergency", "travel", "general"])}
                            actions.append(("savings_goal_started", goal))
                            if rng.random() < 0.55:
                                actions.append(("savings_goal_completed", goal))
                        if rng.random() < 0.30:
                            actions.append(("deposit_initiated", {}))
                    session(when, actions)

    metadata = {
        "synthetic": True, "schema_version": 1, "seed": seed, "customer_count": count,
        "history_start": START.isoformat(), "history_end_exclusive": CUTOFF.isoformat(),
        "tables": {name: {"row_count": total, "sha256": digest(directory / f"{name}.ndjson")}
                   for name, total in totals.items()},
    }
    pending = manifest.with_suffix(".tmp")
    pending.write_text(json.dumps(metadata, indent=2) + "\n")
    pending.replace(manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/history"))
    parser.add_argument("--customers", type=int, default=40_000)
    parser.add_argument("--seed", type=int, default=20270101)
    args = parser.parse_args()
    if args.customers < 1:
        parser.error("--customers must be positive")
    generate(args.output, args.customers, args.seed)
