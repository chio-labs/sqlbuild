import type {
	AdhocRunCheck,
	AdhocRunRequest,
	Bootstrap,
	Check,
	Connection,
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
} from './types';
import type { ChangeSubscription } from './signals';
import type { PlatformApi } from './platform-client';

/**
 * Everything the UI reads from or asks of the server.
 *
 * Pages depend on this interface only. The mock implementation stands in until
 * the server's OpenAPI client exists; that client is wrapped to implement the
 * same interface.
 */
export interface ApiClient extends PlatformApi {
	bootstrap(): Promise<Bootstrap>;

	navCounts(scope: Scope): Promise<NavCounts>;
	overview(scope: Scope): Promise<Overview>;

	// ---- OPERATE: runs, queue, run panel, jobs and triggers (types/operate.ts) ----
	listRuns(scope: Scope, query?: RunListQuery): Promise<Run[]>;
	getRun(scope: Scope, runId: string): Promise<Run | null>;
	/** Nodes, children, liveness, cancel progress and provenance for one run. */
	getRunDetail(scope: Scope, runId: string): Promise<RunDetail | null>;
	/** Recall events and scheduler facts in storage order, paged by `after`. */
	listRunEvents(scope: Scope, runId: string, query?: { after?: number; limit?: number }): Promise<RunEventPage>;
	listRunStatements(scope: Scope, runId: string): Promise<RunStatement[]>;
	listRunOutput(scope: Scope, runId: string): Promise<RunOutputLine[]>;
	/** Queued runs in claim order, with why each one waits. */
	listQueue(scope: Scope): Promise<QueueEntry[]>;
	timeline(scope: Scope, window: { since: string; until: string }): Promise<Timeline>;
	/** Writes a `cancel_requested` fact; the scheduler then signals the worker. */
	cancelRun(scope: Scope, runId: string): Promise<Run>;
	rerunRun(scope: Scope, runId: string, mode: RerunMode): Promise<Run>;

	listSnapshotNodes(scope: Scope): Promise<SnapshotNode[]>;
	/** The server's pre-launch check: resolution, write set and authorization. */
	checkAdhocRun(scope: Scope, request: AdhocRunRequest): Promise<AdhocRunCheck>;
	launchAdhocRun(scope: Scope, request: AdhocRunRequest): Promise<Run>;

	listJobs(scope: Scope): Promise<Job[]>;
	getJob(scope: Scope, key: string): Promise<JobDetail | null>;
	launchJob(scope: Scope, key: string, options?: JobLaunchOptions): Promise<Run>;

	listTriggers(scope: Scope): Promise<Trigger[]>;
	getTrigger(scope: Scope, id: string): Promise<TriggerDetail | null>;
	/** One audited state fact per trigger. */
	setTriggerStates(scope: Scope, ids: string[], state: TriggerState, reason?: string | null): Promise<Trigger[]>;
	resetTriggerToDefault(scope: Scope, id: string): Promise<Trigger>;
	resetSensorCursor(scope: Scope, id: string, reason?: string | null): Promise<TriggerDetail>;
	// ---- end OPERATE ----

	listChecks(scope: Scope): Promise<Check[]>;
	listConnections(scope: Scope): Promise<Connection[]>;

	listPlatformEvents(query: { activeOnly: boolean }): Promise<PlatformEvent[]>;

	getWarehouseSync(scope: Scope): Promise<WarehouseSync>;
	/** Coalescing: merges into a running sync, with at most one follow-up queued. */
	requestWarehouseSync(scope: Scope): Promise<WarehouseSyncRequestResult>;

	/** Live "changed" signals (SSE in the server client); consumers refetch. */
	changes: ChangeSubscription;
}

export class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
		this.name = 'ApiError';
	}
}
