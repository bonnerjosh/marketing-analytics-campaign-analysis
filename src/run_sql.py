"""Load and validate Phase 2 history using the configured BigQuery CLI."""
import argparse
from datetime import datetime
import fcntl
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

from generate_data import CUTOFF, START, digest
from schema import SCHEMAS

ROOT = Path(__file__).resolve().parents[1]
MARTS = (
    "mart_customer_savings_lifecycle", "mart_app_sessions", "mart_customer_profiles",
    "mart_savings_cohorts", "mart_savings_funnel", "mart_history_summary",
)
QUERY_PARAMS = {"cutoff": ("TIMESTAMP", CUTOFF.isoformat())}


def cli(config, *args, sql=None):
    project, _, location = config
    return subprocess.run(
        ["bq", f"--project_id={project}", f"--quota_project_id={project}", f"--location={location}", "--quiet", *args],
        input=sql, check=True, text=True, stdout=subprocess.PIPE,
    ).stdout


def query(config, sql, *, estimate_sql=None, rows=100):
    sql = sql.strip()
    byte_cap = 1 << 30
    flags = ["--use_legacy_sql=false", f"--maximum_bytes_billed={byte_cap}", f"--max_rows={rows}"]
    for name, (kind, value) in QUERY_PARAMS.items():
        if f"@{name}" in sql:
            flags.append(f"--parameter={name}:{kind}:{value}")
    returns_rows = sql.upper().startswith(("SELECT", "WITH"))
    if returns_rows or estimate_sql is not None:
        estimate = cli(config, "--format=json", "query", *flags, "--dry_run",
                       sql=estimate_sql if estimate_sql is not None else sql)
        estimated_bytes = int(json.loads(estimate)["statistics"]["totalBytesProcessed"])
        print(f"BigQuery dry run: {estimated_bytes:,} bytes processed", flush=True)
        if estimated_bytes > byte_cap:
            raise RuntimeError("BigQuery dry-run estimate exceeds the 1 GiB query cap")
    result = cli(config, "--format=json", "query", *flags, sql=sql)
    if returns_rows:
        records = json.loads(result)
        if not isinstance(records, list):
            raise ValueError("Expected BigQuery query result as an array")
        return records
    return None

def load(config, name, source, schema):
    project, dataset, _ = config
    with TemporaryDirectory() as temp:
        schema_path = Path(temp) / "schema.json"
        schema_path.write_text(json.dumps(schema))
        if source.stat().st_size > 16 * (1 << 20):
            compressed = Path(temp) / f"{source.name}.gz"
            with source.open("rb") as original, gzip.open(compressed, "wb", compresslevel=1) as target:
                shutil.copyfileobj(original, target)
            source = compressed
        cli(config, "load", "--replace", "--source_format=NEWLINE_DELIMITED_JSON",
            f"{project}:{dataset}.{name}", str(source), str(schema_path))


def smoke(config):
    project, dataset, _ = config
    table = "smoke_" + uuid4().hex
    with TemporaryDirectory() as temp:
        sample = Path(temp) / "sample.ndjson"
        try:
            for expected in (1, 2):
                sample.write_text(json.dumps({"value": expected}) + "\n")
                load(config, table, sample, [{"name": "value", "type": "INTEGER"}])
                observed = query(config, f"SELECT value FROM `{project}.{dataset}.{table}`")
                if observed is None or [int(row["value"]) for row in observed] != [expected]:
                    raise RuntimeError("Smoke test failed load/read/replace verification")
        finally:
            cli(config, "rm", "-f", "-t", f"{project}:{dataset}.{table}")


def column_type(field):
    name = field["type"]
    if name == "RECORD":
        nested = ", ".join(f"{item['name']} {column_type(item)}" for item in field["fields"])
        name = f"STRUCT<{nested}>"
    name = {"INTEGER": "INT64", "FLOAT": "FLOAT64"}.get(name, name)
    return f"ARRAY<{name}>" if field["mode"] == "REPEATED" else name


def load_history(config, directory, manifest):
    project, dataset, _ = config
    for name in ("experiments", "marketing_events"):
        table = f"`{project}.{dataset}.raw_{name}`"
        columns = ", ".join(f"{f['name']} {column_type(f)} NOT NULL" for f in SCHEMAS[name])
        query(config, f"CREATE TABLE IF NOT EXISTS {table} ({columns})")
        if query(config, f"SELECT 1 AS found FROM {table} LIMIT 1"):
            raise RuntimeError(f"Phase 2 refresh requires empty raw_{name}")
    for name, schema in SCHEMAS.items():
        if name in ("experiments", "marketing_events"):
            continue
        if manifest["tables"][name]["row_count"]:
            load(config, f"raw_{name}", directory / f"{name}.ndjson", schema)
        else:
            columns = ", ".join(
                f"{f['name']} {column_type(f)}" + (" NOT NULL" if f["mode"] == "REQUIRED" else "")
                for f in schema
            )
            query(config, f"CREATE OR REPLACE TABLE `{project}.{dataset}.raw_{name}` ({columns})")


