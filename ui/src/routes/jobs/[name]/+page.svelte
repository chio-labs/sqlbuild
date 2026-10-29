<script lang="ts">
	import { page } from '$app/state';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import type { OnFailure, Trigger } from '$lib/api';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatAgo, formatDuration, formatStamp } from '$lib/format/time';
	import { formatNodeCounts, runStatusLabel, runStatusTone } from '$lib/status';

	const name = $derived(page.params.name ?? '');

	const job = createResource((client, scope) => client.getJob(scope, name), ['jobs', 'runs']);
	const jobRuns = createResource((client, scope) => client.listRuns(scope, { jobKey: name, limit: 8 }), ['runs']);
	const triggers = createResource((client, scope) => client.listTriggers(scope), ['triggers']);

	const def = $derived(job.data ?? null);
	const jobTriggers = $derived((triggers.data ?? []).filter((t) => t.jobKey === name));
	const runs = $derived(jobRuns.data ?? []);
	const canToggle = $derived(app.can('trigger.toggle'));
	const canRun = $derived(app.can('job.run'));

	async function toggleTrig(trigger: Trigger) {
		const scope = app.scope;
		if (!scope) return;
		await app.client.setTriggerState(scope, trigger.name, trigger.state === 'running' ? 'paused' : 'running');
	}

	const onFailureLabel: Record<OnFailure, string> = {
		skip_dependents: 'Skip dependents',
		skip_downstream_jobs: 'Skip downstream jobs',
		stop_group: 'Stop group'
	};

	// Resolved selection is still prototype data until the API serves it.
	type NodeStatus = 'ok' | 'fail' | 'warn' | 'stale' | 'src';
	const resolved: { name: string; kind: string; status: NodeStatus }[] = [
		{ name: 'raw__customers', kind: 'source', status: 'src' },
		{ name: 'raw__orders', kind: 'source', status: 'src' },
		{ name: 'raw__payments', kind: 'source', status: 'src' },
		{ name: 'stg_customers', kind: 'view', status: 'ok' },
		{ name: 'stg_orders', kind: 'view', status: 'ok' },
		{ name: 'stg_payments', kind: 'view', status: 'warn' },
		{ name: 'fact_orders', kind: 'table', status: 'ok' },
		{ name: 'dim_customers', kind: 'table', status: 'ok' },
		{ name: 'daily_revenue', kind: 'table', status: 'ok' },
		{ name: 'customer_status', kind: 'incremental', status: 'stale' },
		{ name: 'hourly_order_act', kind: 'incremental', status: 'ok' },
		{ name: 'hourly_activity_ctx', kind: 'incremental', status: 'fail' }
	];
	const statusColor: Record<NodeStatus, string> = {
		ok: 'var(--sb-success)',
		fail: 'var(--sb-error)',
		warn: 'var(--sb-warning)',
		stale: 'var(--sb-stale)',
		src: 'var(--sb-text-faint)'
	};
	function kindColor(kind: string): string {
		if (kind.startsWith('source') || kind.startsWith('seed') || kind.startsWith('loader')) return '#7c8aa5';
		if (kind === 'view') return '#5aa9e6';
		if (kind === 'table') return '#2e90ff';
		return '#3fb6c9';
	}

</script>

