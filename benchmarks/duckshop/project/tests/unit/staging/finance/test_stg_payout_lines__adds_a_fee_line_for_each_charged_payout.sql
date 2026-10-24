TEST (name "stg_payout_lines__adds_a_fee_line_for_each_charged_payout");

WITH __ref__stg_payouts AS (
  SELECT
    'PO1' AS payout_id,
    NULL AS provider_code,
    NULL AS currency_code,
    NULL AS amount_minor,
    25 AS fee_minor,
    NULL AS net_minor,
    NULL AS paid_out_on,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'payment_id',
        'PM1',
        'gross_minor',
        1000,
        'fee_minor',
        30
      ),
      OBJECT_CONSTRUCT(
        'payment_id',
        'PM2',
        'type',
        'Refund',
        'gross_minor',
        200
      )
    )::ARRAY AS lines,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'PO2',
    NULL,
    NULL,
    NULL,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__stg_payout_lines AS (
  SELECT
    'PO1:0' AS payout_line_key,
    'PM1' AS payment_id,
    'charge' AS line_type,
    1000 AS gross_minor,
    30 AS fee_minor
  UNION ALL
  SELECT
    'PO1:1' AS payout_line_key,
    'PM2' AS payment_id,
    'refund' AS line_type,
    200 AS gross_minor,
    0 AS fee_minor
  UNION ALL
  SELECT
    'PO1:fee' AS payout_line_key,
    CAST(NULL AS VARCHAR) AS payment_id,
    'payout_fee' AS line_type,
    0 AS gross_minor,
    25 AS fee_minor
)
