<script lang="ts">
	import { goto } from '$app/navigation';
	import type { RerunMode, RunNodeStatus } from '$lib/api';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import GatedButton from '$lib/components/operate/gated-button.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatDuration, formatStamp } from '$lib/format/time';
	import { isActiveRun, runKindLabel, runStatusLabel, runStatusTone } from '$lib/status';
	import { formatCost, NODE_STATUS_ORDER, nodeStatusLabel, nodeStatusTone } from '$lib/operate/labels';
	import RunFacts from './run-facts.svelte';
	import RunGantt from './run-gantt.svelte';
	import RunGraph from './run-graph.svelte';
	import RunTabs from './run-tabs.svelte';

	let { runId }: { runId: string } = $props();

	// svelte-ignore state_referenced_locally
	const topics = [`run:${runId}`, 'runs'];
	const detailRes = createResource((client, scope) => client.getRunDetail(scope, runId), topics);
	const eventsRes = createResource((client, scope) => client.listRunEvents(scope, runId, { limit: 5000 }), topics);
	const outputRes = createResource((client, scope) => client.listRunOutput(scope, runId), topics);
	const statementsRes = createResource((client, scope) => client.listRunStatements(scope, runId), topics);

	const detail = $derived(detailRes.data ?? null);
	const run = $derived(detail?.run ?? null);
	const nodes = $derived(detail?.nodes ?? []);
	const active = $derived(!!run && isActiveRun(run.status));

	let topView = $state<'timeline' | 'graph'>('timeline');
	let railFilter = $state<Set<RunNodeStatus>>(new Set());
	let selected = $state<string | null>(null);
	let tab = $state<'events' | 'output' | 'statements' | 'provenance'>('events');
	let query = $state('');
	let tabs = $state<RunTabs>();

	const counts = $derived(
		Object.fromEntries(NODE_STATUS_ORDER.map((s) => [s, nodes.filter((n) => n.status === s).length])) as Record<RunNodeStatus, number>
	);
	const visible = $derived(railFilter.size ? nodes.filter((n) => railFilter.has(n.status)) : nodes);
	const origin = $derived.by(() => {
		const starts = nodes.map((n) => (n.startedAt ? Date.parse(n.startedAt) : Infinity));
		const first = Math.min(...starts);
		if (Number.isFinite(first)) return first;
		return run?.startedAt ? Date.parse(run.startedAt) : app.now;
	});
	const groups = $derived(
		(detail?.children ?? []).map((c) => ({ runId: c.id, label: `${c.jobKey} · ${c.id}`, tone: runStatusTone[c.status], href: `/runs/${c.id}` }))
	);

	function toggleRail(s: RunNodeStatus) {
		const next = new Set(railFilter);
		if (next.has(s)) next.delete(s);
		else next.add(s);
		railFilter = next;
	}

	function selectNode(key: string) {
		selected = selected === key ? null : key;
		tab = 'events';
		query = selected ?? '';
	}

	// ---- split between the execution view and the tabs ----
	let topFrac = $state(0.52);
	let dragging = $state(false);
	let splitEl = $state<HTMLDivElement>();
	function onDrag(e: PointerEvent) {
		if (!dragging || !splitEl) return;
		const r = splitEl.getBoundingClientRect();
		topFrac = Math.min(0.85, Math.max(0.2, (e.clientY - r.top) / r.height));
	}

	// ---- actions ----
	let busy = $state<'cancel' | RerunMode | null>(null);
	let actionError = $state<string | null>(null);
	let confirmFromFailure = $state(false);

	async function act(kind: 'cancel' | RerunMode) {
		const scope = app.scope;
		if (!scope || !run) return;
		busy = kind;
		actionError = null;
		try {
			if (kind === 'cancel') {
				await app.client.cancelRun(scope, run.id);
				detailRes.refresh();
			} else {
				const next = await app.client.rerunRun(scope, run.id, kind);
				await goto(`/runs/${next.id}`);
			}
		} catch (e) {
			actionError = e instanceof Error ? e.message : String(e);
		} finally {
			busy = null;
			confirmFromFailure = false;
		}
	}

	const fromFailure = $derived(detail?.rerunFromFailureNodes ?? []);
	const failedForRerun = $derived(nodes.filter((n) => n.status === 'failed' && fromFailure.includes(n.nodeKey)).map((n) => n.nodeKey));
	const skippedForRerun = $derived(nodes.filter((n) => n.status === 'skipped' && fromFailure.includes(n.nodeKey)).map((n) => n.nodeKey));
	const rerunCaps = $derived(run?.rewriteHistory ? (['run.rerun', 'run.rewrite_history'] as const) : (['run.rerun'] as const));
</script>

