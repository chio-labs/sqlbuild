<script lang="ts">
	import UserIcon from '@lucide/svelte/icons/user';
	import BotIcon from '@lucide/svelte/icons/bot';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import ListToolbar from '$lib/components/list/list-toolbar.svelte';
	import LoadRow from '$lib/components/list/load-row.svelte';
	import RelativeTime from '$lib/components/list/relative-time.svelte';
	import StatusLabel from '$lib/components/list/status-label.svelte';
	import GatedButton from '$lib/components/platform/gated-button.svelte';
	import IssuedSecret from '$lib/components/platform/issued-secret.svelte';
	import LocationTokens from '$lib/components/platform/location-tokens.svelte';
	import NoAccess from '$lib/components/platform/no-access.svelte';
	import PageTabs from '$lib/components/platform/page-tabs.svelte';
	import Panel from '$lib/components/platform/panel.svelte';
	import type { Account, AccountSource, ApiToken, IssuedToken } from '$lib/api';
	import { formatAgo, formatIn, formatStamp } from '$lib/format/time';
	import { errorMessage, tokenLabel, tokenTone } from '$lib/platform/labels';
	import { app } from '$lib/state/app.svelte';
	import { createResource } from '$lib/state/resource.svelte';

	type Tab = 'accounts' | 'tokens' | 'locations';
	const canUsers = $derived(app.can('user.manage'));
	const canTokens = $derived(app.can('token.manage'));
	const canLocations = $derived(app.can('location.manage'));
	const tabs = $derived(
		[
			canUsers && { value: 'accounts' as const, label: 'Users & service accounts' },
			canTokens && { value: 'tokens' as const, label: 'API tokens' },
			canLocations && { value: 'locations' as const, label: 'Location tokens' }
		].filter((t) => !!t)
	);
	let chosen = $state<Tab | null>(null);
	const tab = $derived(tabs.some((t) => t.value === chosen) ? chosen : (tabs[0]?.value ?? null));

	const accounts = createResource((client) => (app.can('user.manage') ? client.listAccounts() : Promise.resolve([])));
	const tokens = createResource((client) => (app.can('token.manage') ? client.listApiTokens() : Promise.resolve([])));

	const sourceLabel: Record<AccountSource, string> = {
		oidc: 'SSO (OIDC)',
		trusted_proxy: 'Trusted proxy',
		password: 'Password',
		service_account: 'Service account'
	};

	let query = $state('');
	const q = $derived(query.trim().toLowerCase());
	const shownAccounts = $derived(
		(accounts.data ?? []).filter((a) => !q || `${a.name} ${a.displayName} ${a.email ?? ''} ${a.ssoGroups.join(' ')}`.toLowerCase().includes(q))
	);
	const shownTokens = $derived(
		(tokens.data ?? []).filter((t) => !q || `${t.label} ${t.owner.name} ${t.prefix}`.toLowerCase().includes(q))
	);

	// ---- token actions ----
	let label = $state('');
	let owner = $state('');
	let expires = $state('90');
	let busy = $state<string | null>(null);
	let actionError = $state<string | null>(null);
	let issued = $state<IssuedToken<ApiToken> | null>(null);
	const owners = $derived(accounts.data?.filter((a) => !a.disabled) ?? []);

	async function act(key: string, action: () => Promise<unknown>) {
		busy = key;
		actionError = null;
		try {
			await action();
			tokens.refresh();
		} catch (error) {
			actionError = errorMessage(error);
		} finally {
			busy = null;
		}
	}

	function create() {
		void act('create', async () => {
			issued = await app.client.createApiToken({
				label,
				owner: owner || app.user?.name || '',
				expiresInDays: expires === 'never' ? null : Number(expires)
			});
			label = '';
		});
	}
	// ---- account actions ----
	let accountBusy = $state<string | null>(null);
	let accountError = $state<string | null>(null);
	let creatingService = $state(false);
	let serviceName = $state('');
	let serviceDescription = $state('');
	let createdService = $state<Account | null>(null);

	async function accountAct(key: string, action: () => Promise<unknown>) {
		accountBusy = key;
		accountError = null;
		try {
			await action();
			accounts.refresh();
		} catch (error) {
			accountError = errorMessage(error);
		} finally {
			accountBusy = null;
		}
	}

	function disable(a: Account) {
		const sessions = a.activeSessions === 1 ? '1 active session' : `${a.activeSessions} active sessions`;
		const tokens = a.kind === 'service_account' ? ' Its API tokens stop working.' : '';
		if (!confirm(`Disable ${a.displayName} (${a.name})? They can no longer sign in, and ${sessions} will be revoked now.${tokens}`)) return;
		void accountAct(a.name, () => app.client.disableAccount(a.name));
	}

	function createService() {
		void accountAct('create-service', async () => {
			createdService = await app.client.createServiceAccount({ name: serviceName, description: serviceDescription });
			serviceName = '';
			serviceDescription = '';
			creatingService = false;
		});
	}

	function issueTokenFor(a: Account) {
		owner = a.name;
		label = '';
		createdService = null;
		chosen = 'tokens';
	}

	const rotate = (t: ApiToken) => act(t.id, async () => (issued = await app.client.rotateApiToken(t.id)));
	function revoke(t: ApiToken) {
		if (!confirm(`Revoke "${t.label}" (${t.prefix}…)? Anything using it stops working.`)) return;
		void act(t.id, () => app.client.revokeApiToken(t.id));
	}
