// Deterministic mock run history for the activity timeline.

import type { RunKind, RunStatus, TimelineBar } from '../types';

const MIN = 60_000;

type JobSpec = {
	key: string;
	every: number; // minutes between ticks
	at: number; // minute offset within the day
	dur: number; // typical duration, minutes
	kind: RunKind;
};

const SPECS: JobSpec[] = [
	{ key: 'nightly_build', every: 180, at: 0, dur: 24, kind: 'schedule' },
	{ key: 'marts_only', every: 240, at: 30, dur: 14, kind: 'schedule' },
	{ key: 'revenue_refresh', every: 360, at: 75, dur: 38, kind: 'schedule' },
	{ key: 'customer_snapshots', every: 720, at: 150, dur: 52, kind: 'schedule' },
	{ key: 'finance_daily', every: 1440, at: 360, dur: 95, kind: 'schedule' },
	{ key: 'hourly_orders', every: 60, at: 10, dur: 6, kind: 'schedule' },
	{ key: 'load_sources', every: 120, at: 50, dur: 9, kind: 'sensor' },
	{ key: 'load_payments', every: 90, at: 20, dur: 11, kind: 'sensor' },
	{ key: 'load_customers', every: 240, at: 5, dur: 18, kind: 'schedule' },
	{ key: 'sync_crm', every: 360, at: 200, dur: 26, kind: 'schedule' },
	{ key: 'ingest_events', every: 30, at: 3, dur: 3, kind: 'sensor' },
	{ key: 'checks_only', every: 180, at: 100, dur: 7, kind: 'schedule' },
	{ key: 'freshness_checks', every: 60, at: 40, dur: 2, kind: 'schedule' },
	{ key: 'audit_nightly', every: 1440, at: 150, dur: 44, kind: 'schedule' }
];

export const TIMELINE_JOB_KEYS = SPECS.map(({ key }) => key);

function rng(seed: number) {
	return () => {
		seed |= 0;
		seed = (seed + 0x6d2b79f5) | 0;
		let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

function pickStatus(r: number): RunStatus {
	if (r < 0.02) return 'failed';
	if (r < 0.035) return 'partial';
	if (r < 0.07) return 'warn';
	return 'success';
}

/** Runs from eight days before `now` plus projected ticks for the next day. */
export function buildTimelineBars(now: number): TimelineBar[] {
	const bars: TimelineBar[] = [];
	const from = now - 8 * 1440 * MIN;
	const to = now + 1440 * MIN;
	const day0 = new Date(from);
	day0.setHours(0, 0, 0, 0);
	const iso = (t: number) => new Date(t).toISOString();
	SPECS.forEach((spec, jobIndex) => {
		const rand = rng(jobIndex * 7919 + 17);
		for (let t = day0.getTime() + spec.at * MIN; t < to; t += spec.every * MIN) {
			if (t < from) continue;
			const dur = spec.dur * (0.7 + rand() * 0.7) * MIN;
			const id = `run-${Math.floor(rand() * 0xffff)
				.toString(16)
				.padStart(4, '0')}`;
			if (t > now) {
				bars.push({ runId: null, jobKey: spec.key, kind: spec.kind, status: 'projected', start: iso(t), end: iso(t + spec.dur * MIN) });
				continue;
			}
			const r = rand();
			const running = t + dur > now;
			bars.push({
				runId: id,
				jobKey: spec.key,
				kind: spec.kind,
				status: running ? 'running' : pickStatus(r),
				start: iso(t),
				end: iso(running ? now : t + dur)
			});
		}
	});
	return bars.sort((a, b) => a.start.localeCompare(b.start));
}
