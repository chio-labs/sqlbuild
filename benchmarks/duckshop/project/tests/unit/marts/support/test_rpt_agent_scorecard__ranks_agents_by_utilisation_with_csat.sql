TEST (name "rpt_agent_scorecard__ranks_agents_by_utilisation_with_csat");

WITH __ref__int_agent_utilisation AS (
  SELECT
    'SH1' AS shift_id,
    'A1' AS agent_id,
    'EU' AS team_code,
    '2026-03-02 08:00:00'::TIMESTAMPNTZ AS shift_start_utc,
    NULL AS shift_end_utc,
    360 AS productive_minutes,
    NULL AS call_minutes,
    10 AS calls_handled,
    5 AS tickets_first_responded,
    0.75::DECIMAL(9, 4) AS utilisation,
    NULL AS is_overnight
  UNION ALL
  SELECT
    'SH2',
    'A1',
    'EU',
    '2026-03-03 08:00:00'::TIMESTAMPNTZ,
    NULL,
    300,
    NULL,
    8,
    4,
    0.65::DECIMAL(9, 4),
    NULL
  UNION ALL
  SELECT
    'SH3',
    'A2',
    'EU',
    '2026-03-02 08:00:00'::TIMESTAMPNTZ,
    NULL,
    420,
    NULL,
    12,
    6,
    0.9::DECIMAL(9, 4),
    NULL
  UNION ALL
  SELECT
    'SH4',
    'A3',
    'EU',
    '2026-03-02 08:00:00'::TIMESTAMPNTZ,
    NULL,
    0,
    NULL,
    0,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'SH5',
    'A1',
    'EU',
    '2026-04-01 08:00:00'::TIMESTAMPNTZ,
    NULL,
    120,
    NULL,
    2,
    1,
    0.5::DECIMAL(9, 4),
    NULL
),

__ref__int_ticket_first_response AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS created_at_utc,
    '2026-03-02 09:00:00'::TIMESTAMPNTZ AS first_response_at_utc,
    'A1' AS first_responder_id,
    NULL AS minutes_to_first_response,
    NULL AS first_customer_reply_at_utc,
    NULL AS agent_responses_before_customer_reply,
    NULL AS has_auto_reply
  UNION ALL
  SELECT
    'T2',
    NULL,
    '2026-03-05 09:00:00'::TIMESTAMPNTZ,
    'A1',
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    NULL,
    '2026-03-02 09:00:00'::TIMESTAMPNTZ,
    'A2',
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    NULL,
    '2026-04-01 09:00:00'::TIMESTAMPNTZ,
    'A1',
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_customer_support_history AS (
  SELECT
    'T1' AS ticket_id,
    'C1' AS customer_id,
    NULL AS ticket_number_for_customer,
    NULL AS days_since_previous_ticket,
    5 AS csat_score,
    NULL AS rolling_csat_avg,
    NULL AS is_repeat_contact_7d,
    NULL AS contact_reason
  UNION ALL
  SELECT
    'T2',
    'C2',
    NULL,
    NULL,
    3,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    'C3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__rpt_agent_scorecard AS (
  SELECT
    'A1:2026-03' AS agent_month_key,
    2 AS shifts,
    11.0::DECIMAL(10, 2) AS productive_hours,
    0.7::DECIMAL(9, 4) AS average_utilisation,
    18 AS calls_handled,
    9 AS tickets_first_responded,
    4.0::DECIMAL(4, 2) AS average_csat,
    2 AS utilisation_rank_in_team
  UNION ALL
  SELECT
    'A2:2026-03' AS agent_month_key,
    1 AS shifts,
    7.0::DECIMAL(10, 2) AS productive_hours,
    0.9::DECIMAL(9, 4) AS average_utilisation,
    12 AS calls_handled,
    6 AS tickets_first_responded,
    CAST(NULL AS DECIMAL(4, 2)) AS average_csat,
    1 AS utilisation_rank_in_team
  UNION ALL
  SELECT
    'A3:2026-03' AS agent_month_key,
    1 AS shifts,
    0.0::DECIMAL(10, 2) AS productive_hours,
    CAST(NULL AS DECIMAL(9, 4)) AS average_utilisation,
    0 AS calls_handled,
    0 AS tickets_first_responded,
    CAST(NULL AS DECIMAL(4, 2)) AS average_csat,
    3 AS utilisation_rank_in_team
  UNION ALL
  SELECT
    'A1:2026-04' AS agent_month_key,
    1 AS shifts,
    2.0::DECIMAL(10, 2) AS productive_hours,
    0.5::DECIMAL(9, 4) AS average_utilisation,
    2 AS calls_handled,
    1 AS tickets_first_responded,
    CAST(NULL AS DECIMAL(4, 2)) AS average_csat,
    1 AS utilisation_rank_in_team
),

__assert__agent_month_key_is_unique_and_present AS (
  SELECT t.agent_month_key
  FROM __ref("rpt_agent_scorecard") AS t
  GROUP BY
    t.agent_month_key
  HAVING
    COUNT(*) > 1
    OR t.agent_month_key IS NULL
)
