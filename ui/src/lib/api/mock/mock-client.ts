import type { ApiClient } from '../client';
import { ApiError } from '../client';
import { LocalChangeBus } from '../signals';
import type {
	AdhocRunCheck,
	AdhocRunRequest,
	Bootstrap,
	BuiltInRole,
	Check,
	Connection,
	CurrentUser,
	Job,
	JobDetail,
	JobLaunchOptions,
	NavCounts,
	Overview,
	PlatformEvent,
	QueueEntry,
	RerunMode,
	Run,
	RunDetail,
	RunEventPage,
	RunListQuery,
	RunOutputLine,
	RunStatement,
	Scope,
	SnapshotNode,
	Timeline,
	Trigger,
	TriggerDetail,
	TriggerState,
	WarehouseSync,
	WarehouseSyncRequestResult
} from '../types';
import { createFixtures, DEMO_USER, ROLE_CAPABILITIES, type Fixtures } from './fixtures';
import { MockOperate } from './operate-store';

export type MockOptions = {
	role?: BuiltInRole;
	/** `default` shows two warnings; `none` is all clear; `all` adds critical events. */
	alerts?: 'default' | 'none' | 'all';
	/** Simulated request latency in milliseconds. */
	latencyMs?: number;
	/** How long a simulated warehouse sync takes. */
	syncDurationMs?: number;
};

/** In-memory `ApiClient` with neutral example data. Mutations persist per page load. */
export class MockApiClient implements ApiClient {
	readonly changes = new LocalChangeBus();
	readonly #options: Required<MockOptions>;
	readonly #fixtures: Fixtures;
	readonly #createdAt = Date.now();
	readonly #operate: MockOperate;
	readonly #syncs = new Map<string, WarehouseSync>();
	readonly #syncTimers = new Map<string, ReturnType<typeof setTimeout>>();

