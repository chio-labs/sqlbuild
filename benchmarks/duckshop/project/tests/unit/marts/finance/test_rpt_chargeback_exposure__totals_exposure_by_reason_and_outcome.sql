TEST (name "rpt_chargeback_exposure__totals_exposure_by_reason_and_outcome");

WITH __ref__int_chargeback_exposure AS (
  SELECT
    'CB1' AS chargeback_id,
    NULL AS payment_id,
    NULL AS order_id,
    NULL AS customer_id,
    NULL AS payment_method,
    NULL AS reason_code,
    'fraud' AS reason_family,
    NULL AS opened_at,
    NULL AS response_due_on,
    'open' AS outcome,
    50.0::DECIMAL(18, 2) AS amount_usd,
    NULL AS share_of_payment,
    NULL AS evidence_kinds,
    TRUE AS has_delivery_proof,
    NULL AS days_open,
    TRUE AS is_overdue,
    50.0::DECIMAL(18, 2) AS at_risk_usd,
    0 AS prior_chargebacks_for_customer
  UNION ALL
  SELECT
    'CB2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'fraud',
    NULL,
    NULL,
    'open',
    30.0::DECIMAL(18, 2),
    NULL,
    NULL,
    FALSE,
    NULL,
    FALSE,
    30.0::DECIMAL(18, 2),
    2
  UNION ALL
  SELECT
    'CB3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'service',
    NULL,
    NULL,
    'won',
    20.0::DECIMAL(18, 2),
    NULL,
    NULL,
    TRUE,
    NULL,
    FALSE,
    0.0::DECIMAL(18, 2),
    0
),

__expected__rpt_chargeback_exposure AS (
  SELECT
    'fraud:open' AS exposure_key,
    2 AS chargebacks,
    80.0::DECIMAL(18, 2) AS amount_usd,
    80.0::DECIMAL(18, 2) AS at_risk_usd,
    1 AS overdue_responses,
    1 AS with_delivery_proof,
    1 AS repeat_customer_chargebacks
  UNION ALL
  SELECT
    'service:won' AS exposure_key,
    1 AS chargebacks,
    20.0::DECIMAL(18, 2) AS amount_usd,
    0.0::DECIMAL(18, 2) AS at_risk_usd,
    0 AS overdue_responses,
    1 AS with_delivery_proof,
    0 AS repeat_customer_chargebacks
),

__assert__exposure_key_is_unique_and_present AS (
  SELECT t.exposure_key
  FROM __ref("rpt_chargeback_exposure") AS t
  GROUP BY
    t.exposure_key
  HAVING
    COUNT(*) > 1
    OR t.exposure_key IS NULL
)
