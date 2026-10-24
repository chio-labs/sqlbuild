TEST (mode macro, name "round_half_even__rounds_ties_to_even");

WITH cases AS (
  SELECT
    v.case_name,
    v.amount::NUMBER(10, 3) AS amount
  FROM VALUES
    ('tie_down', 2.345),
    ('tie_up', 2.355),
    ('not_a_tie', 2.346) AS v(case_name, amount)
),

__macro_actual__ AS (
  SELECT
    c.case_name,
    @py.round_half_even("c.amount", 2) AS rounded
  FROM cases AS c
),

__macro_expected__ AS (
  SELECT
    v.case_name,
    v.rounded::NUMBER(10, 2) AS rounded
  FROM VALUES ('tie_down', 2.34), ('tie_up', 2.36), ('not_a_tie', 2.35) AS v(case_name, rounded)
)
