WITH sessions AS (
  SELECT customer_id, COUNT(*) AS sessions, COUNTIF(savings_engaged) AS savings_sessions
  FROM `{{dataset}}.mart_app_sessions`
  WHERE session_start >= TIMESTAMP_SUB(@cutoff, INTERVAL 30 DAY) AND session_start < @cutoff
  GROUP BY customer_id
),
checking AS (
  SELECT a.customer_id, COUNT(*) AS checking_transactions
  FROM `{{dataset}}.stg_transactions` AS t
  JOIN `{{dataset}}.stg_accounts` AS a USING (account_id)
  WHERE a.account_type = 'CHECKING'
    AND t.transaction_status = 'COMPLETED' AND t.transaction_type IN ('DEBIT', 'CREDIT')
    AND t.transaction_timestamp >= TIMESTAMP_SUB(@cutoff, INTERVAL 30 DAY)
    AND t.transaction_timestamp < @cutoff
  GROUP BY a.customer_id
),
features AS (
  SELECT
    l.customer_id, l.region, l.acquisition_channel, l.customer_segment,
    l.open_savings_account_id, l.eligibility_status,
    TIMESTAMP_DIFF(@cutoff, l.signup_timestamp, DAY) AS tenure_days,
    COALESCE(s.sessions, 0) AS sessions,
    COALESCE(s.savings_sessions, 0) AS savings_sessions,
    COALESCE(c.checking_transactions, 0) AS checking_transactions
  FROM `{{dataset}}.mart_customer_savings_lifecycle` AS l
  LEFT JOIN sessions AS s USING (customer_id)
  LEFT JOIN checking AS c USING (customer_id)
)
SELECT
  *,
  CASE
    WHEN eligibility_status != 'ELIGIBLE' THEN NULL
    WHEN sessions >= 6 AND savings_sessions >= 2 AND checking_transactions >= 4 THEN 'A'
    WHEN checking_transactions >= 6 AND sessions >= 2 AND savings_sessions <= 1 THEN 'B'
    ELSE 'C'
  END AS profile
FROM features
