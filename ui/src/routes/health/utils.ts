import type { HeartbeatStatus, PlatformEventKind, PlatformEventRecord } from '$lib/api';
import type { HistoryView, KindFilter } from './types';

export const EVENT_KINDS: readonly PlatformEventKind[] = ['tick_overdue', 'scheduler_no_leader', 'location_broken', 'launch_failed', 'heartbeat'];

export function matchesKind(event: PlatformEventRecord, kind: KindFilter): boolean {
	return kind === 'any' ? event.kind !== 'heartbeat' : event.kind === kind;
}

export function filterEvents(events: readonly PlatformEventRecord[], view: HistoryView, kind: KindFilter): PlatformEventRecord[] {
	return events.filter((e) => (view === 'all' || e.active) && matchesKind(e, kind));
}

/** Late once two intervals pass without a heartbeat. */
export function heartbeatLate(heartbeat: HeartbeatStatus, now: number): boolean {
	if (!heartbeat.lastEmittedAt) return true;
	return now - Date.parse(heartbeat.lastEmittedAt) > 2 * heartbeat.intervalSeconds * 1000;
}

/** A replica is live while it was seen within the last minute. */
export function replicaLive(lastSeenAt: string, now: number): boolean {
	return now - Date.parse(lastSeenAt) < 60_000;
}

export function payloadSummary(payload: Record<string, string>): string {
	return Object.entries(payload)
		.map(([key, value]) => `${key}: ${value}`)
		.join('\n');
}