def build(config, directory, manifest):
    project, dataset, _ = config
    prefix = f"{project}.{dataset}"

    def read_sql(relative_path):
        return (ROOT / relative_path).read_text().replace("{{dataset}}", prefix).strip()

    # Assert raw integrity before building views that assume unique keys and parameters.
    validate(config, read_sql("tests/raw_history.sql"))
    for path in sorted((ROOT / "sql/staging").glob("*.sql")):
        body = read_sql(path)
        query(config, f"CREATE OR REPLACE VIEW `{prefix}.{path.stem}` AS\n{body}", estimate_sql=body)
    for name in MARTS:
        body = read_sql(f"sql/marts/{name}.sql")
        query(config, f"CREATE OR REPLACE TABLE `{prefix}.{name}` AS\n{body}", estimate_sql=body)
    validate(config, read_sql("tests/history_marts.sql"))

    records = query(config, f"""
        SELECT customer_id, profile, open_savings_account_id
        FROM `{prefix}.mart_customer_profiles`
        WHERE eligibility_status = 'ELIGIBLE'
        ORDER BY customer_id
        """, rows=manifest["customer_count"])
    counts = query(config, f"""
        SELECT COUNT(*) AS customers, COUNTIF(eligibility_status = 'ELIGIBLE') AS eligible
        FROM `{prefix}.mart_customer_profiles`
        """)
    if int(counts[0]["customers"]) != manifest["customer_count"] or int(counts[0]["eligible"]) != len(records):
        raise RuntimeError("Warehouse counts disagree with the manifest or exported snapshot")
    for name, table in manifest["tables"].items():
        raw_count = query(config, f"SELECT COUNT(*) AS n FROM `{prefix}.raw_{name}`")
        if int(raw_count[0]["n"]) != table["row_count"]:
            raise RuntimeError(f"Unexpected BigQuery row count for raw_{name}")

    occupancy = query(config, f"""
        SELECT profile, COUNT(*) AS customers,
          AVG(tenure_days) AS mean_tenure_days,
          AVG(sessions) AS mean_sessions,
          AVG(savings_sessions) AS mean_savings_sessions,
          AVG(checking_transactions) AS mean_checking_transactions
        FROM `{prefix}.mart_customer_profiles`
        WHERE eligibility_status = 'ELIGIBLE'
        GROUP BY profile ORDER BY profile
        """)
    snapshot = directory / "eligible.ndjson"
    temporary = snapshot.with_suffix(".tmp")
    temporary.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    temporary.replace(snapshot)
    receipt = directory / "warehouse_validation.json"
    temporary = receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "synthetic": True, "destination": prefix, "eligible_count": len(records),
        "history_manifest_sha256": digest(directory / "history_manifest.json"),
        "eligible_snapshot_sha256": digest(snapshot),
        "profile_counts": {label: sum(row["profile"] == label for row in records) for label in "ABC"},
    }, indent=2) + "\n")
    temporary.replace(receipt)
    print(receipt.read_text(), end="")
    print(json.dumps(occupancy, indent=2))


def validate(config, sql):
    issues = query(config, sql)
    failed = {row["check_name"]: int(row["violations"]) for row in issues if int(row["violations"])}
    if failed:
        raise RuntimeError(f"Warehouse validation failed: {failed}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create-dataset", "smoke", "history", "marts"))
    parser.add_argument("--data", type=Path, default=ROOT / "data/history")
    args = parser.parse_args()
    project = os.environ.get("BQ_PROJECT", "")
    dataset = os.environ.get("BQ_DATASET", "")
    location = os.environ.get("BQ_LOCATION", "US")
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        parser.error("BQ_PROJECT must be an explicit valid Google Cloud project ID")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,1023}", dataset):
        parser.error("BQ_DATASET must be an explicit valid BigQuery dataset ID")
    if location != "US":
        parser.error("Use BQ_LOCATION=US for the documented setup")
    config = project, dataset, location
    if args.action == "create-dataset":
        print(cli(config, "mk", "--dataset", "--default_table_expiration=5184000", f"{project}:{dataset}"), end="")
    elif args.action == "smoke":
        smoke(config)
        print("BigQuery smoke check passed")
    else:
        temporary_root = ROOT / "data"
        temporary_root.mkdir(exist_ok=True)
        with (temporary_root / f".{project}.{dataset}.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Invalidate prior receipts before touching warehouse state.
            for name in ("warehouse_validation.json", "eligible.ndjson"):
                (args.data / name).unlink(missing_ok=True)
            manifest = json.loads((args.data / "history_manifest.json").read_text())
            if (manifest["synthetic"] is not True or manifest["schema_version"] != 1
                    or datetime.fromisoformat(manifest["history_start"]) != START
                    or datetime.fromisoformat(manifest["history_end_exclusive"]) != CUTOFF
                    or set(manifest["tables"]) != set(SCHEMAS)
                    or any(manifest["tables"][name]["row_count"] for name in ("experiments", "marketing_events"))
                    or not all(digest(args.data / f"{name}.ndjson") == table["sha256"]
                               for name, table in manifest["tables"].items())):
                raise RuntimeError("Invalid synthetic history manifest or file hashes")
            raw_receipt = args.data / "raw_load_receipt.json"
            load_receipt = {
                "destination": f"{project}.{dataset}",
                "manifest_sha256": digest(args.data / "history_manifest.json"),
            }
            if args.action == "history":
                raw_receipt.unlink(missing_ok=True)
                load_history(config, args.data, manifest)
                temporary = raw_receipt.with_suffix(".tmp")
                temporary.write_text(json.dumps(load_receipt) + "\n")
                temporary.replace(raw_receipt)
            elif not raw_receipt.exists() or json.loads(raw_receipt.read_text()) != load_receipt:
                raise RuntimeError("No matching receipt for the raw tables; run history to load them")
            build(config, args.data, manifest)


if __name__ == "__main__":
    main()
