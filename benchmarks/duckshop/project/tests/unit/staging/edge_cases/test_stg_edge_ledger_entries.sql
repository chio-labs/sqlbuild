TEST (name "stg_edge_ledger_entries__reads_quantity_text_in_every_number_spelling");

WITH __source__edge__ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    NULL AS channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    NULL AS quantity,
    v.quantity_text,
    NULL AS unit_price_minor,
    NULL AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    NULL AS status,
    NULL AS reason_code,
    NULL AS customer_tier,
    NULL AS changed_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('LE-01', '007'),
    ('LE-02', '+7'),
    ('LE-03', '1e0'),
    ('LE-04', ' 1.5 '),
    ('LE-05', '-0'),
    ('LE-06', '1,000'),
    ('LE-07', 'n/a'),
    ('LE-08', ''),
    ('LE-09', '1.005'),
    ('LE-10', '2.5'),
    ('LE-11', '\u0661\u0662'),
    ('LE-12', '0x1F'),
    ('LE-13', '1_000'),
    ('LE-14', '.5'),
    ('LE-15', '5.'),
    ('LE-16', '1234567890123456.789') AS v(entry_id, quantity_text)
),

__expected__stg_edge_ledger_entries AS (
  SELECT
    'LE-01' AS entry_id,
    7.00::NUMBER(18, 2) AS quantity_from_text,
    7 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-02' AS entry_id,
    7.00::NUMBER(18, 2) AS quantity_from_text,
    7 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-03' AS entry_id,
    1.00::NUMBER(18, 2) AS quantity_from_text,
    1 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-04' AS entry_id,
    1.50::NUMBER(18, 2) AS quantity_from_text,
    2 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-05' AS entry_id,
    0.00::NUMBER(18, 2) AS quantity_from_text,
    0 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-06' AS entry_id,
    CAST(NULL AS NUMBER(18, 2)) AS quantity_from_text,
    CAST(NULL AS NUMBER(18, 0)) AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-07' AS entry_id,
    CAST(NULL AS NUMBER(18, 2)) AS quantity_from_text,
    CAST(NULL AS NUMBER(18, 0)) AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-08' AS entry_id,
    CAST(NULL AS NUMBER(18, 2)) AS quantity_from_text,
    CAST(NULL AS NUMBER(18, 0)) AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-09' AS entry_id,
    1.01::NUMBER(18, 2) AS quantity_from_text,
    1 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-10' AS entry_id,
    2.50::NUMBER(18, 2) AS quantity_from_text,
    3 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-11' AS entry_id,
    CAST(NULL AS NUMBER(18, 2)) AS quantity_from_text,
    CAST(NULL AS NUMBER(18, 0)) AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-12' AS entry_id,
    CAST(NULL AS NUMBER(18, 2)) AS quantity_from_text,
    CAST(NULL AS NUMBER(18, 0)) AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-13' AS entry_id,
    CAST(NULL AS NUMBER(18, 2)) AS quantity_from_text,
    CAST(NULL AS NUMBER(18, 0)) AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-14' AS entry_id,
    0.50::NUMBER(18, 2) AS quantity_from_text,
    1 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-15' AS entry_id,
    5.00::NUMBER(18, 2) AS quantity_from_text,
    5 AS quantity_text_decimal
  UNION ALL
  SELECT
    'LE-16' AS entry_id,
    1234567890123456.79::NUMBER(18, 2) AS quantity_from_text,
    1234567890123457 AS quantity_text_decimal
)

TEST (name "stg_edge_ledger_entries__keeps_38_digit_amounts_exact");

WITH __source__edge__ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    NULL AS channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    NULL AS quantity,
    NULL AS quantity_text,
    NULL AS unit_price_minor,
    v.amount::NUMBER(38, 10) AS amount,
    NULL AS currency_code,
    NULL AS fx_rate,
    NULL AS status,
    NULL AS reason_code,
    NULL AS customer_tier,
    NULL AS changed_at,
    '2026-03-05 00:00:00'::TIMESTAMP_NTZ AS _loaded_at
  FROM VALUES
    ('LE-01', '9999999999999999999999999999.9999999999'),
    ('LE-02', '1234567890123456789012345678.0123456789'),
    ('LE-03', '-9999999999999999999999999999.9999999999'),
    ('LE-04', '0.0000000001'),
    ('LE-05', '9007199254740993.0000000001') AS v(entry_id, amount)
),

__expected__stg_edge_ledger_entries AS (
  SELECT
    'LE-01' AS entry_id,
    9999999999999999999999999999.9999999999::NUMBER(38, 10) AS amount
  UNION ALL
  SELECT
    'LE-02' AS entry_id,
    1234567890123456789012345678.0123456789::NUMBER(38, 10) AS amount
  UNION ALL
  SELECT
    'LE-03' AS entry_id,
    -9999999999999999999999999999.9999999999::NUMBER(38, 10) AS amount
  UNION ALL
  SELECT
    'LE-04' AS entry_id,
    0.0000000001::NUMBER(38, 10) AS amount
  UNION ALL
  SELECT
    'LE-05' AS entry_id,
    9007199254740993.0000000001::NUMBER(38, 10) AS amount
)
