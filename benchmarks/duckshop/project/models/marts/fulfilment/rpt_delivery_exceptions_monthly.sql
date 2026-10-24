MODEL (
  description """
    One row per month, carrier and responsibility with delivery exceptions and compensation paid
  """,
  columns (
    exception_month_key (type VARCHAR, nullable false, audits [not_null, unique]),
    exception_month (type DATE),
    carrier_code (type VARCHAR),
    responsibility (type VARCHAR),
    exceptions (type INT),
    shipments_affected (type INT),
    median_hours_to_resolve (type NUMBER(10, 2)),
    compensation_usd (type NUMBER(18, 2)),
    top_exception_code (type VARCHAR),
  ),
);

WITH exceptions AS (
  SELECT *
  FROM __ref("int_delivery_exceptions_classified")
),

final AS (
  SELECT
    (
      TO_VARCHAR(
        DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', e.occurred_at)),
        'YYYY-MM'
      )
      || ':' || e.carrier_code || ':' || e.responsibility
    )::VARCHAR AS exception_month_key,
    DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', e.occurred_at))::DATE AS exception_month,
    e.carrier_code,
    e.responsibility,
    COUNT(*)::INT AS exceptions,
    COUNT(DISTINCT e.shipment_id)::INT AS shipments_affected,
    ROUND(MEDIAN(e.hours_to_resolve), 2)::NUMBER(10, 2) AS median_hours_to_resolve,
    SUM(e.compensation_usd)::NUMBER(18, 2) AS compensation_usd,
    MODE(e.exception_code)::VARCHAR AS top_exception_code
  FROM exceptions AS e
  GROUP BY
    DATE_TRUNC(
      'month',
      CONVERT_TIMEZONE('UTC', e.occurred_at)
    ),
    e.carrier_code,
    e.responsibility
)

SELECT *
FROM final
