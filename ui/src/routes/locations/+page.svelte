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
	import { healthTone, healthWords, testTone } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';
	import ServerStatus from './server-status.svelte';

	const locations = createResource((client) => client.listLocations(), ['snapshot', 'platform_events']);
	let status = $state<ServerStatus>();

	let query = $state('');
	const all = $derived(locations.data ?? []);
	const filtered = $derived(all.filter((l) => !query.trim() || l.name.toLowerCase().includes(query.trim().toLowerCase())));
	const unhealthy = $derived(all.filter((l) => l.health !== 'healthy' || l.activeProblems > 0).length);
</script>

<AppTopbar title="Locations">
	<Button variant="outline" size="sm" onclick={() => (locations.refresh(), status?.refresh())}>↻ Refresh</Button>
</AppTopbar>

<ServerStatus bind:this={status} />

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
				<th>Deployed versions</th>
				<th>Location processes</th>
				<th title="What happens when a deploy fails to load">If a deploy fails</th>
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
								<div class="cell-desc" title="Location ID">{l.targets.length} target{l.targets.length === 1 ? '' : 's'}</div>
							</div>
						</div>
					</td>
					<td>
						<StatusLabel tone={l.failedDeploy || l.activeProblems ? healthTone[l.health === 'healthy' ? 'degraded' : l.health] : healthTone[l.health]} label={healthWords(l)} />
						{#if l.activeProblems}
							<div class="cell-desc"><a class="link" href="/locations/{l.id}#problems" onclick={(e) => e.stopPropagation()}>{l.activeProblems} open problem{l.activeProblems === 1 ? '' : 's'}</a></div>
						{/if}
					</td>
					<td>
						<div class="targets">
							{#each l.targets as t (t.name)}
								<span class="target" title={t.snapshot ? `Commit ${t.snapshot.gitRevision} by ${t.snapshot.gitAuthor}, deployed ${formatStamp(t.snapshot.publishedAt)} (snapshot generation ${t.snapshot.generation})` : undefined}>
									<i style:background={t.connectionTest ? testTone[t.connectionTest.outcome] : 'var(--sb-text-faint)'} title={t.connectionTest ? `Warehouse connection test ${t.connectionTest.outcome === 'ok' ? 'passed' : 'failed'} ${formatAgo(t.connectionTest.at, app.now)}` : 'Connection not tested yet'}></i>
									<b>{t.name}</b>
									{#if t.snapshot}
										<span class="muted">Version {t.snapshot.generation}, deployed {formatAgo(t.snapshot.publishedAt, app.now)}</span>
									{:else}
										<span class="muted">nothing deployed yet</span>
									{/if}
								</span>
							{/each}
						</div>
					</td>
					<td>
						<div>{l.liveInstances} running</div>
						<RelativeTime value="last seen {formatAgo(l.lastSeenAt, app.now)}" exact={formatStamp(l.lastSeenAt)} />
					</td>
					<td class="muted">{l.brokenDeployPolicy === 'fallback' ? 'Keep running the previous version' : 'Hold scheduled runs until a deploy works'}</td>
				</tr>
			{:else}
				<LoadRow colspan={5} resource={locations} empty={all.length ? 'No locations match the search.' : 'No code locations yet. Register one with the server using a location token.'} />
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
</style>
