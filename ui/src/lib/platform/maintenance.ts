// Pure projections over synced migration, old-name view and janitor state.

import type { MigrationDecision, MigrationEvent, OldNameEventType, OldNameView } from '$lib/api';

export type OldNameStatus = 'pending' | 'not_kept' | 'live' | 'expired' | 'dropped';

/** Current state of one compatibility view, derived from its append-only steps. */
export function oldNameStatus(view: OldNameView, now: number): OldNameStatus {
	const has = (type: OldNameEventType) => view.steps.some((s) => s.eventType === type);
	if (has('view_dropped')) return 'dropped';
	if (has('view_created')) return view.expiresAt && Date.parse(view.expiresAt) <= now ? 'expired' : 'live';
	if (view.retention === 'false') return 'not_kept';
	return 'pending';
}

export const oldNameStatusLabel: Record<OldNameStatus, string> = {
	pending: 'Pending',
	not_kept: 'No view kept',
	live: 'Live',
	expired: 'Expired',
	dropped: 'Dropped'
};

export const oldNameStatusTone: Record<OldNameStatus, string> = {
	pending: 'var(--sb-running)',
	not_kept: 'var(--sb-text-faint)',
	live: 'var(--sb-success)',
	expired: 'var(--sb-warning)',
	dropped: 'var(--sb-text-faint)'
};

export const oldNameStepLabel: Record<OldNameEventType, string> = {
	required: 'Required',
	origin_archived: 'Old table archived',
	view_created: 'View created',
	view_dropped: 'View dropped'
};

export const decisionLabel: Record<MigrationDecision, string> = {
	migrate: 'Migrated',
	redo: 'Redone',
	superseded_replace: 'Superseded replace',
	forced_replace: 'Forced replace',
	renamed: 'Renamed'
};

/** A move changes schema (or database); a rename keeps it. */
export function migrationKind(event: MigrationEvent): 'rename' | 'move' {
	const { origin, destination } = event;
	return origin.schema !== destination.schema || origin.database !== destination.database ? 'move' : 'rename';
}
