WITH assignment AS (
  SELECT customer_id, COUNT(*) AS rows_per_customer,
    COUNTIF(experiment_id = @experiment_id AND eligibility_status = 'ELIGIBLE'
      AND assigned_variant IN ('control', 'treatment') AND assignment_timestamp = @cutoff) AS valid_rows
  FROM `{{dataset}}.raw_experiments`
  GROUP BY customer_id
),
eligible AS (
  SELECT customer_id
  FROM `{{dataset}}.mart_customer_profiles` WHERE eligibility_status = 'ELIGIBLE'
),
messages AS (
  SELECT message_id, ANY_VALUE(customer_id) AS customer_id,
    COUNT(DISTINCT customer_id) AS owners, COUNT(DISTINCT campaign_id) AS campaigns,
    COUNTIF(event_type = 'sent') AS n_sent, COUNTIF(event_type = 'delivered') AS n_delivered,
    COUNTIF(event_type = 'clicked') AS n_clicked, COUNTIF(event_type NOT IN ('sent','delivered','clicked')) AS invalid_types,
    MIN(IF(event_type = 'sent', event_timestamp, NULL)) AS sent,
    MIN(IF(event_type = 'delivered', event_timestamp, NULL)) AS delivered,
    MIN(IF(event_type = 'clicked', event_timestamp, NULL)) AS clicked
  FROM `{{dataset}}.raw_marketing_events`
  GROUP BY message_id
),
eligible_accounts AS (
  SELECT open_savings_account_id AS account_id FROM `{{dataset}}.mart_customer_profiles` WHERE eligibility_status = 'ELIGIBLE'
)
SELECT 'assignment_population' AS check_name, COUNTIF(
  e.customer_id IS NULL OR a.customer_id IS NULL OR rows_per_customer != 1 OR valid_rows != 1
) AS violations
FROM eligible AS e FULL JOIN assignment AS a USING (customer_id)
UNION ALL
SELECT 'mart_grain', COUNT(*) - COUNT(DISTINCT customer_id)
FROM `{{dataset}}.mart_experiment_customers`
UNION ALL
SELECT 'mart_population_count', ABS(
  (SELECT COUNT(*) FROM eligible) - (SELECT COUNT(*) FROM `{{dataset}}.mart_experiment_customers`)
)
UNION ALL
SELECT 'transaction_keys', COUNT(*) - COUNT(DISTINCT transaction_id)
FROM `{{dataset}}.raw_followup_transactions`
UNION ALL
SELECT 'followup_deposits', COUNTIF(a.account_id IS NULL OR t.transaction_timestamp < @cutoff
  OR t.transaction_timestamp >= @observation_end OR amount <= 0 OR transaction_status != 'COMPLETED'
  OR transaction_type != 'DEPOSIT')
FROM `{{dataset}}.raw_followup_transactions` AS t LEFT JOIN eligible_accounts AS a USING (account_id)
UNION ALL
SELECT 'followup_event_keys', COUNT(*) - COUNT(DISTINCT event_id)
FROM `{{dataset}}.raw_followup_ga4_events`
UNION ALL
SELECT 'followup_app_identity_time', COUNTIF(e.customer_id IS NULL
  OR g.user_pseudo_id != CONCAT('P', SUBSTR(g.user_id, 2))
  OR TIMESTAMP_MICROS(g.event_timestamp) < @cutoff
  OR TIMESTAMP_MICROS(g.event_timestamp) >= @observation_end)
FROM `{{dataset}}.raw_followup_ga4_events` AS g LEFT JOIN eligible AS e ON g.user_id = e.customer_id
UNION ALL
SELECT 'message_order_and_grain', COUNTIF(
  e.customer_id IS NULL OR owners != 1 OR campaigns != 1 OR invalid_types != 0
  OR n_sent != 1 OR n_delivered > 1 OR n_clicked > 1
  OR sent < @cutoff OR sent >= @observation_end
  OR (delivered IS NOT NULL AND (delivered <= sent OR delivered >= @observation_end))
  OR (clicked IS NOT NULL AND (delivered IS NULL OR clicked <= delivered
      OR clicked >= TIMESTAMP_ADD(delivered, INTERVAL 7 DAY) OR clicked >= @observation_end))
)
FROM messages AS m LEFT JOIN eligible AS e USING (customer_id)
UNION ALL
SELECT 'primary_secondary_nesting', COUNTIF(
  (activated_14d AND NOT activated_30d) OR (sustained_saving AND NOT activated_14d)
  OR (activated_30d AND deposit_amount_30d <= 0) OR (NOT activated_30d AND deposit_amount_30d != 0)
  OR (second_deposit IS NOT NULL AND second_deposit < first_deposit)
)
FROM `{{dataset}}.mart_experiment_customers`
UNION ALL
SELECT 'touch_pool_reconciliation', ABS(
  (SELECT COUNTIF(activated_14d) FROM `{{dataset}}.mart_experiment_customers`)
  - (SELECT COUNT(*) FROM `{{dataset}}.mart_campaign_attribution`)
)
UNION ALL
SELECT 'touch_rule_consistency', COUNTIF((first_touch_campaign IS NULL) != (last_touch_campaign IS NULL))
FROM `{{dataset}}.mart_campaign_attribution`
UNION ALL
SELECT 'campaign_denominator_nesting', COUNTIF(
  messages_delivered > messages_sent OR mature_delivered_recipients > messages_delivered
  OR unique_clickers > mature_delivered_recipients OR activated_after_click > unique_clickers_14d
)
FROM `{{dataset}}.mart_campaign_performance`
