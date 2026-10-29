import type {
	Bootstrap,
	Check,
	Connection,
	Job,
	NavCounts,
	Overview,
	PlatformEvent,
	Run,
	RunListQuery,
	Scope,
	Timeline,
	Trigger,
	TriggerState,
	WarehouseSync,
	WarehouseSyncRequestResult
} from './types';
import type { ChangeSubscription } from './signals';

/**
 * Everything the UI reads from or asks of the server.
 *
 * Pages depend on this interface only. The mock implementation stands in until
 * the server's OpenAPI client exists; that client is wrapped to implement the
 * same interface.
 */
export interface ApiClient {
	bootstrap(): Promise<Bootstrap>;

	navCounts(scope: Scope): Promise<NavCounts>;
	overview(scope: Scope): Promise<Overview>;

	listRuns(scope: Scope, query?: RunListQuery): Promise<Run[]>;
	getRun(scope: Scope, runId: string): Promise<Run | null>;
	timeline(scope: Scope, window: { since: string; until: string }): Promise<Timeline>;

	listJobs(scope: Scope): Promise<Job[]>;
	getJob(scope: Scope, key: string): Promise<Job | null>;

	listTriggers(scope: Scope): Promise<Trigger[]>;
	setTriggerState(scope: Scope, name: string, state: TriggerState): Promise<Trigger>;

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
