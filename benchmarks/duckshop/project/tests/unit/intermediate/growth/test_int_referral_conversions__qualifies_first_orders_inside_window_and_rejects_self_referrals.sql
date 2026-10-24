TEST (name "int_referral_conversions__qualifies_first_orders_inside_window_and_rejects_self_referrals");

WITH __ref__stg_referral_invites AS (
  SELECT
    'I1' AS invite_id,
    'R1' AS referrer_customer_id,
    'new@example.com' AS invitee_email,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS sent_at,
    '2026-03-01 13:30:00 +00:00'::TIMESTAMP_TZ AS accepted_at,
    1000 AS reward_amount_minor,
    'EUR' AS reward_currency_code,
    NULL AS reward,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'I2',
    'R1',
    'self@example.com',
    '2026-03-02 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    500,
    'GBP',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'I3',
    'R2',
    'late@example.com',
    '2026-01-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    1000,
    'JPY',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'I4',
    'R2',
    'ghost@example.org',
    '2026-01-02 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    2000,
    'USD',
    NULL,
    NULL,
    NULL
),

__ref__int_customer_identity AS (
  SELECT
    'C9' AS customer_id,
    'new@example.com' AS email_normalised,
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
    'R1',
    'self@example.com',
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
  UNION ALL
  SELECT
    'C8',
    'late@example.com',
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

__ref__int_customer_order_sequence AS (
  SELECT
    'O1' AS order_id,
    'C9' AS customer_id,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_number,
    NULL AS is_first_order,
    NULL AS days_since_previous_order,
    25.0::NUMBER(18, 2) AS amount_usd,
    NULL AS lifetime_revenue_usd,
    NULL AS rolling_90d_revenue_usd,
    NULL AS previous_sales_channel,
    NULL AS is_channel_switch,
    NULL AS cohort_month
  UNION ALL
  SELECT
    'O2',
    'C9',
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    5.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O3',
    'R1',
    '2026-02-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    50.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O4',
    'R1',
    '2026-02-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    15.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O5',
    'C8',
    '2026-03-15 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    30.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-02-28'::DATE AS rate_date,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'GBP',
    '2026-03-01'::DATE,
    1.25::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'JPY',
    '2025-12-31'::DATE,
    0.0067::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'USD',
    '2026-01-01'::DATE,
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
    'GBP',
    NULL,
    2,
    NULL
  UNION ALL
  SELECT
    'JPY',
    NULL,
    0,
    NULL
  UNION ALL
  SELECT
    'USD',
    NULL,
    2,
    NULL
),

__expected__int_referral_conversions AS (
  SELECT
    'I1' AS invite_id,
    'C9' AS invitee_customer_id,
    'example.com' AS invitee_email_domain,
    3.5::DECIMAL(10, 2) AS hours_to_accept,
    'O1' AS first_order_id,
    25.0::DECIMAL(18, 2) AS first_order_usd,
    4 AS days_to_first_order,
    FALSE AS is_self_referral,
    TRUE AS is_qualified,
    11.0::DECIMAL(18, 2) AS reward_usd,
    1 AS invite_sequence_for_referrer,
    2 AS referrer_lifetime_orders
  UNION ALL
  SELECT
    'I2' AS invite_id,
    'R1' AS invitee_customer_id,
    'example.com' AS invitee_email_domain,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_accept,
    'O3' AS first_order_id,
    50.0::DECIMAL(18, 2) AS first_order_usd,
    -29 AS days_to_first_order,
    TRUE AS is_self_referral,
    FALSE AS is_qualified,
    6.25::DECIMAL(18, 2) AS reward_usd,
    2 AS invite_sequence_for_referrer,
    2 AS referrer_lifetime_orders
  UNION ALL
  SELECT
    'I3' AS invite_id,
    'C8' AS invitee_customer_id,
    'example.com' AS invitee_email_domain,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_accept,
    'O5' AS first_order_id,
    30.0::DECIMAL(18, 2) AS first_order_usd,
    73 AS days_to_first_order,
    FALSE AS is_self_referral,
    FALSE AS is_qualified,
    6.7::DECIMAL(18, 2) AS reward_usd,
    1 AS invite_sequence_for_referrer,
    0 AS referrer_lifetime_orders
  UNION ALL
  SELECT
    'I4' AS invite_id,
    CAST(NULL AS VARCHAR) AS invitee_customer_id,
    'example.org' AS invitee_email_domain,
    CAST(NULL AS DECIMAL(10, 2)) AS hours_to_accept,
    CAST(NULL AS VARCHAR) AS first_order_id,
    CAST(NULL AS DECIMAL(18, 2)) AS first_order_usd,
    CAST(NULL AS INT) AS days_to_first_order,
    FALSE AS is_self_referral,
    FALSE AS is_qualified,
    20.0::DECIMAL(18, 2) AS reward_usd,
    2 AS invite_sequence_for_referrer,
    0 AS referrer_lifetime_orders
)
