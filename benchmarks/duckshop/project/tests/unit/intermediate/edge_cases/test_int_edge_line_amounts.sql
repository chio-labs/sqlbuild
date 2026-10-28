TEST (name "int_edge_line_amounts__divides_rounds_and_buckets_money_at_its_edges");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    NULL AS channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    v.amount::NUMBER(38, 10) AS amount,
    NULL AS currency_code,
    v.fx_rate::FLOAT AS fx_rate
  FROM VALUES
    ('LE-01', 3, 1299, '2.5', '1.27'),
    ('LE-02', 3, 1299, '-2.5', '1.27'),
    ('LE-03', 2, 899, '0.005', '0.1'),
    ('LE-04', 0, 1350, '1.0000000005', '3.25'),
    ('LE-05', -4, 205, '-7.5', '0.0067'),
    ('LE-06', NULL, 1005, '0.015', '1.005'),
    ('LE-07', 7, 1, '-0.0000000001', '0.3'),
    ('LE-08', 3, 100, '1', '-1.5') AS v(entry_id, quantity, unit_price_minor, amount, fx_rate)
),

__expected__int_edge_line_amounts AS (
  SELECT
    'LE-01' AS entry_id,
    0.8333333333::NUMBER(38, 10) AS unit_amount,
    0.8333333333::NUMBER(38, 10) AS share_of_three,
    0.8333333333::NUMBER(38, 10) AS unit_amount_div0,
    0.8333333333::NUMBER(38, 10) AS unit_amount_nullifzero,
    2.50::NUMBER(38, 2) AS amount_rounded,
    3 AS amount_rounded_whole,
    '3.0'::FLOAT AS amount_float_rounded,
    '1649.73'::FLOAT AS converted_minor,
    1649.73::NUMBER(18, 2) AS converted_2dp,
    1649.730000::NUMBER(18, 6) AS converted_6dp,
    1649.73::NUMBER(18, 2) AS converted_rounded,
    2.5000000000::NUMBER(38, 10) AS line_bucket,
    '0.27'::FLOAT AS rate_bucket,
    1.2500000000::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-02' AS entry_id,
    -0.8333333333::NUMBER(38, 10) AS unit_amount,
    -0.8333333333::NUMBER(38, 10) AS share_of_three,
    -0.8333333333::NUMBER(38, 10) AS unit_amount_div0,
    -0.8333333333::NUMBER(38, 10) AS unit_amount_nullifzero,
    -2.50::NUMBER(38, 2) AS amount_rounded,
    -3 AS amount_rounded_whole,
    '-3.0'::FLOAT AS amount_float_rounded,
    '1649.73'::FLOAT AS converted_minor,
    1649.73::NUMBER(18, 2) AS converted_2dp,
    1649.730000::NUMBER(18, 6) AS converted_6dp,
    1649.73::NUMBER(18, 2) AS converted_rounded,
    -2.5000000000::NUMBER(38, 10) AS line_bucket,
    '0.27'::FLOAT AS rate_bucket,
    -1.2500000000::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-03' AS entry_id,
    0.0025000000::NUMBER(38, 10) AS unit_amount,
    0.0016666667::NUMBER(38, 10) AS share_of_three,
    0.0025000000::NUMBER(38, 10) AS unit_amount_div0,
    0.0025000000::NUMBER(38, 10) AS unit_amount_nullifzero,
    0.01::NUMBER(38, 2) AS amount_rounded,
    0 AS amount_rounded_whole,
    '0.0'::FLOAT AS amount_float_rounded,
    '89.9'::FLOAT AS converted_minor,
    89.90::NUMBER(18, 2) AS converted_2dp,
    89.900000::NUMBER(18, 6) AS converted_6dp,
    89.90::NUMBER(18, 2) AS converted_rounded,
    0.0050000000::NUMBER(38, 10) AS line_bucket,
    '0.1'::FLOAT AS rate_bucket,
    0.0025000000::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-04' AS entry_id,
    CAST(NULL AS NUMBER(38, 10)) AS unit_amount,
    0.3333333335::NUMBER(38, 10) AS share_of_three,
    0.0000000000::NUMBER(38, 10) AS unit_amount_div0,
    CAST(NULL AS NUMBER(38, 10)) AS unit_amount_nullifzero,
    1.00::NUMBER(38, 2) AS amount_rounded,
    1 AS amount_rounded_whole,
    '1.0'::FLOAT AS amount_float_rounded,
    '4387.5'::FLOAT AS converted_minor,
    4387.50::NUMBER(18, 2) AS converted_2dp,
    4387.500000::NUMBER(18, 6) AS converted_6dp,
    4387.50::NUMBER(18, 2) AS converted_rounded,
    1.0000000005::NUMBER(38, 10) AS line_bucket,
    '0.25'::FLOAT AS rate_bucket,
    0.5000000003::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-05' AS entry_id,
    1.8750000000::NUMBER(38, 10) AS unit_amount,
    -2.5000000000::NUMBER(38, 10) AS share_of_three,
    1.8750000000::NUMBER(38, 10) AS unit_amount_div0,
    1.8750000000::NUMBER(38, 10) AS unit_amount_nullifzero,
    -7.50::NUMBER(38, 2) AS amount_rounded,
    -8 AS amount_rounded_whole,
    '-8.0'::FLOAT AS amount_float_rounded,
    '1.3735'::FLOAT AS converted_minor,
    1.37::NUMBER(18, 2) AS converted_2dp,
    1.373500::NUMBER(18, 6) AS converted_6dp,
    1.37::NUMBER(18, 2) AS converted_rounded,
    -0.5000000000::NUMBER(38, 10) AS line_bucket,
    '0.0067'::FLOAT AS rate_bucket,
    -3.7500000000::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-06' AS entry_id,
    CAST(NULL AS NUMBER(38, 10)) AS unit_amount,
    0.0050000000::NUMBER(38, 10) AS share_of_three,
    CAST(NULL AS NUMBER(38, 10)) AS unit_amount_div0,
    CAST(NULL AS NUMBER(38, 10)) AS unit_amount_nullifzero,
    0.02::NUMBER(38, 2) AS amount_rounded,
    0 AS amount_rounded_whole,
    '0.0'::FLOAT AS amount_float_rounded,
    '1010.0249999999999'::FLOAT AS converted_minor,
    1010.02::NUMBER(18, 2) AS converted_2dp,
    1010.025000::NUMBER(18, 6) AS converted_6dp,
    1010.02::NUMBER(18, 2) AS converted_rounded,
    0.0150000000::NUMBER(38, 10) AS line_bucket,
    '0.004999999999999893'::FLOAT AS rate_bucket,
    0.0075000000::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-07' AS entry_id,
    0.0000000000::NUMBER(38, 10) AS unit_amount,
    0.0000000000::NUMBER(38, 10) AS share_of_three,
    0.0000000000::NUMBER(38, 10) AS unit_amount_div0,
    0.0000000000::NUMBER(38, 10) AS unit_amount_nullifzero,
    0.00::NUMBER(38, 2) AS amount_rounded,
    0 AS amount_rounded_whole,
    '0.0'::FLOAT AS amount_float_rounded,
    '0.3'::FLOAT AS converted_minor,
    0.30::NUMBER(18, 2) AS converted_2dp,
    0.300000::NUMBER(18, 6) AS converted_6dp,
    0.30::NUMBER(18, 2) AS converted_rounded,
    -0.0000000001::NUMBER(38, 10) AS line_bucket,
    '0.3'::FLOAT AS rate_bucket,
    -0.0000000001::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-08' AS entry_id,
    0.3333333333::NUMBER(38, 10) AS unit_amount,
    0.3333333333::NUMBER(38, 10) AS share_of_three,
    0.3333333333::NUMBER(38, 10) AS unit_amount_div0,
    0.3333333333::NUMBER(38, 10) AS unit_amount_nullifzero,
    1.00::NUMBER(38, 2) AS amount_rounded,
    1 AS amount_rounded_whole,
    '1.0'::FLOAT AS amount_float_rounded,
    '-150.0'::FLOAT AS converted_minor,
    -150.00::NUMBER(18, 2) AS converted_2dp,
    -150.000000::NUMBER(18, 6) AS converted_6dp,
    -150.00::NUMBER(18, 2) AS converted_rounded,
    1.0000000000::NUMBER(38, 10) AS line_bucket,
    '0.0'::FLOAT AS rate_bucket,
    0.5000000000::NUMBER(38, 10) AS amount_halved
)

