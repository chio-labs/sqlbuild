import { createResource } from '$lib/state/resource.svelte';
import type { HistoryView, KindFilter } from './types';
import { filterEvents, matchesKind } from './utils';

/** Health page state. Must be created during component initialisation. */
export function createHealthState() {
	const health = createResource((client) => client.platformHealth(), ['platform_events']);
	const events = createResource((client) => client.listPlatformEventHistory(), ['platform_events']);

	let view = $state<HistoryView>('active');
	let kind = $state<KindFilter>('any');

	const all = $derived(events.data ?? []);
	const shown = $derived(filterEvents(all, view, kind));
	const activeCount = $derived(all.filter((e) => e.active && matchesKind(e, kind)).length);
	const historyCount = $derived(all.filter((e) => matchesKind(e, kind)).length);

	// Lease, replicas, heartbeat and sink are liveness signals; poll them while the page is open.
	$effect(() => {
		const timer = setInterval(() => health.refresh(), 15_000);
		return () => clearInterval(timer);
	});

	function refresh() {
		health.refresh();
		events.refresh();
	}

	return {
		health,
		events,
		get view() {
			return view;
		},
		set view(value: HistoryView) {
			view = value;
		},
		get kind() {
			return kind;
		},
		set kind(value: KindFilter) {
			kind = value;
		},
		get shown() {
			return shown;
		},
		get activeCount() {
			return activeCount;
		},
		get historyCount() {
			return historyCount;
		},
		refresh
	};
}

export type HealthState = ReturnType<typeof createHealthState>;
