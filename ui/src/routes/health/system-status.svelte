<script lang="ts">
	import LockIcon from '@lucide/svelte/icons/lock';
	import type { PlatformHealth } from '$lib/api';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import { formatAgo, formatDuration, formatIn, formatStamp } from '$lib/format/time';
	import type { Resource } from '$lib/state/resource.svelte';
	import { app } from '$lib/state/app.svelte';
	import { heartbeatLate, replicaLive } from './utils';

	let { health }: { health: Resource<PlatformHealth> } = $props();

	const scheduler = $derived(health.data?.scheduler ?? null);
	const heartbeat = $derived(health.data?.heartbeat ?? null);
	const sink = $derived(health.data?.sink ?? null);
	const late = $derived(!!heartbeat && heartbeatLate(heartbeat, app.now));
	const placeholder = $derived(health.error ? '—' : 'Loading…');
</script>

<div class="status">
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
	</div>

	<div class="card">
		<div class="card-title">Server replicas</div>
		{#if scheduler}
			<ul class="replicas">
				{#each scheduler.instances as i (i.instanceId)}
					<li>
						<span class="dot" style:background={replicaLive(i.lastSeenAt, app.now) ? 'var(--sb-success)' : 'var(--sb-error)'}></span>
						<code>{i.instanceId}</code>
						<span class="muted">{i.schedulerEnabled ? (scheduler.lease?.holder === i.instanceId ? 'leader' : 'standby') : '--no-scheduler'}</span>
						<span class="faint" title={formatStamp(i.lastSeenAt)}>seen {formatAgo(i.lastSeenAt, app.now)}</span>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="muted">{placeholder}</p>
		{/if}
	</div>

	<div class="card">
		<div class="card-title">Heartbeat</div>
		{#if heartbeat}
			<StatusLabel
				tone={late ? 'var(--sb-error)' : 'var(--sb-success)'}
				label={heartbeat.lastEmittedAt ? `Last emitted ${formatAgo(heartbeat.lastEmittedAt, app.now)}` : 'Never emitted'}
			/>
			<p class="muted">
				A <code>heartbeat</code> platform event every {heartbeat.intervalSeconds}s. Watch for it downstream: when it stops arriving, the server is down.
			</p>
		{:else}
			<p class="muted">{placeholder}</p>
		{/if}
	</div>

	<div class="card">
		<div class="card-title">
			Platform-event sink
			<span class="locked" title="Configured in the server config; read-only here"><LockIcon size={11} /> server config</span>
		</div>
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
			<p class="muted">Sensors still receive platform events through their cursors. A server-side sink pushes them without user code.</p>
		{:else}
			<p class="muted">{placeholder}</p>
		{/if}
	</div>
</div>

<style>
	.status {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
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
		display: flex;
		align-items: center;
		gap: 8px;
		color: var(--muted-foreground);
		font-size: 12px;
		font-weight: 500;
	}
	.locked {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		margin-left: auto;
		color: var(--sb-text-faint);
		font-size: 11px;
		font-weight: 400;
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
	.replicas {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.replicas li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.replicas li .faint {
		margin-left: auto;
	}
	.dot {
		width: 8px;
		height: 8px;
		flex: 0 0 8px;
		border-radius: 50%;
	}
</style>
