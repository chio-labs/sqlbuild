import type { ApiClient } from './client';
import { MockApiClient, type MockOptions } from './mock/mock-client';
import type { BuiltInRole } from './types';

export type { ApiClient } from './client';
export { ApiError } from './client';
export * from './types';
export * from './signals';
export { hasCapability, hasAnyCapability, ADMIN_CAPABILITIES } from './capabilities';

const ROLES: readonly BuiltInRole[] = ['viewer', 'operator', 'developer', 'admin'];
const EVENTS: readonly NonNullable<MockOptions['events']>[] = ['default', 'none', 'all'];
const LIVE: readonly NonNullable<MockOptions['connection']>[] = ['live', 'reconnecting', 'offline'];

/**
 * The client the app uses. Until the server API exists this is the mock;
 * `?as=<role>`, `?events=none|all` and `?live=reconnecting|offline` on first
 * load adjust the mock for demos.
 */
export function createClient(search: URLSearchParams): ApiClient {
	const role = search.get('as');
	const events = search.get('events');
	const live = search.get('live');
	return new MockApiClient({
		role: ROLES.find((r) => r === role),
		events: EVENTS.find((e) => e === events),
		connection: LIVE.find((l) => l === live)
	});
}