<AppTopbar title="Jobs">
	<Button size="sm" disabled={!canRun || !def} title={canRun ? undefined : 'Requires job.run'}>▷ Launch</Button>
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<!-- header -->
	<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
		<a href="/jobs" class="text-muted-foreground hover:text-foreground text-[13px]">← Jobs</a>
		<span class="font-display text-[17px] font-semibold">{name}</span>
		{#if def?.kind === 'group'}
			<span class="text-muted-foreground text-[12px]">Group · {def.members.join(' → ')}</span>
		{:else if def}
			<code class="bg-secondary rounded-[2px] px-1.5 py-0.5 font-mono text-[11px]" style="color:var(--syn-keyword)">--select {def.select}</code>
		{/if}
		{#if def}<span class="text-muted-foreground text-[12px]">· {def.nodeCount} nodes</span>{/if}
	</div>

	{#if job.error}
		<div class="text-[var(--sb-error)] px-6 py-4 text-[13px]">Couldn't load this job: {job.error}</div>
	{:else if job.data === null}
		<div class="text-muted-foreground px-6 py-4 text-[13px]">No job or group named <code>{name}</code> in this target's snapshot.</div>
	{/if}

	<div class="sb-scroll flex min-h-0 flex-1">
		<!-- main -->
		<div class="sb-scroll min-h-0 flex-1 overflow-auto p-6">
			<p class="text-muted-foreground mb-6 max-w-[760px] text-[13px] leading-relaxed">{def?.description ?? ''}</p>

			<!-- recent runs -->
			<div class="mb-7">
				<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Recent runs</div>
				<table class="w-full border-collapse">
					<tbody>
						{#each runs as r (r.id)}
							<tr class="hover:bg-[var(--sb-hover)] cursor-pointer border-b border-[var(--border-subtle)]" onclick={() => (window.location.href = `/runs/${r.id}`)}>
								<td class="py-2.5 pr-3"><span class="inline-block h-1.5 w-1.5 rounded-[2px]" style:background={runStatusTone[r.status]} title={runStatusLabel[r.status]}></span></td>
								<td class="py-2.5 pr-4"><a href="/runs/{r.id}" class="hover:text-primary text-[12.5px]">{r.id}</a></td>
								<td class="text-muted-foreground py-2.5 pr-4 text-[11.5px]">{runStatusLabel[r.status]} · {formatNodeCounts(r.nodeCounts)}</td>
								<td class="text-[var(--sb-text-faint)] py-2.5 pr-4 text-[11.5px]">{r.startedAt ? formatDuration(r.startedAt, r.endedAt, app.now) : '—'}</td>
								<td class="text-[var(--sb-text-faint)] py-2.5 pr-4 text-[11.5px]" title={formatStamp(r.queuedAt)}>{formatAgo(r.startedAt ?? r.queuedAt, app.now)}</td>
								<td class="text-muted-foreground py-2.5 text-[11.5px]">{r.requestedBy.name}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<!-- resolved nodes -->
			<div>
				<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Selected nodes · {resolved.length}</div>
				<div class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-1.5">
					{#each resolved as n (n.name)}
						<a href="/catalog/{n.name}" class="bg-secondary hover:bg-[var(--sb-hover)] flex items-center gap-2 rounded-[2px] border border-border px-2.5 py-1.5">
							<span class="h-[9px] w-[9px] shrink-0 rounded-[2px]" style:background={kindColor(n.kind)}></span>
							<span class="truncate text-[12px]">{n.name}</span>
							<span class="h-1.5 w-1.5 shrink-0 rounded-[2px]" style:background={statusColor[n.status]} title={n.status}></span>
						</a>
					{/each}
				</div>
			</div>
		</div>

		<!-- right: definition rail -->
		<div class="sb-scroll w-[280px] shrink-0 overflow-auto border-l border-border p-5">
			<div class="text-[var(--sb-text-faint)] mb-2 text-[12px] font-medium">Definition</div>
			<div class="flex flex-col gap-2 text-[12.5px]">
				{#each def ? [['Kind', def.kind === 'group' ? 'Group' : 'Job'], ['Selector', def.select ?? '—'], ['Overlap', def.overlap], ['On failure', onFailureLabel[def.onFailure]], ['Concurrency groups', def.concurrencyGroups.join(', ') || '—'], ['Source', def.sourceFile]] : [] as [k, v] (k)}
					<div class="flex items-baseline justify-between gap-3">
						<span class="text-muted-foreground shrink-0">{k}</span>
						<span class="truncate text-right text-[11.5px]" title={v}>{v}</span>
					</div>
				{/each}
			</div>
			<div class="mt-5">
				<div class="text-[var(--sb-text-faint)] mb-1.5 flex items-center justify-between text-[12px] font-medium">
					<span>Triggers · {jobTriggers.length}</span>
					<a href="/triggers" class="text-[var(--sb-text-faint)] hover:text-primary normal-case tracking-normal">all →</a>
				</div>
				{#if jobTriggers.length === 0}
					<div class="text-[var(--sb-text-faint)] text-[11.5px]">No trigger — run manually.</div>
				{:else}
					<div class="flex flex-col gap-1.5">
						{#each jobTriggers as t (t.name)}
							<div class="flex items-center gap-2 rounded-[2px] border border-[var(--border-subtle)] px-2.5 py-2" style:opacity={t.state === 'running' ? 1 : 0.6}>
								<span class="text-[var(--sb-text-faint)] shrink-0 text-[11px]">{t.type === 'schedule' ? '◷' : '⚡'}</span>
								<div class="min-w-0">
									<div class="truncate text-[11.5px]">{t.name}</div>
									<div class="text-[var(--sb-text-faint)] truncate text-[11.5px]">{t.cadence}</div>
								</div>
								<button
									class="sb-toggle ml-auto"
									class:on={t.state === 'running'}
									disabled={!canToggle}
									onclick={() => toggleTrig(t)}
									title={canToggle ? (t.state === 'running' ? 'Pause' : 'Resume') : 'Requires trigger.toggle'}
									aria-label="Toggle {t.name}"
								></button>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.sb-scroll {
		scrollbar-width: thin;
		scrollbar-color: var(--border-strong) transparent;
	}
	.sb-scroll::-webkit-scrollbar {
		width: 9px;
		height: 9px;
	}
	.sb-scroll::-webkit-scrollbar-thumb {
		background: var(--border-strong);
		border-radius: 2px;
		border: 2px solid transparent;
		background-clip: content-box;
	}
</style>
