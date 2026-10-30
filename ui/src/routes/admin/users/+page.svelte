<script lang="ts">
	import UserIcon from '@lucide/svelte/icons/user';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import GatedButton from '$lib/components/platform/gated-button.svelte';
	import NoAccess from '$lib/components/platform/no-access.svelte';
	import type { Account } from '$lib/api';
	import { formatAgo, formatStamp } from '$lib/format/time';
	import { accountSourceLabel, errorMessage } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	const accounts = createResource((client) => (app.can('user.manage') ? client.listAccounts() : Promise.resolve([])));

	let query = $state('');
	const q = $derived(query.trim().toLowerCase());
	const people = $derived((accounts.data ?? []).filter((a) => a.kind === 'user'));
	const shown = $derived(people.filter((a) => !q || `${a.name} ${a.displayName} ${a.email ?? ''} ${a.ssoGroups.join(' ')}`.toLowerCase().includes(q)));

	let busy = $state<string | null>(null);
	let error = $state<string | null>(null);

	async function act(key: string, action: () => Promise<unknown>) {
		busy = key;
		error = null;
		try {
			await action();
			accounts.refresh();
		} catch (e) {
			error = errorMessage(e);
		} finally {
			busy = null;
		}
	}

	function disable(a: Account) {
		const sessions = a.activeSessions === 1 ? 'their 1 signed-in session ends' : `their ${a.activeSessions} signed-in sessions end`;
		if (!confirm(`Disable ${a.displayName} (${a.name})? They can't sign in any more, in the browser or with sqb login, and ${sessions} now.`)) return;
		void act(a.name, () => app.client.disableAccount(a.name));
	}

	function enable(a: Account) {
		if (!confirm(`Enable ${a.displayName} (${a.name})? They can sign in again.`)) return;
		void act(a.name, () => app.client.enableAccount(a.name));
	}
</script>

<AppTopbar title="Users">
	<Button variant="outline" size="sm" onclick={() => accounts.refresh()}>↻ Refresh</Button>
</AppTopbar>

{#if !app.can('user.manage')}
	<NoAccess what="people" requires="user.manage" />
{:else}
	<div class="intro">
		<p>
			People appear here the first time they sign in. They sign in to this UI with single sign-on, and on the command line with <code>sqb login</code>, which opens the
			browser and keeps a short-lived session. People don't have API tokens; for scripts and CI, use a <a href="/admin/service-accounts">service account</a>.
		</p>
		<p class="faint">What someone can do comes from their roles and SSO groups, under <a href="/admin/roles">Roles &amp; approvals</a>.</p>
	</div>
	<ListToolbar bind:query placeholder="Search people and groups" total="{shown.length} of {people.length} people" />
	{#if error}<p class="err">{error}</p>{/if}
	<div class="sb-list-wrap">
		<table class="sb-list static">
			<thead>
				<tr>
					<th>Person</th>
					<th>Signs in with</th>
					<th>SSO groups</th>
					<th>Last seen</th>
					<th>Status</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each shown as a (a.name)}
					<tr class:sb-row-off={a.disabled}>
						<td>
							<div class="cell-name">
								<UserIcon size={15} strokeWidth={1.75} />
								<div class="min-w-0">
									<strong>{a.displayName}</strong>
									<div class="cell-desc"><code>{a.name}</code>{#if a.email}&nbsp;· {a.email}{/if}</div>
								</div>
							</div>
						</td>
						<td class="muted">{accountSourceLabel[a.source]}</td>
						<td>
							{#each a.ssoGroups as g (g)}<span class="sb-tag group">{g}</span>{:else}<span class="muted">—</span>{/each}
						</td>
						<td><RelativeTime value={a.lastSeenAt ? formatAgo(a.lastSeenAt, app.now) : 'Never'} exact={formatStamp(a.lastSeenAt)} /></td>
						<td>
							<StatusLabel tone={a.disabled ? 'var(--sb-text-faint)' : 'var(--sb-success)'} label={a.disabled ? 'Disabled' : 'Active'} muted={a.disabled} />
							{#if !a.disabled}<div class="cell-desc">{a.activeSessions === 0 ? 'not signed in' : a.activeSessions === 1 ? 'signed in on 1 device' : `signed in on ${a.activeSessions} devices`}</div>{/if}
						</td>
						<td class="num">
							{#if a.name === app.user?.name}
								<span class="faint">you</span>
							{:else if !a.disabled}
								<GatedButton requires="user.manage" size="xs" variant="destructive" busy={busy === a.name} onclick={() => disable(a)}>Disable</GatedButton>
							{:else}
								<GatedButton requires="user.manage" size="xs" busy={busy === a.name} onclick={() => enable(a)}>Enable</GatedButton>
							{/if}
						</td>
					</tr>
				{:else}
					<LoadRow colspan={6} resource={accounts} empty={people.length ? 'No one matches the search.' : 'No one has signed in yet.'} />
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	:global(.sb-list.static tbody tr) {
		cursor: default;
	}
	.intro {
		flex: 0 0 auto;
		max-width: 900px;
		padding: 14px 20px 10px;
		font-size: 12.5px;
		line-height: 1.55;
	}
	.intro p + p {
		margin-top: 4px;
	}
	.intro a {
		color: var(--primary);
	}
	code {
		font-family: var(--font-mono);
		font-size: 12px;
	}
	.group {
		margin-right: 4px;
	}
	.faint {
		color: var(--sb-text-faint);
		font-size: 12px;
	}
	.err {
		padding: 8px 20px 0;
		color: var(--sb-error);
		font-size: 12.5px;
	}
</style>
