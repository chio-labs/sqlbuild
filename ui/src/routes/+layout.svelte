<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import AppSidebar from '$lib/components/app-sidebar.svelte';
	import { app } from '$lib/state/app.svelte';

	let { children } = $props();

	onMount(() => {
		void app.start();
	});
</script>

<svelte:head>
	<link rel="icon" href="/favicon.png" />
</svelte:head>

{#if app.bootError}
	<div class="grid h-screen place-items-center p-8">
		<div class="max-w-md text-center">
			<h1 class="text-[15px] font-semibold">Can't reach the SQLBuild server</h1>
			<p class="text-muted-foreground mt-2 text-[13px]">{app.bootError}</p>
			<button class="mt-4 rounded-md border border-border px-3 py-1.5 text-[13px]" onclick={() => location.reload()}>Retry</button>
		</div>
	</div>
{:else if app.bootstrap && app.bootstrap.locations.length === 0}
	<div class="grid h-screen place-items-center p-8">
		<div class="max-w-md text-center">
			<h1 class="text-[15px] font-semibold">No code locations yet</h1>
			<p class="text-muted-foreground mt-2 text-[13px]">Register a code location with the server, then reload this page.</p>
		</div>
	</div>
{:else if !app.scope}
	<div class="text-muted-foreground grid h-screen place-items-center text-[13px]">Loading…</div>
{:else}
	<div class="flex h-screen overflow-hidden">
		<AppSidebar />
		<div class="flex min-w-0 flex-1 flex-col">
			{@render children()}
		</div>
	</div>
{/if}
