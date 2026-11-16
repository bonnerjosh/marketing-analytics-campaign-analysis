SELECT
  *,
  transaction_type = 'DEPOSIT' AND transaction_status = 'COMPLETED' AND amount > 0
    AS is_completed_positive_deposit
FROM `{{dataset}}.raw_transactions`
