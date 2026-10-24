TEST (name "rpt_payout_reconciliation_status__tracks_unreconciled_payout_value_by_month");

WITH __ref__int_payout_reconciliation AS (
  SELECT
    'PO1' AS payout_id,
    'PSP1' AS provider_code,
    NULL AS currency_code,
    '2026-03-02'::DATE AS paid_out_on,
    1000 AS payout_net_minor,
    NULL AS lines_net_minor,
    NULL AS charge_line_count,
    NULL AS refund_line_count,
    0 AS orphan_line_count,
    NULL AS embedded_line_count,
    NULL AS loaded_line_count,
    NULL AS matched_payment_minor,
    NULL AS report_id,
    NULL AS report_net_minor,
    NULL AS lines_match_payout,
    NULL AS report_matches_payout,
    'reconciled' AS reconciliation_status,
    NULL AS days_since_previous_payout
  UNION ALL
  SELECT
    'PO2',
    'PSP1',
    NULL,
    '2026-03-15'::DATE,
    500,
    NULL,
    NULL,
    NULL,
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'awaiting_report',
    NULL
  UNION ALL
  SELECT
    'PO3',
    'PSP1',
    NULL,
    '2026-03-28'::DATE,
    200,
    NULL,
    NULL,
    NULL,
    2,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'line_mismatch',
    NULL
  UNION ALL
  SELECT
    'PO4',
    'PSP1',
    NULL,
    '2026-04-01'::DATE,
    300,
    NULL,
    NULL,
    NULL,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'report_mismatch',
    NULL
),

__expected__rpt_payout_reconciliation_status AS (
  SELECT
    'PSP1:2026-03' AS payout_status_key,
    3 AS payouts,
    1 AS reconciled,
    1 AS awaiting_report,
    1 AS mismatched,
    3 AS orphan_lines,
    700 AS unreconciled_net_minor,
    0.3333::DECIMAL(9, 4) AS reconciled_share
  UNION ALL
  SELECT
    'PSP1:2026-04' AS payout_status_key,
    1 AS payouts,
    0 AS reconciled,
    0 AS awaiting_report,
    1 AS mismatched,
    0 AS orphan_lines,
    300 AS unreconciled_net_minor,
    0.0::DECIMAL(9, 4) AS reconciled_share
),

__assert__payout_status_key_is_unique_and_present AS (
  SELECT t.payout_status_key
  FROM __ref("rpt_payout_reconciliation_status") AS t
  GROUP BY
    t.payout_status_key
  HAVING
    COUNT(*) > 1
    OR t.payout_status_key IS NULL
)
