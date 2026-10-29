<script lang="ts">
	import type { ConnectionTest, Scope } from '$lib/api';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { errorMessage, testLabel, testTone } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import GatedButton from './gated-button.svelte';

	type Props = { scope: Scope; connection: string; last: ConnectionTest | null; ontested?: () => void };
	let { scope, connection, last, ontested }: Props = $props();

	let testing = $state(false);
	let result = $state<ConnectionTest | null>(null);
	let failure = $state<string | null>(null);
	const shown = $derived(result ?? last);

	async function test() {
		testing = true;
		failure = null;
		try {
			result = await app.client.testConnection(scope, connection);
			ontested?.();
		} catch (error) {
			failure = errorMessage(error);
		} finally {
			testing = false;
		}
	}

	function origin(t: ConnectionTest): string {
		return t.trigger === 'publish' ? 'after publish' : `by ${t.by?.name ?? 'unknown'}`;
	}
</script>

<div class="connection-test">
	<div class="min-w-0 flex-1">
		{#if testing}
			<StatusLabel tone="var(--sb-running)" label="Testing… (sqb debug)" />
		{:else if shown}
			<span title="{formatStamp(shown.at)} · {shown.durationMs} ms">
				<StatusLabel tone={testTone[shown.outcome]} label="{testLabel[shown.outcome]} {formatAgo(shown.at, app.now)} {origin(shown)}" />
			</span>
			<div class="message">{shown.message}</div>
		{:else}
			<StatusLabel tone="var(--sb-text-faint)" label="Not tested" muted />
		{/if}
		{#if failure}<div class="message err">{failure}</div>{/if}
	</div>
	<GatedButton requires="connection.test" busy={testing} onclick={test}>Test connection</GatedButton>
</div>

<style>
	.connection-test {
		display: flex;
		align-items: center;
		gap: 12px;
		min-width: 0;
	}
	.message {
		margin-top: 2px;
		overflow: hidden;
		color: var(--muted-foreground);
		font-size: 12px;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.err {
		color: var(--sb-error);
	}
</style>
