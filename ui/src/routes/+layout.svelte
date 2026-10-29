<script lang="ts">
	import './layout.css';
	import AppSidebar from '$lib/components/app-sidebar.svelte';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href="/favicon.png" />
</svelte:head>

<div class="flex h-screen overflow-hidden">
	<AppSidebar />
	<div class="flex min-w-0 flex-1 flex-col">
		{@render children()}
	</div>
</div>
