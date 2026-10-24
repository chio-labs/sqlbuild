TEST (name "rpt_survey_nps_monthly__scores_nps_from_responses_with_a_rating");

WITH __ref__int_survey_answers_flat AS (
  SELECT
    'R1:nps' AS answer_key,
    'R1' AS response_id,
    'POST_PURCHASE' AS survey_code,
    NULL AS customer_id,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS submitted_at,
    'nps' AS question_key,
    'number' AS answer_kind,
    NULL AS answer_number,
    NULL AS answer_flag,
    NULL AS answer_text,
    NULL AS answer_choices,
    NULL AS is_answered,
    'promoter' AS nps_group,
    NULL AS question_position
  UNION ALL
  SELECT
    'R1:comment',
    'R1',
    'POST_PURCHASE',
    NULL,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ,
    'comment',
    'text',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R2:nps',
    'R2',
    'POST_PURCHASE',
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    'nps',
    'number',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'detractor',
    NULL
  UNION ALL
  SELECT
    'R3:comment',
    'R3',
    'POST_PURCHASE',
    NULL,
    '2026-03-12 10:00:00 +00:00'::TIMESTAMP_TZ,
    'comment',
    'text',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R5:nps',
    'R5',
    'POST_PURCHASE',
    NULL,
    '2026-03-15 10:00:00 +00:00'::TIMESTAMP_TZ,
    'nps',
    'number',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'promoter',
    NULL
  UNION ALL
  SELECT
    'R4:nps',
    'R4',
    'POST_PURCHASE',
    NULL,
    '2026-03-31 23:30:00 -02:00'::TIMESTAMP_TZ,
    'nps',
    'number',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'passive',
    NULL
),

__expected__rpt_survey_nps_monthly AS (
  SELECT
    'POST_PURCHASE:2026-03' AS nps_key,
    4 AS responses,
    2 AS promoters,
    0 AS passives,
    1 AS detractors,
    33.33::DECIMAL(6, 2) AS net_promoter_score,
    2 AS free_text_answers
  UNION ALL
  SELECT
    'POST_PURCHASE:2026-04' AS nps_key,
    1 AS responses,
    0 AS promoters,
    1 AS passives,
    0 AS detractors,
    0.0::DECIMAL(6, 2) AS net_promoter_score,
    0 AS free_text_answers
),

__assert__nps_key_is_unique_and_present AS (
  SELECT t.nps_key
  FROM __ref("rpt_survey_nps_monthly") AS t
  GROUP BY
    t.nps_key
  HAVING
    COUNT(*) > 1
    OR t.nps_key IS NULL
)
