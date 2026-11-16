WITH savings_accounts AS (
  SELECT *
  FROM `{{dataset}}.stg_accounts`
  WHERE account_type = 'SAVINGS' AND account_open_timestamp < @cutoff
),
first_account AS (
  SELECT customer_id, MIN(account_open_timestamp) AS first_savings_open
  FROM savings_accounts
  GROUP BY customer_id
),
open_at_cutoff AS (
  SELECT customer_id, account_id
  FROM savings_accounts
  WHERE account_close_timestamp IS NULL OR account_close_timestamp >= @cutoff
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id ORDER BY account_open_timestamp, account_id
  ) = 1
),
ranked_deposits AS (
  SELECT
    a.customer_id,
    t.transaction_timestamp,
    ROW_NUMBER() OVER (
      PARTITION BY a.customer_id ORDER BY t.transaction_timestamp, t.transaction_id
    ) AS deposit_rank
  FROM `{{dataset}}.stg_transactions` AS t
  JOIN savings_accounts AS a USING (account_id)
  WHERE t.is_completed_positive_deposit AND t.transaction_timestamp < @cutoff
),
first_two AS (
  SELECT
    customer_id,
    MAX(IF(deposit_rank = 1, transaction_timestamp, NULL)) AS first_deposit,
    MAX(IF(deposit_rank = 2, transaction_timestamp, NULL)) AS second_deposit
  FROM ranked_deposits
  WHERE deposit_rank <= 2
  GROUP BY customer_id
)
SELECT
  c.*,
  f.first_savings_open,
  d.first_deposit,
  d.second_deposit,
  COALESCE(f.first_savings_open < TIMESTAMP_ADD(c.signup_timestamp, INTERVAL 30 DAY), FALSE) AS opened_in_30d,
  COALESCE(d.first_deposit < TIMESTAMP_ADD(f.first_savings_open, INTERVAL 30 DAY), FALSE) AS funded_in_30d,
  COALESCE(d.second_deposit < TIMESTAMP_ADD(d.first_deposit, INTERVAL 30 DAY), FALSE) AS repeated_in_30d,
  o.account_id AS open_savings_account_id,
  CASE
    WHEN o.account_id IS NULL THEN 'NO_OPEN_SAVINGS'
    WHEN d.first_deposit IS NOT NULL THEN 'PRIOR_FUNDING'
    ELSE 'ELIGIBLE'
  END AS eligibility_status
FROM `{{dataset}}.stg_customers` AS c
LEFT JOIN first_account AS f USING (customer_id)
LEFT JOIN open_at_cutoff AS o USING (customer_id)
LEFT JOIN first_two AS d USING (customer_id)
WHERE c.signup_timestamp < @cutoff
