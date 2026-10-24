TEST (name "stg_carrier_rate_cards__keeps_latest_live_version");

WITH __source__fulfilment__carrier_rate_cards AS (
  SELECT
    'K1' AS rate_card_id,
    NULL AS carrier_code,
    NULL AS service_level,
    NULL AS origin_country,
    NULL AS destination_country,
    NULL AS currency_code,
    NULL AS valid_from,
    NULL AS valid_to,
    NULL AS bands,
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
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_carrier_rate_cards AS (
  SELECT
    'K1' AS rate_card_id,
    2 AS source_seq
)
