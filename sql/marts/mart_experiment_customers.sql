WITH deposits AS (
  SELECT
    a.customer_id,
    ARRAY_AGG(t.transaction_timestamp ORDER BY t.transaction_timestamp, t.transaction_id LIMIT 2) AS first_two,
    SUM(IF(t.transaction_timestamp < TIMESTAMP_ADD(@cutoff, INTERVAL 30 DAY), t.amount, 0)) AS deposit_amount_30d
  FROM `{{dataset}}.raw_followup_transactions` AS t
  JOIN `{{dataset}}.stg_accounts` AS a USING (account_id)
  WHERE a.account_type = 'SAVINGS'
    AND t.transaction_type = 'DEPOSIT' AND t.transaction_status = 'COMPLETED' AND t.amount > 0
    AND t.transaction_timestamp >= @cutoff AND t.transaction_timestamp < @observation_end
  GROUP BY a.customer_id
),
app AS (
  SELECT DISTINCT user_id AS customer_id
  FROM `{{dataset}}.raw_followup_ga4_events`
  WHERE TIMESTAMP_MICROS(event_timestamp) >= @cutoff
    AND TIMESTAMP_MICROS(event_timestamp) < TIMESTAMP_ADD(@cutoff, INTERVAL 30 DAY)
    AND event_name IN ('savings_account_view', 'savings_goal_started', 'savings_goal_completed', 'deposit_initiated')
),
outcomes AS (
  SELECT
    e.experiment_id, e.customer_id, e.assigned_variant, e.assignment_timestamp,
    p.profile, p.open_savings_account_id, p.region, p.acquisition_channel,
    p.tenure_days, p.sessions, p.savings_sessions, p.checking_transactions,
    d.first_two[SAFE_OFFSET(0)] AS first_deposit,
    d.first_two[SAFE_OFFSET(1)] AS second_deposit,
    COALESCE(d.deposit_amount_30d, 0) AS deposit_amount_30d,
    a.customer_id IS NOT NULL AS app_engaged_30d
  FROM `{{dataset}}.stg_experiments` AS e
  JOIN `{{dataset}}.mart_customer_profiles` AS p USING (customer_id)
  LEFT JOIN deposits AS d USING (customer_id)
  LEFT JOIN app AS a USING (customer_id)
  WHERE e.experiment_id = @experiment_id AND e.eligibility_status = 'ELIGIBLE'
),
flags AS (
  SELECT
    *,
    COALESCE(first_deposit < TIMESTAMP_ADD(assignment_timestamp, INTERVAL 14 DAY), FALSE) AS activated_14d,
    COALESCE(first_deposit < TIMESTAMP_ADD(assignment_timestamp, INTERVAL 30 DAY), FALSE) AS activated_30d
  FROM outcomes
)
SELECT
  *,
  activated_14d AND COALESCE(second_deposit < TIMESTAMP_ADD(first_deposit, INTERVAL 30 DAY), FALSE)
    AS sustained_saving
FROM flags
