TEST (name "rpt_experiment_results__computes_lift_and_z_score_against_control");

WITH __ref__int_experiment_exposures AS (
  SELECT
    'EA1' AS assignment_id,
    'golden-duck-banner' AS experiment_key,
    'control' AS variant_key,
    TRUE AS is_control,
    'A1' AS anonymous_id,
    NULL AS assigned_at_utc,
    NULL AS sessions_after,
    TRUE AS converted,
    1::DECIMAL(10, 2) AS days_to_convert,
    NULL AS assignment_surface
  UNION ALL
  SELECT
    'EA2',
    'golden-duck-banner',
    'control',
    TRUE,
    'A2',
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'EA3',
    'golden-duck-banner',
    'control',
    TRUE,
    'A3',
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'EA4',
    'golden-duck-banner',
    'control',
    TRUE,
    'A4',
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'EA5',
    'golden-duck-banner',
    'banner',
    FALSE,
    'A5',
    NULL,
    NULL,
    TRUE,
    2::DECIMAL(10, 2),
    NULL
  UNION ALL
  SELECT
    'EA6',
    'golden-duck-banner',
    'banner',
    FALSE,
    'A6',
    NULL,
    NULL,
    TRUE,
    4::DECIMAL(10, 2),
    NULL
  UNION ALL
  SELECT
    'EA7',
    'golden-duck-banner',
    'banner',
    FALSE,
    'A7',
    NULL,
    NULL,
    TRUE,
    6::DECIMAL(10, 2),
    NULL
  UNION ALL
  SELECT
    'EA8',
    'golden-duck-banner',
    'banner',
    FALSE,
    'A8',
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'EA9',
    'pond-week-copy',
    'short',
    FALSE,
    'A9',
    NULL,
    NULL,
    TRUE,
    3::DECIMAL(10, 2),
    NULL
  UNION ALL
  SELECT
    'EA10',
    'pond-week-copy',
    'short',
    FALSE,
    'A10',
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL
),

__expected__rpt_experiment_results AS (
  SELECT
    'golden-duck-banner:control' AS experiment_variant_key,
    4 AS exposed,
    1 AS converted,
    0.25::DECIMAL(9, 6) AS conversion_rate,
    0.0::DECIMAL(9, 6) AS lift_vs_control,
    0.0::DECIMAL(9, 4) AS z_score,
    1.0::DECIMAL(10, 2) AS median_days_to_convert
  UNION ALL
  SELECT
    'golden-duck-banner:banner' AS experiment_variant_key,
    4 AS exposed,
    3 AS converted,
    0.75::DECIMAL(9, 6) AS conversion_rate,
    0.5::DECIMAL(9, 6) AS lift_vs_control,
    1.4142::DECIMAL(9, 4) AS z_score,
    4.0::DECIMAL(10, 2) AS median_days_to_convert
  UNION ALL
  SELECT
    'pond-week-copy:short' AS experiment_variant_key,
    2 AS exposed,
    1 AS converted,
    0.5::DECIMAL(9, 6) AS conversion_rate,
    CAST(NULL AS DECIMAL(9, 6)) AS lift_vs_control,
    CAST(NULL AS DECIMAL(9, 4)) AS z_score,
    3.0::DECIMAL(10, 2) AS median_days_to_convert
),

__assert__experiment_variant_key_is_unique_and_present AS (
  SELECT t.experiment_variant_key
  FROM __ref("rpt_experiment_results") AS t
  GROUP BY
    t.experiment_variant_key
  HAVING
    COUNT(*) > 1
    OR t.experiment_variant_key IS NULL
)
