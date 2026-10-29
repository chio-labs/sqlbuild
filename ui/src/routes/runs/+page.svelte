<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { RUN_KINDS, RUN_ORIGINS, RUN_STATUSES, type Run, type RunKind, type RunOrigin, type RunStatus } from '$lib/api';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import ChoiceFilter from '$lib/components/list/choice-filter.svelte';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import GatedButton from '$lib/components/operate/gated-button.svelte';
	import RunTimeline from '$lib/components/timeline/run-timeline.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import RunPanel from '$lib/run/run-panel.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { isActiveRun, isProblemRun, runKindLabel, runOriginLabel, runStatusLabel } from '$lib/status';
	import RunList from './run-list.svelte';
	import RunQueue from './run-queue.svelte';

	type View = 'list' | 'timeline' | 'queue';
	type StatusFilter = 'active' | 'problems' | RunStatus;
	type Window = '24h' | '7d';

	const VIEWS: View[] = ['list', 'timeline', 'queue'];
	const initialView = page.url.searchParams.get('view');
	let view = $state<View>(VIEWS.find((v) => v === initialView) ?? 'list');
	let query = $state('');
	let status = $state<StatusFilter | ''>('');
	let kind = $state<RunKind | ''>('');
	let origin = $state<RunOrigin | ''>('');
	let period = $state<Window | ''>('24h');
	let panelOpen = $state(false);

	$effect(() => {
		const url = new URL(globalThis.location.href);
		if (view === 'list') url.searchParams.delete('view');
		else url.searchParams.set('view', view);
		if (url.href !== globalThis.location.href) goto(url, { replaceState: true, noScroll: true, keepFocus: true });
	});

	const since = $derived(period ? new Date(Date.now() - (period === '24h' ? 1 : 7) * 86_400_000).toISOString() : undefined);
	const runs = createResource((client, scope) => client.listRuns(scope, { since }), ['runs']);
	const queue = createResource((client, scope) => client.listQueue(scope), ['runs']);

	const all = $derived(runs.data ?? []);
	const children = $derived.by(() => {
		const map = new Map<string, Run[]>();
		for (const r of all) if (r.parentRunId) map.set(r.parentRunId, [...(map.get(r.parentRunId) ?? []), r]);
		for (const list of map.values()) list.sort((a, b) => a.queuedAt.localeCompare(b.queuedAt) || a.id.localeCompare(b.id));
		return map;
	});
	const topLevel = $derived(all.filter((r) => !r.parentRunId));

	function statusMatches(r: Run): boolean {
		if (!status) return true;
		if (status === 'active') return isActiveRun(r.status);
		if (status === 'problems') return isProblemRun(r.status);
		return r.status === status;
	}

	const filtered = $derived(
		topLevel
			.filter((r) => {
				if (!statusMatches(r) || (kind && r.kind !== kind) || (origin && r.origin !== origin)) return false;
				const q = query.trim().toLowerCase();
				return !q || `${r.id} ${r.jobKey ?? ''} ${r.triggerName ?? ''} ${r.requestedBy.name} ${r.runKey ?? ''}`.toLowerCase().includes(q);
			})
			.sort((a, b) => Number(isActiveRun(b.status)) - Number(isActiveRun(a.status)) || b.queuedAt.localeCompare(a.queuedAt))
	);

	const activeCount = $derived(topLevel.filter((r) => isActiveRun(r.status)).length);
	const problemCount = $derived(topLevel.filter((r) => isProblemRun(r.status)).length);
	const statusOptions = $derived<{ value: StatusFilter; label: string; count: number }[]>([
		{ value: 'active', label: 'Active', count: activeCount },
		{ value: 'problems', label: 'Failed, partial or presumed failed', count: problemCount },
		...RUN_STATUSES.map((s) => ({ value: s, label: runStatusLabel[s], count: topLevel.filter((r) => r.status === s).length }))
	]);
	const kindOptions = $derived(RUN_KINDS.map((k) => ({ value: k, label: runKindLabel[k], count: topLevel.filter((r) => r.kind === k).length })));
	const originOptions = $derived(RUN_ORIGINS.map((o) => ({ value: o, label: runOriginLabel[o], count: topLevel.filter((r) => r.origin === o).length })));
	const queueEntries = $derived(queue.data ?? []);
	const queueFiltered = $derived(
		queueEntries.filter((e) => {
			const q = query.trim().toLowerCase();
			return !q || `${e.run.id} ${e.run.jobKey ?? ''} ${e.run.requestedBy.name}`.toLowerCase().includes(q);
		})
	);
</script>

<AppTopbar title="Runs">
	<GatedButton requires="run.adhoc" variant="default" onclick={() => (panelOpen = true)}>▷ New run</GatedButton>
	<Button variant="outline" size="sm" onclick={() => (runs.refresh(), queue.refresh())}>↻ Refresh</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder={view === 'timeline' ? 'Search jobs' : 'Search runs, jobs, triggers, run keys'}
	total={view === 'timeline' ? 'Timeline' : view === 'queue' ? `${queueEntries.length} queued` : `${filtered.length} of ${topLevel.length} runs`}
	counts={view === 'list'
		? [
				{ tone: 'var(--sb-running)', count: activeCount, label: 'active' },
				{ tone: 'var(--sb-error)', count: problemCount, label: 'failed or partial' }
			]
		: []}
>
	{#snippet filters()}
		<SegmentedFilter
			bind:value={view}
			options={[
				{ value: 'list', label: 'List' },
				{ value: 'timeline', label: 'Timeline' },
				{ value: 'queue', label: 'Queue', count: queueEntries.length }
			]}
		/>
		{#if view === 'list'}
			<ChoiceFilter label="Status" bind:value={status} options={statusOptions} />
			<ChoiceFilter label="Kind" bind:value={kind} options={kindOptions} />
			<ChoiceFilter label="Origin" bind:value={origin} options={originOptions} />
			<ChoiceFilter label="Queued" bind:value={period} all="Any time" options={[{ value: '24h', label: 'Last 24h' }, { value: '7d', label: 'Last 7 days' }]} />
		{/if}
	{/snippet}
</ListToolbar>

{#if view === 'timeline'}
	<div class="timeline-page"><RunTimeline bind:query showSearch={false} /></div>
{:else if view === 'queue'}
	<RunQueue entries={queueFiltered} resource={queue} />
{:else}
	<RunList runs={filtered} {children} resource={runs} emptyText={topLevel.length ? 'No runs match the filter.' : 'No runs in this window for this target.'} />
{/if}

<RunPanel bind:open={panelOpen} />

<style>
	.timeline-page {
		display: flex;
		min-height: 0;
		flex: 1;
		flex-direction: column;
	}
</style>