	constructor(options: MockOptions = {}) {
		this.#options = {
			role: options.role ?? 'admin',
			alerts: options.alerts ?? 'default',
			latencyMs: options.latencyMs ?? 120,
			syncDurationMs: options.syncDurationMs ?? 8000
		};
		this.#fixtures = createFixtures(this.#createdAt);
		this.#operate = new MockOperate({
			changes: this.changes,
			role: () => this.#options.role,
			can: (capability) => ROLE_CAPABILITIES[this.#options.role].includes(capability),
			user: () => DEMO_USER,
			adapter: (scope) => this.#location(scope).targets.find((t) => t.name === scope.target)?.adapter ?? '',
			reply: (value) => this.#reply(value)
		});
	}

	async bootstrap(): Promise<Bootstrap> {
		const user: CurrentUser = { ...DEMO_USER, kind: 'user', role: this.#options.role };
		return this.#reply({
			serverVersion: '0.185.0',
			authMode: 'disabled',
			user,
			capabilities: ROLE_CAPABILITIES[this.#options.role],
			locations: this.#fixtures.locations.map((location) => ({
				...location,
				targets: location.targets.map((target) => ({
					...target,
					warehouseSync: this.#sync({ locationId: location.id, target: target.name })
				}))
			}))
		});
	}

	async navCounts(scope: Scope): Promise<NavCounts> {
		this.#location(scope);
		return this.#reply({
			catalogNodes: 42,
			failingChecks: this.#fixtures.checks.filter((c) => c.result !== 'pass').length,
			activeRuns: this.#operate.activeRunCount(),
			pausedTriggers: this.#operate.pausedTriggerCount(scope),
			activeAlerts: this.#platformEvents().filter((e) => e.active).length,
			pendingApprovals: 1
		});
	}

	async overview(scope: Scope): Promise<Overview> {
		this.#location(scope);
		const { checks, changes } = this.#fixtures;
		const runs = this.#operate.topLevelRuns(scope);
		const dayAgo = this.#createdAt - 24 * 3600_000;
		const recent = runs.filter((r) => r.startedAt && Date.parse(r.startedAt) >= dayAgo);
		const succeeded = recent.filter((r) => r.status === 'success' || r.status === 'warn').length;
		const failingChecks = checks.filter((c) => c.result === 'fail').length;
		const latest = runs.find((r) => r.endedAt) ?? null;
		return this.#reply({
			metrics: [
				{ label: 'Models', value: '42', detail: '7 views', note: '+3 this week', tone: 'success' },
				{ label: 'Runs · 24h', value: String(recent.length), detail: `${succeeded} successful`, note: `${Math.round((succeeded / Math.max(1, recent.length)) * 100)}% success` },
				{ label: 'Checks passing', value: String(checks.filter((c) => c.result === 'pass').length), detail: `of ${checks.length}`, note: `${checks.length - checks.filter((c) => c.result === 'pass').length} need attention`, tone: 'warning' },
				{ label: 'Stale', value: '2', detail: 'of 42', note: '4.8% of project', tone: 'stale' }
			],
			attention: [
				{ id: 'att-1', tone: 'error', title: 'core_build partially failed', detail: 'dim_customers · numeric value out of range', since: '18 minutes ago', href: '/runs/run-4f2a', action: 'View run' },
				{ id: 'att-2', tone: 'stale', title: '2 models are stale', detail: 'daily_revenue · customer_status', since: 'changed since the last build', href: '/catalog', action: 'View catalog' },
				{ id: 'att-3', tone: 'warning', title: 'Source freshness warning', detail: 'raw.payments is 23m behind', since: 'threshold 15 minutes', href: '/checks', action: 'View check' }
			],
			currentNodes: 40,
			staleNodes: 2,
			failingChecks,
			latestRun: latest && { id: latest.id, status: latest.status, endedAt: latest.endedAt },
			recentChanges: [...changes].sort((a, b) => b.at.localeCompare(a.at))
		});
	}

	// ---- OPERATE: delegated to the operate store (operate-store.ts) ----

	async listRuns(scope: Scope, query: RunListQuery = {}): Promise<Run[]> {
		this.#location(scope);
		return this.#operate.listRuns(scope, query);
	}

	async getRun(scope: Scope, runId: string): Promise<Run | null> {
		this.#location(scope);
		return this.#operate.getRun(scope, runId);
	}

	async getRunDetail(scope: Scope, runId: string): Promise<RunDetail | null> {
		this.#location(scope);
		return this.#operate.getRunDetail(scope, runId);
	}

	async listRunEvents(scope: Scope, runId: string, query?: { after?: number; limit?: number }): Promise<RunEventPage> {
		this.#location(scope);
		return this.#operate.listRunEvents(scope, runId, query);
	}

	async listRunStatements(scope: Scope, runId: string): Promise<RunStatement[]> {
		this.#location(scope);
		return this.#operate.listRunStatements(scope, runId);
	}

	async listRunOutput(scope: Scope, runId: string): Promise<RunOutputLine[]> {
		this.#location(scope);
		return this.#operate.listRunOutput(scope, runId);
	}

	async listQueue(scope: Scope): Promise<QueueEntry[]> {
		this.#location(scope);
		return this.#operate.listQueue(scope);
	}

	async timeline(scope: Scope, window: { since: string; until: string }): Promise<Timeline> {
		this.#location(scope);
		return this.#operate.timeline(scope, window);
	}

	async cancelRun(scope: Scope, runId: string): Promise<Run> {
		this.#location(scope);
		return this.#operate.cancelRun(scope, runId);
	}

	async rerunRun(scope: Scope, runId: string, mode: RerunMode): Promise<Run> {
		this.#location(scope);
		return this.#operate.rerunRun(scope, runId, mode);
	}

	async listSnapshotNodes(scope: Scope): Promise<SnapshotNode[]> {
		this.#location(scope);
		return this.#operate.listSnapshotNodes(scope);
	}

	async checkAdhocRun(scope: Scope, request: AdhocRunRequest): Promise<AdhocRunCheck> {
		this.#location(scope);
		return this.#operate.checkAdhocRun(scope, request);
	}

	async launchAdhocRun(scope: Scope, request: AdhocRunRequest): Promise<Run> {
		this.#location(scope);
		return this.#operate.launchAdhocRun(scope, request);
	}

	async listJobs(scope: Scope): Promise<Job[]> {
		this.#location(scope);
		return this.#operate.listJobs(scope);
	}

	async getJob(scope: Scope, key: string): Promise<JobDetail | null> {
		this.#location(scope);
		return this.#operate.getJob(scope, key);
	}

	async launchJob(scope: Scope, key: string, options?: JobLaunchOptions): Promise<Run> {
		this.#location(scope);
		return this.#operate.launchJob(scope, key, options);
	}

	async listTriggers(scope: Scope): Promise<Trigger[]> {
		this.#location(scope);
		return this.#operate.listTriggers(scope);
	}

	async getTrigger(scope: Scope, id: string): Promise<TriggerDetail | null> {
		this.#location(scope);
		return this.#operate.getTrigger(scope, id);
	}

	async setTriggerStates(scope: Scope, ids: string[], state: TriggerState, reason?: string | null): Promise<Trigger[]> {
		this.#location(scope);
		return this.#operate.setTriggerStates(scope, ids, state, reason ?? null);
	}

	async resetTriggerToDefault(scope: Scope, id: string): Promise<Trigger> {
		this.#location(scope);
		return this.#operate.resetTriggerToDefault(scope, id);
	}

	async resetSensorCursor(scope: Scope, id: string, reason?: string | null): Promise<TriggerDetail> {
		this.#location(scope);
		return this.#operate.resetSensorCursor(scope, id, reason ?? null);
	}

	// ---- end OPERATE ----

	async listChecks(scope: Scope): Promise<Check[]> {
		this.#location(scope);
		return this.#reply(structuredClone(this.#fixtures.checks));
	}

	async listConnections(scope: Scope): Promise<Connection[]> {
		this.#location(scope);
		return this.#reply(structuredClone(this.#fixtures.connections));
	}

	async listPlatformEvents(query: { activeOnly: boolean }): Promise<PlatformEvent[]> {
		const events = this.#platformEvents();
		return this.#reply(query.activeOnly ? events.filter((e) => e.active) : events);
	}

	async getWarehouseSync(scope: Scope): Promise<WarehouseSync> {
		this.#location(scope);
		return this.#reply({ ...this.#sync(scope) });
	}

	async requestWarehouseSync(scope: Scope): Promise<WarehouseSyncRequestResult> {
		this.#location(scope);
		const key = scopeKey(scope);
		const sync = this.#sync(scope);
		if (sync.state === 'running') {
			const outcome = sync.followUpQueued ? 'merged' : 'follow_up_queued';
			sync.followUpQueued = true;
			this.changes.emit(`warehouse_sync:${key}`);
			return this.#reply({ outcome, sync: { ...sync } });
		}
		this.#startSync(key, sync);
		return this.#reply({ outcome: 'started', sync: { ...sync } });
	}

	#startSync(key: string, sync: WarehouseSync) {
		sync.state = 'running';
		sync.runningSince = new Date().toISOString();
		sync.lastError = null;
		this.changes.emit(`warehouse_sync:${key}`);
		clearTimeout(this.#syncTimers.get(key));
		this.#syncTimers.set(
			key,
			setTimeout(() => {
				sync.state = 'idle';
				sync.lastSyncedAt = new Date().toISOString();
				sync.runningSince = null;
				if (sync.followUpQueued) {
					sync.followUpQueued = false;
					this.#startSync(key, sync);
				} else {
					this.changes.emit(`warehouse_sync:${key}`);
				}
			}, this.#options.syncDurationMs)
		);
	}

	#sync(scope: Scope): WarehouseSync {
		const key = scopeKey(scope);
		let sync = this.#syncs.get(key);
		if (!sync) {
			const target = this.#location(scope).targets.find((t) => t.name === scope.target)!;
			sync = { ...target.warehouseSync };
			this.#syncs.set(key, sync);
		}
		return sync;
	}

	#platformEvents(): PlatformEvent[] {
		const { platformEvents, extraPlatformEvents } = this.#fixtures;
		if (this.#options.alerts === 'none') return platformEvents.filter((e) => !e.active);
		if (this.#options.alerts === 'all') return [...extraPlatformEvents, ...platformEvents];
		return platformEvents;
	}

	#location(scope: Scope) {
		const location = this.#fixtures.locations.find((l) => l.id === scope.locationId);
		if (!location || !location.targets.some((t) => t.name === scope.target)) {
			throw new ApiError(`Unknown location or target: ${scope.locationId} / ${scope.target}`, 404);
		}
		return location;
	}

	#reply<T>(value: T): Promise<T> {
		return new Promise((resolve) => setTimeout(() => resolve(value), this.#options.latencyMs));
	}
}

function scopeKey(scope: Scope): string {
	return `${scope.locationId}/${scope.target}`;
}
