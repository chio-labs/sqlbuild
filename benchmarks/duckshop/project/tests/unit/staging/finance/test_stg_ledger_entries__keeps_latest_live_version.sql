TEST (name "stg_ledger_entries__keeps_latest_live_version");

WITH __source__finance__ledger_entries AS (
  SELECT
    'K1' AS entry_id,
    NULL AS journal_code,
    NULL AS account_code,
    NULL AS debit_minor,
    NULL AS credit_minor,
    NULL AS currency_code,
    NULL AS posted_at,
    NULL AS reference,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_ledger_entries AS (
  SELECT
    'K1' AS entry_id,
    2 AS source_seq
)
