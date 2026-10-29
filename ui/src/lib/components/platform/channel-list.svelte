<script lang="ts">
	import BellIcon from '@lucide/svelte/icons/bell';
	import MailIcon from '@lucide/svelte/icons/mail';
	import WebhookIcon from '@lucide/svelte/icons/webhook';
	import type { Component } from 'svelte';
	import type { Channel, ChannelTestResult, ChannelType } from '$lib/api';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { errorMessage, testLabel, testTone } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import GatedButton from './gated-button.svelte';

	let { channels, ontested }: { channels: Channel[]; ontested?: () => void } = $props();

	const icon: Record<ChannelType, Component> = { slack: BellIcon, email: MailIcon, webhook: WebhookIcon };

	let testing = $state<string | null>(null);
	let results = $state<Record<string, ChannelTestResult>>({});
	let failure = $state<string | null>(null);

	async function testSend(name: string) {
		const scope = app.scope;
		if (!scope) return;
		testing = name;
		failure = null;
		try {
			results = { ...results, [name]: await app.client.testChannel(scope, name) };
			ontested?.();
		} catch (error) {
			failure = errorMessage(error);
		} finally {
			testing = null;
		}
	}
</script>

{#if failure}<p class="failure">Couldn't send: {failure}</p>{/if}
<table class="sb-list channels">
	<thead>
		<tr>
			<th>Channel</th>
			<th>Destination</th>
			<th>Last test</th>
			<th></th>
		</tr>
	</thead>
	<tbody>
		{#each channels as c (c.name)}
			{@const Glyph = icon[c.type]}
			{@const test = results[c.name] ?? c.lastTest}
			<tr>
				<td>
					<div class="cell-name">
						<Glyph size={15} strokeWidth={1.75} />
						<div class="min-w-0">
							<strong>{c.name}</strong>
							<div class="cell-desc">{c.type} · {c.description}</div>
						</div>
					</div>
				</td>
				<td class="muted" title="Defined in {c.sourceFile}"><code>{c.destinationSource}</code></td>
				<td title={test ? `${test.message} · ${test.by.name} · ${formatStamp(test.at)}` : undefined}>
					{#if test}
						<StatusLabel tone={testTone[test.outcome]} label="{testLabel[test.outcome]} {formatAgo(test.at, app.now)}" />
						<div class="cell-desc">{test.message}</div>
					{:else}
						<span class="muted">Never tested</span>
					{/if}
				</td>
				<td class="num">
					<GatedButton requires="connection.test" busy={testing === c.name} onclick={() => testSend(c.name)}>
						{testing === c.name ? 'Sending…' : 'Send test'}
					</GatedButton>
				</td>
			</tr>
		{/each}
	</tbody>
</table>

<style>
	.channels {
		border-top: 1px solid var(--border);
	}
	:global(.sb-list.channels tbody tr) {
		cursor: default;
	}
	.failure {
		margin-bottom: 8px;
		color: var(--sb-error);
		font-size: 12.5px;
	}
</style>
