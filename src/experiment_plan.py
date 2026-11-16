"""Validate the frozen population and calculate pre-outcome power."""
from collections import Counter
import json
from math import ceil, sqrt
from pathlib import Path
from statistics import NormalDist
import argparse

from generate_data import digest

BASELINES = {"A": .12, "B": .08, "C": .04}
LIFT = .02
ALPHA = .05
TARGET_POWER = .80
EXPERIMENT_ID = "new_year_savings_2027"
NORMAL = NormalDist()


def frozen_population(history):
    snapshot = history / "eligible.ndjson"
    receipt = json.loads((history / "warehouse_validation.json").read_text())
    if (receipt.get("synthetic") is not True
            or digest(snapshot) != receipt["eligible_snapshot_sha256"]
            or digest(history / "history_manifest.json") != receipt["history_manifest_sha256"]):
        raise ValueError("Frozen population or history manifest hash mismatch")
    with snapshot.open() as handle:
        people = sorted(map(json.loads, handle), key=lambda row: row["customer_id"])
    if (len(people) != receipt["eligible_count"]
            or len({row["customer_id"] for row in people}) != len(people)
            or len({row["open_savings_account_id"] for row in people}) != len(people)
            or any(not row["customer_id"] or not row["open_savings_account_id"] for row in people)
            or Counter(row["profile"] for row in people) != receipt["profile_counts"]
            or not set(receipt["profile_counts"]) <= BASELINES.keys()):
        raise ValueError("Frozen population count, profile, or key mismatch")
    return people, receipt


def power(p0, delta, n_control, n_treatment):
    p1 = p0 + delta
    pooled = (n_control * p0 + n_treatment * p1) / (n_control + n_treatment)
    null_sd = sqrt(pooled * (1 - pooled) * (1 / n_control + 1 / n_treatment))
    alternative_sd = sqrt(p0 * (1 - p0) / n_control + p1 * (1 - p1) / n_treatment)
    threshold = NORMAL.inv_cdf(1 - ALPHA / 2) * null_sd
    return NORMAL.cdf((delta - threshold) / alternative_sd) + NORMAL.cdf((-delta - threshold) / alternative_sd)


def design_row(p0, n):
    pooled = p0 + LIFT / 2
    variance = p0 * (1 - p0) + (p0 + LIFT) * (1 - p0 - LIFT)
    estimate = ((NORMAL.inv_cdf(1 - ALPHA / 2) * sqrt(2 * pooled * (1 - pooled))
                 + NORMAL.inv_cdf(TARGET_POWER) * sqrt(variance)) / LIFT) ** 2
    required = ceil(estimate)
    while power(p0, LIFT, required - 1, required - 1) >= TARGET_POWER:
        required -= 1
    while power(p0, LIFT, required, required) < TARGET_POWER:
        required += 1
    lo, hi = 0.0, 1.0 - p0
    for _ in range(55):
        middle = (lo + hi) / 2
        if power(p0, middle, n, n) >= TARGET_POWER:
            hi = middle
        else:
            lo = middle
    return {"control_assumption": p0, "n_required_per_arm": required,
            "power_at_target": power(p0, LIFT, n, n), "mde_absolute": hi}


def build_plan(history):
    population, receipt = frozen_population(history)
    counts = Counter(row["profile"] for row in population)
    pooled = sum(counts[k] * BASELINES[k] for k in counts) / len(population)
    n = len(population) // 2
    return {
        "synthetic": True, "eligible_snapshot_sha256": receipt["eligible_snapshot_sha256"],
        "eligible": len(population), "planned_per_arm": n, "profile_counts": counts,
        "alpha_two_sided": ALPHA, "target_power": TARGET_POWER, "target_lift": LIFT,
        "profile_mixture": design_row(pooled, n),
        "sensitivity": [design_row(p, n) for p in (.04, .08, .12)],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_plan(args.history), indent=2) + "\n")
    print(args.output.read_text(), end="")
