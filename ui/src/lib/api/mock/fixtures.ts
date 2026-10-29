// Neutral example data for the mock client: a fictional waffle shop's orders,
// customers and payments. Times are relative to `now` so ages stay realistic.

import type { BuiltInRole, Capability, Change, Check, Connection, Location, PlatformEvent, Snapshot } from '../types';
import { CAPABILITIES } from '../types';
import { CI_ACCOUNT } from './principals';

export { SCHEDULER, SENSOR_DAEMON, CI_ACCOUNT, DEMO_USER } from './principals';

const MIN = 60_000;

const OPERATE: Capability[] = ['view', 'view.sql', 'job.run', 'run.cancel', 'run.rerun', 'trigger.toggle', 'sensor.reset_cursor', 'warehouse.sync'];
const DEVELOP: Capability[] = [...OPERATE, 'view.evidence', 'run.rewrite_history', 'run.adhoc', 'connection.test', 'plan.preview'];

/** Mock-only approximation of the built-in roles; the server owns the real grants. */
export const ROLE_CAPABILITIES: Record<BuiltInRole, Capability[]> = {
	viewer: ['view'],
	operator: OPERATE,
	developer: DEVELOP,
	admin: [...CAPABILITIES]
};

export const LOCATION_SHOP = '0d9c6a52-3f1e-4b7a-9c43-5b8e2f61a7d4';
export const LOCATION_MARKETING = '7a41e0c8-62b5-4d19-8f3a-c1e95d0b2e66';

