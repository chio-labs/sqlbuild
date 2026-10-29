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
	import type { LocationInstance } from '$lib/api';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { healthLabel, healthTone, shortImage } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	const id = $derived(page.params.id ?? '');
	const location = createResource((client) => client.getLocation(id), ['snapshot', 'warehouse_sync']);
	const detail = $derived(location.data ?? null);

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
	<Button variant="outline" size="sm" onclick={() => location.refresh()}>↻ Refresh</Button>
</AppTopbar>

<div class="flex min-h-0 flex-1 flex-col">
	<div class="flex items-center gap-3 border-b border-border px-6 py-3.5">
		<a href="/locations" class="text-muted-foreground hover:text-foreground text-[13px]">← Locations</a>
		<span class="font-display text-[17px] font-semibold">{detail?.name ?? ''}</span>
		{#if detail}
			<StatusLabel tone={healthTone[detail.health]} label={healthLabel[detail.health]} />
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
								Deploy <code>{detail.failedDeploy.gitRevision}</code> (image <code>{shortImage(detail.failedDeploy.imageId)}</code>) failed {formatAgo(detail.failedDeploy.attemptedAt, app.now)},
								{#if detail.brokenDeployPolicy === 'fallback'}
									running on <code>{current?.snapshot?.gitRevision ?? '—'}</code> (image <code>{shortImage(current?.imageId ?? null)}</code>)
								{:else}
									scheduled runs are queued until a deploy publishes
								{/if}
							</div>
							<p>
								A deploy becomes current only once it publishes a valid snapshot. Policy <code>{detail.brokenDeployPolicy}</code>:
								{detail.brokenDeployPolicy === 'fallback'
									? 'scheduled runs keep starting from the last good snapshot and image.'
									: 'scheduled runs wait, and a platform alert stays open.'}
							</p>
							<pre>{detail.failedDeploy.error}</pre>
						</div>
					</div>
				{:else if detail.lastLoadError}
					<div class="fallback">
						<TriangleAlertIcon size={15} />
						<div class="min-w-0 flex-1">
							<div class="headline">Last load error</div>
							<pre>{detail.lastLoadError}</pre>
						</div>
					</div>
				{/if}

				<Panel title="Targets" note="Current snapshot and the connection test run after each publish">
					<table class="sb-list static">
						<thead>
							<tr>
								<th>Target</th>
								<th>Current snapshot</th>
								<th>Image</th>
								<th>Connection test</th>
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
											<div>Generation {t.snapshot.generation} · <code>{t.snapshot.gitRevision}</code>{#if t.snapshot.gitDirty}<span class="warn"> (uncommitted changes)</span>{/if}</div>
											<div class="cell-desc" title={formatStamp(t.snapshot.publishedAt)}>
												{t.snapshot.gitAuthor} · published {formatAgo(t.snapshot.publishedAt, app.now)} · sqb {t.snapshot.sqbVersion}
											</div>
										{:else}
											<span class="muted">No snapshot published</span>
										{/if}
									</td>
									<td>{#if t.imageId}<code title={t.imageId}>{shortImage(t.imageId)}</code>{:else}<span class="muted" title="Runs start as local subprocesses">local</span>{/if}</td>
									<td class="test-cell">
										<ConnectionTest scope={{ locationId: detail.id, target: t.name }} connection={t.warehouseConnection} last={t.connectionTest} />
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</Panel>

				<Panel title="Warehouse sync" note="SQLBuild state tables synced from the warehouse by the location">
					{#snippet actions()}
						{#if detail.targets.length > 1}
							<SegmentedFilter bind:value={() => syncTargetName, (v) => (syncTarget = v)} options={detail.targets.map((t) => ({ value: t.name, label: t.name }))} />
						{/if}
					{/snippet}
					<table class="sb-list static">
						<thead>
							<tr>
								<th>State table</th>
								<th class="num">Schemas</th>
								<th>Last synced</th>
								<th class="num">Rows last pass</th>
								<th class="num">Cost · 24h</th>
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
											<StatusLabel tone="var(--sb-error)" label="Failing since {formatAgo(row.lastSyncedAt, app.now)}" />
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

				<Panel title="Instances" note="Location processes registered with the server">
					<table class="sb-list static">
						<thead>
							<tr>
								<th>Instance</th>
								<th>Image</th>
								<th>Revision</th>
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
						{ label: 'Broken deploys', value: detail.brokenDeployPolicy === 'fallback' ? 'Fall back to last good image' : 'Queue runs and alert' },
						{ label: 'Targets', value: detail.targets.map((t) => t.name).join(', ') }
					]}
				/>
				<div class="rail-title mt-6">Location tokens</div>
				<p class="rail-note">Allow only registering this location, publishing its snapshots and reporting health.</p>
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
