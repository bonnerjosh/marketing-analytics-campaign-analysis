WITH cohort_rows AS (
  SELECT
    c.*,
    cohort.kind,
    cohort.cohort_month,
    cohort.maturity_days,
    dimension.name AS breakdown,
    dimension.value AS breakdown_value
  FROM `{{dataset}}.mart_customer_savings_lifecycle` AS c
  CROSS JOIN UNNEST([
    STRUCT('signup' AS kind, DATE_TRUNC(DATE(signup_timestamp), MONTH) AS cohort_month, 90 AS maturity_days),
    STRUCT('first_open', DATE_TRUNC(DATE(first_savings_open), MONTH), 60)
  ]) AS cohort
  CROSS JOIN UNNEST([
    STRUCT('overall' AS name, 'all' AS value),
    STRUCT('acquisition_channel', acquisition_channel),
    STRUCT('customer_segment', customer_segment),
    STRUCT('region', region),
    STRUCT('market_type', market_type),
    STRUCT('age_band', age_band)
  ]) AS dimension
  WHERE TIMESTAMP_ADD(
    TIMESTAMP(DATE_ADD(cohort.cohort_month, INTERVAL 1 MONTH)), INTERVAL cohort.maturity_days DAY
  ) <= @cutoff
),
counts AS (
  SELECT
    kind, cohort_month, breakdown, breakdown_value,
    COUNT(*) AS cohort_customers,
    COUNTIF(kind = 'first_open' OR opened_in_30d) AS opened_customers,
    COUNTIF((kind = 'first_open' OR opened_in_30d) AND funded_in_30d) AS activated_customers,
    COUNTIF((kind = 'first_open' OR opened_in_30d) AND funded_in_30d AND repeated_in_30d)
      AS repeat_customers,
    APPROX_QUANTILES(
      IF(kind = 'signup' AND opened_in_30d, TIMESTAMP_DIFF(first_savings_open, signup_timestamp, SECOND), NULL),
      100 IGNORE NULLS
    )[SAFE_OFFSET(50)] / 86400.0 AS median_days_to_open,
    APPROX_QUANTILES(
      IF((kind = 'first_open' OR opened_in_30d) AND funded_in_30d,
         TIMESTAMP_DIFF(first_deposit, first_savings_open, SECOND), NULL), 100 IGNORE NULLS
    )[SAFE_OFFSET(50)] / 86400.0 AS median_days_to_activation
  FROM cohort_rows
  GROUP BY kind, cohort_month, breakdown, breakdown_value
)
SELECT
  *,
  IF(kind = 'signup', SAFE_DIVIDE(opened_customers, cohort_customers), NULL) AS open_rate,
  SAFE_DIVIDE(activated_customers, opened_customers) AS activation_rate,
  SAFE_DIVIDE(repeat_customers, activated_customers) AS repeat_rate
FROM counts
