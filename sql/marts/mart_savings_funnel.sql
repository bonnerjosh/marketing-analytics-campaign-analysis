WITH mature_signups AS (
  SELECT *
  FROM `{{dataset}}.mart_customer_savings_lifecycle`
  WHERE TIMESTAMP_ADD(signup_timestamp, INTERVAL 90 DAY) <= @cutoff
),
counts AS (
  SELECT
    COUNT(*) AS signups,
    COUNTIF(opened_in_30d) AS opened,
    COUNTIF(opened_in_30d AND funded_in_30d) AS activated,
    COUNTIF(opened_in_30d AND funded_in_30d AND repeated_in_30d) AS repeated,
    APPROX_QUANTILES(
      IF(opened_in_30d, TIMESTAMP_DIFF(first_savings_open, signup_timestamp, SECOND), NULL),
      100 IGNORE NULLS
    )[SAFE_OFFSET(50)] / 86400.0 AS median_days_to_open,
    APPROX_QUANTILES(
      IF(opened_in_30d AND funded_in_30d, TIMESTAMP_DIFF(first_deposit, first_savings_open, SECOND), NULL),
      100 IGNORE NULLS
    )[SAFE_OFFSET(50)] / 86400.0 AS median_days_to_activation
  FROM mature_signups
)
SELECT
  *,
  SAFE_DIVIDE(opened, signups) AS open_rate,
  SAFE_DIVIDE(activated, opened) AS activation_rate,
  SAFE_DIVIDE(repeated, activated) AS repeat_rate,
  SAFE_DIVIDE(signups - opened, signups) AS opening_drop_off,
  SAFE_DIVIDE(opened - activated, opened) AS activation_drop_off,
  SAFE_DIVIDE(activated - repeated, activated) AS repeat_drop_off
FROM counts
