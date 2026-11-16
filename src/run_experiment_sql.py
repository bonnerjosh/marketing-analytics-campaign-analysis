"""Build and export the BigQuery experiment and campaign marts for both scenarios."""
import argparse
import fcntl
import json
import os
import re
from pathlib import Path

from experiment_plan import EXPERIMENT_ID, frozen_population
from generate_data import digest
from run_sql import QUERY_PARAMS, ROOT, load, query, validate
from schema import SCHEMAS
from simulate_experiment import END, TABLES

MODELS = ("mart_experiment_customers", "mart_campaign_messages",
          "mart_campaign_attribution", "mart_campaign_performance")
DESTINATIONS = {"experiments": "raw_experiments", "marketing_events": "raw_marketing_events",
                "transactions": "raw_followup_transactions", "ga4_events": "raw_followup_ga4_events"}


def verified_manifest(directory, expected_hash):
    manifest = json.loads((directory / "scenario_manifest.json").read_text())
    if (manifest.get("synthetic") is not True
            or manifest["scenario"] != directory.name
            or manifest["coverage_end_exclusive"] != END.isoformat()
            or manifest["eligible_snapshot_sha256"] != expected_hash
            or set(manifest["tables"]) != set(TABLES)
            or not all(digest(directory / f"{name}.ndjson") == entry["sha256"]
                       for name, entry in manifest["tables"].items())):
        raise ValueError(f"Invalid {directory.name} manifest or scenario inputs")
    return manifest


def run(history, experiment, scenarios):
    population, receipt = frozen_population(history)
    project, dataset = receipt["destination"].split(".")
    if (project != os.environ.get("BQ_PROJECT") or dataset != os.environ.get("BQ_DATASET")
            or not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,1023}", dataset)
            or os.environ.get("BQ_LOCATION", "US") != "US"):
        raise ValueError("Set the approved US warehouse target from the Phase 2 receipt")
    config = project, dataset, "US"
    prefix = receipt["destination"]
    QUERY_PARAMS.update({"experiment_id": ("STRING", EXPERIMENT_ID),
                         "observation_end": ("TIMESTAMP", END.isoformat())})
    manifests = {name: verified_manifest(experiment / name, receipt["eligible_snapshot_sha256"])
                 for name in ("null", "nonzero")}
    for name in ("experiments", "marketing_events"):
        if manifests["null"]["tables"][name] != manifests["nonzero"]["tables"][name]:
            raise ValueError(f"Both scenarios must share the same {name}")

    def sql(relative_path):
        return (ROOT / relative_path).read_text().replace("{{dataset}}", prefix).strip()

    lock_root = ROOT / "data"
    lock_root.mkdir(exist_ok=True)
    checkpoint = experiment / "warehouse_load_state.json"
    with (lock_root / f".{prefix}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        loaded = prior.get("tables", {}) if prior.get("destination") == prefix else {}
        for scenario in scenarios:
            print(f"Building {scenario} scenario", flush=True)
            directory = experiment / scenario
            export_receipt = directory / "mart_receipt.json"
            export_receipt.unlink(missing_ok=True)
            for name in TABLES:
                source = directory / f"{name}.ndjson"
                destination = DESTINATIONS[name]
                expected = manifests[scenario]["tables"][name]["sha256"]
                if loaded.get(destination) != expected:
                    load(config, destination, source, SCHEMAS[name])
                    loaded[destination] = expected
                    temporary = checkpoint.with_suffix(".tmp")
                    temporary.write_text(json.dumps({"destination": prefix, "tables": loaded}) + "\n")
                    temporary.replace(checkpoint)
            for name in MODELS:
                body = sql(f"sql/marts/{name}.sql")
                query(config, f"CREATE OR REPLACE TABLE `{prefix}.{name}` AS\n{body}", estimate_sql=body)
            validate(config, sql("tests/experiment_marts.sql"))
            # Export sorted rows and independent arm counts from the same validated mart.
            customers = query(config, f"SELECT * FROM `{prefix}.mart_experiment_customers` ORDER BY customer_id",
                              rows=len(population))
            arm_counts = query(config, f"""
                SELECT assigned_variant, COUNT(*) AS n, COUNTIF(activated_14d) AS activated_14d,
                  COUNTIF(activated_30d) AS activated_30d, COUNTIF(sustained_saving) AS sustained_saving,
                  COUNTIF(app_engaged_30d) AS app_engaged_30d, SUM(deposit_amount_30d) AS deposit_amount_30d
                FROM `{prefix}.mart_experiment_customers` GROUP BY assigned_variant ORDER BY assigned_variant
                """)
            campaign = query(config, f"""
                SELECT * FROM `{prefix}.mart_campaign_performance`
                ORDER BY campaign_id, breakdown, breakdown_value
                """)
            touches = query(config, f"""
                SELECT first_touch_campaign, last_touch_campaign, COUNT(*) AS activations
                FROM `{prefix}.mart_campaign_attribution` GROUP BY first_touch_campaign, last_touch_campaign
                ORDER BY first_touch_campaign, last_touch_campaign
                """)
            if len(customers) != len(population):
                raise RuntimeError("Experiment mart export count differs from frozen population")
            extracts = {"experiment_customers.json": customers, "arm_counts.json": arm_counts,
                        "campaign_performance.json": campaign, "attribution_counts.json": touches}
            for filename, value in extracts.items():
                (directory / filename).write_text(json.dumps(value, separators=(",", ":")) + "\n")
            export_receipt.write_text(json.dumps({
                "synthetic": True, "scenario": scenario, "destination": prefix,
                "manifest_sha256": digest(directory / "scenario_manifest.json"),
                "exports": {filename: digest(directory / filename) for filename in extracts},
            }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--scenario", choices=("null", "nonzero", "both"), default="both")
    args = parser.parse_args()
    run(args.history, args.experiment, ("null", "nonzero") if args.scenario == "both" else (args.scenario,))
