TEST (name "int_payout_reconciliation__classifies_each_payout_against_lines_and_reports");

WITH __ref__stg_payouts AS (
  SELECT
    'PO1' AS payout_id,
    'PAYCO' AS provider_code,
    'EUR' AS currency_code,
    NULL AS amount_minor,
    NULL AS fee_minor,
    9400 AS net_minor,
    '2026-03-10'::DATE AS paid_out_on,
    PARSE_JSON('[{}, {}, {}]')::ARRAY AS lines,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'PO2',
    'PAYCO',
    'EUR',
    NULL,
    NULL,
    5000,
    '2026-03-12'::DATE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'PO3',
    'PAYCO',
    'EUR',
    NULL,
    NULL,
    1000,
    '2026-03-13'::DATE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'PO4',
    'PAYCO',
    'EUR',
    NULL,
    NULL,
    2000,
    '2026-03-14'::DATE,
    NULL,
    NULL,
    NULL
),

__ref__stg_payout_lines AS (
  SELECT
    'PO1#1' AS payout_line_key,
    'PO1' AS payout_id,
    'PM1' AS payment_id,
    'charge' AS line_type,
    10000 AS gross_minor,
    300 AS fee_minor
  UNION ALL
  SELECT
    'PO1#2',
    'PO1',
    'PM2',
    'refund',
    500,
    0
  UNION ALL
  SELECT
    'PO1#3',
    'PO1',
    'PM3',
    'charge',
    200,
    NULL
  UNION ALL
  SELECT
    'PO2#1',
    'PO2',
    'PM9',
    'charge',
    5000,
    0
  UNION ALL
  SELECT
    'PO3#1',
    'PO3',
    'PM4',
    'charge',
    1000,
    0
  UNION ALL
  SELECT
    'PO4#1',
    'PO4',
    'PM5',
    'charge',
    2000,
    0
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
    NULL AS gateway_reference,
    NULL AS gateway_response,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'PM2',
    NULL,
    NULL,
    500,
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
  UNION ALL
  SELECT
    'PM3',
    NULL,
    NULL,
    200,
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
  UNION ALL
  SELECT
    'PM4',
    NULL,
    NULL,
    1000,
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
  UNION ALL
  SELECT
    'PM5',
    NULL,
    NULL,
    2000,
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

__ref__stg_settlement_reports AS (
  SELECT
    'R1' AS report_id,
    'PAYCO' AS provider_code,
    '2026-03-10'::DATE AS report_date,
    'EUR' AS currency_code,
    9700 AS gross_minor,
    300 AS fees_minor,
    3 AS line_count,
    NULL AS report
  UNION ALL
  SELECT
    'R1B',
    'PAYCO',
    '2026-03-10'::DATE,
    'EUR',
    0,
    0,
    1,
    NULL
  UNION ALL
  SELECT
    'R2',
    'PAYCO',
    '2026-03-12'::DATE,
    'EUR',
    5000,
    0,
    1,
    NULL
  UNION ALL
  SELECT
    'R4',
    'PAYCO',
    '2026-03-14'::DATE,
    'EUR',
    2100,
    NULL,
    1,
    NULL
),

__expected__int_payout_reconciliation AS (
  SELECT
    'PO1' AS payout_id,
    9400 AS lines_net_minor,
    2 AS charge_line_count,
    1 AS refund_line_count,
    0 AS orphan_line_count,
    3 AS embedded_line_count,
    3 AS loaded_line_count,
    10200 AS matched_payment_minor,
    'R1' AS report_id,
    9400 AS report_net_minor,
    TRUE AS lines_match_payout,
    TRUE AS report_matches_payout,
    'reconciled' AS reconciliation_status,
    CAST(NULL AS INT) AS days_since_previous_payout
  UNION ALL
  SELECT
    'PO2' AS payout_id,
    5000 AS lines_net_minor,
    1 AS charge_line_count,
    0 AS refund_line_count,
    1 AS orphan_line_count,
    0 AS embedded_line_count,
    1 AS loaded_line_count,
    0 AS matched_payment_minor,
    'R2' AS report_id,
    5000 AS report_net_minor,
    TRUE AS lines_match_payout,
    TRUE AS report_matches_payout,
    'orphan_lines' AS reconciliation_status,
    2 AS days_since_previous_payout
  UNION ALL
  SELECT
    'PO3' AS payout_id,
    1000 AS lines_net_minor,
    1 AS charge_line_count,
    0 AS refund_line_count,
    0 AS orphan_line_count,
    0 AS embedded_line_count,
    1 AS loaded_line_count,
    1000 AS matched_payment_minor,
    CAST(NULL AS VARCHAR) AS report_id,
    CAST(NULL AS INT) AS report_net_minor,
    TRUE AS lines_match_payout,
    FALSE AS report_matches_payout,
    'awaiting_report' AS reconciliation_status,
    1 AS days_since_previous_payout
  UNION ALL
  SELECT
    'PO4' AS payout_id,
    2000 AS lines_net_minor,
    1 AS charge_line_count,
    0 AS refund_line_count,
    0 AS orphan_line_count,
    0 AS embedded_line_count,
    1 AS loaded_line_count,
    2000 AS matched_payment_minor,
    'R4' AS report_id,
    2100 AS report_net_minor,
    TRUE AS lines_match_payout,
    FALSE AS report_matches_payout,
    'report_mismatch' AS reconciliation_status,
    1 AS days_since_previous_payout
)
