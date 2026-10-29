import type { CheckResult, NodeCounts, RunKind, RunOrigin, RunStatus, TickOutcome, TriggerState } from '$lib/api/types';

export const runStatusTone: Record<RunStatus, string> = {
	queued: 'var(--sb-text-faint)',
	launched: 'var(--sb-running)',
	running: 'var(--sb-running)',
	unresponsive: 'var(--sb-warning)',
	success: 'var(--sb-success)',
	warn: 'var(--sb-warning)',
	partial: 'color-mix(in srgb, var(--sb-error) 55%, var(--sb-warning))',
	failed: 'var(--sb-error)',
	cancelled: 'var(--sb-text-faint)',
	presumed_failed: 'var(--sb-error)'
};

export const runStatusLabel: Record<RunStatus, string> = {
	queued: 'Queued',
	launched: 'Launched',
	running: 'Running',
	unresponsive: 'Unresponsive',
	success: 'Success',
	warn: 'Warning',
	partial: 'Partial',
	failed: 'Failed',
	cancelled: 'Cancelled',
	presumed_failed: 'Presumed failed'
};

const ACTIVE: ReadonlySet<RunStatus> = new Set(['queued', 'launched', 'running', 'unresponsive']);
const PROBLEM: ReadonlySet<RunStatus> = new Set(['failed', 'partial', 'presumed_failed']);

/** Not yet terminal: waiting, starting or executing. */
export function isActiveRun(status: RunStatus): boolean {
	return ACTIVE.has(status);
}

/** Terminal with at least one failure. */
export function isProblemRun(status: RunStatus): boolean {
	return PROBLEM.has(status);
}

/** Sort weight: problems and live runs first. */
export function runStatusRank(status: RunStatus): number {
	if (PROBLEM.has(status)) return 3;
	if (ACTIVE.has(status)) return 2;
	if (status === 'warn') return 1;
	return 0;
}

export const tickOutcomeLabel: Record<TickOutcome, string> = {
	requested: 'Run requested',
	skipped: 'Skipped',
	covered: 'Covered by a waiting run',
	failed: 'Tick failed',
	deferred: 'Deferred'
};

export const triggerStateLabel: Record<TriggerState, string> = {
	running: 'Running',
	paused: 'Paused'
};

export const checkResultTone: Record<CheckResult, string> = {
	pass: 'var(--sb-success)',
	fail: 'var(--sb-error)',
	warn: 'var(--sb-warning)'
};

export const checkResultLabel: Record<CheckResult, string> = {
	pass: 'Passed',
	fail: 'Failed',
	warn: 'Warning'
};

/** e.g. `8 ok · 1 warn · 1 failed · 3 skipped`, or `4 running · 10 pending`. */
export function formatNodeCounts(counts: NodeCounts): string {
	const parts: string[] = [];
	if (counts.running) parts.push(`${counts.running} running`);
	if (counts.success) parts.push(`${counts.success} ok`);
	if (counts.warn) parts.push(`${counts.warn} warn`);
	if (counts.failed) parts.push(`${counts.failed} failed`);
	if (counts.skipped) parts.push(`${counts.skipped} skipped`);
	if (counts.pending) parts.push(`${counts.pending} pending`);
	return parts.join(' · ') || '—';
}

export const runKindLabel: Record<RunKind, string> = {
	job: 'Job',
	group: 'Group',
	adhoc: 'Ad hoc'
};

export const runOriginLabel: Record<RunOrigin, string> = {
	manual: 'Manual',
	schedule: 'Schedule',
	sensor: 'Sensor',
	rerun: 'Rerun'
};

/** One-line "what · why" label, e.g. "Group · Schedule". */
export function runKindOriginLabel(run: { kind: RunKind; origin: RunOrigin }): string {
	return `${runKindLabel[run.kind]} · ${runOriginLabel[run.origin]}`;
}
