// Wire types for the SQLBuild server API.
//
// These mirror the server's resource shapes so that a client generated from the
// OpenAPI schema can replace them later. Timestamps are ISO-8601 strings and IDs
// are opaque strings.

import type { Run } from './types/operate';

export type Iso = string;

// ---- identity, roles and capabilities ----

export type BuiltInRole = 'viewer' | 'operator' | 'developer' | 'admin';

export const CAPABILITIES = [
	'view',
	'view.sql',
	'view.evidence',
	'job.run',
	'run.cancel',
	'run.rerun',
	'run.rewrite_history',
	'trigger.toggle',
	'sensor.reset_cursor',
	'run.adhoc',
	'connection.test',
	'warehouse.sync',
	'plan.preview',
	'location.manage',
	'user.manage',
	'role.assign',
	'token.manage',
	'audit.view'
] as const;
export type Capability = (typeof CAPABILITIES)[number];

export type PrincipalKind = 'user' | 'service_account' | 'scheduler' | 'sensor' | 'system';
export type Principal = {
	kind: PrincipalKind;
	/** Stable handle, e.g. a user name, service account or `scheduler`. */
	name: string;
	displayName: string;
};

export type CurrentUser = Principal & {
	kind: 'user' | 'service_account';
	role: BuiltInRole;
};

export type AuthMode = 'oidc' | 'trusted_proxy' | 'password' | 'disabled';

// ---- locations, targets and snapshots ----

export type Snapshot = {
	id: string;
	/** Increases per (location, target); an older compile never replaces a newer one. */
	generation: number;
	gitRevision: string;
	gitDirty: boolean;
	gitAuthor: string;
	publishedAt: Iso;
	sqbVersion: string;
};

export type WarehouseSyncState = 'idle' | 'running' | 'failed';
export type WarehouseSync = {
	state: WarehouseSyncState;
	lastSyncedAt: Iso | null;
	/** Start of the sync in progress, when `state` is `running`. */
	runningSince: Iso | null;
	/** A follow-up sync is queued behind the running one (at most one). */
	followUpQueued: boolean;
	lastError: string | null;
};

export type WarehouseSyncRequestOutcome =
	/** No sync was running; a new one started. */
	| 'started'
	/** A sync was running; one follow-up sync was queued behind it. */
	| 'follow_up_queued'
	/** A sync was running and a follow-up was already queued; the request merged into it. */
	| 'merged';

export type WarehouseSyncRequestResult = {
	outcome: WarehouseSyncRequestOutcome;
	sync: WarehouseSync;
};

export type Target = {
	name: string;
	adapter: string;
	isDefault: boolean;
	snapshot: Snapshot | null;
	warehouseSync: WarehouseSync;
};

export type LocationHealth = 'healthy' | 'degraded' | 'falling_back' | 'broken';
export type Location = {
	/** Opaque server-generated UUID; the name is a mutable label. */
	id: string;
	name: string;
	health: LocationHealth;
	lastSeenAt: Iso | null;
	targets: Target[];
};

export type Scope = { locationId: string; target: string };

// ---- bootstrap ----

export type Bootstrap = {
	serverVersion: string;
	authMode: AuthMode;
	user: CurrentUser;
	capabilities: Capability[];
	locations: Location[];
};

// ---- checks ----

export type CheckResult = 'pass' | 'warn' | 'fail';
export type CheckSeverity = 'error' | 'warn';
export type RunScopePhase = 'delta_and_final' | 'final';
export type Check = {
	name: string;
	/** Attached node; null for standalone checks. */
	node: string | null;
	checkType: string;
	severity: CheckSeverity;
	runScopePhase: RunScopePhase;
	result: CheckResult;
	detail: string;
	lastRunId: string;
	evaluatedAt: Iso;
};

// ---- connections ----

export type ConnectionKind = 'warehouse' | 'provider' | 'channel';
export type ConnectionStatus = 'ok' | 'error' | 'untested';
export type Connection = {
	id: string;
	name: string;
	kind: ConnectionKind;
	type: string;
	status: ConnectionStatus;
	usedBy: number;
	summary: string;
};

// ---- platform events ----

export type PlatformEventKind =
	| 'tick_overdue'
	| 'scheduler_no_leader'
	| 'location_broken'
	| 'launch_failed'
	| 'heartbeat';
export type PlatformEventSeverity = 'info' | 'warning' | 'critical';
export type PlatformEvent = {
	id: string;
	kind: PlatformEventKind;
	severity: PlatformEventSeverity;
	occurredAt: Iso;
	/** Still unresolved; only active events surface in the banner. */
	active: boolean;
	locationId: string | null;
	subject: string | null;
	message: string;
};

// ---- overview and change feed ----

export type ChangeKind = 'snapshot' | 'macro' | 'model_added' | 'column_added';
export type Change = {
	id: string;
	kind: ChangeKind;
	title: string;
	detail: string;
	actor: Principal;
	at: Iso;
	href: string;
};

export type AttentionTone = 'error' | 'warning' | 'stale';
export type AttentionItem = {
	id: string;
	tone: AttentionTone;
	title: string;
	detail: string;
	since: string;
	href: string;
	action: string;
};

export type OverviewMetric = {
	label: string;
	value: string;
	detail: string;
	note: string;
	tone?: 'success' | 'warning' | 'stale';
};

export type Overview = {
	metrics: OverviewMetric[];
	attention: AttentionItem[];
	currentNodes: number;
	staleNodes: number;
	failingChecks: number;
	latestRun: Pick<Run, 'id' | 'status' | 'endedAt'> | null;
	recentChanges: Change[];
};

// ---- navigation ----

export type NavCounts = {
	catalogNodes: number;
	failingChecks: number;
	activeRuns: number;
	pausedTriggers: number;
	activeAlerts: number;
	pendingApprovals: number;
};

export * from './types/operate';
export * from './types/platform';
