# Data model

## Grains and types

Keys and categories are STRING unless noted. Financial amounts use NUMERIC in USD. Relational times use TIMESTAMP. IDs are synthetic, stable within a run and unique at the stated grain.

| Raw table | Grain and fields |
|---|---|
| `raw_customers` | One per `customer_id`. `signup_timestamp`, `acquisition_channel`, `acquisition_campaign`, signup `customer_segment`, `state`, `region`, `market_type`, `age_band`. |
| `raw_accounts` | One per `account_id`. FK `customer_id`, `account_type`, `account_open_timestamp`, nullable `account_close_timestamp`, `account_status` as of extract end. Open/close timestamps determine historical status. |
| `raw_transactions` | One per `transaction_id`. FK `account_id`, `transaction_timestamp` (posting time for completed rows), `transaction_type`, `amount`, `transaction_status`. |
| `raw_marketing_events` | One per `event_id`. FK `customer_id`, `message_id`, `campaign_id`, `event_timestamp`, `event_type`, `channel`, `message_variant`. Each message has a single send and at most one delivery, with optional later clicks. |
| `raw_experiments` | One per `experiment_id, customer_id`. `assigned_variant`, `assignment_timestamp`, `eligibility_status`. Contains assigned eligible customers only. The SQL candidate snapshot retains the eligibility denominator and exclusion reasons for the full base. |
| `raw_ga4_events` | One per synthetic `event_id`. `event_date` STRING YYYYMMDD, `event_timestamp` INT64 UTC microseconds, `user_pseudo_id`, `user_id`, `event_name`, `platform`, and repeated `event_params` STRUCT of `key` plus `value` STRUCT (`string_value`, `int_value`, `double_value`, `float_value`). |

UTC is also the synthetic reporting timezone. Application timestamps model occurrence with no upload lag. `user_id` equals the authenticated `customer_id`; one stable pseudo ID per synthetic customer avoids stitching. Session key is (`user_pseudo_id, ga_session_id`), with the numeric `ga_session_id` stored in `event_params`. Include `screen_name`, `campaign_id` and `savings_goal_type` as applicable. Use one local batch-loaded event table and a synthetic event key. [GA4 BigQuery export schema](https://support.google.com/analytics/answer/7029846?hl=en)

## Generation sequence

1. Generate around 40,000 customers with 2026 signup dates. Document input weights and pin the seed and dependency versions. Derive region from one state lookup using the four US Census regions across 50 states and DC. Draw urban/suburban/rural conditional on state, and draw age bands independently of eligibility logic. Use signup `customer_segment` as a coarse synthetic product-use intent such as everyday banking, payments or savings interest. It is distinct from the later behavioral profile. [Census region membership](https://www.census.gov/data/data-tools/survey-explorer/geo.html)
2. Draw customer-level latent engagement and savings propensity conditional on signup intent and acquisition channel, with modest geographic/market and age differences in baseline behavior. Use these propensities for checking transaction frequency, app sessions and savings account opening and funding. Generate account open/close dates before evaluating status, include some multi-account customers, and support never-opened, unfunded, funded, repeat and formerly active savers. Tenure is elapsed days from signup at the relevant snapshot.
3. Simulate 2026 behavior and financial activity before any assignment. Build sessions with one start and ordered events from the brief. Some app deposit attempts fail or are abandoned and some qualifying deposits lack a corresponding app event. Generate confirmation views only after a corresponding successful posting in that simulated journey. A single-statement-status simplification treats FAILED, PENDING and REVERSED rows as terminal synthetic outcomes for the observation period. A REVERSED row represents an attempt that never qualified; post-cutoff reversal corrections are outside this MVP.
4. Freeze SQL-derived eligibility and profiles before randomization. Export customer IDs, profile, and the chosen eligible open savings account (earliest opened; account ID breaks ties). Use separate seeded streams for history, assignment, potential outcome draws, and marketing/app activity. The simulator writes January–February experiment activity separately from the historical records. Campaign delivery, click and deposit events retain chronological order; outcomes can occur without delivery or clicks. Use shared engagement propensity to create realistic selection into clicking.
5. Record seed, scenario, history fingerprint, observation coverage, generated row counts and schema/config version in a local manifest. Keep scenario runs isolated by sequential rebuild and scenario-labeled artifacts. Publish one documented scenario, with the null available as a validation run.

## SQL dependencies

| Layer | Grain and responsibilities |
|---|---|
| `stg_customers`, `stg_accounts`, `stg_transactions`, `stg_marketing_events`, `stg_ga4_events`, `stg_experiments` | Clean types and categories and retain raw grains. Flag qualifying deposits once. Use correlated `UNNEST` to extract event parameters without multiplying events. Assert source keys and parameter uniqueness; if exact duplicate replay rows are accepted, use deterministic `ROW_NUMBER` and `QUALIFY`, and fail on conflicting duplicates. |
| `mart_customer_savings_lifecycle` | One customer; first savings opening, first and second qualified deposit across accounts, historical features and eligible savings account. Rank deposits by timestamp and transaction ID. Filter strictly before assignment. |
| `mart_app_sessions` | One session; order events with timestamp and stable event ID, calculate engagement and ordered behavioral milestones. Aggregate sessions before customer-level joins. |
| `mart_customer_profiles` | One row per historical customer with eligibility, tenure and 30-day features. Assign profiles only for eligible customers by ordered CASE rules in the metrics contract. |
| `mart_savings_cohorts` | One row per cohort definition, period and requested breakdown. Reuse the lifecycle customer grain and carry eligible denominator counts, milestone counts and timing summaries. |
| `mart_savings_funnel`, `mart_history_summary` | Mature-signup funnel and descriptive profile, market and app summaries. |
| `mart_campaign_messages` | One row per sent message with delivery and first valid click. |
| `mart_campaign_attribution` | One first activation per customer in the campaign analysis window, with separately ranked first and last eligible touches, including unattributed outcomes. |
| `mart_campaign_performance` | Campaign and breakdown aggregates from message and recipient grains. Aggregate delivery and click metrics independently of deposit joins. |
| `mart_experiment_customers` | One row per randomized eligible customer, joined to the frozen profile and left-joined to aggregated outcome/engagement facts. Retain zero outcomes, assignment and window flags. Python uses this mart for inference. |

Assert transaction timestamps lie within account lifetime, session starts precede session actions, every event customer exists and the pseudo-ID mapping is one-to-one, exactly one frozen profile exists per eligible customer, and the experiment mart matches the frozen population and raw assignments. Test multi-account customers, timestamp ties, reversed deposits and empty activity.

The deployed `raw_followup_transactions` and `raw_followup_ga4_events` tables use the
same schemas as their historical counterparts. Keep the follow-up facts separate
so scenario runs can replace two small tables without rewriting history. Both
scenarios share the same assignment and marketing facts. The warehouse run leaves the
nonzero scenario in the warehouse and keeps both scenarios' verified extracts locally.
