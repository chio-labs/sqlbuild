TEST (name "stg_affiliate_conversions__reads_click_time_and_sub_id_from_payload");

WITH __source__growth__affiliate_conversions AS (
  SELECT
    'CV1' AS conversion_id,
    'awn-x' AS affiliate_code,
    'O1' AS order_id,
    500 AS commission_minor,
    'eur' AS currency_code,
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ AS converted_at,
    OBJECT_CONSTRUCT(
      'clicked_at',
      '2026-03-09 10:00:00 +00:00',
      'landing_url',
      'https://shop.example.com/?subid=social_pf&x=1'
    )::VARIANT AS click_payload,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'CV1',
    'awn-x',
    'O1',
    600,
    'eur',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    OBJECT_CONSTRUCT(
      'clicked_at',
      '2026-03-09 10:00:00 +00:00',
      'landing_url',
      'https://shop.example.com/?subid=social_pf&x=1'
    )::VARIANT,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'CV2',
    'pn_kw',
    'O2',
    100,
    'kwd',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    PARSE_JSON('{}')::VARIANT,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'CV3',
    'pn_kw',
    'O3',
    100,
    'kwd',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'I',
    4,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'CV3',
    'pn_kw',
    'O3',
    100,
    'kwd',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'D',
    5,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_affiliate_conversions AS (
  SELECT
    'CV1' AS conversion_id,
    'AWN-X' AS affiliate_code,
    600 AS commission_minor,
    'EUR' AS currency_code,
    '2026-03-09 10:00:00 +00:00'::TIMESTAMP_TZ AS clicked_at,
    26 AS click_to_conversion_hours,
    'social_pf' AS sub_id,
    2 AS source_seq
  UNION ALL
  SELECT
    'CV2' AS conversion_id,
    'PN_KW' AS affiliate_code,
    100 AS commission_minor,
    'KWD' AS currency_code,
    CAST(NULL AS TIMESTAMP_TZ) AS clicked_at,
    CAST(NULL AS INT) AS click_to_conversion_hours,
    CAST(NULL AS VARCHAR) AS sub_id,
    3 AS source_seq
)
