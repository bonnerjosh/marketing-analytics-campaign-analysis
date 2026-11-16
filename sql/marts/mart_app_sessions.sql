WITH ordered AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY user_pseudo_id, session_id ORDER BY event_timestamp, event_id
    ) AS event_order
  FROM `{{dataset}}.stg_ga4_events`
  WHERE event_timestamp < @cutoff
),
viewed AS (
  SELECT
    *,
    MIN(IF(event_name = 'savings_account_view', event_order, NULL))
      OVER (PARTITION BY user_pseudo_id, session_id) AS view_order
  FROM ordered
),
initiated AS (
  SELECT
    *,
    MIN(IF(event_name = 'deposit_initiated' AND event_order > view_order, event_order, NULL))
      OVER (PARTITION BY user_pseudo_id, session_id) AS attempt_order
  FROM viewed
)
SELECT
  customer_id, user_pseudo_id, session_id,
  MIN(event_timestamp) AS session_start,
  TIMESTAMP_DIFF(MAX(event_timestamp), MIN(event_timestamp), SECOND) AS duration_seconds,
  COUNT(*) AS event_count,
  LOGICAL_OR(event_name IN (
    'savings_account_view', 'savings_goal_started', 'savings_goal_completed', 'deposit_initiated'
  )) AS savings_engaged,
  LOGICAL_OR(view_order IS NOT NULL) AS ordered_savings_view,
  LOGICAL_OR(attempt_order IS NOT NULL) AS ordered_initiation,
  COUNTIF(event_name = 'deposit_initiated') > 0 AS any_initiation,
  COUNTIF(event_name = 'deposit_confirmation_view' AND event_order > attempt_order) > 0
    AS ordered_confirmation
FROM initiated
GROUP BY customer_id, user_pseudo_id, session_id
