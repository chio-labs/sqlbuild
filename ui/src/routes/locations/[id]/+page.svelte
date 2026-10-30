<script lang="ts">
	import { page } from '$app/state';
	import TriangleAlertIcon from '@lucide/svelte/icons/triangle-alert';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import ConnectionTest from '$lib/components/platform/connection-test.svelte';
	import KeyValues from '$lib/components/platform/key-values.svelte';
	import LocationTokens from '$lib/components/platform/location-tokens.svelte';
	import Panel from '$lib/components/platform/panel.svelte';
	import ProblemList from '$lib/components/platform/problem-list.svelte';
	import SegmentedFilterProblems from '$lib/components/list/segmented-filter.svelte';
	import type { LocationInstance } from '$lib/api';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { healthLabel, healthTone, shortImage } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	const id = $derived(page.params.id ?? '');
	const location = createResource((client) => client.getLocation(id), ['snapshot', 'warehouse_sync']);
	const problems = createResource((client) => client.listPlatformEventHistory({ locationId: id }), ['platform_events']);
	const detail = $derived(location.data ?? null);
	let problemView = $state<'open' | 'all'>('all');
	const problemRows = $derived((problems.data ?? []).filter((e) => problemView === 'all' || e.active));
	const openProblems = $derived((problems.data ?? []).filter((e) => e.active).length);

	let syncTarget = $state('');
	const syncTargetName = $derived(detail?.targets.some((t) => t.name === syncTarget) ? syncTarget : (detail?.targets.find((t) => t.isDefault) ?? detail?.targets[0])?.name ?? '');
	const syncRows = $derived(detail?.targets.find((t) => t.name === syncTargetName)?.stateSync ?? []);
	const current = $derived(detail?.targets.find((t) => t.isDefault) ?? detail?.targets[0] ?? null);

	const instanceTone: Record<LocationInstance['state'], string> = {
		live: 'var(--sb-success)',
		stale: 'var(--sb-warning)',
		gone: 'var(--sb-text-faint)'
	};
</script>

