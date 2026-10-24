TEST (name "int_partner_orders_unified__unifies_payload_versions_and_links_hashed_buyers");

WITH __ref__stg_partner_orders_v1 AS (
  SELECT
    'PK1' AS partner_order_key,
    'MKT' AS partner_code,
    'A1' AS external_order_id,
    'a@example.com' AS buyer_email,
    'EUR' AS currency_code,
    12.5::DECIMAL(18, 3) AS order_total,
    '2026-03-10 23:30:00 -02:00'::TIMESTAMP_TZ AS placed_at,
    NULL AS lines
),

__ref__stg_partner_orders_v2 AS (
  SELECT
    'PK2' AS partner_order_key,
    'MKT' AS partner_code,
    'B7' AS external_order_id,
    SHA2('b@example.com', 256) AS buyer_email_hash,
    'KWD' AS currency_code,
    1500::DECIMAL(38, 0) AS order_total_minor,
    '2026-03-10 08:00:00'::TIMESTAMP_NTZ AS placed_at_utc,
    NULL AS items
  UNION ALL
  SELECT
    'PK3',
    'OTHER',
    'C1',
    SHA2('z@example.com', 256),
    'USD',
    999::DECIMAL(38, 0),
    '2026-03-12 10:00:00'::TIMESTAMP_NTZ,
    NULL
),

__ref__stg_partner_order_lines AS (
  SELECT
    'PK1#1' AS partner_order_line_key,
    'PK1' AS partner_order_key,
    NULL AS payload_version,
    'DUCK-1' AS sku,
    2 AS quantity,
    500::DECIMAL(38, 0) AS unit_amount_minor
  UNION ALL
  SELECT
    'PK1#2',
    'PK1',
    NULL,
    'DUCK-2',
    1,
    250::DECIMAL(38, 0)
  UNION ALL
  SELECT
    'PK2#1',
    'PK2',
    NULL,
    'DUCK-1',
    1,
    1400::DECIMAL(38, 0)
),

__ref__int_customer_identity AS (
  SELECT
    'C1' AS customer_id,
    'a@example.com' AS email_normalised,
    NULL AS email_domain,
    NULL AS email_dedupe_key,
    NULL AS phone_normalised,
    NULL AS full_name,
    NULL AS anonymous_ids,
    NULL AS anonymous_id_count,
    NULL AS newsletter_lists,
    NULL AS ticket_count,
    NULL AS duplicate_candidate_id,
    NULL AS duplicate_name_similarity,
    NULL AS accounts_sharing_email
  UNION ALL
  SELECT
    'C2',
    'b@example.com',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-11'::DATE AS rate_date,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'KWD',
    '2026-03-01'::DATE,
    3.25::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'USD',
    '2026-03-01'::DATE,
    1.0::NUMBER(18, 8),
    NULL,
    NULL
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'KWD',
    NULL,
    3,
    NULL
  UNION ALL
  SELECT
    'USD',
    NULL,
    2,
    NULL
),

__expected__int_partner_orders_unified AS (
  SELECT
    'PK1' AS partner_order_key,
    'stg_partner_orders_v1' AS source_relation,
    1 AS payload_version,
    '2026-03-11 01:30:00'::TIMESTAMPNTZ AS placed_at_utc,
    '2026-03-11'::DATE AS placed_date,
    1250 AS order_total_minor,
    13.75::DECIMAL(18, 2) AS order_total_usd,
    2 AS line_count,
    3 AS units,
    1250 AS lines_total_minor,
    TRUE AS lines_match_total,
    'C1' AS customer_id,
    TRUE AS is_known_customer,
    2 AS order_rank_for_partner
  UNION ALL
  SELECT
    'PK2' AS partner_order_key,
    'stg_partner_orders_v2' AS source_relation,
    2 AS payload_version,
    '2026-03-10 08:00:00'::TIMESTAMPNTZ AS placed_at_utc,
    '2026-03-10'::DATE AS placed_date,
    1500 AS order_total_minor,
    4.88::DECIMAL(18, 2) AS order_total_usd,
    1 AS line_count,
    1 AS units,
    1400 AS lines_total_minor,
    FALSE AS lines_match_total,
    'C2' AS customer_id,
    TRUE AS is_known_customer,
    1 AS order_rank_for_partner
  UNION ALL
  SELECT
    'PK3' AS partner_order_key,
    'stg_partner_orders_v2' AS source_relation,
    2 AS payload_version,
    '2026-03-12 10:00:00'::TIMESTAMPNTZ AS placed_at_utc,
    '2026-03-12'::DATE AS placed_date,
    999 AS order_total_minor,
    9.99::DECIMAL(18, 2) AS order_total_usd,
    0 AS line_count,
    0 AS units,
    0 AS lines_total_minor,
    FALSE AS lines_match_total,
    CAST(NULL AS VARCHAR) AS customer_id,
    FALSE AS is_known_customer,
    1 AS order_rank_for_partner
)
