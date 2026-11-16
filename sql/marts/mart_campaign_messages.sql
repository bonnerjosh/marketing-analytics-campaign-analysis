WITH deliveries AS (
  SELECT message_id, MIN(event_timestamp) AS delivered_at
  FROM `{{dataset}}.stg_marketing_events`
  WHERE event_type = 'delivered'
  GROUP BY message_id
),
clicks AS (
  SELECT e.message_id, MIN(e.event_timestamp) AS first_click
  FROM `{{dataset}}.stg_marketing_events` AS e
  JOIN deliveries AS d USING (message_id)
  WHERE e.event_type = 'clicked'
    AND e.event_timestamp >= d.delivered_at
    AND e.event_timestamp < TIMESTAMP_ADD(d.delivered_at, INTERVAL 7 DAY)
  GROUP BY e.message_id
)
SELECT
  s.customer_id, s.campaign_id, s.message_id, s.message_variant, s.channel,
  s.event_timestamp AS sent_at, d.delivered_at, c.first_click
FROM `{{dataset}}.stg_marketing_events` AS s
LEFT JOIN deliveries AS d USING (message_id)
LEFT JOIN clicks AS c USING (message_id)
WHERE s.event_type = 'sent'
