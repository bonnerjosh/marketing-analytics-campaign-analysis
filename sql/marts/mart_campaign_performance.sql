WITH counts AS (
  SELECT
    m.campaign_id, dimension.name AS breakdown, dimension.value AS breakdown_value,
    COUNT(*) AS messages_sent,
    COUNTIF(m.delivered_at IS NOT NULL) AS messages_delivered,
    COUNT(DISTINCT IF(m.delivered_at < TIMESTAMP_SUB(@observation_end, INTERVAL 7 DAY), m.customer_id, NULL))
      AS mature_delivered_recipients,
    COUNT(DISTINCT IF(m.first_click IS NOT NULL
        AND m.delivered_at < TIMESTAMP_SUB(@observation_end, INTERVAL 7 DAY), m.customer_id, NULL)) AS unique_clickers,
    COUNT(DISTINCT IF(m.first_click >= e.assignment_timestamp
        AND m.first_click < TIMESTAMP_ADD(e.assignment_timestamp, INTERVAL 14 DAY), m.customer_id, NULL))
      AS unique_clickers_14d,
    COUNT(DISTINCT IF(e.activated_14d AND m.first_click >= e.assignment_timestamp
        AND m.first_click < e.first_deposit AND e.first_deposit < TIMESTAMP_ADD(m.first_click, INTERVAL 7 DAY),
        m.customer_id, NULL)) AS activated_after_click,
    COUNT(DISTINCT IF(a.first_touch_campaign = m.campaign_id, m.customer_id, NULL)) AS first_touch_credits,
    COUNT(DISTINCT IF(a.last_touch_campaign = m.campaign_id, m.customer_id, NULL)) AS last_touch_credits
  FROM `{{dataset}}.mart_campaign_messages` AS m
  JOIN `{{dataset}}.mart_experiment_customers` AS e USING (customer_id)
  LEFT JOIN `{{dataset}}.mart_campaign_attribution` AS a USING (customer_id)
  CROSS JOIN UNNEST([
    STRUCT('overall' AS name, 'all' AS value),
    STRUCT('acquisition_channel', e.acquisition_channel),
    STRUCT('profile', e.profile),
    STRUCT('region', e.region),
    STRUCT('assignment', e.assigned_variant)
  ]) AS dimension
  GROUP BY m.campaign_id, breakdown, breakdown_value
)
SELECT *,
  SAFE_DIVIDE(messages_delivered, messages_sent) AS delivery_rate,
  SAFE_DIVIDE(unique_clickers, mature_delivered_recipients) AS click_through_rate,
  SAFE_DIVIDE(activated_after_click, unique_clickers_14d) AS post_click_activation_rate
FROM counts
