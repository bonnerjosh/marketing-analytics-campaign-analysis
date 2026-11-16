SELECT
  event_id,
  PARSE_DATE('%Y%m%d', event_date) AS event_date,
  TIMESTAMP_MICROS(event_timestamp) AS event_timestamp,
  user_id AS customer_id,
  user_pseudo_id,
  event_name,
  platform,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS session_id,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'screen_name') AS screen_name,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'campaign_id') AS campaign_id,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'savings_goal_type') AS savings_goal_type
FROM `{{dataset}}.raw_ga4_events`