export function createFixtures(now: number) {
	const ago = (minutes: number) => new Date(now - minutes * MIN).toISOString();

	const snapshot = (generation: number, revision: string, minutesAgo: number, dirty = false): Snapshot => ({
		id: `snap-${revision}`,
		generation,
		gitRevision: revision,
		gitDirty: dirty,
		gitAuthor: dirty ? 'Demo User' : 'Release automation',
		publishedAt: ago(minutesAgo),
		sqbVersion: '0.185.0'
	});

	const idleSync = (minutesAgo: number) => ({
		state: 'idle' as const,
		lastSyncedAt: ago(minutesAgo),
		runningSince: null,
		followUpQueued: false,
		lastError: null
	});

	const locations: Location[] = [
		{
			id: LOCATION_SHOP,
			name: 'waffle-shop',
			health: 'healthy',
			lastSeenAt: ago(0.2),
			targets: [
				{ name: 'prod', adapter: 'snowflake', isDefault: true, snapshot: snapshot(42, '7d2e41a', 190), warehouseSync: idleSync(4) },
				{ name: 'staging', adapter: 'snowflake', isDefault: false, snapshot: snapshot(57, 'b81c09e', 35), warehouseSync: idleSync(11) },
				{ name: 'dev', adapter: 'duckdb', isDefault: false, snapshot: snapshot(311, 'b81c09e', 2, true), warehouseSync: idleSync(1) }
			]
		},
		{
			id: LOCATION_MARKETING,
			name: 'marketing-analytics',
			health: 'falling_back',
			lastSeenAt: ago(0.5),
			targets: [
				{ name: 'prod', adapter: 'postgres', isDefault: true, snapshot: snapshot(18, '3e5f7aa', 1440), warehouseSync: idleSync(26) }
			]
		}
	];

	const checks: Check[] = [
		{ name: 'not_null(order_id)', node: 'fact_orders', checkType: 'not_null', severity: 'error', runScopePhase: 'final', result: 'pass', detail: '0 rows', lastRunId: 'run-4f2a', evaluatedAt: ago(18) },
		{ name: 'unique(order_id)', node: 'fact_orders', checkType: 'unique', severity: 'error', runScopePhase: 'final', result: 'pass', detail: '0 rows', lastRunId: 'run-4f2a', evaluatedAt: ago(18) },
		{ name: 'relationships(customer_id → dim_customers)', node: 'fact_orders', checkType: 'relationships', severity: 'error', runScopePhase: 'final', result: 'pass', detail: '0 orphans', lastRunId: 'run-4f2a', evaluatedAt: ago(18) },
		{ name: 'not_null(customer_id)', node: 'stg_customers', checkType: 'not_null', severity: 'error', runScopePhase: 'final', result: 'pass', detail: '0 rows', lastRunId: 'run-4f2a', evaluatedAt: ago(18) },
		{ name: 'not_null(payment_id)', node: 'stg_payments', checkType: 'not_null', severity: 'warn', runScopePhase: 'final', result: 'warn', detail: '2 nulls', lastRunId: 'run-4f2a', evaluatedAt: ago(18) },
		{ name: 'accepted_values(order_status)', node: 'stg_orders', checkType: 'accepted_values', severity: 'error', runScopePhase: 'final', result: 'pass', detail: '0 rows', lastRunId: 'run-4f2a', evaluatedAt: ago(18) },
		{ name: 'expression_is_true(activity_hour IS NOT NULL)', node: 'hourly_activity_ctx', checkType: 'expression_is_true', severity: 'error', runScopePhase: 'delta_and_final', result: 'fail', detail: '7 rows · blocked promotion', lastRunId: 'run-4f2a', evaluatedAt: ago(18) },
		{ name: 'unique(activity_hour)', node: 'daily_activity', checkType: 'unique', severity: 'error', runScopePhase: 'final', result: 'pass', detail: '0 rows', lastRunId: 'run-2b70', evaluatedAt: ago(176) },
		{ name: 'revenue reconciles to source', node: null, checkType: 'standalone', severity: 'error', runScopePhase: 'final', result: 'pass', detail: 'within 0.1%', lastRunId: 'run-c40e', evaluatedAt: ago(1079) }
	];

	const connections: Connection[] = [
		{ id: 'snowflake_prod', name: 'snowflake · prod', kind: 'warehouse', type: 'snowflake', status: 'ok', usedBy: 16, summary: 'Production warehouse for the prod target.' },
		{ id: 'duckdb_dev', name: 'duckdb · dev', kind: 'warehouse', type: 'duckdb', status: 'ok', usedBy: 16, summary: 'Local DuckDB file for the dev target.' },
		{ id: 'orders_api', name: 'orders_api', kind: 'provider', type: 'rest', status: 'ok', usedBy: 1, summary: 'Source loader connection for raw__orders ingestion.' },
		{ id: 's3_archive', name: 's3_archive', kind: 'provider', type: 's3', status: 'untested', usedBy: 2, summary: 'Object storage bucket for CSV exports and backups.' },
		{ id: 'chat_alerts', name: 'chat_alerts', kind: 'channel', type: 'webhook', status: 'ok', usedBy: 1, summary: 'Posts run-failure alerts to the team channel.' },
		{ id: 'warehouse_eu', name: 'warehouse · eu', kind: 'warehouse', type: 'bigquery', status: 'error', usedBy: 0, summary: 'Service account credentials expired.' }
	];

	const platformEvents: PlatformEvent[] = [
		{ id: 'pe-1', kind: 'location_broken', severity: 'warning', occurredAt: ago(48), active: true, locationId: LOCATION_MARKETING, subject: 'marketing-analytics', message: 'The latest image failed to start; running the last good image.' },
		{ id: 'pe-2', kind: 'tick_overdue', severity: 'warning', occurredAt: ago(12), active: true, locationId: LOCATION_SHOP, subject: 'segments_hourly', message: 'Tick is 12 minutes overdue.' },
		{ id: 'pe-3', kind: 'heartbeat', severity: 'info', occurredAt: ago(1), active: false, locationId: null, subject: null, message: 'Server heartbeat.' }
	];
	const extraPlatformEvents: PlatformEvent[] = [
		{ id: 'pe-4', kind: 'scheduler_no_leader', severity: 'critical', occurredAt: ago(2), active: true, locationId: null, subject: null, message: 'No scheduler holds the leader lease; ticks are not being evaluated.' },
		{ id: 'pe-5', kind: 'launch_failed', severity: 'critical', occurredAt: ago(6), active: true, locationId: LOCATION_SHOP, subject: 'revenue_refresh', message: 'Three consecutive launches failed: image pull error.' }
	];

	const changes: Change[] = [
		{ id: 'ch-1', kind: 'macro', title: 'Macro cents_to_dollars updated', detail: 'Used by 3 models · stg_payments, fact_orders, daily_revenue', actor: CI_ACCOUNT, at: ago(300), href: '/catalog/stg_payments?tab=sql' },
		{ id: 'ch-2', kind: 'model_added', title: 'New model customer_status', detail: 'marts · view', actor: CI_ACCOUNT, at: ago(1440), href: '/catalog/customer_status' },
		{ id: 'ch-3', kind: 'column_added', title: 'Column added dim_customers.lifetime_value', detail: 'decimal(18,2)', actor: CI_ACCOUNT, at: ago(1500), href: '/catalog/dim_customers?tab=columns' },
		{ id: 'ch-4', kind: 'snapshot', title: 'Snapshot 7d2e41a published to prod', detail: '3 models changed · fact_orders, stg_payments, dim_customers', actor: CI_ACCOUNT, at: ago(4320), href: '/runs/run-77b3' }
	];

	return { locations, checks, connections, platformEvents, extraPlatformEvents, changes };
}

export type Fixtures = ReturnType<typeof createFixtures>;
