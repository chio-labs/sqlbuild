TEST (name "int_settlement_lines__matches_lines_by_structured_or_described_reference");

WITH __ref__stg_settlement_reports AS (
  SELECT
    'SR1' AS report_id,
    'PAYCO' AS provider_code,
    '2026-03-10'::DATE AS report_date,
    NULL AS currency_code,
    NULL AS gross_minor,
    NULL AS fees_minor,
    NULL AS line_count,
    OBJECT_CONSTRUCT(
      'lines',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
          'type',
          'Charge',
          'reference',
          '771001',
          'gross_minor',
          10000,
          'fee_minor',
          290
        ),
        OBJECT_CONSTRUCT(
          'record_type',
          'refund',
          'description',
          'Refund for pi_XYZ7890 order',
          'gross',
          '-25.50'
        ),
        OBJECT_CONSTRUCT(
          'reference',
          '  ',
          'description',
          'adjustment',
          'gross_minor',
          100
        ),
        OBJECT_CONSTRUCT(
          'type',
          'refund',
          'reference',
          'RF1',
          'gross_minor',
          -500,
          'fee_minor',
          0
        )
      )
    )::VARIANT AS report
  UNION ALL
  SELECT
    'SR2',
    'PAYCO',
    '2026-03-11'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('{}')::VARIANT
),

__ref__stg_payments AS (
  SELECT
    'PM1' AS payment_id,
    NULL AS order_id,
    NULL AS payment_method,
    10000 AS amount_minor,
    NULL AS currency_code,
    NULL AS authorised_at,
    NULL AS captured_at,
    NULL AS card_bin,
    NULL AS gateway_status,
    NULL AS gateway_error_code,
    NULL AS risk_score,
    NULL AS three_ds_outcome,
    771001 AS gateway_reference,
    NULL AS gateway_response,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_refunds AS (
  SELECT
    'RF1' AS refund_id,
    NULL AS payment_id,
    500 AS amount_minor,
    NULL AS reason_text,
    NULL AS reason_category,
    NULL AS refunded_at,
    NULL AS initiated_by,
    NULL AS refunded_line_count,
    NULL AS refunded_items,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_settlement_lines AS (
  SELECT
    'SR1:00000' AS settlement_line_key,
    1 AS line_number,
    'charge' AS line_type,
    '771001' AS payment_reference,
    'structured' AS reference_source,
    10000 AS gross_minor,
    290 AS fee_minor,
    9710 AS net_minor,
    'PM1' AS matched_payment_id,
    CAST(NULL AS VARCHAR) AS matched_refund_id,
    TRUE AS is_matched,
    TRUE AS amount_matches,
    0.029::DECIMAL(9, 6) AS fee_rate
  UNION ALL
  SELECT
    'SR1:00001' AS settlement_line_key,
    2 AS line_number,
    'refund' AS line_type,
    'pi_XYZ7890' AS payment_reference,
    'description' AS reference_source,
    -2550 AS gross_minor,
    0 AS fee_minor,
    -2550 AS net_minor,
    CAST(NULL AS VARCHAR) AS matched_payment_id,
    CAST(NULL AS VARCHAR) AS matched_refund_id,
    FALSE AS is_matched,
    FALSE AS amount_matches,
    0.0::DECIMAL(9, 6) AS fee_rate
  UNION ALL
  SELECT
    'SR1:00002' AS settlement_line_key,
    3 AS line_number,
    'unknown' AS line_type,
    CAST(NULL AS VARCHAR) AS payment_reference,
    'none' AS reference_source,
    100 AS gross_minor,
    0 AS fee_minor,
    100 AS net_minor,
    CAST(NULL AS VARCHAR) AS matched_payment_id,
    CAST(NULL AS VARCHAR) AS matched_refund_id,
    FALSE AS is_matched,
    FALSE AS amount_matches,
    0.0::DECIMAL(9, 6) AS fee_rate
  UNION ALL
  SELECT
    'SR1:00003' AS settlement_line_key,
    4 AS line_number,
    'refund' AS line_type,
    'RF1' AS payment_reference,
    'structured' AS reference_source,
    -500 AS gross_minor,
    0 AS fee_minor,
    -500 AS net_minor,
    CAST(NULL AS VARCHAR) AS matched_payment_id,
    'RF1' AS matched_refund_id,
    TRUE AS is_matched,
    TRUE AS amount_matches,
    0.0::DECIMAL(9, 6) AS fee_rate
)
