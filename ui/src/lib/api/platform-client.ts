import type {
	AccessExplanation,
	AccessQuery,
	Account,
	ApiToken,
	ApiTokenRequest,
	AuditEntry,
	AuditQuery,
	ChannelTestResult,
	ConnectionTest,
	ConnectionsOverview,
	IssuedToken,
	LocationDetail,
	LocationSummary,
	LocationToken,
	MaintenanceHistory,
	PlatformEventQuery,
	PlatformEventRecord,
	PlatformHealth,
	RoleApproval,
	RoleAssignment,
	RoleAssignmentRequest,
	RoleDefinition,
	Scope,
	ServerSettings
} from './types';

/**
 * Platform (alerts, locations, connections, maintenance) and admin (users,
 * tokens, roles, audit, settings) endpoints. Part of `ApiClient`.
 *
 * Mutations are audited server-side; the capability noted on each is the
 * server's check, mirrored in the UI only to hide or disable controls.
 */
export interface PlatformApi {
	// ---- alerts ----
	platformHealth(): Promise<PlatformHealth>;
	listPlatformEventHistory(query?: PlatformEventQuery): Promise<PlatformEventRecord[]>;
	/** `connection.test` */
	testChannel(scope: Scope, name: string): Promise<ChannelTestResult>;

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

	// ---- connections ----
	connections(scope: Scope): Promise<ConnectionsOverview>;

	// ---- maintenance ----
	maintenanceHistory(scope: Scope): Promise<MaintenanceHistory>;

	// ---- users and tokens ----
	/** `user.manage` */
	listAccounts(): Promise<Account[]>;
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
