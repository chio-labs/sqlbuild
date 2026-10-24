TEST (name "udf__sku_family__extracts_leading_letters");

WITH input_values AS (
  SELECT
    v.sku
  FROM VALUES
    ('DUCK-MAL-01'),
    ('decoy-teal-1'),
    ('123-POND'),
    (NULL) AS v(sku)
),

__udf_actual__ AS (
  SELECT
    i.sku,
    __udf("udf__sku_family")(i.sku) AS sku_family
  FROM input_values AS i
),

__udf_expected__ AS (
  SELECT
    v.sku::VARCHAR AS sku,
    v.sku_family::VARCHAR AS sku_family
  FROM VALUES
    ('DUCK-MAL-01', 'DUCK'),
    ('decoy-teal-1', 'DECOY'),
    ('123-POND', NULL),
    (NULL, NULL) AS v(sku, sku_family)
)
