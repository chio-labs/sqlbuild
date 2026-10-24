TEST (mode macro, name "safe_divide__returns_null_for_zero_denominators");

WITH cases AS (
  SELECT
    v.case_name,
    v.numerator,
    v.denominator
  FROM VALUES
    ('exact', 10, 4),
    ('zero_denominator', 1, 0),
    ('null_denominator', 1, NULL) AS v(case_name, numerator, denominator)
),

__macro_actual__ AS (
  SELECT
    c.case_name,
    @sql.safe_divide(c.numerator, c.denominator) AS ratio
  FROM cases AS c
),

__macro_expected__ AS (
  SELECT
    v.case_name,
    v.ratio::NUMBER(38, 6) AS ratio
  FROM VALUES
    ('exact', 2.5),
    ('zero_denominator', NULL),
    ('null_denominator', NULL) AS v(case_name, ratio)
)
