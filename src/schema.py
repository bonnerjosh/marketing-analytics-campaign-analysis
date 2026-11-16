"""Explicit BigQuery schemas for the synthetic raw tables."""
import json
from pathlib import Path


def fields(*specifications):
    result = []
    for specification in specifications:
        name, kind, *mode = specification.split(":")
        result.append({"name": name, "type": kind, "mode": mode[0] if mode else "REQUIRED"})
    return result


SCHEMAS = {
    "customers": fields(
        "customer_id:STRING", "signup_timestamp:TIMESTAMP", "acquisition_channel:STRING",
        "acquisition_campaign:STRING", "customer_segment:STRING", "state:STRING",
        "region:STRING", "market_type:STRING", "age_band:STRING",
    ),
    "accounts": fields(
        "account_id:STRING", "customer_id:STRING", "account_type:STRING",
        "account_open_timestamp:TIMESTAMP", "account_close_timestamp:TIMESTAMP:NULLABLE",
        "account_status:STRING",
    ),
    "transactions": fields(
        "transaction_id:STRING", "account_id:STRING", "transaction_timestamp:TIMESTAMP",
        "transaction_type:STRING", "amount:NUMERIC", "transaction_status:STRING",
    ),
    "marketing_events": fields(
        "event_id:STRING", "customer_id:STRING", "message_id:STRING", "campaign_id:STRING",
        "event_timestamp:TIMESTAMP", "event_type:STRING", "channel:STRING", "message_variant:STRING",
    ),
    "experiments": fields(
        "experiment_id:STRING", "customer_id:STRING", "assigned_variant:STRING",
        "assignment_timestamp:TIMESTAMP", "eligibility_status:STRING",
    ),
    "ga4_events": fields(
        "event_id:STRING", "event_date:STRING", "event_timestamp:INTEGER", "user_pseudo_id:STRING",
        "user_id:STRING", "event_name:STRING", "platform:STRING",
    ) + [{
        "name": "event_params", "type": "RECORD", "mode": "REPEATED",
        "fields": fields("key:STRING") + [{
            "name": "value", "type": "RECORD", "mode": "REQUIRED",
            "fields": fields(
                "string_value:STRING:NULLABLE", "int_value:INTEGER:NULLABLE",
                "double_value:FLOAT:NULLABLE", "float_value:FLOAT:NULLABLE",
            ),
        }],
    }],
}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("table", choices=SCHEMAS)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(SCHEMAS[args.table], indent=2) + "\n")
