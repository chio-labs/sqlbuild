<script lang="ts">
	import SunIcon from '@lucide/svelte/icons/sun';
	import MoonIcon from '@lucide/svelte/icons/moon';
	import type { Snippet } from 'svelte';
	import type { ConnectionState } from '$lib/api';
	import { theme, toggleTheme } from '$lib/theme.svelte';
	import { formatAgo } from '$lib/format/time';
	import { app } from '$lib/state/app.svelte';
	import PlatformAlertBanner from './shell/platform-alert-banner.svelte';
	import WarehouseSyncStatus from './shell/warehouse-sync-status.svelte';

	type Props = { title: string; children?: Snippet };
	let { title, children }: Props = $props();

	const connectionTone: Record<ConnectionState, string> = {
		live: 'var(--sb-success)',
		connecting: 'var(--sb-text-faint)',
		reconnecting: 'var(--sb-warning)',
		offline: 'var(--sb-error)'
	};
	const connectionLabel: Record<ConnectionState, string> = {
		live: 'Live',
		connecting: 'Connecting',
		reconnecting: 'Reconnecting',
		offline: 'Offline'
	};

	const snapshot = $derived(app.target?.snapshot ?? null);
</script>

<div class="app-topbar flex h-[52px] shrink-0 items-center gap-3 border-b border-border px-5">
	<h1 class="text-[15px] font-semibold">{title}</h1>
	<span class="text-muted-foreground text-[12.5px]">{app.location?.name ?? '—'} / {app.targetName || '—'}</span>
	<div class="ml-auto flex items-center gap-2.5">
		<span
			class="text-muted-foreground flex items-center gap-[7px] text-[12px]"
			title={snapshot
				? `Snapshot generation ${snapshot.generation} · ${snapshot.gitRevision}${snapshot.gitDirty ? ' (uncommitted changes)' : ''} · ${snapshot.gitAuthor}`
				: 'No snapshot published for this target'}
		>
			<span class="h-[7px] w-[7px] rounded-full" style:background={connectionTone[app.connection]}></span>
			{connectionLabel[app.connection]}
			<span class="text-[var(--sb-text-faint)]">·</span>
			{snapshot ? `snapshot ${formatAgo(snapshot.publishedAt, app.now)}` : 'no snapshot'}
		</span>
		<span class="text-[var(--sb-text-faint)]">·</span>
		<WarehouseSyncStatus />
		{#if children}<span class="ml-1 flex items-center gap-2.5">{@render children()}</span>{/if}
		<button
			class="bg-card text-muted-foreground hover:text-foreground hover:bg-[var(--sb-hover)] grid h-8 w-8 place-items-center rounded-md border border-border"
			aria-label="Toggle theme"
			onclick={toggleTheme}
		>
			{#if theme.value === 'dark'}
				<SunIcon size={14} />
			{:else}
				<MoonIcon size={14} />
			{/if}
		</button>
	</div>
</div>
<PlatformAlertBanner />

<style>
	.app-topbar {
		background: color-mix(in srgb, var(--background) 94%, transparent);
		backdrop-filter: blur(12px);
	}
</style>
