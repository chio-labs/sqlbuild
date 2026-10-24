TEST (name "int_email_engagement__separates_machine_opens_and_click_domains");

WITH __ref__stg_email_events AS (
  SELECT
    'm1' AS email_event_id,
    'M1' AS message_id,
    'sent' AS event_type,
    'a@example.com' AS recipient_email,
    'CMP1' AS campaign_id,
    '2026-03-10 09:00:00 +00:00'::TIMESTAMP_TZ AS occurred_at,
    NULL AS clicked_url,
    NULL AS bounce_type,
    NULL AS is_machine_open,
    NULL AS details
  UNION ALL
  SELECT
    'm2',
    'M1',
    'delivered',
    'a@example.com',
    'CMP1',
    '2026-03-10 09:00:05 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'm3',
    'M1',
    'open',
    'a@example.com',
    'CMP1',
    '2026-03-10 09:00:06 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    TRUE,
    NULL
  UNION ALL
  SELECT
    'm4',
    'M1',
    'open',
    'a@example.com',
    'CMP1',
    '2026-03-10 09:20:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    FALSE,
    NULL
  UNION ALL
  SELECT
    'm5',
    'M1',
    'click',
    'a@example.com',
    'CMP1',
    '2026-03-10 09:30:00 +00:00'::TIMESTAMP_TZ,
    'https://Shop.Example.com/p/1',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'm6',
    'M1',
    'click',
    'a@example.com',
    'CMP1',
    '2026-03-10 09:45:00 +00:00'::TIMESTAMP_TZ,
    'https://blog.example.com/x',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'm7',
    'M1',
    'unsubscribe',
    'a@example.com',
    'CMP1',
    '2026-03-10 09:50:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'n1',
    'M2',
    'sent',
    'b@example.com',
    'CMP2',
    '2026-02-01 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'n2',
    'M2',
    'bounce',
    'b@example.com',
    'CMP2',
    '2026-02-01 09:00:01 +00:00'::TIMESTAMP_TZ,
    NULL,
    'hard',
    NULL,
    NULL
),

__ref__stg_customers AS (
  SELECT
    'C1' AS customer_id,
    'a@example.com' AS email_normalised,
    NULL AS phone_normalised,
    NULL AS first_name,
    NULL AS last_name,
    NULL AS region_code,
    NULL AS storefront_code,
    NULL AS created_at,
    NULL AS preferred_language,
    NULL AS marketing_opt_in,
    NULL AS consent_types,
    NULL AS birth_year,
    NULL AS preferences,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_campaigns AS (
  SELECT
    'CMP1' AS campaign_id,
    NULL AS campaign_name,
    'email' AS channel,
    NULL AS objective,
    '2026-03-01'::DATE AS starts_on,
    NULL AS ends_on,
    NULL AS budget_minor,
    NULL AS currency_code,
    NULL AS target_regions,
    NULL AS target_age_min,
    NULL AS target_age_max,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_email_engagement AS (
  SELECT
    'M1' AS message_id,
    '2026-03-10 09:00:00 +00:00'::TIMESTAMP_TZ AS sent_at,
    TRUE AS is_delivered,
    CAST(NULL AS VARCHAR) AS bounce_type,
    1 AS human_open_count,
    2 AS click_count,
    TRUE AS unsubscribed,
    FALSE AS complained,
    30 AS minutes_to_first_click,
    'C1' AS customer_id,
    'email' AS campaign_channel,
    TRUE AS is_campaign_in_flight
  UNION ALL
  SELECT
    'M2' AS message_id,
    '2026-02-01 09:00:00 +00:00'::TIMESTAMP_TZ AS sent_at,
    FALSE AS is_delivered,
    'hard' AS bounce_type,
    0 AS human_open_count,
    0 AS click_count,
    FALSE AS unsubscribed,
    FALSE AS complained,
    CAST(NULL AS INT) AS minutes_to_first_click,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS VARCHAR) AS campaign_channel,
    FALSE AS is_campaign_in_flight
),

__assert__clicked_domains_are_lower_cased_hosts AS (
  SELECT e.message_id
  FROM __ref("int_email_engagement") AS e
  WHERE
    ARRAY_TO_STRING(e.clicked_domains, ',') <> IFF(
      e.message_id = 'M1',
      'blog.example.com,shop.example.com',
      ''
    )
)