</script>

<AppTopbar title="Users & tokens">
	<Button
		variant="outline"
		size="sm"
		onclick={() => {
			accounts.refresh();
			tokens.refresh();
		}}>↻ Refresh</Button
	>
</AppTopbar>

{#if !tab}
	<NoAccess what="users and tokens" requires="user.manage, token.manage or location.manage" />
{:else}
	<PageTabs bind:value={() => tab, (v) => (chosen = v)} {tabs} />

	{#if tab === 'accounts'}
		<ListToolbar bind:query placeholder="Search people, service accounts and groups" total="{shownAccounts.length} of {accounts.data?.length ?? 0} accounts">
			{#snippet actions()}
				<span class="note">People appear on first sign-in; SSO groups map to roles in Roles &amp; approvals.</span>
				<GatedButton requires="user.manage" onclick={() => (creatingService = !creatingService)}>New service account</GatedButton>
			{/snippet}
		</ListToolbar>
		{#if creatingService}
			<div class="create-bar">
				<input class="field" placeholder="Name, e.g. svc-exports" bind:value={serviceName} aria-label="Service account name" />
				<input class="field wide" placeholder="What it is for" bind:value={serviceDescription} aria-label="Description" />
				<GatedButton requires="user.manage" variant="default" busy={accountBusy === 'create-service'} disabled={!serviceName.trim()} onclick={createService}>Create service account</GatedButton>
				<Button variant="ghost" size="sm" onclick={() => (creatingService = false)}>Cancel</Button>
				<span class="note">Signs in with API tokens only; give it roles in Roles &amp; approvals.</span>
			</div>
		{/if}
		{#if createdService}
			<div class="created">
				Created service account <code>{createdService.name}</code>. It has no roles or tokens yet.
				{#if canTokens}<Button variant="outline" size="xs" onclick={() => issueTokenFor(createdService!)}>Issue an API token</Button>{/if}
				<Button variant="ghost" size="xs" onclick={() => (createdService = null)}>Dismiss</Button>
			</div>
		{/if}
		{#if accountError}<p class="err">{accountError}</p>{/if}
		<div class="sb-list-wrap">
			<table class="sb-list static">
				<thead>
					<tr>
						<th>Account</th>
						<th>Sign-in</th>
						<th>SSO groups</th>
						<th>Last seen</th>
						<th>Status</th>
						<th></th>
					</tr>
				</thead>
				<tbody>
					{#each shownAccounts as a (a.name)}
						<tr class:sb-row-off={a.disabled}>
							<td>
								<div class="cell-name">
									{#if a.kind === 'service_account'}<BotIcon size={15} strokeWidth={1.75} />{:else}<UserIcon size={15} strokeWidth={1.75} />{/if}
									<div class="min-w-0">
										<strong>{a.displayName}</strong>
										<div class="cell-desc"><code>{a.name}</code>{#if a.email}&nbsp;· {a.email}{/if}{#if a.owner}&nbsp;· owned by {a.owner}{/if}</div>
										{#if a.description && a.description !== a.displayName}<div class="cell-desc">{a.description}</div>{/if}
									</div>
								</div>
							</td>
							<td class="muted">{sourceLabel[a.source]}</td>
							<td>
								{#each a.ssoGroups as g (g)}<span class="sb-tag group">{g}</span>{:else}<span class="muted">—</span>{/each}
							</td>
							<td><RelativeTime value={a.lastSeenAt ? formatAgo(a.lastSeenAt, app.now) : 'Never'} exact={formatStamp(a.lastSeenAt)} /></td>
							<td>
								<StatusLabel tone={a.disabled ? 'var(--sb-text-faint)' : 'var(--sb-success)'} label={a.disabled ? 'Disabled' : 'Active'} muted={a.disabled} />
								{#if !a.disabled && a.kind === 'user'}<div class="cell-desc">{a.activeSessions === 1 ? '1 session' : `${a.activeSessions} sessions`}</div>{/if}
							</td>
							<td class="num">
								{#if a.name === app.user?.name}
									<span class="faint">you</span>
								{:else if !a.disabled}
									<GatedButton requires="user.manage" size="xs" variant="destructive" busy={accountBusy === a.name} onclick={() => disable(a)}>Disable</GatedButton>
								{/if}
							</td>
						</tr>
					{:else}
						<LoadRow colspan={6} resource={accounts} empty="No accounts match the search." />
					{/each}
				</tbody>
			</table>
		</div>
	{:else if tab === 'tokens'}
		<div class="create-bar">
			<input class="field" placeholder="Token label, e.g. CI deploys" bind:value={label} aria-label="Token label" />
			{#if owners.length}
				<select class="field" bind:value={owner} aria-label="Owner">
					<option value="">Owner: me ({app.user?.name})</option>
					{#each owners.filter((o) => o.name !== app.user?.name) as o (o.name)}
						<option value={o.name}>Owner: {o.name}{o.kind === 'service_account' ? ' (service account)' : ''}</option>
					{/each}
				</select>
			{/if}
			<select class="field" bind:value={expires} aria-label="Expiry">
				<option value="30">Expires in 30 days</option>
				<option value="90">Expires in 90 days</option>
				<option value="365">Expires in 1 year</option>
				<option value="never">Never expires</option>
			</select>
			<GatedButton requires="token.manage" variant="default" busy={busy === 'create'} disabled={!label.trim()} onclick={create}>Create token</GatedButton>
			<span class="note">Same permissions as the owner. The secret is shown once.</span>
		</div>
		{#if issued}
			<IssuedSecret label={`Token "${issued.token.label}" for ${issued.token.owner.name}`} secret={issued.secret} ondismiss={() => (issued = null)} />
		{/if}
		{#if actionError}<p class="err">{actionError}</p>{/if}
		<ListToolbar bind:query placeholder="Search tokens" total="{shownTokens.length} of {tokens.data?.length ?? 0} tokens" />
		<div class="sb-list-wrap">
			<table class="sb-list static">
				<thead>
					<tr>
						<th>Token</th>
						<th>Owner</th>
						<th>Created</th>
						<th>Last used</th>
						<th>Expires</th>
						<th>Status</th>
						<th></th>
					</tr>
				</thead>
				<tbody>
					{#each shownTokens as t (t.id)}
						<tr class:sb-row-off={t.state !== 'active'}>
							<td>
								<strong>{t.label}</strong>
								<div class="cell-desc"><code>{t.prefix}…</code></div>
							</td>
							<td>{t.owner.name}{#if t.owner.kind === 'service_account'}<div class="cell-desc">service account</div>{/if}</td>
							<td>
								<RelativeTime value={formatAgo(t.createdAt, app.now)} exact={formatStamp(t.createdAt)} />
								<div class="cell-desc">by {t.createdBy.name}</div>
							</td>
							<td><RelativeTime value={t.lastUsedAt ? formatAgo(t.lastUsedAt, app.now) : 'Never'} exact={formatStamp(t.lastUsedAt)} /></td>
							<td>
								<RelativeTime
									value={t.revokedAt ? `revoked ${formatAgo(t.revokedAt, app.now)}` : t.expiresAt ? (Date.parse(t.expiresAt) > app.now ? formatIn(t.expiresAt, app.now) : formatAgo(t.expiresAt, app.now)) : 'Never'}
									exact={formatStamp(t.revokedAt ?? t.expiresAt)}
								/>
							</td>
							<td><StatusLabel tone={tokenTone[t.state]} label={tokenLabel[t.state]} muted={t.state !== 'active'} /></td>
							<td class="num">
								{#if t.state === 'active'}
									<span class="row-actions">
										<GatedButton requires="token.manage" size="xs" busy={busy === t.id} onclick={() => rotate(t)}>Rotate</GatedButton>
										<GatedButton requires="token.manage" size="xs" variant="destructive" busy={busy === t.id} onclick={() => revoke(t)}>Revoke</GatedButton>
									</span>
								{/if}
							</td>
						</tr>
					{:else}
						<LoadRow colspan={7} resource={tokens} empty="No tokens match the search." />
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<div class="min-h-0 flex-1 overflow-auto px-6 pt-5">
			<p class="lede">A location token lets one code location register, publish its own snapshots and report health. Nothing else.</p>
			<div class="locations">
				{#each app.bootstrap?.locations ?? [] as l (l.id)}
					<Panel title={l.name} note={l.id}>
						<LocationTokens locationId={l.id} />
					</Panel>
				{/each}
			</div>
		</div>
	{/if}
{/if}

<style>
	:global(.sb-list.static tbody tr) {
		cursor: default;
	}
	.note {
		margin-left: 8px;
		color: var(--muted-foreground);
		font-size: 12px;
	}
	.group {
		margin-right: 4px;
	}
	.create-bar {
		display: flex;
		flex: 0 0 auto;
		align-items: center;
		gap: 8px;
		padding: 12px 20px;
		border-bottom: 1px solid var(--border);
	}
	.field {
		height: 32px;
		padding: 0 9px;
		border: 1px solid var(--border);
		border-radius: 2px;
		background: var(--background);
		color: var(--foreground);
		font-size: 12.5px;
	}
	input.field {
		width: 260px;
	}
	input.field.wide {
		width: 340px;
	}
	.created {
		display: flex;
		flex: 0 0 auto;
		align-items: center;
		gap: 8px;
		padding: 10px 20px;
		border-bottom: 1px solid var(--border);
		font-size: 12.5px;
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
	.row-actions {
		display: inline-flex;
		gap: 4px;
	}
	.lede {
		margin-bottom: 18px;
		color: var(--muted-foreground);
		font-size: 12.5px;
	}
	.locations {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
		gap: 0 24px;
	}
</style>