<AppTopbar title="Locations">
	<Button variant="outline" size="sm" onclick={() => (location.refresh(), problems.refresh())}>↻ Refresh</Button>
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
		<a href="/locations" class="text-muted-foreground hover:text-foreground text-[13px]">← Locations</a>
		<span class="font-display text-[17px] font-semibold">{detail?.name ?? ''}</span>
		{#if detail}
			<StatusLabel tone={healthTone[detail.health]} label={healthLabel[detail.health]} />
			{#if openProblems}<a class="text-[12.5px] text-[var(--sb-warning)]" href="#problems">{openProblems} open problem{openProblems === 1 ? '' : 's'}</a>{/if}
		{/if}
	</div>

	{#if location.error}
		<div class="text-[var(--sb-error)] px-6 py-4 text-[13px]">Couldn't load this location: {location.error}</div>
	{:else if location.data === null}
		<div class="text-muted-foreground px-6 py-4 text-[13px]">No location with ID <code>{id}</code>.</div>
	{:else if !detail}
		<div class="text-muted-foreground px-6 py-4 text-[13px]">Loading…</div>
	{:else}
		<div class="flex min-h-0 flex-1">
			<div class="min-h-0 flex-1 overflow-auto p-6">
				{#if detail.failedDeploy}
					<div class="fallback">
						<TriangleAlertIcon size={15} />
						<div class="min-w-0 flex-1">
							<div class="headline">
								The deploy of commit <code>{detail.failedDeploy.gitRevision}</code> failed {formatAgo(detail.failedDeploy.attemptedAt, app.now)}.
								{#if detail.brokenDeployPolicy === 'fallback'}
									Still running the previous version{current?.snapshot ? ` (version ${current.snapshot.generation}, commit ${current.snapshot.gitRevision})` : ''}.
								{:else}
									Scheduled runs wait until a deploy works.
								{/if}
							</div>
							<p>Fix the error below and deploy again. A deploy only takes over once it loads without errors.</p>
							<pre>{detail.failedDeploy.error}</pre>
							<details>
								<summary>Details</summary>
								<p>
									Failed image <code>{shortImage(detail.failedDeploy.imageId)}</code>; running image <code>{shortImage(current?.imageId ?? null)}</code>. Broken-deploy policy
									<code>{detail.brokenDeployPolicy}</code>: {detail.brokenDeployPolicy === 'fallback' ? 'scheduled runs keep starting from the last good version.' : 'scheduled runs wait, and the problem stays open.'}
								</p>
							</details>
						</div>
					</div>
				{:else if detail.lastLoadError}
					<div class="fallback">
						<TriangleAlertIcon size={15} />
						<div class="min-w-0 flex-1">
							<div class="headline">The last load reported an error</div>
							<pre>{detail.lastLoadError}</pre>
						</div>
					</div>
				{/if}

				<div id="problems">
					<Panel title="Problems" note="Overdue schedules, failed deploys, runs that couldn't start and failed connection tests, with the sensors that reacted">
						{#snippet actions()}
							<SegmentedFilterProblems
								bind:value={problemView}
								options={[
									{ value: 'open', label: 'Open', count: openProblems },
									{ value: 'all', label: 'History', count: problems.data?.length ?? 0 }
								]}
							/>
						{/snippet}
						<ProblemList events={problemRows} resource={problems} currentLocationId={id} empty={problemView === 'open' ? 'No open problems. Everything is running normally.' : 'No problems recorded for this location.'} />
					</Panel>
				</div>

				<Panel title="Targets" note="The deployed version per target, and the warehouse connection test run after each deploy">
					<table class="sb-list static">
						<thead>
							<tr>
								<th>Target</th>
								<th>Deployed version</th>
								<th>Image</th>
								<th>Warehouse connection</th>
							</tr>
						</thead>
						<tbody>
							{#each detail.targets as t (t.name)}
								<tr>
									<td>
										<strong>{t.name}</strong>{#if t.isDefault}<span class="muted"> · default</span>{/if}
										<div class="cell-desc">{t.adapter}</div>
									</td>
									<td>
										{#if t.snapshot}
											<div title="Snapshot {t.snapshot.id}, generation {t.snapshot.generation}">Version {t.snapshot.generation} · commit <code>{t.snapshot.gitRevision}</code>{#if t.snapshot.gitDirty}<span class="warn"> (with uncommitted changes)</span>{/if}</div>
											<div class="cell-desc" title={formatStamp(t.snapshot.publishedAt)}>
												by {t.snapshot.gitAuthor} · deployed {formatAgo(t.snapshot.publishedAt, app.now)} · sqb {t.snapshot.sqbVersion}
											</div>
										{:else}
											<span class="muted">Nothing deployed yet</span>
										{/if}
									</td>
									<td>{#if t.imageId}<code title={t.imageId}>{shortImage(t.imageId)}</code>{:else}<span class="muted" title="Runs start as local processes, not containers">local</span>{/if}</td>
									<td class="test-cell">
										<ConnectionTest scope={{ locationId: detail.id, target: t.name }} connection={t.warehouseConnection} last={t.connectionTest} />
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</Panel>

				<Panel title="Warehouse sync" note="SQLBuild's own tables in the warehouse, read back by the location so this UI shows what was built">
					{#snippet actions()}
						{#if detail.targets.length > 1}
							<SegmentedFilter bind:value={() => syncTargetName, (v) => (syncTarget = v)} options={detail.targets.map((t) => ({ value: t.name, label: t.name }))} />
						{/if}
					{/snippet}
					<table class="sb-list static">
						<thead>
							<tr>
								<th>Table</th>
								<th class="num">Schemas</th>
								<th>Last synced</th>
								<th class="num" title="Rows read by the last sync">New rows</th>
								<th class="num" title="Warehouse cost of the sync queries in the last 24 hours">Cost, 24h</th>
							</tr>
						</thead>
						<tbody>
							{#each syncRows as row (row.table)}
								<tr>
									<td>
										<code>{row.table}</code>
										{#if row.lastError}<div class="cell-desc err" title={row.lastError}>{row.lastError}</div>{/if}
									</td>
									<td class="num muted">{row.schemas}</td>
									<td>
										{#if row.lastError}
											<StatusLabel tone="var(--sb-error)" label="Failing; last worked {formatAgo(row.lastSyncedAt, app.now)}" />
										{:else}
											<RelativeTime value={formatAgo(row.lastSyncedAt, app.now)} exact={formatStamp(row.lastSyncedAt)} />
										{/if}
									</td>
									<td class="num muted">{row.rowsLastPass}</td>
									<td class="num muted" title={row.cost24h ? undefined : 'This warehouse has no cost concept'}>
										{row.cost24h ? `${row.cost24h.amount} ${row.cost24h.unit}` : '—'}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</Panel>

				<Panel title="Location processes" note="Running copies of this location that load the code and start runs">
					<table class="sb-list static">
						<thead>
							<tr>
								<th>Process</th>
								<th>Image</th>
								<th>Commit</th>
								<th>Started</th>
								<th>Last seen</th>
							</tr>
						</thead>
						<tbody>
							{#each detail.instances as i (i.id)}
								<tr class:sb-row-off={i.state === 'gone'}>
									<td><StatusLabel tone={instanceTone[i.state]} label={i.id} /></td>
									<td><code title={i.imageId}>{shortImage(i.imageId)}</code></td>
									<td><code>{i.gitRevision}</code></td>
									<td><RelativeTime value={formatAgo(i.startedAt, app.now)} exact={formatStamp(i.startedAt)} /></td>
									<td><RelativeTime value={formatAgo(i.lastSeenAt, app.now)} exact={formatStamp(i.lastSeenAt)} /></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</Panel>
			</div>

			<aside class="w-[320px] shrink-0 overflow-auto border-l border-border p-5">
				<div class="rail-title">Location</div>
				<KeyValues
					rows={[
						{ label: 'ID', value: detail.id, mono: true },
						{ label: 'Created', value: formatAgo(detail.createdAt, app.now), title: formatStamp(detail.createdAt) },
						{ label: 'If a deploy fails', value: detail.brokenDeployPolicy === 'fallback' ? 'Keep running the previous version' : 'Hold scheduled runs until a deploy works' },
						{ label: 'Targets', value: detail.targets.map((t) => t.name).join(', ') }
					]}
				/>
				<div class="rail-title mt-6">Location tokens</div>
				<p class="rail-note">A location token lets this location's processes connect to the server, deploy new versions and report problems. It can't do anything else.</p>
				<LocationTokens locationId={detail.id} />
			</aside>
		</div>
	{/if}
</div>

<style>
	.fallback {
		display: flex;
		gap: 10px;
		margin-bottom: 24px;
		padding: 12px 14px;
		border: 1px solid color-mix(in srgb, var(--sb-warning) 40%, var(--border));
		border-radius: 2px;
		background: color-mix(in srgb, var(--sb-warning) 8%, var(--background));
		font-size: 12.5px;
	}
	.fallback > :global(svg) {
		margin-top: 2px;
		color: var(--sb-warning);
	}
	.headline {
		font-weight: 600;
	}
	.fallback p {
		margin: 4px 0 8px;
		color: var(--muted-foreground);
	}
	.fallback details {
		margin-top: 6px;
		color: var(--muted-foreground);
	}
	.fallback summary {
		cursor: pointer;
	}
	#problems {
		scroll-margin-top: 12px;
	}
	pre {
		overflow: auto;
		padding: 8px 10px;
		border-radius: 2px;
		background: var(--sb-inset);
		color: var(--sb-mono-err);
		font-family: var(--font-mono);
		font-size: 12px;
		white-space: pre-wrap;
	}
	code {
		font-family: var(--font-mono);
		font-size: 12px;
	}
	.static {
		border-top: 1px solid var(--border);
	}
	:global(.sb-list.static tbody tr) {
		cursor: default;
	}
	.test-cell {
		width: 42%;
		max-width: 0;
	}
	.muted {
		color: var(--muted-foreground);
	}
	.warn {
		color: var(--sb-warning);
	}
	.err {
		color: var(--sb-error) !important;
	}
	.rail-title {
		margin-bottom: 8px;
		color: var(--sb-text-faint);
		font-size: 12px;
		font-weight: 500;
	}
	.rail-note {
		margin-bottom: 8px;
		color: var(--muted-foreground);
		font-size: 12px;
	}
</style>
