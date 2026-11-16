WITH credit AS (
  SELECT
    e.customer_id, e.first_deposit,
    ARRAY_AGG(m.campaign_id IGNORE NULLS ORDER BY m.delivered_at, m.message_id LIMIT 1)[SAFE_OFFSET(0)]
      AS first_touch_campaign,
    ARRAY_AGG(m.campaign_id IGNORE NULLS ORDER BY m.delivered_at DESC, m.message_id DESC LIMIT 1)[SAFE_OFFSET(0)]
      AS last_touch_campaign
  FROM `{{dataset}}.mart_experiment_customers` AS e
  LEFT JOIN `{{dataset}}.mart_campaign_messages` AS m
    ON e.customer_id = m.customer_id
   AND m.delivered_at >= e.assignment_timestamp
   AND m.delivered_at < e.first_deposit
   AND e.first_deposit < TIMESTAMP_ADD(m.delivered_at, INTERVAL 7 DAY)
  WHERE e.activated_14d
  GROUP BY e.customer_id, e.first_deposit
)
SELECT *
FROM credit
