<script lang="ts">
	import SearchIcon from '@lucide/svelte/icons/search';
	import { page } from '$app/state';
	import '@xyflow/svelte/dist/style.css';
	import { SvelteFlow, Background, Controls, type Node, type Edge } from '@xyflow/svelte';
	import AssetNode from '$lib/components/lineage/asset-node.svelte';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import { layoutGraph } from '$lib/lineage/layout';

	const runId = $derived(page.params.id ?? 'run-4f2a');

	type ExecStatus = 'ok' | 'fail' | 'warn' | 'skip' | 'run';
	type ExecRow = { id: string; name: string; status: ExecStatus; start: number; dur: number; kind: string; icon: string };

	// start/dur in seconds along a 1.42s run
	const exec: ExecRow[] = [
		{ id: 'stg_customers', name: 'stg_customers', status: 'ok', start: 0.0, dur: 0.05, kind: 'view', icon: 'view' },
		{ id: 'stg_orders', name: 'stg_orders', status: 'ok', start: 0.0, dur: 0.03, kind: 'view', icon: 'view' },
		{ id: 'stg_payments', name: 'stg_payments', status: 'warn', start: 0.05, dur: 0.02, kind: 'view', icon: 'view' },
		{ id: 'fact_orders', name: 'fact_orders', status: 'ok', start: 0.08, dur: 0.04, kind: 'table', icon: 'table' },
		{ id: 'dim_customers', name: 'dim_customers', status: 'ok', start: 0.08, dur: 0.05, kind: 'table', icon: 'table' },
		{ id: 'daily_revenue', name: 'daily_revenue', status: 'ok', start: 0.14, dur: 0.05, kind: 'table', icon: 'table' },
		{ id: 'hourly_order_activity', name: 'hourly_order_activity', status: 'ok', start: 0.2, dur: 0.16, kind: 'incremental', icon: 'microbatch' },
		{ id: 'hourly_ctx', name: 'hourly_activity_with_daily_context', status: 'fail', start: 0.8, dur: 0.61, kind: 'incremental', icon: 'microbatch' },
		{ id: 'daily_activity_rollup', name: 'daily_activity_rollup', status: 'skip', start: 0, dur: 0, kind: 'incremental', icon: 'microbatch' }
	];
	const TOTAL = 1.42;

	const statusColor: Record<ExecStatus, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)',
		skip: 'var(--sb-text-faint)',
		run: 'var(--sb-running)'
	};
	const statusLabel: Record<ExecStatus, string> = {
		fail: 'Failed',
		run: 'Running',
		warn: 'Warned',
		ok: 'Succeeded',
		skip: 'Skipped'
	};
	// rail order: problems/active first, then success, then skipped
	const railOrder: ExecStatus[] = ['fail', 'run', 'warn', 'ok', 'skip'];

	// ---- gantt time-axis: pixels-per-second model with zoom + horizontal scroll ----
	// zoom = 1 means "fit the run to the available track width"; higher = pan/scroll.
	let zoom = $state(1);
	const ZOOM_MIN = 1;
	const ZOOM_MAX = 60;
	// measured width of the OUTER scroll viewport (fixed; never the scaled content).
	// We measure a dedicated zero-content element pinned to the pane, so its size can
	// NEVER be influenced by the scaled timeline content (which would feed back).
	let viewportW = $state(900);
	let measureEl: HTMLDivElement;

	// available timeline width = viewport minus gutter minus right pad
	const trackBaseW = $derived(Math.max(120, viewportW - gutterW - 24));
	// total scaled width of the timeline content
	const trackW = $derived(trackBaseW * zoom);
	// represent slightly more than the run duration so the longest bar never kisses
	// the right edge and the trailing duration label has room
	const AXIS_PAD = 1.05;
	const axisSpan = TOTAL * AXIS_PAD;
	// pixels per second at the current zoom
	const pxPerSec = $derived(trackW / axisSpan);
	const xOf = (sec: number) => sec * pxPerSec;

	// nice tick step (seconds) so ~6–10 labels show; re-granulates as you zoom in
	const tickStep = $derived.by(() => {
		const targetTicks = Math.max(4, Math.floor(trackW / 130));
		const raw = TOTAL / targetTicks;
		const candidates = [0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
		return candidates.find((c) => c >= raw) ?? 600;
	});
	const axisTicks = $derived.by(() => {
		const out: number[] = [];
		for (let t = 0; t <= TOTAL + 1e-9; t += tickStep) out.push(Number(t.toFixed(3)));
		return out;
	});
	const fmtTick = (s: number) => (tickStep < 1 ? `${s.toFixed(2)}s` : s < 60 ? `${s.toFixed(s % 1 ? 1 : 0)}s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`);

	// horizontal scroll state (drives gutter shadow)
	let scrolledX = $state(false);
	function onTimelineScroll(e: Event) {
		scrolledX = (e.currentTarget as HTMLElement).scrollLeft > 1;
	}
	function zoomBy(factor: number) {
		zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom * factor));
	}
	function resetZoom() {
		zoom = 1;
		if (timelineEl) timelineEl.scrollLeft = 0;
	}

	// ---- step selection + gantt-side filtering (scales to 100s of models) ----
	let selectedStep = $state<string | null>(null);
	let statusFilter = $state<Set<ExecStatus>>(new Set()); // empty = show all
	let ganttQuery = $state('');

	const statusCounts = $derived(
		railOrder.reduce(
			(acc, s) => {
				acc[s] = exec.filter((e) => e.status === s).length;
				return acc;
			},
			{} as Record<ExecStatus, number>
		)
	);

	const visibleExec = $derived(
		exec.filter((e) => {
			if (statusFilter.size && !statusFilter.has(e.status)) return false;
			if (ganttQuery.trim() && !e.name.toLowerCase().includes(ganttQuery.trim().toLowerCase())) return false;
			return true;
		})
	);

	function toggleStatusFilter(s: ExecStatus) {
		const next = new Set(statusFilter);
		next.has(s) ? next.delete(s) : next.add(s);
		statusFilter = next;
	}

	function selectStep(name: string) {
		selectedStep = selectedStep === name ? null : name;
		if (selectedStep) {
			// scope the events panel to the selected step
			bottomTab = 'events';
			query = name;
		} else {
			query = '';
		}
	}

	// ---- top view toggle ----
	let topView = $state<'timeline' | 'graph'>('timeline');

	// ---- resizable split between top (gantt/dag) and bottom (events) ----
	let topFrac = $state(0.55); // fraction of the available area given to the top pane
	let dragging = $state(false);
	let splitEl: HTMLDivElement;

	// ---- resizable gantt label gutter ----
	// Width is transient view state, not a saved preference: it auto-fits to the
	// longest step name each time you land on the page; dragging is an in-session
	// override that resets on navigate-away/return.
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	const GUTTER_MIN = 140;
	const GUTTER_MAX = 560;
	const GUTTER_AUTOFIT_CAP = 360; // auto-fit never exceeds this; widen manually beyond it

	// gutter layout constants: pl-6 (24) + pr-3 (12) + border (8) + breathing slack (16)
	const GUTTER_PAD = 24 + 12 + 8 + 16;

	let gutterDragging = $state(false);
	let ganttEl: HTMLDivElement;

	// auto-fit the gutter to the longest step name
	function autoFitGutter(): number {
		if (!browser) return 250;
		const canvas = document.createElement('canvas');
		const ctx = canvas.getContext('2d');
		if (!ctx) return 250;
		ctx.font = '12px "IBM Plex Mono", ui-monospace, monospace';
		let widest = 0;
		for (const e of exec) widest = Math.max(widest, ctx.measureText(e.name).width);
		return Math.min(GUTTER_AUTOFIT_CAP, Math.max(GUTTER_MIN, Math.ceil(widest) + GUTTER_PAD));
	}

	let gutterW = $state(250);
	onMount(() => {
		gutterW = autoFitGutter();
		// measure a dedicated zero-content element (never the scrollable content),
		// so zoom can't feed back into the measurement and grow without bound.
		if (measureEl) {
			const measure = () => {
				viewportW = measureEl.clientWidth;
			};
			const ro = new ResizeObserver(measure);
			ro.observe(measureEl);
			measure();
			return () => ro.disconnect();
		}
	});

	function startGutter(e: PointerEvent) {
		gutterDragging = true;
		(e.target as HTMLElement).setPointerCapture(e.pointerId);
		e.stopPropagation();
	}
	function onGutter(e: PointerEvent) {
		if (!gutterDragging || !ganttEl) return;
		const r = ganttEl.getBoundingClientRect();
		gutterW = Math.min(GUTTER_MAX, Math.max(GUTTER_MIN, e.clientX - r.left));
	}
	function endGutter(e: PointerEvent) {
		if (!gutterDragging) return;
		gutterDragging = false;
		try {
			(e.target as HTMLElement).releasePointerCapture(e.pointerId);
		} catch {}
	}
	// double-click the divider to re-fit to the longest name
	function resetGutter() {
		gutterW = autoFitGutter();
	}

	function startDrag(e: PointerEvent) {
		dragging = true;
		(e.target as HTMLElement).setPointerCapture(e.pointerId);
	}
	function onDrag(e: PointerEvent) {
		if (!dragging || !splitEl) return;
		const r = splitEl.getBoundingClientRect();
		const f = (e.clientY - r.top) / r.height;
		topFrac = Math.min(0.85, Math.max(0.2, f));
	}
	function endDrag(e: PointerEvent) {
		dragging = false;
		try {
			(e.target as HTMLElement).releasePointerCapture(e.pointerId);
		} catch {}
	}

	// ---- DAG view (execution graph, reuses AssetNode, colored by step status) ----
	const P = { x: 0, y: 0 };
	let nodes = $state.raw<Node[]>(
		exec
			.filter((e) => e.status !== 'skip')
			.map((e) => ({
				id: e.id,
				type: 'asset',
				position: { ...P },
				data: { name: e.name, kind: e.kind, status: e.status, icon: e.icon }
			}))
	);
	const dagE = (s: string, t: string): Edge => ({ id: `${s}-${t}`, source: s, target: t, type: 'bezier', style: 'stroke: var(--sb-edge); stroke-width: 1.5;' });
	let edges = $state.raw<Edge[]>([
		dagE('stg_customers', 'fact_orders'),
		dagE('stg_orders', 'fact_orders'),
		dagE('stg_payments', 'fact_orders'),
		dagE('stg_customers', 'daily_revenue'),
		dagE('fact_orders', 'dim_customers'),
		dagE('fact_orders', 'hourly_order_activity'),
		dagE('hourly_order_activity', 'hourly_ctx')
	]);
	const nodeTypes = { asset: AssetNode };
	let laidOut = false;
	$effect(() => {
		if (topView !== 'graph' || laidOut) return;
		if (!nodes.every((n) => n.measured?.width && n.measured?.height)) return;
		nodes = layoutGraph(nodes, edges);
		laidOut = true;
	});

	// ---- bottom tabbed panel ----
	let bottomTab = $state<'events' | 'logs' | 'stdout' | 'stderr'>('events');

	type EventKind = 'start' | 'success' | 'pass' | 'warn' | 'fail' | 'materialized' | 'skip' | 'runfail';
	type Level = 'debug' | 'info' | 'warn' | 'error';
	type Ev = { t: string; step: string; kind: EventKind; info: string };
	// severity level derived from event kind
	const kindLevel: Record<EventKind, Level> = {
		start: 'debug',
		success: 'info',
		pass: 'info',
		materialized: 'info',
		warn: 'warn',
		fail: 'error',
		runfail: 'error',
		skip: 'info'
	};
	const eventColor: Record<EventKind, string> = {
		start: 'var(--sb-running)',
		success: 'var(--sb-success)',
		pass: 'var(--sb-success)',
		materialized: 'var(--sb-success)',
		warn: 'var(--sb-warning)',
		fail: 'var(--sb-error)',
		runfail: 'var(--sb-error)',
		skip: 'var(--sb-text-faint)'
	};
	const eventLabel: Record<EventKind, string> = {
		start: 'STEP_START',
		success: 'STEP_SUCCESS',
		pass: 'AUDIT_PASS',
		warn: 'AUDIT_WARN',
		fail: 'AUDIT_FAIL',
		materialized: 'PROMOTED',
		skip: 'STEP_SKIPPED',
		runfail: 'RUN_FAILED'
	};
	const events: Ev[] = [
		{ t: '11:46:10.122', step: 'stg_customers', kind: 'start', info: 'Started execution of step.' },
		{ t: '11:46:10.180', step: 'stg_customers', kind: 'pass', info: 'audit not_null(customer_id) passed.' },
		{ t: '11:46:10.181', step: 'stg_customers', kind: 'success', info: 'Finished in 0.05s.' },
		{ t: '11:46:10.190', step: 'stg_payments', kind: 'warn', info: 'audit not_null(payment_id): 2 nulls.' },
		{ t: '11:46:11.020', step: 'fact_orders', kind: 'materialized', info: 'Promoted table (staging → target).' },
		{ t: '11:46:11.210', step: 'hourly_activity_with_daily_context', kind: 'start', info: 'microbatch · 4 batches.' },
		{ t: '11:46:11.420', step: 'hourly_activity_with_daily_context', kind: 'pass', info: 'batch 1/4 [2026-05-28] expression_is_true passed.' },
		{ t: '11:46:11.480', step: 'hourly_activity_with_daily_context', kind: 'pass', info: 'batch 2/4 [2026-05-29] expression_is_true passed.' },
		{ t: '11:46:11.540', step: 'hourly_activity_with_daily_context', kind: 'fail', info: 'batch 3/4 [2026-05-30] expression_is_true FAILED: 7 rows.' },
		{ t: '11:46:11.541', step: 'daily_activity_rollup', kind: 'skip', info: 'Skipped — upstream failed.' },
		{ t: '11:46:11.542', step: '—', kind: 'runfail', info: '8 ok · 1 warn · 1 fail · 3 skip' }
	];

	// ---- events filtering ----
	const allLevels: Level[] = ['debug', 'info', 'warn', 'error'];
	let activeLevels = $state<Set<Level>>(new Set(allLevels));
	let query = $state('');
	let levelsOpen = $state(false);

	const levelCounts = $derived(
		allLevels.reduce(
			(acc, lv) => {
				acc[lv] = events.filter((e) => kindLevel[e.kind] === lv).length;
				return acc;
			},
			{} as Record<Level, number>
		)
	);

	const filteredEvents = $derived(
		events.filter((e) => {
			if (!activeLevels.has(kindLevel[e.kind])) return false;
			if (query.trim()) {
				const q = query.toLowerCase();
				return (
					e.step.toLowerCase().includes(q) ||
					e.info.toLowerCase().includes(q) ||
					eventLabel[e.kind].toLowerCase().includes(q)
				);
			}
			return true;
		})
	);

	function toggleLevel(lv: Level) {
		const next = new Set(activeLevels);
		next.has(lv) ? next.delete(lv) : next.add(lv);
		activeLevels = next;
	}

	// jump to a filtered events view (used by header fail/warn counts);
	// clicking again when already filtered to just this level clears the filter
	function focusLevel(lv: Level) {
		bottomTab = 'events';
		query = '';
		if (activeLevels.size === 1 && activeLevels.has(lv)) {
			activeLevels = new Set(allLevels);
		} else {
			activeLevels = new Set([lv]);
		}
	}

	const isFocused = (lv: Level) => activeLevels.size === 1 && activeLevels.has(lv);

	const levelDot: Record<Level, string> = {
		debug: 'var(--sb-text-faint)',
		info: 'var(--sb-running)',
		warn: 'var(--sb-warning)',
		error: 'var(--sb-error)'
	};

	type Log = { t: string; text: string; tag?: string; tagKind?: 'ok' | 'warn' | 'fail' | 'dim' };
	const logs: Log[] = [
		{ t: '11:46:10', text: 'compiling model graph (13 nodes)', tag: 'OK', tagKind: 'ok' },
		{ t: '11:46:10', text: 'stg_customers view', tag: 'OK 0.05s', tagKind: 'ok' },
		{ t: '11:46:10', text: '  audit not_null(customer_id)', tag: 'PASS', tagKind: 'ok' },
		{ t: '11:46:10', text: 'stg_payments view', tag: 'WARN 1', tagKind: 'warn' },
		{ t: '11:46:10', text: '  audit not_null(payment_id)', tag: 'WARN 2 nulls', tagKind: 'warn' },
		{ t: '11:46:11', text: 'fact_orders table (staged)', tag: 'OK 0.04s', tagKind: 'ok' },
		{ t: '11:46:11', text: 'hourly_activity_with_daily_context microbatch' },
		{ t: '11:46:11', text: '  batch 1/4 [2026-05-28] audit expression_is_true', tag: 'PASS', tagKind: 'ok' },
		{ t: '11:46:11', text: '  batch 2/4 [2026-05-29] audit expression_is_true', tag: 'PASS', tagKind: 'ok' },
		{ t: '11:46:11', text: '  batch 3/4 [2026-05-30] audit expression_is_true', tag: 'FAIL 7 rows', tagKind: 'fail' },
		{ t: '11:46:11', text: 'error[A104] staging not promoted — target untouched', tagKind: 'fail' },
		{ t: '11:46:11', text: 'daily_activity_rollup', tag: 'SKIPPED (upstream failed)', tagKind: 'dim' },
		{ t: '11:46:11', text: 'run failed  8 ok · 1 warn · 1 fail · 3 skip', tagKind: 'fail' }
	];
	const logColor: Record<string, string> = {
		ok: 'var(--sb-success)',
		warn: 'var(--sb-warning)',
		fail: 'var(--sb-error)',
		dim: 'var(--sb-text-faint)'
	};
	const stdoutText = `[2026-05-31 11:46:11] hourly_activity_with_daily_context: executing microbatch 3/4
SELECT activity_hour, ... FROM staging.hourly_activity_with_daily_context__tmp
-- 7 rows returned where activity_hour IS NULL
audit expression_is_true: FAILED`;
	const stderrText = `Traceback (most recent call last):
  sqlbuild.audit.errors.AuditFailed: expression_is_true failed on batch 3/4
  7 rows violated: activity_hour IS NULL
  staging table not promoted; target left untouched (error[A104])`;
