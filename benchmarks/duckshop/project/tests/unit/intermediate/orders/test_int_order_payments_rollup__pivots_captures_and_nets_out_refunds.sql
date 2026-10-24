TEST (name "int_order_payments_rollup__pivots_captures_and_nets_out_refunds");

WITH __ref__int_payment_attempts AS (
  SELECT
    'P1' AS payment_id,
    'O1' AS order_id,
    NULL AS attempt_number,
    NULL AS attempt_count,
    NULL AS is_final_attempt,
    'card' AS payment_method,
    3000 AS amount_minor,
    NULL AS currency_code,
    NULL AS authorised_at,
    NULL AS seconds_since_previous_attempt,
    NULL AS gateway_status,
    TRUE AS is_successful,
    NULL AS decline_family,
    NULL AS gateway_error_code,
    NULL AS risk_score,
    NULL AS risk_band,
    NULL AS three_ds_outcome,
    NULL AS card_bin_valid,
    NULL AS card_scheme,
    NULL AS had_chargeback
  UNION ALL
  SELECT
    'P2',
    'O1',
    NULL,
    NULL,
    NULL,
    'phone_wallet',
    1000,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
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
    'P3',
    'O1',
    NULL,
    NULL,
    NULL,
    'card',
    3000,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
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
    'P4',
    'O2',
    NULL,
    NULL,
    NULL,
    'voucher',
    700,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_refunds AS (
  SELECT
    'RF1' AS refund_id,
    'P1' AS payment_id,
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

__ref__stg_chargebacks AS (
  SELECT
    'CB1' AS chargeback_id,
    'P2' AS payment_id,
    1000 AS amount_minor,
    NULL AS currency_code,
    NULL AS reason_code,
    NULL AS reason_family,
    NULL AS opened_at,
    NULL AS closed_at,
    'lost' AS outcome,
    NULL AS evidence_document_count,
    NULL AS evidence,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CB2',
    'P4',
    700,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'won',
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_gift_card_transactions AS (
  SELECT
    'G1' AS transaction_id,
    'GC1' AS gift_card_id,
    'O2' AS order_id,
    'REDEEM' AS transaction_type,
    -300 AS signed_amount_minor,
    NULL AS occurred_at,
    NULL AS channel,
    NULL AS terminal_id,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_order_payments_rollup AS (
  SELECT
    'O1' AS order_id,
    3000 AS card_captured_minor,
    1000 AS wallet_captured_minor,
    0 AS other_captured_minor,
    4000 AS captured_minor,
    500 AS refunded_minor,
    1000 AS chargeback_minor,
    2500 AS net_collected_minor,
    1 AS failed_attempts
  UNION ALL
  SELECT
    'O2' AS order_id,
    0 AS card_captured_minor,
    0 AS wallet_captured_minor,
    700 AS other_captured_minor,
    700 AS captured_minor,
    0 AS refunded_minor,
    0 AS chargeback_minor,
    1000 AS net_collected_minor,
    0 AS failed_attempts
),

__assert__tender_methods_are_distinct_and_sorted AS (
  SELECT r.order_id
  FROM __ref("int_order_payments_rollup") AS r
  WHERE
    r.order_id = 'O1'
    AND ARRAY_TO_STRING(r.tender_methods, ',') <> 'card,phone_wallet'
)
