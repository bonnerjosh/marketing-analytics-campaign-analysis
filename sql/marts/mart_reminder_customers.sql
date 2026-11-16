WITH assignments AS (
  SELECT customer_id, account_id, arm, occurred_at AS assigned_at
  FROM `{{dataset}}.raw_reminder_events`
  WHERE kind = 'assignment'
),
deposits AS (
  SELECT a.customer_id, MIN(e.occurred_at) AS first_deposit
  FROM assignments AS a
  JOIN `{{dataset}}.raw_reminder_events` AS e
    ON e.customer_id = a.customer_id AND e.account_id = a.account_id
    AND e.kind = 'posted_savings_deposit' AND e.amount > 0
    AND e.occurred_at >= a.assigned_at
    AND e.occurred_at < TIMESTAMP_ADD(a.assigned_at, INTERVAL 14 DAY)
  GROUP BY a.customer_id
),
touches AS (
  SELECT DISTINCT event_id, customer_id, kind, occurred_at
  FROM `{{dataset}}.raw_reminder_events`
  WHERE kind IN ('email_delivery', 'in_app_impression')
),
credit AS (
  SELECT d.customer_id,
    ARRAY_AGG(t.kind ORDER BY t.occurred_at, t.event_id LIMIT 1)[OFFSET(0)] AS first_touch,
    ARRAY_AGG(t.kind ORDER BY t.occurred_at DESC, t.event_id DESC LIMIT 1)[OFFSET(0)] AS last_touch
  FROM deposits AS d
  JOIN assignments AS a USING (customer_id)
  JOIN touches AS t
    ON t.customer_id = d.customer_id AND t.occurred_at >= a.assigned_at
    AND t.occurred_at < d.first_deposit
    AND d.first_deposit < TIMESTAMP_ADD(t.occurred_at, INTERVAL 7 DAY)
  GROUP BY d.customer_id
),
exposure AS (
  SELECT a.customer_id, COUNTIF(t.kind = 'in_app_impression') AS impressions
  FROM assignments AS a
  LEFT JOIN touches AS t
    ON t.customer_id = a.customer_id AND t.occurred_at >= a.assigned_at
    AND t.occurred_at < TIMESTAMP_ADD(a.assigned_at, INTERVAL 14 DAY)
  GROUP BY a.customer_id
)
SELECT a.customer_id, a.arm, d.first_deposit IS NOT NULL AS funded,
  x.impressions, c.first_touch, c.last_touch
FROM assignments AS a
LEFT JOIN deposits AS d USING (customer_id)
LEFT JOIN credit AS c USING (customer_id)
JOIN exposure AS x USING (customer_id)
