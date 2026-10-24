TEST (name "stg_chat_messages__masks_contact_details_in_messages");

WITH __ref__stg_chat_transcripts AS (
  SELECT
    'CH1' AS chat_id,
    NULL AS ticket_id,
    NULL AS started_at,
    NULL AS ended_at,
    NULL AS message_count,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'role',
        'Customer',
        'ts',
        '2026-03-10 10:00:00 +00:00',
        'text',
        'My duck arrived squashed, call me on +44 20 7946 0958 or mail duck.fan@example.com'
      ),
      OBJECT_CONSTRUCT(
        'role',
        'AGENT',
        'ts',
        'yesterday',
        'text',
        'Sorry!'
      )
    )::ARRAY AS messages,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CH2',
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('[]')::ARRAY,
    NULL,
    NULL
),

__expected__stg_chat_messages AS (
  SELECT
    'CH1#0' AS chat_message_key,
    'customer' AS sender_role,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS sent_at,
    'My duck arrived squashed, call me on <phone> or mail <email>' AS message_text_masked,
    82 AS message_length
  UNION ALL
  SELECT
    'CH1#1' AS chat_message_key,
    'agent' AS sender_role,
    CAST(NULL AS TIMESTAMP_TZ) AS sent_at,
    'Sorry!' AS message_text_masked,
    6 AS message_length
)
