TEST (name "int_payment_attempts__sequences_attempts_and_classifies_declines");

WITH __ref__stg_payments AS (
  SELECT
    'P1' AS payment_id,
    'O1' AS order_id,
    'card' AS payment_method,
    1000 AS amount_minor,
    NULL AS currency_code,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS authorised_at,
    NULL AS captured_at,
    '4876532091847355' AS card_bin,
    'declined' AS gateway_status,
    NULL AS gateway_error_code,
    80::DECIMAL(5, 2) AS risk_score,
    NULL AS three_ds_outcome,
    NULL AS gateway_reference,
    PARSE_JSON('{"status": {"message": "Insufficient funds"}}')::OBJECT AS gateway_response,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    'O1',
    'card',
    1000,
    NULL,
    '2026-03-01 10:00:45 +00:00'::TIMESTAMP_TZ,
    NULL,
    '5318462705936183',
    'captured',
    NULL,
    20::DECIMAL(5, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'P3',
    'O2',
    'wallet',
    500,
    NULL,
    '2026-03-02 09:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    'failed',
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('{"status": {"message": "Gateway error 503"}}')::OBJECT,
    NULL,
    NULL
),

__ref__stg_chargebacks AS (
  SELECT
    'CB1' AS chargeback_id,
    'P2' AS payment_id,
    NULL AS amount_minor,
    NULL AS currency_code,
    NULL AS reason_code,
    NULL AS reason_family,
    NULL AS opened_at,
    NULL AS closed_at,
    NULL AS outcome,
    NULL AS evidence_document_count,
    NULL AS evidence,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_payment_attempts AS (
  SELECT
    'P1' AS payment_id,
    1 AS attempt_number,
    2 AS attempt_count,
    FALSE AS is_final_attempt,
    CAST(NULL AS INT) AS seconds_since_previous_attempt,
    FALSE AS is_successful,
    'INSUFFICIENT_FUNDS' AS decline_family,
    'high' AS risk_band,
    'network_a' AS card_scheme,
    FALSE AS had_chargeback
  UNION ALL
  SELECT
    'P2' AS payment_id,
    2 AS attempt_number,
    2 AS attempt_count,
    TRUE AS is_final_attempt,
    45 AS seconds_since_previous_attempt,
    TRUE AS is_successful,
    'NONE' AS decline_family,
    'low' AS risk_band,
    'network_b' AS card_scheme,
    TRUE AS had_chargeback
  UNION ALL
  SELECT
    'P3' AS payment_id,
    1 AS attempt_number,
    1 AS attempt_count,
    TRUE AS is_final_attempt,
    CAST(NULL AS INT) AS seconds_since_previous_attempt,
    FALSE AS is_successful,
    'TECHNICAL' AS decline_family,
    'unscored' AS risk_band,
    CAST(NULL AS VARCHAR) AS card_scheme,
    FALSE AS had_chargeback
)
