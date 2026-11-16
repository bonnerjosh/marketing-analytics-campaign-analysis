"""Validate scenario extracts against facts and analyze prespecified experiment outcomes."""
import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest, fisher_exact
from statsmodels.formula.api import ols
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from experiment_plan import ALPHA, BASELINES, EXPERIMENT_ID, build_plan, frozen_population, power
from generate_data import CUTOFF, digest
from run_experiment_sql import verified_manifest

ARMS = ("control", "treatment")
BINARY = ("activated_14d", "activated_30d", "sustained_saving", "app_engaged_30d")
AMOUNT = "deposit_amount_30d"


def ndjson(path):
    with path.open() as stream:
        yield from map(json.loads, stream)


def timestamp(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except ValueError:
        parsed = datetime.fromisoformat(value.replace(" UTC", "+00:00").replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def flag(value):
    if isinstance(value, bool):
        return int(value)
    if str(value).lower() in {"true", "1"}:
        return 1
    if str(value).lower() in {"false", "0"}:
        return 0
    raise ValueError(f"Unexpected Boolean value: {value!r}")


def local_outcomes(deposits, engagement):
    first, second = (sorted(deposits) + [(None, 0), (None, 0)])[:2]
    day14, day30 = CUTOFF + timedelta(days=14), CUTOFF + timedelta(days=30)
    timely = first[0] is not None and CUTOFF <= first[0] < day14
    return {
        "first_deposit": first[0], "second_deposit": second[0],
        "activated_14d": int(timely),
        "activated_30d": int(first[0] is not None and CUTOFF <= first[0] < day30),
        "sustained_saving": int(timely and second[0] is not None and second[0] < first[0] + timedelta(days=30)),
        "app_engaged_30d": int(engagement),
        AMOUNT: sum((value for time, value in deposits if CUTOFF <= time < day30), Decimal(0)),
    }


def validate_facts(directory, population, records):
    frozen = {row["customer_id"]: row for row in population}
    owners = {row["open_savings_account_id"]: row["customer_id"] for row in population}
    assigned = {row["customer_id"]: row["assigned_variant"] for row in ndjson(directory / "experiments.ndjson")}
    deposits = defaultdict(list)
    for row in ndjson(directory / "transactions.ndjson"):
        if row["transaction_status"] == "COMPLETED" and row["transaction_type"] == "DEPOSIT":
            value = Decimal(row["amount"])
            if value > 0:
                deposits[owners[row["account_id"]]].append((timestamp(row["transaction_timestamp"]), value))
    engagement = {
        row["user_id"] for row in ndjson(directory / "ga4_events.ndjson")
        if CUTOFF <= timestamp(row["event_timestamp"] / 1_000_000) < CUTOFF + timedelta(days=30)
        and row["event_name"] in {"savings_account_view", "savings_goal_started",
                                  "savings_goal_completed", "deposit_initiated"}
    }
    observed = set()
    for row in records:
        customer = row["customer_id"]
        if customer in observed or customer not in frozen:
            raise ValueError(f"Unexpected or repeated customer {customer}")
        observed.add(customer)
        expected = frozen[customer]
        if (row["open_savings_account_id"] != expected["open_savings_account_id"]
                or row["profile"] != expected["profile"]
                or row["assigned_variant"] != assigned[customer] or row["assigned_variant"] not in ARMS
                or row["experiment_id"] != EXPERIMENT_ID or timestamp(row["assignment_timestamp"]) != CUTOFF):
            raise ValueError(f"SQL mart assignment or frozen profile mismatch for {customer}")
        for key, truth in local_outcomes(deposits[customer], customer in engagement).items():
            if key in BINARY:
                value = flag(row[key])
            elif key == AMOUNT:
                value = Decimal(row[key])
            else:
                value = timestamp(row.get(key))
            if value != truth:
                raise ValueError(f"SQL mart and local facts disagree for {customer}: {key}")
    if observed != set(frozen) or observed != set(assigned):
        raise ValueError("SQL mart did not preserve the frozen randomized population")


def read_frame(history, directory):
    population, frozen = frozen_population(history)
    verified_manifest(directory, frozen["eligible_snapshot_sha256"])
    receipt = json.loads((directory / "mart_receipt.json").read_text())
    if (receipt.get("synthetic") is not True or receipt["scenario"] != directory.name
            or receipt["destination"] != frozen["destination"]
            or receipt["manifest_sha256"] != digest(directory / "scenario_manifest.json")
            or not all(digest(directory / name) == expected for name, expected in receipt["exports"].items())):
        raise ValueError("Scenario warehouse extracts failed provenance validation")
    records = json.loads((directory / "experiment_customers.json").read_text())
    validate_facts(directory, population, records)
    counts = {row["assigned_variant"]: row for row in json.loads((directory / "arm_counts.json").read_text())}
    for arm, fields in counts.items():
        rows = [row for row in records if row["assigned_variant"] == arm]
        if (len(rows) != int(fields["n"]) or any(sum(flag(row[key]) for row in rows) != int(fields[key]) for key in BINARY)
                or sum(Decimal(row[AMOUNT]) for row in rows) != Decimal(fields[AMOUNT])):
            raise ValueError(f"SQL aggregate and row-level metrics disagree: {arm}")
    if set(counts) != set(ARMS):
        raise ValueError("Both assigned arms must appear in the warehouse aggregates")

    frame = pd.DataFrame(records)
    for key in BINARY:
        frame[key] = frame[key].map(flag)
    for key in (AMOUNT, "tenure_days", "sessions", "savings_sessions", "checking_transactions"):
        frame[key] = pd.to_numeric(frame[key], errors="raise")
    frame["treatment"] = frame["assigned_variant"].eq("treatment").astype(int)
    return frame


def risk_difference(frame, outcome, test_primary=False):
    counts = frame.groupby("assigned_variant")[outcome].agg(["sum", "size"])
    yc, nc = map(int, counts.loc["control"])
    yt, nt = map(int, counts.loc["treatment"])
    pc, pt = yc / nc, yt / nt
    ci = confint_proportions_2indep(yt, nt, yc, nc, method="newcomb", compare="diff", alpha=ALPHA)
    result = {"control": {"n": nc, "events": yc, "rate": pc},
              "treatment": {"n": nt, "events": yt, "rate": pt},
              "absolute_lift": pt - pc, "relative_lift": (pt - pc) / pc if pc else None,
              "ci95": list(map(float, ci))}
    if test_primary:
        expected_yes = (yt + yc) / (nt + nc)
        if min(nt * expected_yes, nc * expected_yes, nt * (1 - expected_yes), nc * (1 - expected_yes)) < 5:
            p = fisher_exact([[yt, nt - yt], [yc, nc - yc]], alternative="two-sided").pvalue
            method = "Two-sided Fisher exact"
        else:
            _, p = proportions_ztest([yt, yc], [nt, nc], alternative="two-sided")
            method = "Two-sided pooled proportions z-test"
        result.update({"p_value": float(p), "test": method, "reject_equal_rates": bool(p < ALPHA),
                       "estimated_incremental_activations": (pt - pc) * nt,
                       "incremental_activations_ci95": [float(bound * nt) for bound in ci]})
    return result


def amount_difference(frame):
    arms = {arm: frame.loc[frame["assigned_variant"] == arm, AMOUNT].to_numpy() for arm in ARMS}
    c, t = arms["control"], arms["treatment"]
    rng = np.random.default_rng(20270101)
    samples = []
    for _ in range(50):
        c_mean = c[rng.integers(len(c), size=(100, len(c)))].mean(axis=1)
        t_mean = t[rng.integers(len(t), size=(100, len(t)))].mean(axis=1)
        samples.extend(t_mean - c_mean)
    return {"control_mean": float(c.mean()), "treatment_mean": float(t.mean()),
            "difference": float(t.mean() - c.mean()), "ci95": np.quantile(samples, [.025, .975]).tolist()}


def interaction(frame):
    sizes = frame.groupby(["profile", "treatment"])["activated_14d"].agg(["size", "sum"])
    if (len(sizes) != 2 * len(BASELINES) or sizes["sum"].min() < 5
            or (sizes["size"] - sizes["sum"]).min() < 5):
        return {"p_value": None, "reason": "Sparse profile-by-arm outcomes"}
    fitted = ols("activated_14d ~ treatment * C(profile)", data=frame).fit(cov_type="HC3")
    test = fitted.wald_test("treatment:C(profile)[T.B] = 0, treatment:C(profile)[T.C] = 0",
                            use_f=False, scalar=True)
    return {"p_value": float(test.pvalue), "chi2": float(test.statistic), "df": 2,
            "method": "Joint Wald test with HC3 standard errors", "exploratory": True}


def validate_touches(directory, frame, touches, campaign):
    messages = defaultdict(dict)
    for row in ndjson(directory / "marketing_events.ndjson"):
        message = messages[row["customer_id"]].setdefault(row["message_id"], {"campaign": row["campaign_id"]})
        message[row["event_type"]] = timestamp(row["event_timestamp"])
    phase_end = CUTOFF + timedelta(days=14)
    window = timedelta(days=7)
    patterns = Counter()
    expected_counts = defaultdict(Counter)
    for row in frame.itertuples(index=False):
        first = timestamp(row.first_deposit) if pd.notna(row.first_deposit) else None
        candidates = []
        for message_id, message in messages[row.customer_id].items():
            campaign_id = message["campaign"]
            delivered, clicked = message.get("delivered"), message.get("clicked")
            metrics = expected_counts[campaign_id]
            metrics["messages_sent"] += 1
            metrics["messages_delivered"] += delivered is not None
            # Both fixture campaigns have seven full days of follow-up after delivery.
            metrics["mature_delivered_recipients"] += delivered is not None
            metrics["unique_clickers"] += clicked is not None
            metrics["unique_clickers_14d"] += clicked is not None and CUTOFF <= clicked < phase_end
            if row.activated_14d and clicked is not None and CUTOFF <= clicked < first < clicked + window:
                metrics["activated_after_click"] += 1
            if row.activated_14d and delivered is not None and CUTOFF <= delivered < first < delivered + window:
                candidates.append((delivered, message_id, campaign_id))
        if row.activated_14d:
            candidates.sort()
            patterns[(candidates[0][2], candidates[-1][2]) if candidates else (None, None)] += 1
    sql_patterns = {(row.get("first_touch_campaign"), row.get("last_touch_campaign")): int(row["activations"])
                    for row in touches}
    if patterns != sql_patterns:
        raise ValueError("BigQuery attribution windows disagree with the message and transaction facts")
    for row in campaign:
        if row["breakdown"] == "overall":
            for key, expected in expected_counts[row["campaign_id"]].items():
                if int(row[key]) != expected:
                    raise ValueError(f"Campaign metric does not reconcile: {row['campaign_id']} {key}")


def analyze(history, directory, plan):
    frame = read_frame(history, directory)
    n_treatment = int(frame["treatment"].sum())
    srm = float(binomtest(n_treatment, len(frame), p=.5).pvalue)
    if srm < .01:
        raise ValueError(f"Sample ratio mismatch requires investigation (p = {srm:.4g})")
    features = ["tenure_days", "sessions", "savings_sessions", "checking_transactions"]
    balance = frame.groupby("assigned_variant")[features].mean().to_dict(orient="index")
    metrics = {outcome: risk_difference(frame, outcome, outcome == "activated_14d") for outcome in BINARY}
    metrics[AMOUNT] = amount_difference(frame)
    touches = json.loads((directory / "attribution_counts.json").read_text())
    campaign = json.loads((directory / "campaign_performance.json").read_text())
    validate_touches(directory, frame, touches, campaign)
    if sum(int(row["activations"]) for row in touches) != int(frame["activated_14d"].sum()):
        raise ValueError("Attribution counts do not reconcile to all primary activations")
    touch_totals = {}
    for field in ("first_touch_campaign", "last_touch_campaign"):
        totals = Counter()
        for row in touches:
            totals[row.get(field) or "unattributed"] += int(row["activations"])
        credits = "first_touch_credits" if field.startswith("first") else "last_touch_credits"
        for row in campaign:
            if row["breakdown"] == "overall" and int(row[credits]) != totals[row["campaign_id"]]:
                raise ValueError(f"Campaign credit failed to reconcile: {field}")
        touch_totals[field] = dict(totals)
    result = {
        "synthetic": True, "scenario": directory.name, "analysis_version": 1, "power_plan": plan,
        "srm": {"p_value": srm, "threshold": .01}, "preassignment_balance": balance,
        "design_power_realized_allocation": power(plan["profile_mixture"]["control_assumption"], plan["target_lift"],
                                                  len(frame) - n_treatment, n_treatment),
        "metrics": metrics, "profile_results": {
            key: risk_difference(frame[frame["profile"] == key], "activated_14d") for key in sorted(BASELINES)
        },
        "profile_interaction": interaction(frame), "attribution": touch_totals,
        "campaign_performance": campaign,
    }
    (directory / "analysis.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return result


def validate_scenario_pair(experiment):
    null_dir, nonzero_dir = (experiment / scenario for scenario in ("null", "nonzero"))
    for name in ("experiments.ndjson", "marketing_events.ndjson"):
        if digest(null_dir / name) != digest(nonzero_dir / name):
            raise ValueError(f"Common scenario inputs changed: {name}")
    null, nonzero = (json.loads((directory / "experiment_customers.json").read_text())
                     for directory in (null_dir, nonzero_dir))
    for left, right in zip(null, nonzero, strict=True):
        if (left["customer_id"] != right["customer_id"] or left["assigned_variant"] != right["assigned_variant"]
                or (left["assigned_variant"] == "control" and left != right)
                or flag(left["activated_14d"]) > flag(right["activated_14d"])):
            raise ValueError("Scenario comparison violated frozen assignment or shared outcome draws")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("experiment", type=Path)
    args = parser.parse_args()
    power_plan = json.loads((args.experiment / "power_plan.json").read_text())
    if power_plan != build_plan(args.history):
        parser.error("Power plan does not match the frozen population")
    validate_scenario_pair(args.experiment)
    for name in ("null", "nonzero"):
        result = analyze(args.history, args.experiment / name, power_plan)
        print(json.dumps({"scenario": name, "primary": result["metrics"]["activated_14d"],
                          "srm": result["srm"], "interaction": result["profile_interaction"]}, indent=2))
