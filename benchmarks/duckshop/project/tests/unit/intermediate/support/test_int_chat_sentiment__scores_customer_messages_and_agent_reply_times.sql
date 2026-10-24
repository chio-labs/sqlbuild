TEST (name "int_chat_sentiment__scores_customer_messages_and_agent_reply_times");

WITH __ref__stg_chat_messages AS (
  SELECT
    'CH1:1' AS chat_message_key,
    'CH1' AS chat_id,
    1 AS message_index,
    'customer' AS sender_role,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS sent_at,
    'This is terrible, the item arrived broken' AS message_text_masked,
    NULL AS message_length
  UNION ALL
  SELECT
    'CH1:2',
    'CH1',
    2,
    'agent',
    '2026-03-10 10:01:30 +00:00'::TIMESTAMP_TZ,
    'Sorry to hear that',
    NULL
  UNION ALL
  SELECT
    'CH1:3',
    'CH1',
    3,
    'customer',
    '2026-03-10 10:03:00 +00:00'::TIMESTAMP_TZ,
    'Thanks, that is helpful',
    NULL
  UNION ALL
  SELECT
    'CH1:4',
    'CH1',
    4,
    'agent',
    '2026-03-10 10:03:30 +00:00'::TIMESTAMP_TZ,
    'A replacement is on its way',
    NULL
  UNION ALL
  SELECT
    'CH1:5',
    'CH1',
    5,
    'customer',
    '2026-03-10 10:04:00 +00:00'::TIMESTAMP_TZ,
    'Great, thank you',
    NULL
  UNION ALL
  SELECT
    'CH2:1',
    'CH2',
    1,
    'customer',
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    'Where is my order',
    NULL
  UNION ALL
  SELECT
    'CH2:2',
    'CH2',
    2,
    'customer',
    '2026-03-10 10:00:20 +00:00'::TIMESTAMP_TZ,
    'I want to cancel',
    NULL
),

__ref__stg_chat_transcripts AS (
  SELECT
    'CH1' AS chat_id,
    'T1' AS ticket_id,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS started_at,
    '2026-03-10 10:05:30 +00:00'::TIMESTAMP_TZ AS ended_at,
    NULL AS message_count,
    NULL AS messages,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CH2',
    'T2',
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-10 10:00:20 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'CH3',
    'T3',
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_chat_sentiment AS (
  SELECT
    'CH1' AS chat_id,
    3 AS customer_message_count,
    2 AS agent_message_count,
    2 AS sentiment_score,
    'positive' AS sentiment_label,
    60 AS median_agent_reply_seconds,
    TRUE AS ends_with_thanks,
    5.5::DECIMAL(10, 2) AS chat_minutes
  UNION ALL
  SELECT
    'CH2' AS chat_id,
    2 AS customer_message_count,
    0 AS agent_message_count,
    -1 AS sentiment_score,
    'negative' AS sentiment_label,
    CAST(NULL AS INT) AS median_agent_reply_seconds,
    FALSE AS ends_with_thanks,
    0.33::DECIMAL(10, 2) AS chat_minutes
  UNION ALL
  SELECT
    'CH3' AS chat_id,
    0 AS customer_message_count,
    0 AS agent_message_count,
    0 AS sentiment_score,
    'neutral' AS sentiment_label,
    CAST(NULL AS INT) AS median_agent_reply_seconds,
    FALSE AS ends_with_thanks,
    CAST(NULL AS DECIMAL(10, 2)) AS chat_minutes
)
