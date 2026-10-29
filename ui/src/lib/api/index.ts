import type { ApiClient } from './client';
import { MockApiClient, type MockOptions } from './mock/mock-client';
import type { BuiltInRole } from './types';

export type { ApiClient } from './client';
export { ApiError } from './client';
export * from './types';
export * from './signals';
export { hasCapability, hasAnyCapability, ADMIN_CAPABILITIES } from './capabilities';

const ROLES: readonly BuiltInRole[] = ['viewer', 'operator', 'developer', 'admin'];
const ALERTS: readonly NonNullable<MockOptions['alerts']>[] = ['default', 'none', 'all'];

/**
 * The client the app uses. Until the server API exists this is the mock;
 * `?as=<role>` and `?alerts=none|all` on first load adjust the mock for demos.
 */
export function createClient(search: URLSearchParams): ApiClient {
	const role = search.get('as');
	const alerts = search.get('alerts');
	return new MockApiClient({
		role: ROLES.find((r) => r === role),
		alerts: ALERTS.find((a) => a === alerts)
	});
}
