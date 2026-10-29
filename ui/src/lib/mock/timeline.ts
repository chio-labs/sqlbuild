// Deterministic mock run history for the activity timeline.

export type TimelineStatus = 'ok' | 'warn' | 'fail' | 'running' | 'scheduled';
export type TimelineRun = {
	id: string;
	job: string;
	status: TimelineStatus;
	start: number;
	end: number;
	trigger: 'schedule' | 'sensor' | 'manual';
};
export type TimelineJob = { name: string };

const MIN = 60_000;
export const TIMELINE_NOW = new Date(2026, 4, 31, 12, 8).getTime();

type JobSpec = TimelineJob & {
	every: number; // minutes between ticks
	at: number; // minute offset within the day
	dur: number; // typical duration, minutes
	trigger: TimelineRun['trigger'];
};

const SPECS: JobSpec[] = [
	{ name: 'nightly_build', every: 180, at: 0, dur: 24, trigger: 'schedule' },
	{ name: 'marts_only', every: 240, at: 30, dur: 14, trigger: 'schedule' },
	{ name: 'revenue_refresh', every: 360, at: 75, dur: 38, trigger: 'schedule' },
	{ name: 'customer_snapshots', every: 720, at: 150, dur: 52, trigger: 'schedule' },
	{ name: 'finance_daily', every: 1440, at: 360, dur: 95, trigger: 'schedule' },
	{ name: 'hourly_orders', every: 60, at: 10, dur: 6, trigger: 'schedule' },
	{ name: 'load_sources', every: 120, at: 50, dur: 9, trigger: 'sensor' },
	{ name: 'load_payments', every: 90, at: 20, dur: 11, trigger: 'sensor' },
	{ name: 'load_customers', every: 240, at: 5, dur: 18, trigger: 'schedule' },
	{ name: 'sync_crm', every: 360, at: 200, dur: 26, trigger: 'schedule' },
	{ name: 'ingest_events', every: 30, at: 3, dur: 3, trigger: 'sensor' },
	{ name: 'checks_only', every: 180, at: 100, dur: 7, trigger: 'schedule' },
	{ name: 'freshness_checks', every: 60, at: 40, dur: 2, trigger: 'schedule' },
	{ name: 'audit_nightly', every: 1440, at: 150, dur: 44, trigger: 'schedule' },
];

export const TIMELINE_JOBS: TimelineJob[] = SPECS.map(({ name }) => ({ name }));

function rng(seed: number) {
	return () => {
		seed |= 0;
		seed = (seed + 0x6d2b79f5) | 0;
		let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

function build(): TimelineRun[] {
	const runs: TimelineRun[] = [];
	const from = TIMELINE_NOW - 8 * 1440 * MIN;
	const to = TIMELINE_NOW + 1440 * MIN;
	const day0 = new Date(from);
	day0.setHours(0, 0, 0, 0);
	SPECS.forEach((spec, jobIndex) => {
		const rand = rng(jobIndex * 7919 + 17);
		for (let t = day0.getTime() + spec.at * MIN; t < to; t += spec.every * MIN) {
			if (t < from) continue;
			const dur = spec.dur * (0.7 + rand() * 0.7) * MIN;
			const id = `run-${Math.floor(rand() * 0xffff).toString(16).padStart(4, '0')}`;
			if (t > TIMELINE_NOW) {
				runs.push({ id, job: spec.name, status: 'scheduled', start: t, end: t + spec.dur * MIN, trigger: spec.trigger });
				continue;
			}
			const r = rand();
			const status: TimelineStatus =
				t + dur > TIMELINE_NOW ? 'running' : r < 0.035 ? 'fail' : r < 0.07 ? 'warn' : 'ok';
			runs.push({ id, job: spec.name, status, start: t, end: status === 'running' ? TIMELINE_NOW : t + dur, trigger: spec.trigger });
		}
	});
	// Anchors that match the rest of the prototype's mock data.
	runs.push({ id: 'run-4f2a', job: 'nightly_build', status: 'fail', start: TIMELINE_NOW - 22 * MIN, end: TIMELINE_NOW - 18 * MIN, trigger: 'schedule' });
	runs.push({ id: 'run-91cd', job: 'marts_only', status: 'ok', start: TIMELINE_NOW - 97 * MIN, end: TIMELINE_NOW - 84 * MIN, trigger: 'manual' });
	return runs.sort((a, b) => a.start - b.start);
}

export const TIMELINE_RUNS = build();
