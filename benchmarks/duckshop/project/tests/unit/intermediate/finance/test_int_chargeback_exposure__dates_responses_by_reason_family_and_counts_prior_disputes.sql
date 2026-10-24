TEST (name "int_chargeback_exposure__dates_responses_by_reason_family_and_counts_prior_disputes");

WITH __ref__stg_chargebacks AS (
  SELECT
    'CB1' AS chargeback_id,
    'PM1' AS payment_id,
    10000 AS amount_minor,
    'EUR' AS currency_code,
    '10.4' AS reason_code,
    'fraud' AS reason_family,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMP_TZ AS opened_at,
    NULL AS closed_at,
    'open' AS outcome,
    NULL AS evidence_document_count,
    OBJECT_CONSTRUCT(
      'documents',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT('kind', 'Tracking'),
        OBJECT_CONSTRUCT('kind', 'invoice'),
        OBJECT_CONSTRUCT('kind', 'tracking')
      )
    )::OBJECT AS evidence,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CB2',
    'PM2',
    2500,
    'EUR',
    '13.1',
    'consumer_dispute',
    '2026-03-10 23:30:00 -05:00'::TIMESTAMP_TZ,
    '2026-03-20 10:00:00 +00:00'::TIMESTAMP_TZ,
    'won',
    NULL,
    PARSE_JSON('{}')::OBJECT,
    NULL,
    NULL
  UNION ALL
  SELECT
    'CB3',
    'PM9',
    1000,
    'KWD',
    '99',
    'other',
    '2026-03-25 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    'pending',
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_payments AS (
  SELECT
    'PM1' AS payment_id,
    'O1' AS order_id,
    'card' AS payment_method,
    10000 AS amount_minor,
    NULL AS currency_code,
    NULL AS authorised_at,
    NULL AS captured_at,
    NULL AS card_bin,
    NULL AS gateway_status,
    NULL AS gateway_error_code,
    NULL AS risk_score,
    NULL AS three_ds_outcome,
    NULL AS gateway_reference,
    NULL AS gateway_response,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'PM2',
    'O2',
    'wallet',
    5000,
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
    NULL,
    NULL
),

__ref__int_orders_usd AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    NULL AS region_code,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS amount,
    NULL AS amount_usd,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS rate_age_days,
    NULL AS is_rate_stale,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS basket_size
  UNION ALL
  SELECT
    'O2',
    'C1',
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
    '2026-02-01'::DATE AS rate_date,
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
),

__expected__int_chargeback_exposure AS (
  SELECT
    'CB1' AS chargeback_id,
    'C1' AS customer_id,
    '2026-02-21'::DATE AS response_due_on,
    110.0::DECIMAL(18, 2) AS amount_usd,
    1.0::DECIMAL(9, 6) AS share_of_payment,
    TRUE AS has_delivery_proof,
    58 AS days_open,
    TRUE AS is_overdue,
    110.0::DECIMAL(18, 2) AS at_risk_usd,
    0 AS prior_chargebacks_for_customer
  UNION ALL
  SELECT
    'CB2' AS chargeback_id,
    'C1' AS customer_id,
    '2026-04-10'::DATE AS response_due_on,
    27.5::DECIMAL(18, 2) AS amount_usd,
    0.5::DECIMAL(9, 6) AS share_of_payment,
    FALSE AS has_delivery_proof,
    9 AS days_open,
    FALSE AS is_overdue,
    0.0::DECIMAL(18, 2) AS at_risk_usd,
    1 AS prior_chargebacks_for_customer
  UNION ALL
  SELECT
    'CB3' AS chargeback_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    '2026-04-24'::DATE AS response_due_on,
    3.25::DECIMAL(18, 2) AS amount_usd,
    CAST(NULL AS DECIMAL(9, 6)) AS share_of_payment,
    FALSE AS has_delivery_proof,
    6 AS days_open,
    FALSE AS is_overdue,
    3.25::DECIMAL(18, 2) AS at_risk_usd,
    0 AS prior_chargebacks_for_customer
),

__assert__evidence_kinds_are_distinct_and_lower_cased AS (
  SELECT c.chargeback_id
  FROM __ref("int_chargeback_exposure") AS c
  WHERE
    ARRAY_TO_STRING(c.evidence_kinds, ',') <> IFF(c.chargeback_id = 'CB1', 'invoice,tracking', '')
)
