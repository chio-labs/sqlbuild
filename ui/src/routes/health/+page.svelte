<script lang="ts">
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import EventHistory from './event-history.svelte';
	import { createHealthState } from './state.svelte';
	import SystemStatus from './system-status.svelte';

	const health = createHealthState();
</script>

<AppTopbar title="Health">
	<Button variant="outline" size="sm" onclick={() => health.refresh()}>↻ Refresh</Button>
</AppTopbar>

<div class="min-h-0 flex-1 overflow-auto">
	<SystemStatus health={health.health} />
	<EventHistory {health} />
</div>