<AppTopbar title="Runs">
	{#if run && active}
		<GatedButton requires="run.cancel" busy={busy === 'cancel'} disabled={!!detail?.cancel} reason="Cancel already requested" onclick={() => act('cancel')}>
			{detail?.cancel ? 'Cancelling…' : 'Cancel run'}
		</GatedButton>
	{:else if run}
		<GatedButton requires={[...rerunCaps]} busy={busy === 'all'} onclick={() => act('all')}>↻ Rerun</GatedButton>
		{#if fromFailure.length}
			<div class="relative">
				<GatedButton requires={[...rerunCaps]} variant="default" onclick={() => (confirmFromFailure = !confirmFromFailure)}>▷ Rerun from failure</GatedButton>
				{#if confirmFromFailure}
					<div class="confirm">
						<p>Rerun <b>{fromFailure.length}</b> node{fromFailure.length === 1 ? '' : 's'}: the failed ones plus exactly those skipped because of them.</p>
						{#if failedForRerun.length}<p class="faint">Failed: <code>{failedForRerun.join(', ')}</code></p>{/if}
						{#if skippedForRerun.length}<p class="faint">Skipped: <code>{skippedForRerun.join(', ')}</code></p>{/if}
						<div class="row">
							<Button size="sm" onclick={() => act('from_failure')} disabled={busy === 'from_failure'}>Rerun {fromFailure.length} nodes</Button>
							<Button size="sm" variant="ghost" onclick={() => (confirmFromFailure = false)}>Cancel</Button>
						</div>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<div class="head">
		<a href="/runs" class="back">← Runs</a>
		<span class="font-display text-[17px] font-semibold">{runId}</span>
		{#if run}
			<span class="sb-status" style:--tone={runStatusTone[run.status]}><span></span>{runStatusLabel[run.status].toLowerCase()}</span>
			<span class="meta">
				{#if run.jobKey}<a href="/jobs/{run.jobKey}">{run.jobKey}</a>{:else}ad hoc{/if}
				· {runKindLabel[run.kind].toLowerCase()} · {run.target} · <code>{run.gitRevision}</code>
			</span>
			{#if run.statusReason}<span class="reason" title={run.statusReason}>{run.statusReason}</span>{/if}
			<span class="right">
				<span title={formatStamp(run.startedAt ?? run.queuedAt)}>{formatStamp(run.startedAt ?? run.queuedAt)} · {run.startedAt ? formatDuration(run.startedAt, run.endedAt, app.now) : 'not started'}</span>
				{#if run.cost}<span title={run.cost.source}>· {formatCost(run.cost)}</span>{/if}
				{#if counts.success}<span class="chip ok">{counts.success} ok</span>{/if}
				{#if counts.warn}<button class="chip" style:--c="var(--sb-warning)" onclick={() => tabs?.focusLevel('warn')}>{counts.warn} warn</button>{/if}
				{#if counts.failed}<button class="chip" style:--c="var(--sb-error)" onclick={() => tabs?.focusLevel('error')}>{counts.failed} failed</button>{/if}
				{#if counts.skipped}<span class="chip">{counts.skipped} skipped</span>{/if}
			</span>
		{:else if detailRes.error}
			<span class="err">Couldn't load run: {detailRes.error}</span>
		{:else if detailRes.data === null}
			<span class="faint">Not found in this target</span>
		{/if}
	</div>
	{#if actionError}<div class="action-error">{actionError}</div>{/if}

	{#if detail}
		<RunFacts {detail} />

		<div bind:this={splitEl} class="flex min-h-0 flex-1 flex-col" class:select-none={dragging}>
			<div class="flex min-h-0 flex-col" style:flex={topFrac}>
				<div class="exec-head">
					<span class="label">Execution</span>
					{#if detail.children.length}<span class="faint">{detail.children.length} child runs · nodes from all jobs</span>{/if}
					<div class="seg">
						{#each [['timeline', 'Timeline'], ['graph', 'Graph']] as [v, label] (v)}
							<button class:on={topView === v} onclick={() => (topView = v as typeof topView)}>{label}</button>
						{/each}
					</div>
				</div>
				<div class="flex min-h-0 flex-1">
					<div class="relative flex min-h-0 flex-1 flex-col">
						{#if !nodes.length}
							<div class="empty">{detail.children.length ? 'Child runs have no nodes yet.' : 'No nodes: the run has not been claimed yet.'}</div>
						{:else if topView === 'timeline'}
							<RunGantt nodes={visible} {origin} now={app.now} {selected} {groups} onselect={selectNode} />
						{:else}
							<RunGraph {nodes} edges={detail.edges} ownRunId={detail.run.id} />
						{/if}
					</div>
					<div class="rail sb-scroll">
						{#each NODE_STATUS_ORDER as s (s)}
							{#if counts[s]}
								<button class:on={railFilter.has(s)} style:--c={nodeStatusTone[s]} onclick={() => toggleRail(s)} title="Filter the timeline to {nodeStatusLabel[s].toLowerCase()} nodes">
									<i></i><span>{nodeStatusLabel[s]}</span><b>{counts[s]}</b>
								</button>
							{/if}
						{/each}
						{#if railFilter.size}<button class="clear" onclick={() => (railFilter = new Set())}>✕ clear filter</button>{/if}
					</div>
				</div>
			</div>

			<div
				class="splitter"
				onpointerdown={(e) => {
					dragging = true;
					(e.target as HTMLElement).setPointerCapture(e.pointerId);
				}}
				onpointermove={onDrag}
				onpointerup={() => (dragging = false)}
				role="separator"
				aria-label="Resize panels"
				tabindex="-1"
			><span></span></div>

			<div class="flex min-h-0 flex-col" style:flex={1 - topFrac}>
				<RunTabs
					bind:this={tabs}
					bind:tab
					bind:query
					{detail}
					events={eventsRes.data?.events ?? []}
					output={outputRes.data ?? []}
					statements={statementsRes.data ?? []}
				/>
			</div>
		</div>
	{:else if detailRes.loading}
		<div class="empty">Loading…</div>
	{/if}
</div>

<style>
	.head {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 24px;
		border-bottom: 1px solid var(--border);
		font-size: 12px;
	}
	.back {
		color: var(--muted-foreground);
		font-size: 13px;
	}
	.back:hover,
	.meta a:hover {
		color: var(--foreground);
	}
	.meta {
		color: var(--muted-foreground);
	}
	.meta code,
	code {
		font-family: var(--font-mono);
		font-size: 11.5px;
	}
	.reason {
		overflow: hidden;
		max-width: 420px;
		color: var(--muted-foreground);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.right {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-left: auto;
		color: var(--sb-text-faint);
		font-size: 11.5px;
		white-space: nowrap;
	}
	.chip {
		padding: 1px 6px;
		border-radius: 2px;
		background: color-mix(in srgb, var(--c, var(--sb-text-faint)) 13%, transparent);
		color: var(--c, var(--muted-foreground));
	}
	.chip.ok {
		color: var(--foreground);
		background: transparent;
	}
	.err,
	.action-error {
		color: var(--sb-error);
	}
	.action-error {
		padding: 6px 24px;
		font-size: 12.5px;
	}
	.faint {
		color: var(--sb-text-faint);
	}
	.exec-head {
		position: relative;
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 8px 24px;
		border-bottom: 1px solid var(--border);
		font-size: 11.5px;
	}
	.exec-head .label {
		color: var(--sb-text-faint);
		font-size: 12px;
		font-weight: 600;
	}
	.seg {
		display: flex;
		overflow: hidden;
		margin-left: auto;
		border: 1px solid var(--border);
		border-radius: 2px;
	}
	.seg button {
		padding: 3px 12px;
		color: var(--muted-foreground);
		font-size: 11px;
		font-weight: 500;
	}
	.seg button.on {
		background: var(--sidebar-accent);
		color: var(--foreground);
	}
	.rail {
		width: 200px;
		flex-shrink: 0;
		overflow-y: auto;
		border-left: 1px solid var(--border);
	}
	.rail button {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 10px;
		padding: 9px 14px;
		border-bottom: 1px solid var(--border-subtle);
		color: var(--muted-foreground);
		font-size: 12.5px;
		text-align: left;
	}
	.rail button:hover {
		background: var(--sb-hover);
	}
	.rail button.on {
		background: color-mix(in srgb, var(--c) 10%, transparent);
		color: var(--foreground);
	}
	.rail i {
		width: 8px;
		height: 8px;
		border-radius: 2px;
		background: var(--c);
	}
	.rail b {
		margin-left: auto;
		color: var(--c);
		font-size: 13px;
	}
	.rail .clear {
		color: var(--sb-text-faint);
		font-size: 11px;
	}
	.splitter {
		position: relative;
		height: 7px;
		flex-shrink: 0;
		border-block: 1px solid var(--border);
		background: var(--sb-surface-low);
		cursor: row-resize;
	}
	.splitter span {
		position: absolute;
		top: 50%;
		left: 50%;
		width: 36px;
		height: 3px;
		transform: translate(-50%, -50%);
		border-radius: 999px;
		background: var(--border-strong);
	}
	.empty {
		padding: 32px;
		color: var(--sb-text-faint);
		font-size: 12.5px;
		text-align: center;
	}
	.confirm {
		position: absolute;
		top: calc(100% + 6px);
		right: 0;
		z-index: 60;
		width: 360px;
		padding: 12px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--popover);
		box-shadow: var(--sb-elev);
		font-size: 12.5px;
	}
	.confirm p {
		margin-bottom: 6px;
	}
	.confirm .row {
		display: flex;
		gap: 6px;
		margin-top: 8px;
	}
	.sb-scroll {
		scrollbar-width: thin;
		scrollbar-color: var(--border-strong) transparent;
	}
</style>
