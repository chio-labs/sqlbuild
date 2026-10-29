import type { ApiClient } from '../client';
import { ApiError } from '../client';
import { LocalChangeBus } from '../signals';
import type {
	Bootstrap,
	BuiltInRole,
	Capability,
	Check,
	Connection,
	CurrentUser,
	Job,
	NavCounts,
	Overview,
	PlatformEvent,
	Run,
	RunListQuery,
	Scope,
	Timeline,
	TimelineBar,
	Trigger,
	TriggerState,
	WarehouseSync,
	WarehouseSyncRequestResult
} from '../types';
import { createFixtures, DEMO_USER, ROLE_CAPABILITIES, type Fixtures } from './fixtures';
import { buildTimelineBars, TIMELINE_JOB_KEYS } from './timeline';

export type MockOptions = {
	role?: BuiltInRole;
	/** `default` shows two warnings; `none` is all clear; `all` adds critical events. */
	alerts?: 'default' | 'none' | 'all';
	/** Simulated request latency in milliseconds. */
	latencyMs?: number;
	/** How long a simulated warehouse sync takes. */
	syncDurationMs?: number;
};

const ACTIVE_RUN = new Set(['queued', 'launched', 'running', 'unresponsive']);

/** In-memory `ApiClient` with neutral example data. Mutations persist per page load. */
export class MockApiClient implements ApiClient {
	readonly changes = new LocalChangeBus();
	readonly #options: Required<MockOptions>;
	readonly #fixtures: Fixtures;
	readonly #createdAt = Date.now();
	/** Trigger state per scope, so pausing in one target doesn't leak into another. */
	readonly #triggers = new Map<string, Trigger[]>();
	readonly #syncs = new Map<string, WarehouseSync>();
	readonly #syncTimers = new Map<string, ReturnType<typeof setTimeout>>();
	#timelineBars: TimelineBar[] | null = null;

	constructor(options: MockOptions = {}) {
		this.#options = {
			role: options.role ?? 'admin',
			alerts: options.alerts ?? 'default',
			latencyMs: options.latencyMs ?? 120,
			syncDurationMs: options.syncDurationMs ?? 8000
		};
		this.#fixtures = createFixtures(this.#createdAt);
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
		const triggers = this.#triggersFor(scope);
		return this.#reply({
			catalogNodes: 42,
			failingChecks: this.#fixtures.checks.filter((c) => c.result !== 'pass').length,
			activeRuns: this.#fixtures.runs.filter((r) => ACTIVE_RUN.has(r.status)).length,
			pausedTriggers: triggers.filter((t) => t.state === 'paused').length,
			activeAlerts: this.#platformEvents().filter((e) => e.active).length,
			pendingApprovals: 1
		});
	}

	async overview(scope: Scope): Promise<Overview> {
		this.#location(scope);
		const { runs, checks, changes } = this.#fixtures;
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
				{ id: 'att-1', tone: 'error', title: 'nightly_build partially failed', detail: 'hourly_activity_ctx · expression_is_true', since: '18 minutes ago', href: '/runs/run-4f2a', action: 'View run' },
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

	async listRuns(scope: Scope, query: RunListQuery = {}): Promise<Run[]> {
		this.#location(scope);
		let runs = this.#fixtures.runs.map((run) => ({ ...run, locationId: scope.locationId, target: scope.target }));
		if (query.jobKey) runs = runs.filter((r) => r.jobKey === query.jobKey);
		if (query.statuses?.length) runs = runs.filter((r) => query.statuses!.includes(r.status));
		if (query.limit) runs = runs.slice(0, query.limit);
		return this.#reply(runs);
	}

	async getRun(scope: Scope, runId: string): Promise<Run | null> {
		const runs = await this.listRuns(scope);
		return runs.find((r) => r.id === runId) ?? null;
	}

	async timeline(scope: Scope, window: { since: string; until: string }): Promise<Timeline> {
		this.#location(scope);
		this.#timelineBars ??= [
			...buildTimelineBars(this.#createdAt),
			...this.#fixtures.runs
				.filter((r) => r.jobKey && r.startedAt)
				.map(
					(r): TimelineBar => ({
						runId: r.id,
						jobKey: r.jobKey!,
						kind: r.kind,
						status: r.status,
						start: r.startedAt!,
						end: r.endedAt ?? new Date(this.#createdAt).toISOString()
					})
				)
		];
		const bars = this.#timelineBars.filter((b) => b.end > window.since && b.start < window.until);
		const jobKeys = [...new Set([...TIMELINE_JOB_KEYS, ...this.#fixtures.jobs.map((j) => j.key)])];
		return this.#reply({ now: new Date(this.#createdAt).toISOString(), jobKeys, bars });
	}

	async listJobs(scope: Scope): Promise<Job[]> {
		this.#location(scope);
		return this.#reply(structuredClone(this.#fixtures.jobs));
	}

	async getJob(scope: Scope, key: string): Promise<Job | null> {
		const jobs = await this.listJobs(scope);
		return jobs.find((j) => j.key === key) ?? null;
	}

	async listTriggers(scope: Scope): Promise<Trigger[]> {
		this.#location(scope);
		return this.#reply(structuredClone(this.#triggersFor(scope)));
	}

	async setTriggerState(scope: Scope, name: string, state: TriggerState): Promise<Trigger> {
		this.#require('trigger.toggle');
		const triggers = this.#triggersFor(scope);
		const trigger = triggers.find((t) => t.name === name);
		if (!trigger) throw new ApiError(`Unknown trigger ${name}`, 404);
		trigger.state = state;
		trigger.nextTickAt = state === 'paused' || !trigger.cron ? null : new Date(Date.now() + 15 * 60_000).toISOString();
		this.changes.emit('triggers');
		return this.#reply(structuredClone(trigger));
	}

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

	#triggersFor(scope: Scope): Trigger[] {
		const key = scopeKey(scope);
		let triggers = this.#triggers.get(key);
		if (!triggers) {
			triggers = structuredClone(this.#fixtures.triggers);
			// Development targets start with every trigger paused.
			if (scope.target === 'dev') {
				for (const t of triggers) {
					t.state = 'paused';
					t.nextTickAt = null;
				}
			}
			this.#triggers.set(key, triggers);
		}
		return triggers;
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

	#require(capability: Capability) {
		if (!ROLE_CAPABILITIES[this.#options.role].includes(capability)) {
			throw new ApiError(`Missing permission: ${capability}`, 403);
		}
	}

	#reply<T>(value: T): Promise<T> {
		return new Promise((resolve) => setTimeout(() => resolve(value), this.#options.latencyMs));
	}
}

function scopeKey(scope: Scope): string {
	return `${scope.locationId}/${scope.target}`;
}
