"""Export only verified aggregate facts for the static dashboard."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re

from analyze_experiment import ARMS
from experiment_plan import frozen_population
from generate_data import CUTOFF, START, digest
from run_sql import ROOT, query
from simulate_experiment import END


def export(history, experiment, destination):
    population, frozen = frozen_population(history)
    selected = experiment / "nonzero"
    receipt = json.loads((selected / "mart_receipt.json").read_text())
    analysis = json.loads((selected / "analysis.json").read_text())
    if (receipt["scenario"] != "nonzero" or analysis["scenario"] != "nonzero"
            or not receipt["synthetic"] or not analysis["synthetic"]
            or receipt["destination"] != frozen["destination"]
            or receipt["manifest_sha256"] != digest(selected / "scenario_manifest.json")
            or not all(digest(selected / name) == expected for name, expected in receipt["exports"].items())
            or analysis["power_plan"]["eligible_snapshot_sha256"] != frozen["eligible_snapshot_sha256"]):
        raise ValueError("Experiment inputs failed aggregate export provenance validation")

    project, dataset = frozen["destination"].split(".")
    if (project != os.environ.get("BQ_PROJECT") or dataset != os.environ.get("BQ_DATASET")
            or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,1023}", dataset)
            or os.environ.get("BQ_LOCATION", "US") != "US"):
        raise ValueError("Set the project, dataset and US location used for the validated snapshot")
    prefix = f"{project}.{dataset}"
    records = query((project, dataset, "US"), f"""
        SELECT TO_JSON_STRING(STRUCT(
          (SELECT AS STRUCT * FROM `{prefix}.mart_savings_funnel`) AS funnel,
          ARRAY(SELECT AS STRUCT * FROM `{prefix}.mart_savings_cohorts`
                ORDER BY kind, breakdown, breakdown_value, cohort_month) AS cohorts,
          ARRAY(SELECT AS STRUCT * FROM `{prefix}.mart_history_summary`
                ORDER BY breakdown, breakdown_value) AS segments
        )) AS payload
        """, rows=1)
    historical = json.loads(records[0]["payload"])
    overall, = [row for row in historical["segments"] if row["breakdown"] == "overall"]
    if overall["customers"] != json.loads((history / "history_manifest.json").read_text())["customer_count"]:
        raise ValueError("The historical customer count differs from the validated manifest")
    if (overall["eligible_customers"] != len(population)
            or any(overall[f"profile_{key.lower()}"] != count for key, count in frozen["profile_counts"].items())):
        raise ValueError("Warehouse history and frozen eligibility disagree")

    counts = {row["assigned_variant"]: row for row in json.loads((selected / "arm_counts.json").read_text())}
    if (set(counts) != set(ARMS) or sum(int(counts[arm]["n"]) for arm in ARMS) != len(population)
            or any(analysis["metrics"][metric][arm]["events"] != int(counts[arm][metric])
                   or analysis["metrics"][metric][arm]["n"] != int(counts[arm]["n"])
                   for arm in ARMS for metric in ("activated_14d", "activated_30d", "sustained_saving", "app_engaged_30d"))
            or any(abs(analysis["metrics"]["deposit_amount_30d"][f"{arm}_mean"]
                       - float(counts[arm]["deposit_amount_30d"]) / int(counts[arm]["n"])) > 1e-8 for arm in ARMS)
            or any(sum(result[arm]["n"] for arm in ARMS) != frozen["profile_counts"][profile]
                   for profile, result in analysis["profile_results"].items())
            or analysis["campaign_performance"] != json.loads((selected / "campaign_performance.json").read_text())):
        raise ValueError("Dashboard experiment measurements could not reconcile to warehouse extracts")

    attribution = json.loads((selected / "attribution_counts.json").read_text())
    for key, totals in analysis["attribution"].items():
        expected = Counter()
        for row in attribution:
            expected[row.get(key) or "unattributed"] += int(row["activations"])
        if dict(expected) != totals:
            raise ValueError("Dashboard attribution totals differ from the warehouse extract")
    plan = {key: value for key, value in analysis["power_plan"].items() if key != "eligible_snapshot_sha256"}
    primary = analysis["metrics"]["activated_14d"]
    recommendation = ("Validate the personalized email with a real randomized test and track cost per incremental first deposit."
                      if primary["reject_equal_rates"] and primary["absolute_lift"] > 0
                      else "Keep the standard email as the baseline and use a real randomized test to narrow the interval.")
    heterogeneity = analysis["profile_interaction"]["p_value"]
    targeting = ("Test the apparent profile differences in a separate randomized follow-up before changing targeting."
                 if heterogeneity is not None and heterogeneity < .05
                 else "Keep the real-world test broad across behavioral profiles. The interaction analysis does not support profile-specific targeting.")
    payload = {
        "schema_version": 1, "synthetic": True,
        "periods": {"history_start": START.date().isoformat(), "assignment": CUTOFF.date().isoformat(),
                    "observation_end_exclusive": END.date().isoformat()},
        "history": historical,
        "experiment": {key: analysis[key] for key in ("scenario", "srm", "metrics", "profile_results",
                                                      "profile_interaction")},
        "power": plan,
        "campaign": {"performance": analysis["campaign_performance"], "attribution": analysis["attribution"]},
        "decisions": {"primary": recommendation, "targeting": targeting,
                      "retention": "Keep measuring who starts and returns. A longer randomized follow-up can assess whether the difference persists."},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "dashboard/data/analytics.json")
    args = parser.parse_args()
    export(args.history, args.experiment, args.output)
