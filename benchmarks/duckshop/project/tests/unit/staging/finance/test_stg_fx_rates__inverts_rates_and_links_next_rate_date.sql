TEST (name "stg_fx_rates__inverts_rates_and_links_next_rate_date");

WITH __source__finance__fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-01'::DATE AS rate_date,
    1.25::NUMBER(18, 8) AS rate_to_usd
  UNION ALL
  SELECT
    'EUR',
    '2026-03-02'::DATE,
    1.1::NUMBER(18, 8)
  UNION ALL
  SELECT
    'JPY',
    '2026-03-01'::DATE,
    0.0067::NUMBER(18, 8)
),

__expected__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-01'::DATE AS rate_date,
    0.8::DECIMAL(18, 8) AS usd_to_rate,
    '2026-03-02'::DATE AS next_rate_date
  UNION ALL
  SELECT
    'EUR' AS currency_code,
    '2026-03-02'::DATE AS rate_date,
    0.90909091::DECIMAL(18, 8) AS usd_to_rate,
    CAST(NULL AS DATE) AS next_rate_date
  UNION ALL
  SELECT
    'JPY' AS currency_code,
    '2026-03-01'::DATE AS rate_date,
    149.25373134::DECIMAL(18, 8) AS usd_to_rate,
    CAST(NULL AS DATE) AS next_rate_date
)
