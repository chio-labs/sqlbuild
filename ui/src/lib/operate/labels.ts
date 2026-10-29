// Labels and tones for the OPERATE area's vocabulary. Pure; no side effects.

import type {
	LivenessState,
	OnFailure,
	OverlapPolicy,
	QueueWait,
	RunCost,
	RunEvent,
	RunNodeStatus,
	SensorEvaluationOutcome,
	TickOutcome,
	TriggerKind,
	TriggerStateEventKind
} from '$lib/api';

export const nodeStatusTone: Record<RunNodeStatus, string> = {
	pending: 'var(--sb-text-faint)',
	running: 'var(--sb-running)',
	success: 'var(--sb-success)',
	warn: 'var(--sb-warning)',
	failed: 'var(--sb-error)',
	skipped: 'var(--sb-text-faint)',
	cancelled: 'var(--sb-text-faint)',
	not_run: 'var(--sb-text-faint)'
};

export const nodeStatusLabel: Record<RunNodeStatus, string> = {
	pending: 'Pending',
	running: 'Running',
	success: 'Succeeded',
	warn: 'Warned',
	failed: 'Failed',
	skipped: 'Skipped',
	cancelled: 'Cancelled',
	not_run: 'Not run'
};

/** Rail order: problems and live work first. */
export const NODE_STATUS_ORDER: RunNodeStatus[] = ['failed', 'running', 'warn', 'success', 'skipped', 'cancelled', 'not_run', 'pending'];

export const livenessLabel: Record<LivenessState, string> = {
	healthy: 'Heartbeating',
	unresponsive: 'Unresponsive',
	presumed_failed: 'Presumed failed',
	never_started: 'Never started',
	exited: 'Exited'
};

export const livenessTone: Record<LivenessState, string> = {
	healthy: 'var(--sb-success)',
	unresponsive: 'var(--sb-warning)',
	presumed_failed: 'var(--sb-error)',
	never_started: 'var(--sb-error)',
	exited: 'var(--sb-text-faint)'
};

export function formatCost(cost: RunCost | null): string {
	if (!cost) return '—';
	return `${cost.value < 0.01 ? cost.value.toFixed(4) : cost.value.toFixed(3)} cr`;
}

export const overlapLabel: Record<OverlapPolicy, string> = {
	coalesce: 'coalesce',
	queue: 'queue',
	allow: 'allow'
};

export const overlapHelp: Record<OverlapPolicy, string> = {
	coalesce: 'At most one run waits; further ticks merge into it and are recorded as covered',
	queue: 'Every request gets its own run, in order',
	allow: 'Runs alongside existing runs, still subject to the write-set rule'
};

export const onFailureLabel: Record<OnFailure, string> = {
	skip_dependents: 'skip_dependents',
	skip_downstream_jobs: 'skip_downstream_jobs',
	stop_group: 'stop_group'
};

export const onFailureHelp: Record<OnFailure, string> = {
	skip_dependents: 'Only dependents of a failed node are skipped, across jobs',
	skip_downstream_jobs: 'Jobs downstream of a failed job are skipped',
	stop_group: 'Any failure stops the group'
};

export type WaitPart = { text: string; href?: string; code?: boolean };

/** A queue wait as a sentence of linkable parts. */
export function describeWait(wait: QueueWait): WaitPart[] {
	switch (wait.kind) {
		case 'write_claim':
			return [
				{ text: 'Write claim held by ' },
				{ text: wait.runId, href: `/runs/${wait.runId}`, code: true },
				...(wait.jobKey ? [{ text: ` (${wait.jobKey})` }] : []),
				{ text: ' on ' },
				{ text: wait.nodeKey, href: `/catalog/${wait.nodeKey}`, code: true },
				...(wait.otherNodes ? [{ text: ` and ${wait.otherNodes} more node${wait.otherNodes === 1 ? '' : 's'}` }] : [])
			];
		case 'concurrency_group':
			return [
				{ text: 'Concurrency group ' },
				{ text: wait.group, code: true },
				{ text: ` is full (${wait.holders.length}/${wait.limit}): ` },
				...wait.holders.flatMap((id, i) => [...(i ? [{ text: ', ' }] : []), { text: id, href: `/runs/${id}`, code: true }])
			];
		case 'priority':
			return [
				{ text: 'Behind ' },
				...wait.aheadRunIds.flatMap((id, i) => [...(i ? [{ text: ', ' }] : []), { text: id, href: `/runs/${id}`, code: true }]),
				{ text: ' for the same slot (higher priority or queued earlier)' }
			];
		case 'upstream_job':
			return [{ text: 'Waiting for ' }, { text: wait.jobKey || wait.runId, href: `/runs/${wait.runId}`, code: true }, { text: ' to finish first' }];
		case 'group_parent':
			return [{ text: 'Group run ' }, { text: wait.runId, href: `/runs/${wait.runId}`, code: true }, { text: ` (${wait.jobKey}) hasn't been claimed yet` }];
	}
}

export const tickOutcomeTone: Record<TickOutcome, string> = {
	requested: 'var(--sb-success)',
	skipped: 'var(--sb-text-faint)',
	covered: 'var(--sb-running)',
	failed: 'var(--sb-error)'
};

export const tickOutcomeText: Record<TickOutcome, string> = {
	requested: 'requested',
	skipped: 'skipped',
	covered: 'covered',
	failed: 'failed'
};

export const evaluationTone: Record<SensorEvaluationOutcome, string> = {
	requested: 'var(--sb-running)',
	completed: 'var(--sb-success)',
	failed: 'var(--sb-error)',
	timed_out: 'var(--sb-error)',
	abandoned: 'var(--sb-warning)'
};

export const triggerKindLabel: Record<TriggerKind, string> = {
	cron_schedule: 'Cron schedule',
	calendar_schedule: 'Calendar schedule',
	job_sensor: 'Job sensor',
	node_sensor: 'Node sensor',
	platform_sensor: 'Platform-event sensor',
	custom_sensor: 'Custom @sensor'
};

export const stateEventLabel: Record<TriggerStateEventKind, string> = {
	enabled: 'Enabled',
	paused: 'Paused',
	reset_to_default: 'Reset to code default',
	cursor_set: 'Cursor set',
	cursor_reset: 'Cursor reset'
};

export const eventTone = (event: RunEvent): string =>
	event.level === 'error'
		? 'var(--sb-error)'
		: event.level === 'warn'
			? 'var(--sb-warning)'
			: event.producer === 'scheduler'
				? 'var(--sb-stale)'
				: event.type.endsWith('_completed')
					? 'var(--sb-success)'
					: 'var(--sb-running)';

/** e.g. `42s`, `3m 05s`, `2h 10m`. */
export function formatSeconds(seconds: number): string {
	const s = Math.max(0, Math.round(seconds));
	if (s < 60) return `${s}s`;
	if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
	return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

/** `HH:MM:SS.mmm` local time for event tables. */
export function clockTime(iso: string): string {
	const d = new Date(iso);
	const pad = (n: number, w = 2) => String(n).padStart(w, '0');
	return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}
