TEST (name "stg_brands__keeps_latest_brand_and_parses_metadata");

WITH __source__catalogue__brands AS (
  SELECT
    'bw' AS brand_code,
    ' Mallard & Co. ' AS brand_name,
    'de' AS country_code,
    NULL AS is_private_label,
    PARSE_JSON('{"founded": "1990"}')::VARIANT AS metadata,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'bw',
    ' Mallard & Co. Home ',
    'de',
    NULL,
    PARSE_JSON('{"sustainability": {"rating": "a"}, "founded": "Est. 1998"}')::VARIANT,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'nx',
    'Bill & Coo',
    'fr',
    TRUE,
    PARSE_JSON('{"sustainability": {"rating": null}, "founded": "unknown"}')::VARIANT,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'old',
    'Old',
    'de',
    NULL,
    NULL,
    'I',
    4,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'old',
    'Old',
    'de',
    NULL,
    NULL,
    'D',
    5,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_brands AS (
  SELECT
    'BW' AS brand_code,
    'Mallard & Co. Home' AS brand_name,
    'DE' AS country_code,
    FALSE AS is_private_label,
    'A' AS sustainability_rating,
    1998 AS founded_year,
    2 AS source_seq
  UNION ALL
  SELECT
    'NX' AS brand_code,
    'Bill & Coo' AS brand_name,
    'FR' AS country_code,
    TRUE AS is_private_label,
    CAST(NULL AS VARCHAR) AS sustainability_rating,
    CAST(NULL AS INT) AS founded_year,
    3 AS source_seq
)
