<script lang="ts">
	import { goto } from '$app/navigation';
	import MapPinIcon from '@lucide/svelte/icons/map-pin';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { healthLabel, healthTone, testTone } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	const locations = createResource((client) => client.listLocations(), ['snapshot']);

	let query = $state('');
	const all = $derived(locations.data ?? []);
	const filtered = $derived(all.filter((l) => !query.trim() || l.name.toLowerCase().includes(query.trim().toLowerCase())));
	const unhealthy = $derived(all.filter((l) => l.health !== 'healthy').length);
</script>

<AppTopbar title="Locations">
	<Button variant="outline" size="sm" onclick={() => locations.refresh()}>↻ Refresh</Button>
</AppTopbar>

<ListToolbar
	bind:query
	placeholder="Search locations"
	total="{filtered.length} of {all.length} locations"
	counts={[{ tone: 'var(--sb-warning)', count: unhealthy, label: 'need attention' }]}
/>

<div class="sb-list-wrap">
	<table class="sb-list">
		<thead>
			<tr>
				<th>Location</th>
				<th>Health</th>
				<th>Current snapshots</th>
				<th>Instances</th>
				<th>Broken deploys</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as l (l.id)}
				<tr onclick={() => goto(`/locations/${l.id}`)}>
					<td>
						<div class="cell-name">
							<MapPinIcon size={15} strokeWidth={1.75} />
							<div class="min-w-0">
								<a href="/locations/{l.id}" onclick={(e) => e.stopPropagation()}>{l.name}</a>
								<div class="cell-desc"><code>{l.id}</code></div>
							</div>
						</div>
					</td>
					<td>
						<StatusLabel tone={healthTone[l.health]} label={healthLabel[l.health]} />
						{#if l.failedDeploy}
							<div class="cell-desc warn">Deploy {l.failedDeploy.gitRevision} failed</div>
						{/if}
					</td>
					<td>
						<div class="targets">
							{#each l.targets as t (t.name)}
								<span class="target" title={t.snapshot ? `Published ${formatStamp(t.snapshot.publishedAt)} by ${t.snapshot.gitAuthor}` : undefined}>
									<i style:background={t.connectionTest ? testTone[t.connectionTest.outcome] : 'var(--sb-text-faint)'} title="Connection test"></i>
									<b>{t.name}</b>
									{#if t.snapshot}
										<span class="muted">gen {t.snapshot.generation} · <code>{t.snapshot.gitRevision}</code> · {formatAgo(t.snapshot.publishedAt, app.now)}</span>
									{:else}
										<span class="muted">no snapshot</span>
									{/if}
								</span>
							{/each}
						</div>
					</td>
					<td>
						<div>{l.liveInstances} live</div>
						<RelativeTime value="seen {formatAgo(l.lastSeenAt, app.now)}" exact={formatStamp(l.lastSeenAt)} />
					</td>
					<td class="muted">{l.brokenDeployPolicy === 'fallback' ? 'Fall back to last good image' : 'Queue runs until a deploy publishes'}</td>
				</tr>
			{:else}
				<LoadRow colspan={5} resource={locations} empty={all.length ? 'No locations match the filter.' : 'No code locations are registered.'} />
			{/each}
		</tbody>
	</table>
</div>

<style>
	.targets {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.target {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		white-space: nowrap;
	}
	.target i {
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}
	.target b {
		font-weight: 500;
	}
	.warn {
		color: var(--sb-warning) !important;
	}
</style>
