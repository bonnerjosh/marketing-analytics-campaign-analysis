WITH sessions AS (
  SELECT
    COUNTIF(event_name = 'session_start') AS starts,
    ARRAY_AGG(event_name ORDER BY event_timestamp, event_id LIMIT 1)[OFFSET(0)] AS first_event
  FROM `{{dataset}}.stg_ga4_events`
  GROUP BY user_pseudo_id, session_id
)
SELECT 'session_start_order' AS check_name,
  COUNTIF(starts != 1 OR first_event != 'session_start') AS violations
FROM sessions
UNION ALL
SELECT 'profile_coverage_and_eligibility', COUNTIF(
  p.customer_id IS NULL OR l.customer_id IS NULL
  OR (p.profile IS NOT NULL) != (l.open_savings_account_id IS NOT NULL AND l.first_deposit IS NULL)
  OR (p.profile IS NOT NULL AND p.profile NOT IN ('A', 'B', 'C'))
)
FROM `{{dataset}}.mart_customer_profiles` AS p
FULL JOIN `{{dataset}}.mart_customer_savings_lifecycle` AS l USING (customer_id)
UNION ALL
SELECT 'profile_keys', COUNT(*) - COUNT(DISTINCT customer_id)
FROM `{{dataset}}.mart_customer_profiles`
UNION ALL
SELECT 'cohort_nesting_and_maturity', COUNTIF(
  opened_customers > cohort_customers OR activated_customers > opened_customers
  OR repeat_customers > activated_customers OR cohort_customers = 0
  OR TIMESTAMP_ADD(TIMESTAMP(DATE_ADD(cohort_month, INTERVAL 1 MONTH)),
      INTERVAL IF(kind = 'signup', 90, 60) DAY) > @cutoff
)
FROM `{{dataset}}.mart_savings_cohorts`
UNION ALL
SELECT 'signup_funnel_nesting', COUNTIF(opened > signups OR activated > opened OR repeated > activated)
FROM `{{dataset}}.mart_savings_funnel`
UNION ALL
SELECT 'profile_rule_membership', COUNTIF(
  (profile = 'A') != (sessions >= 6 AND savings_sessions >= 2 AND checking_transactions >= 4)
  OR (profile = 'B') != (checking_transactions >= 6 AND sessions >= 2 AND savings_sessions <= 1)
  OR savings_sessions > sessions
)
FROM `{{dataset}}.mart_customer_profiles`
WHERE eligibility_status = 'ELIGIBLE'