</script>

<AppTopbar title="Runs">
	<Button variant="outline" size="sm">↻ Rerun</Button>
	<Button size="sm">▷ Rerun from failure</Button>
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<!-- run header -->
	<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
		<a href="/runs" class="text-muted-foreground hover:text-foreground text-[13px]">← Runs</a>
		<span class="font-display text-[17px] font-semibold">{runId}</span>
		<span class="sb-status" style="--tone:var(--sb-error)">
			<span class="h-1.5 w-1.5 rounded-[2px]" style="background:var(--sb-error)"></span>failed
		</span>
		<span class="text-muted-foreground text-[12px]">nightly_build · schedule · prod · a3f19c2</span>
		<div class="text-[var(--sb-text-faint)] ml-auto flex items-center gap-2 text-[11.5px]">
			<span>11:46:09 · 1.42s · @scheduler</span>
			<span class="text-[var(--sb-text-faint)]">·</span>
			<span class="text-foreground">8 ok</span>
			<button
				class="rounded-[2px] px-1.5 py-0.5 ring-offset-0 transition-shadow {isFocused('warn') ? 'ring-1' : ''}"
				style="background:color-mix(in srgb, var(--sb-warning) {isFocused('warn') ? 22 : 13}%, transparent);color:var(--sb-warning);--tw-ring-color:var(--sb-warning)"
				onclick={() => focusLevel('warn')}
				title={isFocused('warn') ? 'Clear warning filter' : 'Filter events to warnings'}
			>1 warn</button>
			<button
				class="rounded-[2px] px-1.5 py-0.5 ring-offset-0 transition-shadow {isFocused('error') ? 'ring-1' : ''}"
				style="background:color-mix(in srgb, var(--sb-error) {isFocused('error') ? 22 : 13}%, transparent);color:var(--sb-error);--tw-ring-color:var(--sb-error)"
				onclick={() => focusLevel('error')}
				title={isFocused('error') ? 'Clear error filter' : 'Filter events to errors'}
			>1 fail</button>
			<span>3 skip</span>
		</div>
	</div>

	<!-- resizable split container -->
	<div bind:this={splitEl} class="flex min-h-0 flex-1 flex-col" class:select-none={dragging} style:cursor={dragging ? 'row-resize' : undefined}>
	<!-- top: gantt / dag -->
	<div class="flex min-h-0 flex-col" style:flex={topFrac}>
		<div class="flex items-center gap-2 border-b border-border px-6 py-2.5">
			<span class="text-[12px] font-semibold text-[var(--sb-text-faint)]">Execution</span>

			{#if topView === 'timeline'}
				<!-- timeline step filter (status filtering lives in the right rail) -->
				<div class="bg-secondary ml-4 flex items-center gap-1.5 rounded-[2px] border border-border px-2 py-1">
					<SearchIcon size={13} class="shrink-0 text-[var(--sb-text-faint)]" />
					<input
						bind:value={ganttQuery}
						placeholder="Filter steps…"
						class="text-foreground placeholder:text-[var(--sb-text-faint)] w-[160px] bg-transparent text-[11.5px] outline-none"
					/>
					{#if ganttQuery}
						<button class="text-[var(--sb-text-faint)] hover:text-foreground text-[11px]" onclick={() => (ganttQuery = '')}>✕</button>
					{/if}
				</div>
				{#if statusFilter.size || ganttQuery}
					<span class="text-[var(--sb-text-faint)] text-[11px]">{visibleExec.length}/{exec.length} steps</span>
				{/if}

				<!-- zoom control -->
				<div class="ml-auto flex items-center gap-1.5">
					<div class="bg-secondary flex items-center overflow-hidden rounded-[2px] border border-border">
						<button class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] h-[26px] w-7 text-[13px] disabled:opacity-40" onclick={() => zoomBy(1 / 1.5)} disabled={zoom <= ZOOM_MIN} title="Zoom out">−</button>
						<input type="range" min={ZOOM_MIN} max={ZOOM_MAX} step="0.1" bind:value={zoom} class="sb-zoom mx-1.5 w-24" title="Zoom" />
						<button class="text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] h-[26px] w-7 text-[13px] disabled:opacity-40" onclick={() => zoomBy(1.5)} disabled={zoom >= ZOOM_MAX} title="Zoom in">+</button>
					</div>
					<button
						class="bg-secondary text-muted-foreground hover:text-foreground rounded-[2px] border border-border px-2 py-1 text-[11px] disabled:opacity-40"
						onclick={resetZoom}
						disabled={zoom === 1}
						title="Fit to width"
					>fit</button>
				</div>
			{:else}
				<div class="ml-auto"></div>
			{/if}

			<div class="ml-2 flex overflow-hidden rounded-md border border-border">
				{#each [['timeline', 'Timeline'], ['graph', 'Graph']] as [v, lbl] (v)}
					<button
						class="px-3 py-1 text-[11px] {topView === v ? 'bg-[var(--sidebar-accent)] text-foreground' : 'text-muted-foreground'} font-medium"
						onclick={() => (topView = v as 'timeline' | 'graph')}
					>{lbl}</button>
				{/each}
			</div>
		</div>

		<!-- gantt/dag area + right status rail -->
		<div class="flex min-h-0 flex-1">
		<div class="flex min-h-0 flex-1 flex-col">
		{#if topView === 'timeline'}
			<!-- pane wrapper holds a zero-content measuring box (size independent of zoom)
			     plus the scroll container. -->
			<div class="relative min-h-0 flex-1">
			<!-- dedicated viewport-width probe: never contains scaled content -->
			<div bind:this={measureEl} class="pointer-events-none absolute inset-0"></div>
			<!-- single scroll container: scrolls X (timeline) + Y (rows). gutter cells are
			     sticky-left, axis row is sticky-top, corner pins both. -->
			<div
				bind:this={ganttEl}
				class="sb-scroll absolute inset-0 overflow-auto"
				class:select-none={gutterDragging}
				onscroll={onTimelineScroll}
			>
				<div class="relative" style:width="{gutterW + trackW + 24}px" style:min-width="100%">
					<!-- full-height gridlines (under rows), spanning the timeline area only -->
					<div class="pointer-events-none absolute top-7 bottom-0" style:left="{gutterW}px" style:width="{trackW}px">
						{#each axisTicks as tk (tk)}
							<span class="absolute top-0 bottom-0 w-px" style="left:{xOf(tk)}px;background:var(--sb-grid)"></span>
						{/each}
					</div>

					<!-- sticky time axis -->
					<div class="bg-card sticky top-0 z-30 flex h-7 border-b border-border">
						<div
							class="text-[var(--sb-text-faint)] sticky left-0 z-10 flex shrink-0 items-center border-r border-border pl-6 text-[11.5px] font-medium"
							class:sb-gutter-shadow={scrolledX}
							style:width="{gutterW}px"
							style:background="var(--sb-surface-low)"
						>Step</div>
						<div class="relative" style:width="{trackW}px">
							{#each axisTicks as tk (tk)}
								<span class="text-[var(--sb-text-faint)] absolute top-1/2 -translate-y-1/2 text-[11.5px] {tk > 0 ? '-translate-x-1/2' : 'pl-1.5'}" style="left:{xOf(tk)}px">{fmtTick(tk)}</span>
							{/each}
						</div>
					</div>

					<!-- draggable gutter divider (over the axis + rows) -->
					<div
						class="sb-gutter-handle absolute top-0 bottom-0 z-40 -ml-1 w-2 cursor-col-resize"
						style:left="{gutterW}px"
						onpointerdown={startGutter}
						onpointermove={onGutter}
						onpointerup={endGutter}
						ondblclick={resetGutter}
						role="separator"
						aria-label="Resize label column (double-click to auto-fit)"
						title="Drag to resize · double-click to auto-fit"
						tabindex="-1"
					></div>

					<!-- rows -->
					<div class="relative">
						{#each visibleExec as e (e.id)}
							<div
								class="group relative flex h-8 cursor-pointer items-center border-b border-[var(--border-subtle)] hover:bg-[var(--sb-hover)]"
								class:bg-[var(--sb-hover)]={selectedStep === e.name}
								onclick={() => selectStep(e.name)}
							>
								<div
									class="sb-gutter-cell sticky left-0 z-20 flex h-full shrink-0 items-center truncate border-r border-border pl-6 pr-3 text-[12px]"
									class:sb-gutter-shadow={scrolledX}
									class:sb-gutter-sel={selectedStep === e.name}
									style:width="{gutterW}px"
									class:text-muted-foreground={e.status !== 'fail' && e.status !== 'skip'}
									style:color={e.status === 'fail' ? 'var(--sb-error)' : e.status === 'skip' ? 'var(--sb-text-faint)' : undefined}
									title={e.name}
								>
									{#if selectedStep === e.name}<span class="bg-primary absolute left-0 top-[3px] bottom-[3px] w-[2px] rounded-r"></span>{/if}
									{e.name}
								</div>
								<div class="relative h-full" style:width="{trackW}px">
									{#if e.status === 'skip'}
										<span class="text-[var(--sb-text-faint)] absolute top-1/2 left-2 -translate-y-1/2 text-[12px]">skipped (upstream failed)</span>
									{:else}
										{@const endX = xOf(e.start + e.dur)}
										<div
											class="absolute top-1/2 h-4 -translate-y-1/2 rounded-[2px]"
											style="left:{xOf(e.start)}px;width:{Math.max(xOf(e.dur), 3)}px;background:{statusColor[e.status]};box-shadow:inset 0 1px 0 rgba(255,255,255,0.18)"
										></div>
										<!-- duration label: flips left of the bar when near the right edge -->
										{#if endX > trackW - 56}
											<span class="text-[var(--sb-text-faint)] absolute top-1/2 -translate-x-full -translate-y-1/2 text-[11.5px]" style="left:{xOf(e.start) - 8}px">{e.dur.toFixed(2)}s</span>
										{:else}
											<span class="text-[var(--sb-text-faint)] absolute top-1/2 -translate-y-1/2 text-[11.5px]" style="left:{endX + 8}px">{e.dur.toFixed(2)}s</span>
										{/if}
									{/if}
								</div>
							</div>
						{/each}
						{#if visibleExec.length === 0}
							<div class="text-[var(--sb-text-faint)] flex h-24 items-center justify-center text-[12px]">No steps match the current filter.</div>
						{/if}
					</div>
				</div>
			</div>
			</div>
		{:else}
			<div class="sb-flow relative flex-1" style="background: var(--sb-inset)">
				<SvelteFlow bind:nodes bind:edges {nodeTypes} fitView nodesDraggable proOptions={{ hideAttribution: true }}>
					<Background gap={64} bgColor="var(--sb-inset)" patternColor="var(--sb-grid)" />
					<Controls />
				</SvelteFlow>
			</div>
		{/if}
		</div>

		<!-- right status rail (live counts + click-to-filter) -->
		<div class="sb-scroll w-[210px] shrink-0 overflow-y-auto border-l border-border">
			{#each railOrder as s (s)}
				{#if statusCounts[s]}
					{@const active = statusFilter.has(s)}
					<button
						class="flex w-full items-center gap-2.5 border-b border-[var(--border-subtle)] px-3.5 py-2.5 text-left hover:bg-[var(--sb-hover)]"
						style:background={active ? `color-mix(in srgb, ${statusColor[s]} 10%, transparent)` : 'transparent'}
						onclick={() => toggleStatusFilter(s)}
						title="Filter gantt to {statusLabel[s]}"
					>
						<span class="h-2 w-2 shrink-0 rounded-[2px]" style:background={statusColor[s]}></span>
						<span class="text-[12.5px]" style:color={active ? 'var(--foreground)' : 'var(--muted-foreground)'}>{statusLabel[s]}</span>
						<span class="ml-auto text-[13px] font-semibold" style:color={statusColor[s]}>{statusCounts[s]}</span>
					</button>
				{/if}
			{/each}
			{#if statusFilter.size}
				<button class="text-[var(--sb-text-faint)] hover:text-foreground w-full px-3.5 py-2 text-left text-[11px]" onclick={() => (statusFilter = new Set())}>✕ clear filter</button>
			{/if}
		</div>
		</div>
	</div>

	<!-- draggable splitter -->
	<div
		class="sb-splitter group relative h-[7px] shrink-0 cursor-row-resize border-y border-border bg-[var(--sb-surface-low)]"
		onpointerdown={startDrag}
		onpointermove={onDrag}
		onpointerup={endDrag}
		role="separator"
		aria-label="Resize panels"
		tabindex="-1"
	>
		<span class="absolute left-1/2 top-1/2 h-[3px] w-9 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--border-strong)] transition-colors group-hover:bg-[var(--muted-foreground)]"></span>
	</div>

	<!-- bottom: events / logs / stdout / stderr -->
	<div class="flex min-h-0 flex-col" style:flex={1 - topFrac}>
		<div class="flex items-center gap-1 border-b border-border px-4">
			{#each ['events', 'logs', 'stdout', 'stderr'] as tab (tab)}
				<button
					class="border-b-2 px-3 py-2.5 text-[12px] {bottomTab === tab ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground'} font-medium"
					onclick={() => (bottomTab = tab as typeof bottomTab)}
				>{tab}</button>
			{/each}

			{#if bottomTab === 'events'}
				<div class="ml-3 flex items-center gap-2 py-1.5">
					<!-- free-text filter -->
					<div class="bg-secondary flex items-center gap-1.5 rounded-[2px] border border-border px-2 py-1">
						<SearchIcon size={13} class="shrink-0 text-[var(--sb-text-faint)]" />
						<input
							bind:value={query}
							placeholder="Filter steps, events…"
							class="text-foreground placeholder:text-[var(--sb-text-faint)] w-[200px] bg-transparent text-[11.5px] outline-none"
						/>
						{#if query}
							<button class="text-[var(--sb-text-faint)] hover:text-foreground text-[11px]" onclick={() => (query = '')}>✕</button>
						{/if}
					</div>

					<!-- levels dropdown -->
					<div class="relative">
						<button
							class="bg-secondary text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[2px] border border-border px-2.5 py-1 text-[11.5px]"
							onclick={() => (levelsOpen = !levelsOpen)}
						>
							⛁ Levels ({activeLevels.size}/{allLevels.length})
							<span class="text-[9px]">▾</span>
						</button>
						{#if levelsOpen}
							<button class="fixed inset-0 z-10 cursor-default" aria-label="close" onclick={() => (levelsOpen = false)}></button>
							<div class="bg-popover absolute left-0 z-20 mt-1 w-[170px] rounded-[2px] border border-border py-1" style="box-shadow:var(--sb-elev)">
								{#each allLevels as lv (lv)}
									<button
										class="hover:bg-[var(--sb-hover)] flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11.5px]"
										onclick={() => toggleLevel(lv)}
									>
										<span
											class="grid h-3 w-3 place-items-center rounded-[2px] border"
											style:background={activeLevels.has(lv) ? levelDot[lv] : 'transparent'}
											style:border-color={activeLevels.has(lv) ? levelDot[lv] : 'var(--border)'}
										>
											{#if activeLevels.has(lv)}<span class="text-[8px] leading-none text-white">✓</span>{/if}
										</span>
										<span class="capitalize">{lv}</span>
										<span class="text-[var(--sb-text-faint)] ml-auto">{levelCounts[lv]}</span>
									</button>
								{/each}
							</div>
						{/if}
					</div>
				</div>
			{/if}
		</div>

		<div class="sb-scroll min-h-0 flex-1 overflow-auto">
			{#if bottomTab === 'events'}
				<table class="sb-events w-full border-collapse">
					<thead class="sticky top-0 bg-[var(--background)]">
						<tr>
							{#each ['Time', 'Step', 'Event', 'Info'] as h (h)}
								<th class="text-[var(--sb-text-faint)] border-b border-border px-6 py-2 text-left text-[11.5px] font-medium">{h}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each filteredEvents as ev (ev.t + ev.step)}
							<tr class="hover:bg-[var(--sb-hover)] border-b border-[var(--border-subtle)]">
								<td class="text-[var(--sb-text-faint)] px-6 py-2 text-[11.5px] whitespace-nowrap">{ev.t}</td>
								<td class="px-6 py-2 text-[12px]">{ev.step}</td>
								<td class="px-6 py-2">
									<span class="inline-flex rounded-[2px] px-2 py-0.5 text-[11.5px]" style="background:color-mix(in srgb, {eventColor[ev.kind]} 13%, transparent);color:{eventColor[ev.kind]}">{eventLabel[ev.kind]}</span>
								</td>
								<td class="text-muted-foreground px-6 py-2 text-[12.5px]">{ev.info}</td>
							</tr>
						{:else}
							<tr>
								<td colspan="4" class="text-[var(--sb-text-faint)] px-6 py-8 text-center text-[12px]">No events match the current filter.</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{:else if bottomTab === 'logs'}
				<div class="px-6 py-3 text-[11.5px] leading-[1.7]" style="color:var(--sb-mono)">
					{#each logs as l (l.t + l.text)}
						<div class="whitespace-pre-wrap">
							<span style="color:var(--sb-text-faint)">{l.t}</span>
							<span style:color={l.tagKind === 'fail' ? logColor.fail : 'inherit'}> {l.text}</span>
							{#if l.tag}<span style:color={logColor[l.tagKind ?? 'dim']}>  {l.tag}</span>{/if}
						</div>
					{/each}
				</div>
			{:else if bottomTab === 'stdout'}
				<pre class="px-6 py-3 font-mono text-[11.5px] leading-[1.7] whitespace-pre-wrap" style="color:var(--sb-mono)">{stdoutText}</pre>
			{:else}
				<pre class="px-6 py-3 font-mono text-[11.5px] leading-[1.7] whitespace-pre-wrap" style="color:var(--sb-mono-err)">{stderrText}</pre>
			{/if}
		</div>
	</div>
	</div>
</div>

<style>
	.sb-gutter-handle::after {
		content: '';
		position: absolute;
		top: 0;
		bottom: 0;
		left: 50%;
		width: 1px;
		transform: translateX(-0.5px);
		background: transparent;
		transition: background 0.12s;
	}
	.sb-gutter-handle:hover::after,
	.sb-gutter-handle:active::after {
		background: var(--primary);
	}
	/* frozen step-name column: distinct inset surface so it reads as a row-header pane */
	.sb-gutter-cell {
		background: var(--sb-surface-low);
	}
	.group:hover .sb-gutter-cell {
		background: var(--sb-hover);
	}
	.sb-gutter-cell.sb-gutter-sel {
		background: var(--sb-hover);
	}
	/* shadow on the right edge of the pinned gutter when the timeline is scrolled */
	.sb-gutter-shadow {
		box-shadow: 6px 0 8px -6px rgba(0, 0, 0, 0.55);
	}
	/* zoom slider */
	.sb-zoom {
		appearance: none;
		height: 3px;
		border-radius: 2px;
		background: var(--border-strong);
		cursor: pointer;
	}
	.sb-zoom::-webkit-slider-thumb {
		appearance: none;
		width: 11px;
		height: 11px;
		border-radius: 50%;
		background: var(--primary);
	}
	.sb-zoom::-moz-range-thumb {
		width: 11px;
		height: 11px;
		border: none;
		border-radius: 50%;
		background: var(--primary);
	}
	/* thin styled scrollbars */
	.sb-scroll {
		scrollbar-width: thin;
		scrollbar-color: var(--border-strong) transparent;
	}
	.sb-scroll::-webkit-scrollbar {
		width: 9px;
		height: 9px;
	}
	.sb-scroll::-webkit-scrollbar-track {
		background: transparent;
	}
	.sb-scroll::-webkit-scrollbar-thumb {
		background: var(--border-strong);
		border-radius: 2px;
		border: 2px solid transparent;
		background-clip: content-box;
	}
	.sb-scroll::-webkit-scrollbar-thumb:hover {
		background: var(--muted-foreground);
		background-clip: content-box;
	}
	.sb-splitter:active span {
		background: var(--primary);
	}
	.sb-flow :global(.svelte-flow__controls-button) {
		background: var(--card);
		border-bottom: 1px solid var(--border);
	}
	.sb-flow :global(.svelte-flow__controls-button svg) {
		fill: var(--muted-foreground);
	}
	.sb-events :global(th),
	.sb-events :global(td) {
		border-right: 1px solid var(--border-subtle);
	}
	.sb-events :global(th:last-child),
	.sb-events :global(td:last-child) {
		border-right: none;
	}
</style>
