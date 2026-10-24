TEST (mode udf, name "luhn_valid__checks_card_number_checksums");

WITH input_values AS (
  SELECT
    v.digits
  FROM VALUES
    ('79927398713'),
    ('79927398710'),
    ('4629173058461920'),
    ('4000-0566'),
    ('') AS v(digits)
),

__udf_actual__ AS (
  SELECT
    i.digits,
    __udf("luhn_valid")(i.digits) AS is_valid
  FROM input_values AS i
),

__udf_expected__ AS (
  SELECT
    v.digits::VARCHAR AS digits,
    v.is_valid::BOOLEAN AS is_valid
  FROM VALUES
    ('79927398713', TRUE),
    ('79927398710', FALSE),
    ('4629173058461920', TRUE),
    ('4000-0566', NULL),
    ('', NULL) AS v(digits, is_valid)
)
