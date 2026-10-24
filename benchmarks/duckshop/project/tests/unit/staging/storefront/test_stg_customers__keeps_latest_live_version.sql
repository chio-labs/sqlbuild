TEST (name "stg_customers__keeps_latest_live_version");

WITH __source__storefront__customers AS (
  SELECT
    'C1' AS customer_id,
    ' Ada.Featherby@Example.COM ' AS email,
    NULL AS phone,
    'ada featherby' AS full_name,
    'eu' AS region_code,
    'eu-web' AS storefront_code,
    NULL AS created_at,
    NULL AS updated_at,
    PARSE_JSON('{"preferences": {"language": "de"}}') AS profile,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'C1',
    'ada@example.com',
    NULL,
    'Ada Featherby',
    'EU',
    'eu-web',
    NULL,
    NULL,
    PARSE_JSON('{}'),
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'C2',
    'bob@example.com',
    NULL,
    'Bob Reedley',
    'US',
    'us-web',
    NULL,
    NULL,
    PARSE_JSON('{}'),
    'I',
    3,
    '2026-01-01 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'C2',
    'bob@example.com',
    NULL,
    'Bob Reedley',
    'US',
    'us-web',
    NULL,
    NULL,
    PARSE_JSON('{}'),
    'D',
    4,
    '2026-01-03 11:00:00'::TIMESTAMP_NTZ
),

__expected__stg_customers AS (
  SELECT
    'C1' AS customer_id,
    'ada@example.com' AS email_normalised,
    'Ada' AS first_name,
    'Featherby' AS last_name,
    'EU' AS region_code,
    'EU-WEB' AS storefront_code,
    'en' AS preferred_language,
    2 AS source_seq
)
