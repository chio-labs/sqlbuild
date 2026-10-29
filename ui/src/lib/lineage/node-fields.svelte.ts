// Node field preferences for the lineage graph ("Node fields" control).
// Global (applies to all nodes). Persisted to localStorage so a user's
// choice of what to show on nodes survives reloads.

export type NodeFieldKey =
	| 'kind'
	| 'status'
	| 'checks'
	| 'freshness'
	| 'description'
	| 'owner'
	| 'tags'
	| 'columns';

export type NodeField = { key: NodeFieldKey; label: string };

export const NODE_FIELDS: NodeField[] = [
	{ key: 'kind', label: 'Kind' },
	{ key: 'status', label: 'Status' },
	{ key: 'checks', label: 'Checks' },
	{ key: 'freshness', label: 'Freshness' },
	{ key: 'description', label: 'Description' },
	{ key: 'owner', label: 'Owner' },
	{ key: 'tags', label: 'Tags' },
	{ key: 'columns', label: 'Column count' }
];

const DEFAULTS: Record<NodeFieldKey, boolean> = {
	kind: true,
	status: true,
	checks: true,
	freshness: false,
	description: false,
	owner: false,
	tags: false,
	columns: false
};

const STORAGE_KEY = 'sqlbuild.lineage.nodeFields';

function load(): Record<NodeFieldKey, boolean> {
	if (typeof localStorage === 'undefined') return { ...DEFAULTS };
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return { ...DEFAULTS };
		return { ...DEFAULTS, ...JSON.parse(raw) };
	} catch {
		return { ...DEFAULTS };
	}
}

class NodeFieldsState {
	value = $state<Record<NodeFieldKey, boolean>>(load());

	toggle(key: NodeFieldKey) {
		this.value = { ...this.value, [key]: !this.value[key] };
		this.persist();
	}

	reset() {
		this.value = { ...DEFAULTS };
		this.persist();
	}

	private persist() {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(this.value));
		}
	}
}

export const nodeFields = new NodeFieldsState();
