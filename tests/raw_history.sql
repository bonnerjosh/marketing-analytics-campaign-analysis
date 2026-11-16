WITH events AS (
  SELECT
    e.*,
    (SELECT COUNTIF(key = 'ga_session_id') FROM UNNEST(event_params)) AS session_params,
    (SELECT COUNT(DISTINCT key) FROM UNNEST(event_params)) AS distinct_params
  FROM `{{dataset}}.raw_ga4_events` AS e
)
SELECT 'customer_keys' AS check_name,
  COUNT(*) - COUNT(DISTINCT customer_id) AS violations
FROM `{{dataset}}.raw_customers`
UNION ALL
SELECT 'account_keys', COUNT(*) - COUNT(DISTINCT account_id)
FROM `{{dataset}}.raw_accounts`
UNION ALL
SELECT 'transaction_keys', COUNT(*) - COUNT(DISTINCT transaction_id)
FROM `{{dataset}}.raw_transactions`
UNION ALL
SELECT 'event_keys', COUNT(*) - COUNT(DISTINCT event_id)
FROM events
UNION ALL
SELECT 'account_owner_and_dates', COUNTIF(
  c.customer_id IS NULL OR a.account_open_timestamp < c.signup_timestamp
  OR a.account_open_timestamp >= @cutoff
  OR (a.account_close_timestamp IS NOT NULL AND (
    a.account_close_timestamp <= a.account_open_timestamp OR a.account_close_timestamp >= @cutoff
  ))
)
FROM `{{dataset}}.raw_accounts` AS a
LEFT JOIN `{{dataset}}.raw_customers` AS c USING (customer_id)
UNION ALL
SELECT 'transaction_account_and_dates', COUNTIF(
  a.account_id IS NULL OR t.transaction_timestamp < a.account_open_timestamp
  OR t.transaction_timestamp >= COALESCE(a.account_close_timestamp, @cutoff)
  OR (t.transaction_type = 'DEPOSIT' AND a.account_type != 'SAVINGS')
)
FROM `{{dataset}}.raw_transactions` AS t
LEFT JOIN `{{dataset}}.raw_accounts` AS a USING (account_id)
UNION ALL
SELECT 'event_identity_dates_and_parameters', COUNTIF(
  c.customer_id IS NULL OR TIMESTAMP_MICROS(e.event_timestamp) < c.signup_timestamp
  OR TIMESTAMP_MICROS(e.event_timestamp) >= @cutoff
  OR FORMAT_TIMESTAMP('%Y%m%d', TIMESTAMP_MICROS(e.event_timestamp)) != e.event_date
  OR session_params != 1 OR distinct_params != ARRAY_LENGTH(event_params)
  OR NOT EXISTS (
    SELECT 1 FROM UNNEST(event_params) WHERE key = 'ga_session_id' AND value.int_value IS NOT NULL
  )
)
FROM events AS e
LEFT JOIN `{{dataset}}.raw_customers` AS c ON c.customer_id = e.user_id
UNION ALL
SELECT 'pseudo_id_collision', COUNT(*)
FROM (SELECT user_pseudo_id FROM events GROUP BY user_pseudo_id HAVING COUNT(DISTINCT user_id) != 1)
UNION ALL
SELECT 'customer_multiple_pseudo_ids', COUNT(*)
FROM (SELECT user_id FROM events GROUP BY user_id HAVING COUNT(DISTINCT user_pseudo_id) != 1)
UNION ALL
SELECT 'historical_assignments_empty', COUNT(*) FROM `{{dataset}}.raw_experiments`
UNION ALL
SELECT 'historical_campaign_events_empty', COUNT(*) FROM `{{dataset}}.raw_marketing_events`
