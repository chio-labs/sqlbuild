TEST (name "stg_ticket_tags__dedupes_tags_from_fixture_macro");

WITH __ref__stg_tickets AS (
  @py.tagged_tickets([["T3", ["Wrong Colour", "wrong_colour", "WRONG COLOUR"], "Returns"], ["T4", [], None]])
),

__expected__stg_ticket_tags AS (
  SELECT
    'T3:wrong-colour' AS ticket_tag_key,
    'T3' AS ticket_id,
    'wrong-colour' AS tag
  UNION ALL
  SELECT
    'T3:returns' AS ticket_tag_key,
    'T3' AS ticket_id,
    'returns' AS tag
),

__assert__every_tag_is_lower_kebab_case AS (
  SELECT t.ticket_tag_key
  FROM __ref("stg_ticket_tags") AS t
  WHERE NOT REGEXP_LIKE(t.tag, '[a-z0-9]+(-[a-z0-9]+)*')
)
