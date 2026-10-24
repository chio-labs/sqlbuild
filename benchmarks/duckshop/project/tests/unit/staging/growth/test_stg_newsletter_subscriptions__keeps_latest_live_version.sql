TEST (name "stg_newsletter_subscriptions__keeps_latest_live_version");

WITH __source__growth__newsletter_subscriptions AS (
  SELECT
    'K1' AS list_subscription_id,
    NULL AS email,
    NULL AS list_code,
    NULL AS list_status,
    NULL AS subscribed_at,
    NULL AS unsubscribed_at,
    NULL AS signup_source,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_newsletter_subscriptions AS (
  SELECT
    'K1' AS list_subscription_id,
    2 AS source_seq
)
