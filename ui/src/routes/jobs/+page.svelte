<script lang="ts">
	import WorkflowIcon from '@lucide/svelte/icons/workflow';
	import LayersIcon from '@lucide/svelte/icons/layers';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import FilterButton from '$lib/components/list/filter-button.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import { goto } from '$app/navigation';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import type { Trigger } from '$lib/api';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { isProblemRun, runStatusLabel, runStatusTone } from '$lib/status';

	const jobs = createResource((client, scope) => client.listJobs(scope), ['jobs', 'runs']);
	const triggers = createResource((client, scope) => client.listTriggers(scope), ['triggers']);

	const triggerByName = $derived(new Map((triggers.data ?? []).map((t) => [t.name, t])));
	const canToggle = $derived(app.can('trigger.toggle'));

	async function toggle(trigger: Trigger) {
		const scope = app.scope;
		if (!scope) return;
		await app.client.setTriggerState(scope, trigger.name, trigger.state === 'running' ? 'paused' : 'running');
	}

	let query = $state('');
	const all = $derived(jobs.data ?? []);
	const filtered = $derived(
		all.filter((j) => {
			if (!query.trim()) return true;
			const q = query.toLowerCase();
			return j.key.toLowerCase().includes(q) || j.description.toLowerCase().includes(q) || (j.select ?? '').toLowerCase().includes(q);
		})
	);
	const scheduledCount = $derived(all.filter((j) => j.triggerNames.some((n) => triggerByName.get(n)?.state === 'running')).length);
	const failingCount = $derived(all.filter((j) => j.lastRun && isProblemRun(j.lastRun.status)).length);
</script>

<AppTopbar title="Jobs">
	<Button variant="outline" size="sm" onclick={() => (jobs.refresh(), triggers.refresh())}>↻ Refresh</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search jobs"
	total="{filtered.length} of {all.length} jobs and groups"
	counts={[
		{ tone: 'var(--sb-success)', count: scheduledCount, label: 'with a running trigger' },
		{ tone: 'var(--sb-error)', count: failingCount, label: 'failing' }
	]}
>
	{#snippet filters()}
		<FilterButton label="Kind" />
		<FilterButton label="Last run" />
	{/snippet}
</ListToolbar>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th>Job</th>
				<th>Selector</th>
				<th class="num">Nodes</th>
				<th>Triggers</th>
				<th>Last run</th>
				<th>When</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as j (j.key)}
				{@const jobTriggers = j.triggerNames.map((n) => triggerByName.get(n)).filter((t) => t !== undefined)}
				<tr onclick={() => goto(`/jobs/${j.key}`)}>
					<td>
						<div class="cell-name">
							{#if j.kind === 'group'}<LayersIcon size={15} strokeWidth={1.75} />{:else}<WorkflowIcon size={15} strokeWidth={1.75} />{/if}
							<div class="min-w-0">
								<a href="/jobs/{j.key}" onclick={(e) => e.stopPropagation()}>{j.key}</a>
								<div class="cell-desc">{j.description}</div>
							</div>
						</div>
					</td>
					<td>
						{#if j.kind === 'group'}
							<span class="muted">Group · {j.members.join(' → ')}</span>
						{:else}
							<code>{j.select}</code>
						{/if}
					</td>
					<td class="num muted">{j.nodeCount}</td>
					<td>
						{#if jobTriggers.length === 0}
							<span class="muted">Manual</span>
						{:else}
							<div class="flex flex-col gap-1">
								{#each jobTriggers as t (t.name)}
									<div class="flex items-center gap-2.5">
										<button
											class="sb-toggle"
											class:on={t.state === 'running'}
											disabled={!canToggle}
											onclick={(e) => {
												e.stopPropagation();
												void toggle(t);
											}}
											title={canToggle ? (t.state === 'running' ? 'Pause trigger' : 'Resume trigger') : 'Requires trigger.toggle'}
											aria-label="Toggle trigger {t.name}"
										></button>
										<span class:muted={t.state === 'paused'}>{t.cadence}</span>
									</div>
								{/each}
							</div>
						{/if}
					</td>
					<td>
						{#if j.lastRun}
							<StatusLabel tone={runStatusTone[j.lastRun.status]} label={runStatusLabel[j.lastRun.status]} />
						{:else}
							<span class="muted">Never run</span>
						{/if}
					</td>
					<td>
						{#if j.lastRun}
							<RelativeTime value={formatAgo(j.lastRun.startedAt, app.now)} exact={formatStamp(j.lastRun.startedAt)} />
						{:else}
							<span class="muted">—</span>
						{/if}
					</td>
				</tr>
			{:else}
				<LoadRow colspan={6} resource={jobs} empty={all.length ? 'No jobs match the filter.' : 'No jobs are defined in this snapshot.'} />
			{/each}
		</tbody>
	</table>
</div>
