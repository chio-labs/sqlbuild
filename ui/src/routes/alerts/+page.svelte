<script lang="ts">
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import SegmentedFilter from '$lib/components/list/segmented-filter.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import ChannelList from '$lib/components/platform/channel-list.svelte';
	import Panel from '$lib/components/platform/panel.svelte';
	import type { PlatformEventKind, PlatformEventLink } from '$lib/api';
	import { formatAgo, formatDuration, formatIn, formatStamp } from '$lib/format/time';
	import { eventKindLabel, eventLinkHref, eventLinkLabel, locationName, severityTone } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	const health = createResource((client) => client.platformHealth(), ['platform_events']);
	const events = createResource((client) => client.listPlatformEventHistory(), ['platform_events']);
	const connections = createResource((client, scope) => client.connections(scope));

	// Lease, heartbeat and sink are liveness signals; poll them while the page is open.
	$effect(() => {
		const timer = setInterval(() => health.refresh(), 15_000);
		return () => clearInterval(timer);
	});

	type Show = 'active' | 'all';
	let show = $state<Show>('active');
	let kind = $state<PlatformEventKind | 'any'>('any');

	const all = $derived((events.data ?? []).filter((e) => e.kind !== 'heartbeat'));
	const filtered = $derived(all.filter((e) => (show === 'all' || e.active) && (kind === 'any' || e.kind === kind)));
	const activeCount = $derived(all.filter((e) => e.active).length);

	const kinds: PlatformEventKind[] = ['tick_overdue', 'scheduler_no_leader', 'location_broken', 'launch_failed'];

	const scheduler = $derived(health.data?.scheduler ?? null);
	const heartbeat = $derived(health.data?.heartbeat ?? null);
	const sink = $derived(health.data?.sink ?? null);
	const heartbeatLate = $derived(
		!!heartbeat?.lastEmittedAt && app.now - Date.parse(heartbeat.lastEmittedAt) > 2 * heartbeat.intervalSeconds * 1000
	);
	const channels = $derived(connections.data?.channels ?? []);

	/** Scoped links switch the selected location and target before navigating. */
	function follow(link: PlatformEventLink) {
		if (link.kind === 'location') return;
		if (app.locationId !== link.locationId) app.selectLocation(link.locationId);
		if (app.targetName !== link.target) app.selectTarget(link.target);
	}
</script>

<AppTopbar title="Alerts">
	<Button
		variant="outline"
		size="sm"
		onclick={() => {
			health.refresh();
			events.refresh();
		}}>↻ Refresh</Button
	>
</AppTopbar>

