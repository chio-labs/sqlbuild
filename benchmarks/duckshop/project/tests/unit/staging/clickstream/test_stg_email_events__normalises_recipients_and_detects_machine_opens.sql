TEST (name "stg_email_events__normalises_recipients_and_detects_machine_opens");

WITH __source__clickstream__email_events AS (
  SELECT
    'm1' AS email_event_id,
    'M1' AS message_id,
    'SENT' AS event_type,
    'x@example.com' AS recipient_email,
    'CMP1' AS campaign_id,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS occurred_at,
    PARSE_JSON('{}')::VARIANT AS details,
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'm1',
    'M1',
    'CLICK',
    ' Shopper+news@Example.com ',
    'CMP1',
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    PARSE_JSON('{"url": "https://shop.example.com/p/1"}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'm2',
    'M1',
    'Open',
    'shopper@example.com',
    'CMP1',
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    PARSE_JSON('{"user_agent": "Mail Image Proxy 1.0"}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'm3',
    'M1',
    'Bounce',
    'not-an-email',
    'CMP1',
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    PARSE_JSON('{"bounce": {"type": "HARD"}, "machine_open": false}')::VARIANT,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
),

__expected__stg_email_events AS (
  SELECT
    'm1' AS email_event_id,
    'click' AS event_type,
    'shopper@example.com' AS recipient_email,
    'https://shop.example.com/p/1' AS clicked_url,
    CAST(NULL AS VARCHAR) AS bounce_type,
    CAST(NULL AS BOOLEAN) AS is_machine_open
  UNION ALL
  SELECT
    'm2' AS email_event_id,
    'open' AS event_type,
    'shopper@example.com' AS recipient_email,
    CAST(NULL AS VARCHAR) AS clicked_url,
    CAST(NULL AS VARCHAR) AS bounce_type,
    TRUE AS is_machine_open
  UNION ALL
  SELECT
    'm3' AS email_event_id,
    'bounce' AS event_type,
    CAST(NULL AS VARCHAR) AS recipient_email,
    CAST(NULL AS VARCHAR) AS clicked_url,
    'hard' AS bounce_type,
    FALSE AS is_machine_open
)
