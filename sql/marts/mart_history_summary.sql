WITH app AS (
  SELECT
    customer_id,
    COUNT(*) AS session_count,
    COUNTIF(ordered_savings_view) > 0 AS viewed,
    COUNTIF(ordered_initiation) > 0 AS ordered_attempt,
    COUNTIF(any_initiation) > 0 AS attempted,
    COUNTIF(ordered_confirmation) > 0 AS confirmed
  FROM `{{dataset}}.mart_app_sessions`
  GROUP BY customer_id
)
SELECT
  dimension.name AS breakdown,
  dimension.value AS breakdown_value,
  COUNT(*) AS customers,
  COUNTIF(p.eligibility_status = 'ELIGIBLE') AS eligible_customers,
  COUNTIF(p.profile = 'A') AS profile_a,
  COUNTIF(p.profile = 'B') AS profile_b,
  COUNTIF(p.profile = 'C') AS profile_c,
  AVG(p.sessions) AS mean_recent_sessions,
  AVG(p.checking_transactions) AS mean_recent_checking_transactions,
  SUM(COALESCE(a.session_count, 0)) AS historical_sessions,
  COUNTIF(a.session_count > 0) AS active_customers,
  COUNTIF(a.viewed) AS ordered_view_customers,
  COUNTIF(a.ordered_attempt) AS ordered_attempt_customers,
  COUNTIF(a.confirmed) AS ordered_confirmation_customers,
  COUNTIF(a.attempted) AS historical_initiators,
  COUNTIF(l.first_deposit IS NOT NULL) AS historical_depositors,
  COUNTIF(a.attempted AND l.first_deposit IS NOT NULL) AS initiators_who_deposited
FROM `{{dataset}}.mart_customer_profiles` AS p
JOIN `{{dataset}}.mart_customer_savings_lifecycle` AS l USING (customer_id)
LEFT JOIN app AS a USING (customer_id)
CROSS JOIN UNNEST([
  STRUCT('overall' AS name, 'all' AS value),
  STRUCT('region', p.region),
  STRUCT('profile', p.profile)
]) AS dimension
WHERE dimension.value IS NOT NULL
GROUP BY breakdown, breakdown_value
