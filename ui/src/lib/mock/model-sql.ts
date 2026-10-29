// Mock model SQL for the prototype (real data comes from the SQLBuild compiler).

export const FACT_ORDERS_SQL = `MODEL (
  materialized table,
  unique_key order_id,
  tags [finance, core],
  description "One row per order with payment + customer.",
  columns (
    order_id (audits [not_null, unique]),
    customer_id (audits [not_null])
  )
);

WITH orders AS (
  SELECT order_id, customer_id, order_status, total_cents, ordered_at
  FROM __ref("stg_orders")
),
payments AS (
  SELECT order_id, payment_method, amount_cents
  FROM __ref("stg_payments")
  WHERE status = 'success'
),
customers AS (
  SELECT customer_id, first_order_at
  FROM __ref("stg_customers")
)

SELECT
  o.order_id,
  o.customer_id,
  o.order_status,
  o.total_cents,
  p.payment_method,
  o.ordered_at,
  o.ordered_at = c.first_order_at AS is_first_order
FROM orders o
LEFT JOIN payments p USING (order_id)
LEFT JOIN customers c USING (customer_id)`;

export function mockModelSql(name: string, kind: string, parents: string[], description = name): string {
	if (name === 'fact_orders') return FACT_ORDERS_SQL;
	const materialized = kind.split(' · ')[0];
	const ctes = parents.map((parent, i) => `${i === 0 ? 'WITH ' : ''}${parent.replace(/^(stg|raw)_+/, '')} AS (\n  SELECT *\n  FROM __ref("${parent}")\n)`);
	const first = parents[0]?.replace(/^(stg|raw)_+/, '') ?? 'source';
	return `MODEL (\n  materialized ${materialized},\n  description "${description}"\n);\n\n${ctes.join(',\n')}\n\nSELECT\n  *\nFROM ${first}`;
}

// ---- drift mock: stored SQL per build in the current target (SQLBuild keeps raw + compiled per build).
// Drift is computed by the backend against what was last built in this target. ----

export type DriftKind = 'direct' | 'compiled' | 'upstream';
export type SqlVersion = { id: string; label: string; detail: string; raw: string; compiled?: string };

export const MODEL_DRIFT: Record<string, DriftKind> = {
	fact_orders: 'direct',
	stg_payments: 'compiled',
	dim_customers: 'upstream',
	customer_status: 'upstream',
	order_status_idx: 'upstream',
	hourly_order: 'upstream',
	daily_activity: 'upstream',
	hourly_ctx: 'upstream'
};

const FACT_ORDERS_BUILT = FACT_ORDERS_SQL.replace("\n  WHERE status = 'success'", '')
	.replace(',\ncustomers AS (\n  SELECT customer_id, first_order_at\n  FROM __ref("stg_customers")\n)', '')
	.replace('  o.ordered_at = c.first_order_at AS is_first_order', '  row_number() OVER (PARTITION BY o.customer_id ORDER BY o.ordered_at) = 1 AS is_first_order')
	.replace('\nLEFT JOIN customers c USING (customer_id)', '');

const FACT_ORDERS_EARLIER = FACT_ORDERS_SQL.replace("\n  WHERE status = 'success'", '');

/**
 * Versions to compare the current SQL against, newest first. `compiled` overrides
 * the default ref substitution when the stored compiled SQL differed.
 */
export function modelVersions(name: string, current: string): SqlVersion[] {
	if (name === 'fact_orders') {
		return [
			{ id: 'built', label: 'Last build', detail: 'run-9d21 · 4m ago', raw: FACT_ORDERS_BUILT },
			{ id: 'run-91cd', label: 'Build run-91cd', detail: '1h ago', raw: FACT_ORDERS_BUILT },
			{ id: 'run-2b70', label: 'Build run-2b70', detail: '3h ago', raw: FACT_ORDERS_EARLIER }
		];
	}
	const builtCompiled =
		name === 'stg_payments'
			? current.replace(/__ref\("(\w+)"\)/g, '"waffle_shop"."prod"."$1_v1"').replace(/^MODEL\s*\([\s\S]*?\n\);\s*\n+/, '')
			: undefined;
	return [
		{ id: 'built', label: 'Last build', detail: 'run-9d21 · 4m ago', raw: current, compiled: builtCompiled },
		{ id: 'run-91cd', label: 'Build run-91cd', detail: '1h ago', raw: current }
	];
}
