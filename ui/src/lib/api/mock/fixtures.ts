// Neutral example data for the mock client: a fictional waffle shop's orders,
// customers and payments. Times are relative to `now` so ages stay realistic.

import type {
	BuiltInRole,
	Capability,
	Change,
	Check,
	Connection,
	Job,
	Location,
	NodeCounts,
	PlatformEvent,
	Principal,
	Run,
	RunKind,
	RunStatus,
	Snapshot,
	Trigger
} from '../types';
import { CAPABILITIES } from '../types';

const MIN = 60_000;

export const SCHEDULER: Principal = { kind: 'scheduler', name: 'scheduler', displayName: 'Scheduler' };
export const SENSOR_DAEMON: Principal = { kind: 'sensor', name: 'sensors', displayName: 'Sensor daemon' };
export const CI_ACCOUNT: Principal = { kind: 'service_account', name: 'svc-ci', displayName: 'CI service account' };
export const DEMO_USER: Principal = { kind: 'user', name: 'demo', displayName: 'Demo User' };

const OPERATE: Capability[] = ['view', 'view.sql', 'job.run', 'run.cancel', 'run.rerun', 'trigger.toggle', 'sensor.reset_cursor'];
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

function counts(partial: Partial<NodeCounts>): NodeCounts {
	return { success: 0, warn: 0, failed: 0, skipped: 0, running: 0, pending: 0, ...partial };
}

