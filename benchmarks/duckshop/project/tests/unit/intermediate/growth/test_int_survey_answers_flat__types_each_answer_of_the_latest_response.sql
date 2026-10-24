TEST (name "int_survey_answers_flat__types_each_answer_of_the_latest_response");

WITH __ref__stg_survey_responses AS (
  SELECT
    'SR0' AS response_id,
    'post_purchase' AS survey_code,
    'C1' AS customer_id,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMP_TZ AS submitted_at,
    3 AS nps_score,
    NULL AS answer_count,
    PARSE_JSON('{"q1": "old"}')::OBJECT AS answers,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'SR1',
    'post_purchase',
    'C1',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    9,
    NULL,
    OBJECT_CONSTRUCT_KEEP_NULL(
      'Overall Rating',
      4,
      'Would Recommend?',
      TRUE,
      'Comments',
      'Great   service',
      'Features',
      ARRAY_CONSTRUCT('fast', 'cheap'),
      'Skip',
      NULL,
      'Price',
      '12.50'
    )::OBJECT,
    NULL,
    NULL
  UNION ALL
  SELECT
    'SR2',
    'post_purchase',
    'C2',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    6,
    NULL,
    PARSE_JSON('{"q1": "no"}')::OBJECT,
    NULL,
    NULL
),

__expected__int_survey_answers_flat AS (
  SELECT
    'SR1:comments' AS answer_key,
    'text' AS answer_kind,
    CAST(NULL AS DECIMAL(18, 4)) AS answer_number,
    CAST(NULL AS BOOLEAN) AS answer_flag,
    'Great service' AS answer_text,
    TRUE AS is_answered,
    'promoter' AS nps_group,
    1 AS question_position
  UNION ALL
  SELECT
    'SR1:features' AS answer_key,
    'choices' AS answer_kind,
    CAST(NULL AS DECIMAL(18, 4)) AS answer_number,
    CAST(NULL AS BOOLEAN) AS answer_flag,
    CAST(NULL AS VARCHAR) AS answer_text,
    TRUE AS is_answered,
    'promoter' AS nps_group,
    2 AS question_position
  UNION ALL
  SELECT
    'SR1:overall_rating' AS answer_key,
    'number' AS answer_kind,
    4.0::DECIMAL(18, 4) AS answer_number,
    CAST(NULL AS BOOLEAN) AS answer_flag,
    CAST(NULL AS VARCHAR) AS answer_text,
    TRUE AS is_answered,
    'promoter' AS nps_group,
    3 AS question_position
  UNION ALL
  SELECT
    'SR1:price' AS answer_key,
    'number' AS answer_kind,
    12.5::DECIMAL(18, 4) AS answer_number,
    CAST(NULL AS BOOLEAN) AS answer_flag,
    CAST(NULL AS VARCHAR) AS answer_text,
    TRUE AS is_answered,
    'promoter' AS nps_group,
    4 AS question_position
  UNION ALL
  SELECT
    'SR1:skip' AS answer_key,
    'null' AS answer_kind,
    CAST(NULL AS DECIMAL(18, 4)) AS answer_number,
    CAST(NULL AS BOOLEAN) AS answer_flag,
    CAST(NULL AS VARCHAR) AS answer_text,
    FALSE AS is_answered,
    'promoter' AS nps_group,
    5 AS question_position
  UNION ALL
  SELECT
    'SR1:would_recommend_' AS answer_key,
    'flag' AS answer_kind,
    CAST(NULL AS DECIMAL(18, 4)) AS answer_number,
    TRUE AS answer_flag,
    CAST(NULL AS VARCHAR) AS answer_text,
    TRUE AS is_answered,
    'promoter' AS nps_group,
    6 AS question_position
  UNION ALL
  SELECT
    'SR2:q1' AS answer_key,
    'text' AS answer_kind,
    CAST(NULL AS DECIMAL(18, 4)) AS answer_number,
    CAST(NULL AS BOOLEAN) AS answer_flag,
    'no' AS answer_text,
    TRUE AS is_answered,
    'detractor' AS nps_group,
    1 AS question_position
),

__assert__choices_keep_array_order AS (
  SELECT a.answer_key
  FROM __ref("int_survey_answers_flat") AS a
  WHERE
    a.answer_kind = 'choices'
    AND ARRAY_TO_STRING(a.answer_choices, ',') <> 'fast,cheap'
)
