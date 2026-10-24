TEST (name "dim_date__builds_a_gap_free_three_year_calendar");

WITH __seed__holiday_calendar AS (
  SELECT
    'EU' AS region_code,
    '2026-04-03'::DATE AS holiday_date,
    'Good Friday' AS holiday_name
  UNION ALL
  SELECT
    'US',
    '2026-04-03'::DATE,
    'Synthetic holiday'
),

__assert__covers_three_years_without_gaps AS (
  SELECT COUNT(DISTINCT c.calendar_date) AS day_count
  FROM __ref("dim_date") AS c
  HAVING
    COUNT(DISTINCT c.calendar_date) <> 1095
    OR COUNT(*) <> 1095
    OR MIN(c.calendar_date) <> '2025-01-01'::DATE
    OR MAX(c.calendar_date) <> '2027-12-31'::DATE
),

__assert__fiscal_year_starts_in_april AS (
  SELECT c.calendar_date
  FROM __ref("dim_date") AS c
  WHERE
    (
      c.calendar_date = '2026-04-01'::DATE
      AND (
        c.fiscal_year <> 2027
        OR c.fiscal_quarter <> 1
      )
    )
    OR (
      c.calendar_date = '2026-03-31'::DATE
      AND (
        c.fiscal_year <> 2026
        OR c.fiscal_quarter <> 4
      )
    )
),

__assert__iso_week_belongs_to_previous_year_at_boundary AS (
  SELECT c.calendar_date
  FROM __ref("dim_date") AS c
  WHERE
    c.calendar_date = '2027-01-01'::DATE
    AND (
      c.iso_year <> 2026
      OR c.iso_week <> 53
    )
),

__assert__holidays_list_every_region AS (
  SELECT c.calendar_date
  FROM __ref("dim_date") AS c
  WHERE
    (
      c.calendar_date = '2026-04-03'::DATE
      AND (
        ARRAY_TO_STRING(c.holiday_regions, ',') <> 'EU,US'
        OR NOT c.is_holiday_somewhere
      )
    )
    OR (
      c.calendar_date = '2026-04-04'::DATE
      AND c.is_holiday_somewhere
    )
)