export function createFixtures(now: number) {
	const ago = (minutes: number) => new Date(now - minutes * MIN).toISOString();
	const ahead = (minutes: number) => new Date(now + minutes * MIN).toISOString();

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

	type RunSeed = {
		id: string;
		kind: RunKind;
		status: RunStatus;
		job: string | null;
		trigger?: string;
		by: Principal;
		queued: number;
		started?: number;
		ended?: number;
		nodes: Partial<NodeCounts>;
		reason?: string;
		rerunOf?: string;
	};
	const runSeeds: RunSeed[] = [
		{ id: 'run-9d21', kind: 'schedule', status: 'running', job: 'nightly_build', trigger: 'nightly_build', by: SCHEDULER, queued: 3, started: 2.5, nodes: { success: 4, running: 2, pending: 10 } },
		{ id: 'run-5e10', kind: 'job', status: 'queued', job: 'revenue_refresh', by: DEMO_USER, queued: 1, nodes: { pending: 4 }, reason: 'Waiting for run-9d21: overlapping write set' },
		{ id: 'run-6a90', kind: 'schedule', status: 'unresponsive', job: 'activity_microbatch', trigger: 'activity_microbatch', by: SCHEDULER, queued: 9, started: 8.8, nodes: { success: 2, running: 1, pending: 2 }, reason: 'No heartbeat for 95s' },
		{ id: 'run-4f2a', kind: 'schedule', status: 'partial', job: 'nightly_build', trigger: 'nightly_build', by: SCHEDULER, queued: 22, started: 22, ended: 18, nodes: { success: 8, warn: 1, failed: 1, skipped: 3 }, reason: '1 node failed; 3 dependents skipped' },
		{ id: 'run-91cd', kind: 'job', status: 'success', job: 'marts_only', by: DEMO_USER, queued: 97, started: 97, ended: 84, nodes: { success: 6 } },
		{ id: 'run-3b22', kind: 'adhoc', status: 'success', job: null, by: DEMO_USER, queued: 120, started: 120, ended: 118, nodes: { success: 2 } },
		{ id: 'run-2b70', kind: 'schedule', status: 'success', job: 'nightly_build', trigger: 'nightly_build', by: SCHEDULER, queued: 188, started: 188, ended: 176, nodes: { success: 16 } },
		{ id: 'run-88e1', kind: 'sensor', status: 'success', job: 'load_sources', trigger: 'on_raw_orders_landed', by: SENSOR_DAEMON, queued: 206, started: 206, ended: 205, nodes: { success: 3 } },
		{ id: 'run-1a05', kind: 'schedule', status: 'warn', job: 'activity_microbatch', trigger: 'activity_microbatch', by: SCHEDULER, queued: 248, started: 248, ended: 244, nodes: { success: 4, warn: 1 } },
		{ id: 'run-77b3', kind: 'group', status: 'success', job: 'nightly_all', trigger: 'nightly_all', by: SCHEDULER, queued: 368, started: 368, ended: 340, nodes: { success: 19 } },
		{ id: 'run-0c7d', kind: 'rerun', status: 'cancelled', job: 'nightly_build', by: CI_ACCOUNT, queued: 600, started: 600, ended: 597, nodes: { success: 3, skipped: 13 }, rerunOf: 'run-77b3', reason: 'Cancelled by svc-ci' },
		{ id: 'run-c40e', kind: 'job', status: 'success', job: 'checks_only', by: CI_ACCOUNT, queued: 1080, started: 1080, ended: 1079, nodes: { success: 14 } },
		{ id: 'run-e3f8', kind: 'schedule', status: 'presumed_failed', job: 'activity_microbatch', trigger: 'activity_microbatch', by: SCHEDULER, queued: 1500, started: 1500, ended: 1490, nodes: { success: 1, failed: 1, skipped: 3 }, reason: 'Worker lost; no heartbeat after 5m' },
		{ id: 'run-a7c1', kind: 'schedule', status: 'failed', job: 'revenue_refresh', trigger: 'revenue_refresh', by: SCHEDULER, queued: 1620, started: 1620, ended: 1617, nodes: { failed: 1, skipped: 3 }, reason: 'daily_revenue failed: warehouse error' }
	];

	const runs: Run[] = runSeeds.map((s) => ({
		id: s.id,
		kind: s.kind,
		status: s.status,
		statusReason: s.reason ?? null,
		jobKey: s.job,
		parentRunId: null,
		triggerName: s.trigger ?? null,
		rerunOfRunId: s.rerunOf ?? null,
		requestedBy: s.by,
		locationId: LOCATION_SHOP,
		target: 'prod',
		snapshotId: 'snap-7d2e41a',
		gitRevision: '7d2e41a',
		queuedAt: ago(s.queued),
		startedAt: s.started === undefined ? null : ago(s.started),
		endedAt: s.ended === undefined ? null : ago(s.ended),
		nodeCounts: counts(s.nodes)
	}));

	const lastRunOf = (job: string) => {
		const run = runs.find((r) => r.jobKey === job);
		return run ? { id: run.id, status: run.status, startedAt: run.startedAt, endedAt: run.endedAt } : null;
	};

	const jobBase = {
		overlap: 'coalesce' as const,
		onFailure: 'skip_dependents' as const,
		concurrencyGroups: [] as string[],
		members: [] as string[]
	};
	const jobs: Job[] = [
		{ ...jobBase, key: 'nightly_build', kind: 'job', description: 'Full project build', select: '+', nodeCount: 16, concurrencyGroups: ['target:prod'], sourceFile: 'orchestration/jobs.py', triggerNames: ['nightly_build'], lastRun: lastRunOf('nightly_build') },
		{ ...jobBase, key: 'marts_only', kind: 'job', description: 'Marts and their upstreams', select: '+marts', nodeCount: 9, sourceFile: 'orchestration/jobs.py', triggerNames: ['marts_hourly'], lastRun: lastRunOf('marts_only') },
		{ ...jobBase, key: 'load_sources', kind: 'job', description: 'Ingest loaders and sources', select: 'tag:ingest', nodeCount: 3, overlap: 'queue', sourceFile: 'orchestration/jobs.py', triggerNames: ['on_raw_orders_landed', 'on_payments_freshness'], lastRun: lastRunOf('load_sources') },
		{ ...jobBase, key: 'checks_only', kind: 'job', description: 'Run audits across all models', select: '* --checks-only', nodeCount: 14, sourceFile: 'orchestration/jobs.py', triggerNames: [], lastRun: lastRunOf('checks_only') },
		{ ...jobBase, key: 'activity_microbatch', kind: 'job', description: 'Incremental activity models', select: '+hourly_activity_ctx', nodeCount: 5, sourceFile: 'orchestration/activity.py', triggerNames: ['activity_microbatch'], lastRun: lastRunOf('activity_microbatch') },
		{ ...jobBase, key: 'revenue_refresh', kind: 'job', description: 'Daily revenue and downstream reporting', select: 'daily_revenue+', nodeCount: 4, onFailure: 'stop_group', sourceFile: 'orchestration/finance.py', triggerNames: ['revenue_refresh'], lastRun: lastRunOf('revenue_refresh') },
		{ ...jobBase, key: 'nightly_all', kind: 'group', description: 'Sources, then the full build', select: null, members: ['load_sources', 'nightly_build'], nodeCount: 19, onFailure: 'skip_downstream_jobs', sourceFile: 'orchestration/jobs.py', triggerNames: ['nightly_all'], lastRun: lastRunOf('nightly_all') }
	];

	const triggerRun = (id: string | null) => {
		const run = id ? runs.find((r) => r.id === id) : undefined;
		return run ? { id: run.id, status: run.status, startedAt: run.startedAt, endedAt: run.endedAt } : null;
	};
	const triggers: Trigger[] = [
		{ name: 'nightly_build', type: 'schedule', description: 'Nightly full build', jobKey: 'nightly_build', cadence: 'Daily at 02:00 Europe/London', cron: '0 2 * * *', timezone: 'Europe/London', defaultState: 'running', state: 'running', nextTickAt: ahead(13 * 60), lastTick: { id: 'tick-1', scheduledFor: ago(3), outcome: 'requested', runId: 'run-9d21', coveredByRunId: null, reason: null }, lastRun: triggerRun('run-9d21'), sourceFile: 'orchestration/jobs.py' },
		{ name: 'nightly_all', type: 'schedule', description: 'Sources then the full build', jobKey: 'nightly_all', cadence: 'Daily at 01:00 Europe/London', cron: '0 1 * * *', timezone: 'Europe/London', defaultState: 'running', state: 'running', nextTickAt: ahead(12 * 60), lastTick: { id: 'tick-2', scheduledFor: ago(368), outcome: 'requested', runId: 'run-77b3', coveredByRunId: null, reason: null }, lastRun: triggerRun('run-77b3'), sourceFile: 'orchestration/jobs.py' },
		{ name: 'activity_microbatch', type: 'schedule', description: 'Activity models every 15 minutes', jobKey: 'activity_microbatch', cadence: 'Every 15 minutes', cron: '*/15 * * * *', timezone: 'UTC', defaultState: 'running', state: 'running', nextTickAt: ago(12), lastTick: { id: 'tick-3', scheduledFor: ago(24), outcome: 'covered', runId: null, coveredByRunId: 'run-6a90', reason: 'Coalesced into the waiting run' }, lastRun: triggerRun('run-6a90'), sourceFile: 'orchestration/activity.py' },
		{ name: 'revenue_refresh', type: 'schedule', description: 'Daily revenue refresh', jobKey: 'revenue_refresh', cadence: 'Daily at 03:00 UTC', cron: '0 3 * * *', timezone: 'UTC', defaultState: 'running', state: 'paused', nextTickAt: null, lastTick: { id: 'tick-4', scheduledFor: ago(1620), outcome: 'requested', runId: 'run-a7c1', coveredByRunId: null, reason: null }, lastRun: triggerRun('run-a7c1'), sourceFile: 'orchestration/finance.py' },
		{ name: 'marts_hourly', type: 'schedule', description: 'Hourly marts refresh', jobKey: 'marts_only', cadence: 'Hourly at :00', cron: '0 * * * *', timezone: 'UTC', defaultState: 'paused', state: 'paused', nextTickAt: null, lastTick: null, lastRun: null, sourceFile: 'orchestration/jobs.py' },
		{ name: 'on_raw_orders_landed', type: 'sensor', description: 'New raw orders landed', jobKey: 'load_sources', cadence: 'When raw__orders has new data', cron: null, timezone: null, defaultState: 'running', state: 'running', nextTickAt: null, lastTick: { id: 'tick-5', scheduledFor: ago(1), outcome: 'skipped', runId: null, coveredByRunId: null, reason: 'No new data' }, lastRun: triggerRun('run-88e1'), sourceFile: 'orchestration/sensors.py' },
		{ name: 'on_payments_freshness', type: 'sensor', description: 'Payments source is stale', jobKey: 'load_sources', cadence: 'When raw__payments is stale for more than 1h', cron: null, timezone: null, defaultState: 'running', state: 'running', nextTickAt: null, lastTick: { id: 'tick-6', scheduledFor: ago(2), outcome: 'deferred', runId: null, coveredByRunId: null, reason: 'Location unavailable; retrying' }, lastRun: null, sourceFile: 'orchestration/sensors.py' }
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
		{ id: 'pe-2', kind: 'tick_overdue', severity: 'warning', occurredAt: ago(12), active: true, locationId: LOCATION_SHOP, subject: 'activity_microbatch', message: 'Tick is 12 minutes overdue.' },
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

	return { locations, runs, jobs, triggers, checks, connections, platformEvents, extraPlatformEvents, changes };
}

export type Fixtures = ReturnType<typeof createFixtures>;
