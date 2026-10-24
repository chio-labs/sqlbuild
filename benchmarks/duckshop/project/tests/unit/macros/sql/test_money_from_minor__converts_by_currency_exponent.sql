TEST (mode macro, name "money_from_minor__converts_by_currency_exponent");

WITH cases AS (
  SELECT
    v.case_name,
    v.amount_minor,
    v.exponent
  FROM VALUES
    ('two_decimals', 1250, 2),
    ('three_decimals_rounded', 12345, 3),
    ('zero_decimals', 1000, 0),
    ('null_amount', NULL, 2) AS v(case_name, amount_minor, exponent)
),

__macro_actual__ AS (
  SELECT
    c.case_name,
    @sql.money_from_minor(c.amount_minor, c.exponent) AS amount
  FROM cases AS c
),

__macro_expected__ AS (
  SELECT
    v.case_name,
    v.amount::NUMBER(38, 6) AS amount
  FROM VALUES
    ('two_decimals', 12.5),
    ('three_decimals_rounded', 12.35),
    ('zero_decimals', 1000),
    ('null_amount', NULL) AS v(case_name, amount)
)
