<script lang="ts">
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';
	import { goto } from '$app/navigation';
	import type { Run } from '$lib/api';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import type { Resource } from '$lib/state/resource.svelte';
	import { app } from '$lib/state/app.svelte';
	import { formatAgo, formatDuration, formatStamp } from '$lib/format/time';
	import { formatNodeCounts, runKindLabel, runStatusLabel, runStatusTone } from '$lib/status';
	import { formatCost } from '$lib/operate/labels';

	let {
		runs,
		children,
		resource,
		emptyText
	}: {
		/** Top-level runs, already filtered and sorted. */
		runs: Run[];
		/** Child runs by parent run ID. */
		children: Map<string, Run[]>;
		resource: Resource<unknown>;
		emptyText: string;
	} = $props();

	let expanded = $state<Set<string>>(new Set());
	function toggle(id: string) {
		const next = new Set(expanded);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		expanded = next;
	}
</script>

{#snippet row(r: Run, child: boolean)}
	<tr class:child onclick={() => goto(`/runs/${r.id}`)} title={r.statusReason ?? undefined}>
		<td>
			<div class="run-cell">
				{#if r.childRunCount && !child}
					<button
						class="caret"
						onclick={(e) => {
							e.stopPropagation();
							toggle(r.id);
						}}
						aria-label="{expanded.has(r.id) ? 'Hide' : 'Show'} child runs"
					>
						{#if expanded.has(r.id)}<ChevronDownIcon size={14} />{:else}<ChevronRightIcon size={14} />{/if}
					</button>
				{:else}
					<span class="caret-space"></span>
				{/if}
				<StatusLabel tone={runStatusTone[r.status]} label={runStatusLabel[r.status]} />
				<a class="code muted" href="/runs/{r.id}" onclick={(e) => e.stopPropagation()}>{r.id}</a>
			</div>
		</td>
		<td>
			{#if r.jobKey}
				<a class="link" href="/jobs/{r.jobKey}" onclick={(e) => e.stopPropagation()}>{r.jobKey}</a>
				{#if r.childRunCount && !child}<span class="muted"> · {r.childRunCount} jobs</span>{/if}
			{:else}
				<span class="muted">Ad hoc selection</span>
			{/if}
		</td>
		<td class="muted">
			{runKindLabel[r.kind]}{#if r.rerunOfRunId}<span> of <a class="link code" href="/runs/{r.rerunOfRunId}" onclick={(e) => e.stopPropagation()}>{r.rerunOfRunId}</a></span>{/if}
		</td>
		<td>
			{#if r.triggerId && r.triggerName}
				<a class="link" href="/triggers/{r.triggerId}" onclick={(e) => e.stopPropagation()}>{r.triggerName}</a>
				{#if r.tickScheduledFor}<div class="cell-desc" title="Tick {r.tickId}">tick {formatStamp(r.tickScheduledFor)}</div>{/if}
				{#if r.runKey}<div class="cell-desc code" title="Sensor run key">{r.runKey}</div>{/if}
			{:else}
				<span class="muted">—</span>
			{/if}
		</td>
		<td class="muted">{r.requestedBy.name}</td>
		<td class="muted">{formatNodeCounts(r.nodeCounts)}</td>
		<td>
			{#if r.startedAt}
				<RelativeTime value={formatAgo(r.startedAt, app.now)} exact={formatStamp(r.startedAt)} />
			{:else}
				<span class="muted">Queued {formatAgo(r.queuedAt, app.now)}</span>
			{/if}
		</td>
		<td class="num muted">{r.startedAt ? formatDuration(r.startedAt, r.endedAt, app.now) : '—'}</td>
		<td class="num muted" title={r.cost?.source ?? (r.endedAt ? 'No cost reported for this adapter' : 'Reported once the run ends')}>{formatCost(r.cost)}</td>
	</tr>
{/snippet}

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th>Run</th>
				<th>Job</th>
				<th>Kind</th>
				<th>Trigger</th>
				<th>Requested by</th>
				<th>Nodes</th>
				<th>Started</th>
				<th class="num">Duration</th>
				<th class="num">Cost</th>
			</tr>
		</thead>
		<tbody>
			{#each runs as r (r.id)}
				{@render row(r, false)}
				{#if expanded.has(r.id)}
					{#each children.get(r.id) ?? [] as c (c.id)}{@render row(c, true)}{/each}
				{/if}
			{:else}
				<LoadRow colspan={9} {resource} empty={emptyText} />
			{/each}
		</tbody>
	</table>
</div>

<style>
	td {
		white-space: nowrap;
	}
	.run-cell {
		display: grid;
		grid-template-columns: 18px 124px auto;
		align-items: center;
		gap: 8px;
	}
	.caret {
		display: grid;
		place-items: center;
		width: 18px;
		height: 18px;
		border-radius: 2px;
		color: var(--muted-foreground);
	}
	.caret:hover {
		background: var(--border);
		color: var(--foreground);
	}
	tr.child td:first-child {
		padding-left: 44px;
	}
	tr.child {
		background: color-mix(in srgb, var(--sb-hover) 45%, transparent);
	}
</style>
