<script lang="ts">
	import RefreshCwIcon from '@lucide/svelte/icons/refresh-cw';
	import { formatAgo, secondsSince } from '$lib/format/time';
	import { app } from '$lib/state/app.svelte';

	let requesting = $state(false);

	const sync = $derived(app.warehouseSync);
	const running = $derived(sync?.state === 'running');
	const canSync = $derived(app.can('warehouse.sync'));

	const text = $derived.by(() => {
		if (!sync) return 'Warehouse sync —';
		if (running) return `Syncing… started ${secondsSince(sync.runningSince, app.now)}s ago`;
		if (sync.state === 'failed') return `Warehouse sync failed ${formatAgo(sync.lastSyncedAt, app.now)}`;
		return sync.lastSyncedAt ? `Warehouse synced ${formatAgo(sync.lastSyncedAt, app.now)}` : 'Warehouse not synced yet';
	});

	const title = $derived.by(() => {
		if (!sync) return '';
		if (!canSync) return "Reads what's in the warehouse (what was built, checks, freshness). You don't have permission to refresh it (warehouse.sync).";
		if (running && sync.followUpQueued) return 'Another sync is already lined up after this one; more clicks join it.';
		if (running) return 'Click to sync again as soon as this one finishes.';
		return sync.lastError ?? "Reads what's in the warehouse (what was built, checks, freshness). Click to sync now.";
	});

	async function refresh() {
		if (requesting || !canSync) return;
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
	{#if running && sync?.followUpQueued}<span class="queued" title="Another sync runs right after this one">+1 next</span>{/if}
	<button
		class="refresh"
		aria-label={running ? 'Sync again after this one' : 'Sync with the warehouse now'}
		onclick={refresh}
		disabled={!sync || requesting || !canSync}
		title={canSync ? undefined : "You don't have permission to refresh (warehouse.sync)"}
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
