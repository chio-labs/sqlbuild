<script lang="ts">
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw';
	import { formatAgo, secondsSince } from '$lib/format/time';
	import { app } from '$lib/state/app.svelte';

	let requesting = $state(false);

	const sync = $derived(app.warehouseSync);
	const running = $derived(sync?.state === 'running');

	const text = $derived.by(() => {
		if (!sync) return 'Warehouse sync —';
		if (running) return `Syncing… started ${secondsSince(sync.runningSince, app.now)}s ago`;
		if (sync.state === 'failed') return `Warehouse sync failed ${formatAgo(sync.lastSyncedAt, app.now)}`;
		return sync.lastSyncedAt ? `Warehouse synced ${formatAgo(sync.lastSyncedAt, app.now)}` : 'Warehouse not synced yet';
	});

	const title = $derived.by(() => {
		if (!sync) return '';
		if (running && sync.followUpQueued) return 'A follow-up sync is queued; further refreshes merge into it.';
		if (running) return 'Refresh queues one follow-up sync after this one.';
		return sync.lastError ?? 'Sync warehouse metadata now';
	});

	async function refresh() {
		if (requesting) return;
		requesting = true;
		try {
			await app.requestWarehouseSync();
		} finally {
			requesting = false;
		}
	}
</script>

<span class="sync" class:failed={sync?.state === 'failed'} {title}>
	<span>{text}</span>
	{#if running && sync?.followUpQueued}<span class="queued">+1 queued</span>{/if}
	<button
		class="refresh"
		aria-label={running ? 'Queue a follow-up warehouse sync' : 'Sync warehouse now'}
		onclick={refresh}
		disabled={!sync || requesting}
	>
		<RefreshCwIcon size={12} class={running ? 'animate-spin' : ''} />
	</button>
</span>

<style>
	.sync {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		color: var(--muted-foreground);
		font-size: 12px;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.sync.failed {
		color: var(--sb-error);
	}
	.queued {
		padding: 0 5px;
		border-radius: 2px;
		background: color-mix(in srgb, var(--sb-running) 14%, transparent);
		color: var(--sb-running);
		font-size: 11px;
	}
	.refresh {
		display: grid;
		width: 22px;
		height: 22px;
		place-items: center;
		border: 1px solid var(--border);
		border-radius: 4px;
	}
	.refresh:hover:not(:disabled) {
		background: var(--sb-hover);
		color: var(--foreground);
	}
	.refresh:disabled {
		opacity: 0.5;
	}
</style>
