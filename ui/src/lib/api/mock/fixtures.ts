// Neutral example data for the mock client: a fictional waffle shop's orders,
// customers and payments. Times are relative to `now` so ages stay realistic.

import type { BuiltInRole, Capability, Location, PlatformEvent, Snapshot } from '../types';
import { CAPABILITIES } from '../types';

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

	const snapshot = (generation: number, revision: string, minutesAgo: number, author: string, dirty = false): Snapshot => ({
		id: `snap-${revision}`,
		generation,
		gitRevision: revision,
		gitDirty: dirty,
		gitAuthor: author,
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
				{ name: 'prod', adapter: 'snowflake', isDefault: true, snapshot: snapshot(42, '7d2e41a', 190, 'Alex Rivera'), warehouseSync: idleSync(4) },
				{ name: 'staging', adapter: 'snowflake', isDefault: false, snapshot: snapshot(57, 'b81c09e', 35, 'Sam Okafor'), warehouseSync: idleSync(11) },
				{ name: 'dev', adapter: 'duckdb', isDefault: false, snapshot: snapshot(311, 'b81c09e', 2, 'Demo User', true), warehouseSync: idleSync(1) }
			]
		},
		{
			id: LOCATION_MARKETING,
			name: 'marketing-analytics',
			health: 'falling_back',
			lastSeenAt: ago(0.5),
			targets: [
				{ name: 'prod', adapter: 'postgres', isDefault: true, snapshot: snapshot(18, '3e5f7aa', 1440, 'Jordan Lee'), warehouseSync: idleSync(26) }
			]
		}
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

	return { locations, platformEvents, extraPlatformEvents };
}

export type Fixtures = ReturnType<typeof createFixtures>;
