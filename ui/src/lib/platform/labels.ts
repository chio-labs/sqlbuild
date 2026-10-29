// Labels, tones and pure helpers shared by the Platform and Admin pages.

import type {
	AssignmentScope,
	LocationHealth,
	Location,
	PlatformEventKind,
	PlatformEventLink,
	PlatformEventSeverity,
	RelationName,
	TestOutcome,
	TokenState
} from '$lib/api';

export const healthTone: Record<LocationHealth, string> = {
	healthy: 'var(--sb-success)',
	degraded: 'var(--sb-warning)',
	falling_back: 'var(--sb-warning)',
	broken: 'var(--sb-error)'
};

export const healthLabel: Record<LocationHealth, string> = {
	healthy: 'Healthy',
	degraded: 'Degraded',
	falling_back: 'Falling back',
	broken: 'Broken'
};

export const eventKindLabel: Record<PlatformEventKind, string> = {
	tick_overdue: 'Tick overdue',
	scheduler_no_leader: 'No scheduler leader',
	location_broken: 'Location broken',
	launch_failed: 'Launch failed',
	heartbeat: 'Heartbeat'
};

export const severityTone: Record<PlatformEventSeverity, string> = {
	critical: 'var(--sb-error)',
	warning: 'var(--sb-warning)',
	info: 'var(--sb-text-faint)'
};

export const testTone: Record<TestOutcome, string> = { ok: 'var(--sb-success)', failed: 'var(--sb-error)' };
export const testLabel: Record<TestOutcome, string> = { ok: 'Passed', failed: 'Failed' };

export const tokenTone: Record<TokenState, string> = {
	active: 'var(--sb-success)',
	revoked: 'var(--sb-text-faint)',
	expired: 'var(--sb-text-faint)'
};
export const tokenLabel: Record<TokenState, string> = { active: 'Active', revoked: 'Revoked', expired: 'Expired' };

/** `SCHEMA.NAME`, or `DB.SCHEMA.NAME` when `withDatabase`. */
export function formatRelation(relation: RelationName, withDatabase = false): string {
	const parts = withDatabase && relation.database ? [relation.database, relation.schema, relation.name] : [relation.schema, relation.name];
	return parts.join('.');
}

/** Short image ID, e.g. `sha256:4be1c07d9a52` → `4be1c07`. */
export function shortImage(imageId: string | null): string {
	if (!imageId) return '—';
	return imageId.replace(/^sha256:/, '').slice(0, 7);
}

export function locationName(locations: readonly Location[] | undefined, locationId: string | null): string {
	if (!locationId) return 'All locations';
	return locations?.find((l) => l.id === locationId)?.name ?? locationId;
}

/** e.g. `All locations`, `waffle-shop · all targets`, `waffle-shop / prod`. */
export function formatAssignmentScope(scope: AssignmentScope, locations: readonly Location[] | undefined): string {
	if (!scope.locationId) return scope.target ? `All locations / ${scope.target}` : 'Installation';
	const name = locationName(locations, scope.locationId);
	return scope.target ? `${name} / ${scope.target}` : `${name} · all targets`;
}

/** Deep link for an event link; scoped pages carry `?location=&target=`. */
export function eventLinkHref(link: PlatformEventLink): string {
	if (link.kind === 'location') return `/locations/${link.id}`;
	const scope = `location=${encodeURIComponent(link.locationId)}&target=${encodeURIComponent(link.target)}`;
	if (link.kind === 'trigger') return `/triggers?${scope}`;
	if (link.kind === 'job') return `/jobs/${encodeURIComponent(link.key)}?${scope}`;
	return `/runs/${encodeURIComponent(link.id)}?${scope}`;
}

export function eventLinkLabel(link: PlatformEventLink, locations: readonly Location[] | undefined): string {
	if (link.kind === 'location') return `Location ${locationName(locations, link.id)}`;
	if (link.kind === 'trigger') return `Trigger ${link.name}`;
	if (link.kind === 'job') return `Job ${link.key}`;
	return `Run ${link.id}`;
}

export function errorMessage(error: unknown): string {
	return error instanceof Error ? error.message : String(error);
}