TEST (name "int_edge_line_amounts__divides_36_digit_amounts_exactly");

WITH __ref__stg_edge_ledger_entries AS (
  SELECT
    v.entry_id,
    NULL AS order_ref,
    NULL AS channel,
    NULL AS line_no,
    NULL AS sku,
    NULL AS warehouse_code,
    v.quantity::NUMBER(38, 0) AS quantity,
    NULL AS quantity_text,
    NULL AS quantity_from_text,
    NULL AS quantity_text_decimal,
    1 AS unit_price_minor,
    v.amount::NUMBER(38, 10) AS amount,
    NULL AS currency_code,
    1.0::FLOAT AS fx_rate
  FROM VALUES
    ('LE-01', 3, '99999999999999999999999999.9999999999'),
    ('LE-02', 7, '12345678901234567890123456.0123456789'),
    ('LE-03', -3, '-99999999999999999999999999.9999999999'),
    ('LE-04', 1, '0.0000000001') AS v(entry_id, quantity, amount)
),

__expected__int_edge_line_amounts AS (
  SELECT
    'LE-01' AS entry_id,
    33333333333333333333333333.3333333333::NUMBER(38, 10) AS unit_amount,
    33333333333333333333333333.3333333333::NUMBER(38, 10) AS share_of_three,
    100000000000000000000000000.00::NUMBER(38, 2) AS amount_rounded,
    100000000000000000000000000 AS amount_rounded_whole,
    1.9999999999::NUMBER(38, 10) AS line_bucket,
    50000000000000000000000000.0000000000::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-02' AS entry_id,
    1763668414462081127160493.7160493827::NUMBER(38, 10) AS unit_amount,
    4115226300411522630041152.0041152263::NUMBER(38, 10) AS share_of_three,
    12345678901234567890123456.01::NUMBER(38, 2) AS amount_rounded,
    12345678901234567890123456 AS amount_rounded_whole,
    5.0123456789::NUMBER(38, 10) AS line_bucket,
    6172839450617283945061728.0061728395::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-03' AS entry_id,
    33333333333333333333333333.3333333333::NUMBER(38, 10) AS unit_amount,
    -33333333333333333333333333.3333333333::NUMBER(38, 10) AS share_of_three,
    -100000000000000000000000000.00::NUMBER(38, 2) AS amount_rounded,
    -100000000000000000000000000 AS amount_rounded_whole,
    -1.9999999999::NUMBER(38, 10) AS line_bucket,
    -50000000000000000000000000.0000000000::NUMBER(38, 10) AS amount_halved
  UNION ALL
  SELECT
    'LE-04' AS entry_id,
    0.0000000001::NUMBER(38, 10) AS unit_amount,
    0.0000000000::NUMBER(38, 10) AS share_of_three,
    0.00::NUMBER(38, 2) AS amount_rounded,
    0 AS amount_rounded_whole,
    0.0000000001::NUMBER(38, 10) AS line_bucket,
    0.0000000001::NUMBER(38, 10) AS amount_halved
)
