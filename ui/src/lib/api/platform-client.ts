import type {
	AccessExplanation,
	AccessQuery,
	Account,
	ApiToken,
	ApiTokenRequest,
	AuditEntry,
	AuditQuery,
	ConnectionTest,
	IssuedToken,
	LocationDetail,
	LocationSummary,
	LocationToken,
	MaintenanceHistory,
	PlatformEventQuery,
	PlatformEventRecord,
	PlatformHealth,
	ProviderConnection,
	RoleApproval,
	RoleAssignment,
	RoleAssignmentRequest,
	RoleDefinition,
	Scope,
	ServerSettings,
	ServiceAccountRequest,
	WarehouseConnection
} from './types';

/**
 * Platform (server status, locations, connections, providers, maintenance)
 * and admin (users, service accounts, roles, audit, settings) endpoints.
 * Part of `ApiClient`.
 *
 * Mutations are audited server-side; the capability noted on each is the
 * server's check, mirrored in the UI only to hide or disable controls.
 */
export interface PlatformApi {
	// ---- server status and problems (shown on Locations) ----
	/** Scheduler, server replicas, heartbeat and event forwarding. */
	platformHealth(): Promise<PlatformHealth>;
	/** Problems recorded as platform events, newest first; by location, or server-wide with `locationId: null`. */
	listPlatformEventHistory(query?: PlatformEventQuery): Promise<PlatformEventRecord[]>;

	// ---- locations ----
	listLocations(): Promise<LocationSummary[]>;
	getLocation(locationId: string): Promise<LocationDetail | null>;
	/** Runs `sqb debug`'s connection test in the location. `connection.test` */
	testConnection(scope: Scope, connection: string): Promise<ConnectionTest>;
	/** `location.manage` */
	listLocationTokens(locationId: string): Promise<LocationToken[]>;
	/** `location.manage` */
	createLocationToken(locationId: string): Promise<IssuedToken<LocationToken>>;
	/** Issues a new token and revokes the old one. `location.manage` */
	rotateLocationToken(tokenId: string): Promise<IssuedToken<LocationToken>>;
	/** `location.manage` */
	revokeLocationToken(tokenId: string): Promise<LocationToken>;

	// ---- warehouse connections and providers ----
	/** Warehouse connections of the selected target. */
	listWarehouseConnections(scope: Scope): Promise<WarehouseConnection[]>;
	/** Providers declared in the project, with where each one is used. Read-only. */
	listProviders(scope: Scope): Promise<ProviderConnection[]>;

	// ---- maintenance ----
	maintenanceHistory(scope: Scope): Promise<MaintenanceHistory>;

	// ---- users and tokens ----
	/** `user.manage` */
	listAccounts(): Promise<Account[]>;
	/** Blocks sign-in and revokes the account's sessions. You can't disable yourself. `user.manage` */
	disableAccount(name: string): Promise<Account>;
	/** Lets a disabled account sign in again. Sessions revoked on disable stay revoked; its unrevoked API tokens work again. `user.manage` */
	enableAccount(name: string): Promise<Account>;
	/** A non-person account that signs in with API tokens only. `user.manage` */
	createServiceAccount(request: ServiceAccountRequest): Promise<Account>;
	/** `token.manage` */
	listApiTokens(): Promise<ApiToken[]>;
	/** `token.manage` */
	createApiToken(request: ApiTokenRequest): Promise<IssuedToken<ApiToken>>;
	/** `token.manage` */
	rotateApiToken(tokenId: string): Promise<IssuedToken<ApiToken>>;
	/** `token.manage` */
	revokeApiToken(tokenId: string): Promise<ApiToken>;

	// ---- roles and approvals ----
	/** `role.assign` */
	listRoles(locationId: string): Promise<RoleDefinition[]>;
	/** `role.assign` */
	listRoleAssignments(): Promise<RoleAssignment[]>;
	/** `role.assign` */
	createRoleAssignment(request: RoleAssignmentRequest): Promise<RoleAssignment>;
	/** Manual assignments only; SSO-derived ones follow the group mapping. `role.assign` */
	deleteRoleAssignment(assignmentId: string): Promise<void>;
	/** `role.assign` */
	listRoleApprovals(): Promise<RoleApproval[]>;
	/** `role.assign` */
	decideRoleApproval(approvalId: string, decision: 'approve' | 'reject', note: string): Promise<RoleApproval>;

	// ---- audit and access ----
	/** `audit.view` */
	listAuditEntries(query?: AuditQuery): Promise<AuditEntry[]>;
	/** Explaining another principal requires `role.assign` or `audit.view`. */
	explainAccess(query: AccessQuery): Promise<AccessExplanation>;

	// ---- settings ----
	serverSettings(): Promise<ServerSettings>;
}