<div class="min-h-0 flex-1 overflow-auto">
	<div class="health">
		<div class="card">
			<div class="card-title">Scheduler</div>
			{#if health.error}
				<p class="err">Couldn't load: {health.error}</p>
			{:else if !scheduler}
				<p class="muted">Loading…</p>
			{:else if scheduler.lease}
				<StatusLabel tone="var(--sb-success)" label="Leader: {scheduler.lease.holder}" />
				<p class="muted">
					Lease renewed {formatAgo(scheduler.lease.renewedAt, app.now)}, expires {formatIn(scheduler.lease.expiresAt, app.now)} · held for {formatDuration(scheduler.lease.acquiredAt, null, app.now)}
				</p>
			{:else}
				<StatusLabel tone="var(--sb-error)" label="No leader" />
				<p class="muted">No replica holds the scheduler lease; ticks aren't being evaluated.</p>
			{/if}
			{#if scheduler}
				<ul class="instances">
					{#each scheduler.instances as i (i.instanceId)}
						<li>
							<span class="dot" style:background={app.now - Date.parse(i.lastSeenAt) < 60_000 ? 'var(--sb-success)' : 'var(--sb-error)'}></span>
							<code>{i.instanceId}</code>
							<span class="muted">{i.schedulerEnabled ? (scheduler.lease?.holder === i.instanceId ? 'leader' : 'standby') : '--no-scheduler'}</span>
							<span class="faint" title={formatStamp(i.lastSeenAt)}>seen {formatAgo(i.lastSeenAt, app.now)}</span>
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		<div class="card">
			<div class="card-title">Heartbeat</div>
			{#if heartbeat}
				<StatusLabel
					tone={heartbeatLate || !heartbeat.lastEmittedAt ? 'var(--sb-error)' : 'var(--sb-success)'}
					label={heartbeat.lastEmittedAt ? `Last emitted ${formatAgo(heartbeat.lastEmittedAt, app.now)}` : 'Never emitted'}
				/>
				<p class="muted">
					A heartbeat event every {heartbeat.intervalSeconds}s is the dead-man's switch: alert downstream when it stops arriving.
				</p>
			{:else}
				<p class="muted">{health.error ? '—' : 'Loading…'}</p>
			{/if}
		</div>

		<div class="card">
			<div class="card-title">Event sink</div>
			{#if sink}
				<StatusLabel
					tone={sink.lastError ? 'var(--sb-error)' : 'var(--sb-success)'}
					label={sink.lastError ? `Failing (${sink.consecutiveFailures} attempts)` : `Delivered ${formatAgo(sink.lastDeliveredAt, app.now)}`}
				/>
				<p class="muted">
					{sink.kind} · <code>{sink.destinationSource}</code> · {sink.eventKinds.length ? sink.eventKinds.join(', ') : 'all event kinds'}
				</p>
				{#if sink.lastError}<p class="err">{sink.lastError}</p>{/if}
				<p class="faint">
					{sink.pendingEvents} pending · last attempt {formatAgo(sink.lastAttemptAt, app.now)}{#if sink.lastError}
						· last delivered {formatAgo(sink.lastDeliveredAt, app.now)}{/if}
				</p>
			{:else if health.data}
				<StatusLabel tone="var(--sb-text-faint)" label="Not configured" muted />
				<p class="muted">Sensors still receive platform events from their cursors. Configure a server-side sink to push them without user code.</p>
			{:else}
				<p class="muted">{health.error ? '—' : 'Loading…'}</p>
			{/if}
		</div>
	</div>

	<div class="toolbar">
		<SegmentedFilter
			bind:value={show}
			options={[
				{ value: 'active', label: 'Active', count: activeCount },
				{ value: 'all', label: 'History', count: all.length }
			]}
		/>
		<SegmentedFilter
			bind:value={kind}
			options={[{ value: 'any', label: 'All kinds' }, ...kinds.map((k) => ({ value: k, label: eventKindLabel[k] }))]}
		/>
	</div>

	<table class="sb-list events">
		<thead>
			<tr>
				<th>Event</th>
				<th>Location</th>
				<th>Affects</th>
				<th>Occurred</th>
				<th>Resolved</th>
			</tr>
		</thead>
		<tbody>
			{#each filtered as e (e.id)}
				<tr>
					<td>
						<div class="cell-name">
							<span class="dot" style:background={severityTone[e.severity]} title={e.severity}></span>
							<div class="min-w-0">
								<strong>{eventKindLabel[e.kind]}</strong>{#if e.subject}<code class="subject">{e.subject}</code>{/if}
								<div class="cell-desc" title={Object.entries(e.payload).map(([k, v]) => `${k}: ${v}`).join('\n')}>{e.message}</div>
							</div>
						</div>
					</td>
					<td class="muted">
						{e.locationId ? locationName(app.bootstrap?.locations, e.locationId) : 'Server'}{#if e.target}&nbsp;/ {e.target}{/if}
					</td>
					<td>
						{#each e.links as link (eventLinkHref(link))}
							<a class="link affected" href={eventLinkHref(link)} onclick={() => follow(link)}>{eventLinkLabel(link, app.bootstrap?.locations)}</a>
						{:else}
							<span class="muted">—</span>
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
					colspan={5}
					resource={events}
					empty={show === 'active' ? 'No active platform events. Everything is running normally.' : 'No platform events recorded in the retention window.'}
				/>
			{/each}
		</tbody>
	</table>

	<div class="channels">
		<Panel title="Channels" note="Optional; defined in code, configured in Connections">
			{#if connections.error}
				<p class="err">Couldn't load channels: {connections.error}</p>
			{:else if channels.length}
				<ChannelList {channels} ontested={() => connections.refresh()} />
			{:else if connections.data}
				<p class="muted">No channels are defined for this location. Sensors can send alerts from code instead.</p>
			{/if}
		</Panel>
	</div>
</div>

<style>
	.health {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 12px;
		padding: 16px 20px;
		border-bottom: 1px solid var(--border);
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
		padding: 12px 14px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--card);
		font-size: 12.5px;
	}
	.card-title {
		color: var(--muted-foreground);
		font-size: 12px;
		font-weight: 500;
	}
	.muted {
		color: var(--muted-foreground);
	}
	.faint {
		color: var(--sb-text-faint);
	}
	.err {
		color: var(--sb-error);
	}
	code {
		font-family: var(--font-mono);
		font-size: 12px;
	}
	.instances {
		display: flex;
		flex-direction: column;
		gap: 3px;
		margin-top: 4px;
	}
	.instances li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.instances li .faint {
		margin-left: auto;
	}
	.dot {
		width: 8px;
		height: 8px;
		flex: 0 0 8px;
		border-radius: 50%;
	}
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
	.subject {
		margin-left: 8px;
		color: var(--muted-foreground);
	}
	.affected {
		display: block;
		white-space: nowrap;
	}
	.channels {
		padding: 24px 20px 0;
	}
</style>
