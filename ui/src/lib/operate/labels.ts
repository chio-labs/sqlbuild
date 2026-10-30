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
	coalesce: 'At most one run waits; new requests merge into it instead of starting another run',
	queue: 'Every request gets its own run; they run one after another, in order',
	allow: 'Can run alongside other runs of this job, as long as they don’t update the same data'
};

/** Short plain wording of an overlap policy; the policy name goes in a tooltip. */
export const overlapPlain: Record<OverlapPolicy, string> = {
	coalesce: 'Merge new requests',
	queue: 'One run per request, in order',
	allow: 'Can run side by side'
};

export const onFailureLabel: Record<OnFailure, string> = {
	skip_dependents: 'skip_dependents',
	skip_downstream_jobs: 'skip_downstream_jobs',
	stop_group: 'stop_group'
};

export const onFailureHelp: Record<OnFailure, string> = {
	skip_dependents: 'When a node fails, only what depends on it is skipped, even in other jobs',
	skip_downstream_jobs: 'When a job fails, the jobs after it are skipped',
	stop_group: 'Any failure stops the whole group'
};

/** Short plain wording of an on-failure policy. */
export const onFailurePlain: Record<OnFailure, string> = {
	skip_dependents: 'Skip what depends on a failure',
	skip_downstream_jobs: 'Skip later jobs',
	stop_group: 'Stop the group'
};

export type WaitPart = { text: string; href?: string; code?: boolean };

/** `run-4f2a` → `4f2a`: the short form shown in lists; the full ID stays in links and copies. */
export function shortRunId(id: string): string {
	return id.replace(/^run-/, '');
}

/** A concurrency group's slots in words, e.g. `warehouse_heavy` → `warehouse heavy`, `target:prod` → `prod target`. */
export function slotLabel(group: string): string {
	if (group.startsWith('target:')) return `${group.slice('target:'.length)} target`;
	return group.replace(/[_-]+/g, ' ');
}

const runLink = (id: string): WaitPart => ({ text: `run ${shortRunId(id)}`, href: `/runs/${id}` });

/** A queue wait as a plain sentence of linkable parts, e.g. "Waiting: run 7f3a is updating orders". */
export function describeWait(wait: QueueWait): WaitPart[] {
	switch (wait.kind) {
		case 'write_claim':
			return [
				{ text: 'Waiting: ' },
				runLink(wait.runId),
				{ text: ' is updating ' },
				{ text: wait.nodeKey, href: `/catalog/${wait.nodeKey}` },
				...(wait.otherNodes ? [{ text: ` and ${wait.otherNodes} more` }] : [])
			];
		case 'concurrency_group':
			return [
				{ text: `Waiting: ${wait.holders.length} of ${wait.limit} ${slotLabel(wait.group)} slot${wait.limit === 1 ? '' : 's'} in use` },
				...(wait.holders.length ? [{ text: ' (by ' }, ...wait.holders.flatMap((id, i) => [...(i ? [{ text: ', ' }] : []), runLink(id)]), { text: ')' }] : [])
			];
		case 'priority':
			return [
				{ text: `Waiting: behind ${wait.aheadRunIds.length} earlier run${wait.aheadRunIds.length === 1 ? '' : 's'} (` },
				...wait.aheadRunIds.flatMap((id, i) => [...(i ? [{ text: ', ' }] : []), runLink(id)]),
				{ text: ')' }
			];
		case 'upstream_job':
			return [{ text: 'Waiting for ' }, { text: wait.jobKey || shortRunId(wait.runId), href: `/runs/${wait.runId}` }, { text: ' to finish first' }];
		case 'group_parent':
			return [{ text: 'Waiting for its group run ' }, { text: shortRunId(wait.runId), href: `/runs/${wait.runId}` }, { text: ' to start' }];
	}
}

/** The wait as one plain line without links, for status lines and summaries. */
export function waitText(wait: QueueWait): string {
	if (wait.kind === 'concurrency_group') return `Waiting: ${wait.holders.length} of ${wait.limit} ${slotLabel(wait.group)} slot${wait.limit === 1 ? '' : 's'} in use`;
	if (wait.kind === 'priority') return `Waiting: behind ${wait.aheadRunIds.length} earlier run${wait.aheadRunIds.length === 1 ? '' : 's'}`;
	return describeWait(wait)
		.map((p) => p.text)
		.join('');
}

/** The scheduler's own name for a wait, for tooltips and debugging. */
export function waitTechnical(wait: QueueWait): string {
	switch (wait.kind) {
		case 'write_claim':
			return `write claim held by ${wait.runId} on ${wait.nodeKey}${wait.otherNodes ? ` (+${wait.otherNodes})` : ''}`;
		case 'concurrency_group':
			return `concurrency group ${wait.group} full (${wait.holders.length}/${wait.limit}): ${wait.holders.join(', ')}`;
		case 'priority':
			return `behind ${wait.aheadRunIds.join(', ')} for the same slot (priority, then queue order)`;
		case 'upstream_job':
			return `upstream job ${wait.jobKey} (${wait.runId}) still active`;
		case 'group_parent':
			return `group run ${wait.runId} not claimed yet`;
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
