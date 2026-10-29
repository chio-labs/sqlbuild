import type { PlatformEventKind } from '$lib/api';

/** `active` shows ongoing events only; `all` is the retained history. */
export type HistoryView = 'active' | 'all';

/** `any` covers every kind except heartbeats, which are selectable on their own. */
export type KindFilter = PlatformEventKind | 'any';
