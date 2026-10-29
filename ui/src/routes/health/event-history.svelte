<script lang="ts">
	import LoadRow from '$lib/components/list/load-row.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import type { PlatformEventLink, PlatformEventReaction } from '$lib/api';
	import { formatAgo, formatDuration, formatStamp } from '$lib/format/time';
	import {
		eventKindLabel,
		eventLinkHref,
		eventLinkLabel,
		locationName,
		reactionHref,
		reactionLabel,
		reactionTone,
		severityTone
	} from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import type { HealthState } from './state.svelte';
	import { EVENT_KINDS, payloadSummary } from './utils';

	let { health }: { health: HealthState } = $props();

	/** Scoped links switch the selected location and target before navigating. */
	function follow(scope: { locationId: string; target: string }) {
		if (app.locationId !== scope.locationId) app.selectLocation(scope.locationId);
		if (app.targetName !== scope.target) app.selectTarget(scope.target);
	}

	function followLink(link: PlatformEventLink) {
		if (link.kind !== 'location') follow(link);
	}

	function reactionTitle(r: PlatformEventReaction): string {
		const attempts = r.attempts > 1 ? ` after ${r.attempts} evaluations` : '';
		const at = r.at ? ` · ${formatStamp(r.at)}` : '';
		const evaluation = r.evaluationId ? `\n${r.evaluationId}` : '';
		return `${reactionLabel[r.outcome]}${attempts}${at}${evaluation}`;
	}
</script>

<div class="toolbar">
	<SegmentedFilter
		bind:value={health.view}
		options={[
			{ value: 'active', label: 'Active', count: health.activeCount },
			{ value: 'all', label: 'History', count: health.historyCount }
		]}
	/>
	<SegmentedFilter
		bind:value={health.kind}
		options={[{ value: 'any', label: 'All but heartbeats' }, ...EVENT_KINDS.map((k) => ({ value: k, label: eventKindLabel[k] }))]}
	/>
</div>

<table class="sb-list events">
	<thead>
		<tr>
			<th>Platform event</th>
			<th>Location</th>
			<th>Affects</th>
			<th>Sensors</th>
			<th>Occurred</th>
			<th>Resolved</th>
		</tr>
	</thead>
	<tbody>
		{#each health.shown as e (e.id)}
			<tr>
				<td>
					<div class="cell-name">
						<span class="dot" style:background={severityTone[e.severity]} title={e.severity}></span>
						<div class="min-w-0">
							<strong>{eventKindLabel[e.kind]}</strong>{#if e.subject}<code class="subject">{e.subject}</code>{/if}
							<div class="cell-desc" title={payloadSummary(e.payload)}>{e.message}</div>
						</div>
					</div>
				</td>
				<td class="muted">
					{e.locationId ? locationName(app.bootstrap?.locations, e.locationId) : 'Server'}{#if e.target}&nbsp;/ {e.target}{/if}
				</td>
				<td>
					{#each e.links as link (eventLinkHref(link))}
						<a class="link stacked" href={eventLinkHref(link)} onclick={() => followLink(link)}>{eventLinkLabel(link, app.bootstrap?.locations)}</a>
					{:else}
						<span class="muted">—</span>
					{/each}
				</td>
				<td>
					{#each e.reactions as r (r.triggerId)}
						<a class="link stacked reaction" href={reactionHref(r)} onclick={() => follow(r)} title={reactionTitle(r)}>
							<span class="dot" style:background={reactionTone[r.outcome]}></span>{r.triggerName}
							<span class="faint">{reactionLabel[r.outcome]}</span>
						</a>
					{:else}
						<span class="muted" title="No sensor's platform_event condition matches this kind">—</span>
					{/each}
				</td>
				<td><RelativeTime value={formatAgo(e.occurredAt, app.now)} exact={formatStamp(e.occurredAt)} /></td>
				<td>
					{#if e.active}
						<StatusLabel tone={severityTone[e.severity]} label="Ongoing" />
					{:else}
						<RelativeTime value={e.resolvedAt ? `after ${formatDuration(e.occurredAt, e.resolvedAt, app.now)}` : 'Resolved'} exact={formatStamp(e.resolvedAt)} />
					{/if}
				</td>
			</tr>
		{:else}
			<LoadRow
				colspan={6}
				resource={health.events}
				empty={health.view === 'active' ? 'No active platform events. Everything is running normally.' : 'No platform events recorded in the retention window.'}
			/>
		{/each}
	</tbody>
</table>

<style>
	.toolbar {
		display: flex;
		height: 50px;
		align-items: center;
		gap: 10px;
		padding: 0 20px;
		border-bottom: 1px solid var(--border);
	}
	:global(.sb-list.events tbody tr) {
		cursor: default;
	}
	.muted {
		color: var(--muted-foreground);
	}
	.faint {
		color: var(--sb-text-faint);
	}
	code {
		font-family: var(--font-mono);
		font-size: 12px;
	}
	.subject {
		margin-left: 8px;
		color: var(--muted-foreground);
	}
	.stacked {
		display: block;
		white-space: nowrap;
	}
	.reaction {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.dot {
		width: 8px;
		height: 8px;
		flex: 0 0 8px;
		border-radius: 50%;
	}
</style>
