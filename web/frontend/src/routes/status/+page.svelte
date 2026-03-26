<script lang="ts">
	import { onMount } from 'svelte';

	interface StatusData {
		timestamp: number;
		status: 'operational' | 'degraded' | 'down';
		components: Record<string, string>;
		nodes_online: number;
		nodes_total: number;
		queue_depth: number;
		jobs_running: number;
		uptime_seconds: number;
		avg_job_seconds: number;
		recent_incidents: { timestamp: number; status: string; type: string; duration_seconds?: number }[];
		last_incident: number | null;
	}

	interface HistorySnapshot {
		timestamp: number;
		status: string;
		components: Record<string, string>;
		nodes_online: number;
		queue_depth: number;
		jobs_running: number;
	}

	let status = $state<StatusData | null>(null);
	let history = $state<HistorySnapshot[]>([]);
	let error = $state('');
	let lastFetch = $state(0);
	let tick = $state(0);

	async function fetchStatus() {
		try {
			const [statusRes, historyRes] = await Promise.all([
				fetch('/api/status').then((r) => r.json()),
				fetch('/api/status/history?limit=60').then((r) => r.json())
			]);
			status = statusRes;
			history = historyRes.snapshots ?? [];
			error = '';
			lastFetch = Date.now();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to fetch status';
		}
	}

	function formatUptime(seconds: number): string {
		const d = Math.floor(seconds / 86400);
		const h = Math.floor((seconds % 86400) / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		if (d > 0) return `${d}d ${h}h ${m}m`;
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	function formatTime(ts: number): string {
		return new Date(ts * 1000).toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function relativeTime(ts: number): string {
		const diff = Date.now() / 1000 - ts;
		if (diff < 60) return 'just now';
		if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
		if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
		return `${Math.floor(diff / 86400)}d ago`;
	}

	// Sparkline path from history
	function sparklinePath(data: HistorySnapshot[], key: 'nodes_online' | 'queue_depth' | 'jobs_running'): string {
		if (data.length < 2) return '';
		const values = data.map((d) => d[key] ?? 0);
		const max = Math.max(...values, 1);
		const w = 200;
		const h = 32;
		const step = w / (values.length - 1);
		return values
			.map((v, i) => {
				const x = i * step;
				const y = h - (v / max) * (h - 4) - 2;
				return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}

	// Status bar: colored segments for history
	function statusColor(s: string): string {
		if (s === 'operational') return 'var(--state-complete)';
		if (s === 'degraded') return 'var(--accent)';
		return 'var(--state-error)';
	}

	function componentIcon(name: string): string {
		const icons: Record<string, string> = {
			api: '///',
			database: '|||',
			auth: '[=]',
			worker: '>>|',
			disk: '[#]'
		};
		return icons[name] ?? '(?)';
	}

	function componentLabel(name: string): string {
		return name.charAt(0).toUpperCase() + name.slice(1);
	}

	let badgeUrl = $derived(typeof window !== 'undefined' ? `${window.location.origin}/api/status/badge` : '/api/status/badge');

	onMount(() => {
		fetchStatus();
		const interval = setInterval(() => {
			fetchStatus();
			tick++;
		}, 30000);

		// Tick counter for "last updated" display
		const tickInterval = setInterval(() => tick++, 1000);

		return () => {
			clearInterval(interval);
			clearInterval(tickInterval);
		};
	});
</script>

<svelte:head>
	<title>CorridorKey — System Status</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<div class="status-page">
	<div class="status-chrome">
		<header class="status-header">
			<div class="header-left">
				<a href="/" class="logo-link">
					<span class="logo-mark">CK</span>
					<span class="logo-text">CORRIDORKEY</span>
				</a>
				<span class="header-sep">/</span>
				<span class="header-title">SYSTEM STATUS</span>
			</div>
			<div class="header-right mono">
				{#if lastFetch > 0}
					{@const ago = Math.floor((Date.now() - lastFetch) / 1000)}
					<span class="refresh-dot" class:stale={ago > 45}></span>
					<span class="refresh-text">{ago < 5 ? 'LIVE' : `${ago}s ago`}</span>
				{/if}
			</div>
		</header>

		{#if error && !status}
			<div class="error-banner mono">{error}</div>
		{:else if !status}
			<div class="loading-state">
				<div class="loading-pulse"></div>
				<span class="mono">CONNECTING...</span>
			</div>
		{:else}
			<!-- Hero status -->
			<section class="hero-status" data-status={status.status}>
				<div class="status-beacon" data-status={status.status}>
					<div class="beacon-ring"></div>
					<div class="beacon-core"></div>
				</div>
				<div class="status-text-block">
					<h1 class="status-label mono">{status.status.toUpperCase()}</h1>
					<p class="status-sub">
						{#if status.status === 'operational'}
							All systems functioning normally
						{:else if status.status === 'degraded'}
							Some components are experiencing issues
						{:else}
							Platform is currently unavailable
						{/if}
					</p>
				</div>
			</section>

			<!-- Status timeline bar -->
			{#if history.length > 1}
				<section class="timeline-section">
					<div class="section-label mono">LAST {history.length} SNAPSHOTS</div>
					<div class="timeline-bar">
						{#each history as snap, i}
							<div
								class="timeline-segment"
								style="background: {statusColor(snap.status)}; width: {100 / history.length}%"
								title="{new Date(snap.timestamp * 1000).toLocaleTimeString()} — {snap.status}"
							></div>
						{/each}
					</div>
					<div class="timeline-labels mono">
						<span>{history.length > 0 ? relativeTime(history[0].timestamp) : ''}</span>
						<span>now</span>
					</div>
				</section>
			{/if}

			<!-- Component health -->
			<section class="components-section">
				<div class="section-label mono">COMPONENTS</div>
				<div class="components-grid">
					{#each Object.entries(status.components) as [name, state]}
						<div class="component-card" data-state={state}>
							<div class="comp-icon mono">{componentIcon(name)}</div>
							<div class="comp-info">
								<span class="comp-name">{componentLabel(name)}</span>
								<span class="comp-state mono">{state.toUpperCase()}</span>
							</div>
							<div class="comp-dot" data-state={state}></div>
						</div>
					{/each}
				</div>
			</section>

			<!-- Metrics -->
			<section class="metrics-section">
				<div class="section-label mono">METRICS</div>
				<div class="metrics-grid">
					<div class="metric-card">
						<div class="metric-value mono">{status.uptime_seconds > 0 ? formatUptime(status.uptime_seconds) : '--'}</div>
						<div class="metric-label">Uptime</div>
						<div class="metric-icon mono">UP</div>
					</div>
					<div class="metric-card">
						<div class="metric-value mono">
							{status.nodes_online}<span class="metric-dim">/{status.nodes_total}</span>
						</div>
						<div class="metric-label">Nodes Online</div>
						{#if history.length > 1}
							<svg class="metric-spark" viewBox="0 0 200 32" preserveAspectRatio="none">
								<path d={sparklinePath(history, 'nodes_online')} fill="none" stroke="var(--state-complete)" stroke-width="1.5" />
							</svg>
						{/if}
					</div>
					<div class="metric-card">
						<div class="metric-value mono">{status.queue_depth}</div>
						<div class="metric-label">Queue Depth</div>
						{#if history.length > 1}
							<svg class="metric-spark" viewBox="0 0 200 32" preserveAspectRatio="none">
								<path d={sparklinePath(history, 'queue_depth')} fill="none" stroke="var(--accent)" stroke-width="1.5" />
							</svg>
						{/if}
					</div>
					<div class="metric-card">
						<div class="metric-value mono">{status.jobs_running}</div>
						<div class="metric-label">Jobs Running</div>
						{#if history.length > 1}
							<svg class="metric-spark" viewBox="0 0 200 32" preserveAspectRatio="none">
								<path d={sparklinePath(history, 'jobs_running')} fill="none" stroke="var(--secondary)" stroke-width="1.5" />
							</svg>
						{/if}
					</div>
					<div class="metric-card">
						<div class="metric-value mono">
							{status.avg_job_seconds > 0 ? `${status.avg_job_seconds.toFixed(1)}s` : '--'}
						</div>
						<div class="metric-label">Avg Job Time (1h)</div>
						<div class="metric-icon mono">AVG</div>
					</div>
				</div>
			</section>

			<!-- Incidents -->
			<section class="incidents-section">
				<div class="section-label mono">RECENT INCIDENTS</div>
				{#if status.recent_incidents.length === 0}
					<div class="no-incidents mono">No recent incidents</div>
				{:else}
					<div class="incidents-list">
						{#each status.recent_incidents as incident}
							<div class="incident-row" data-type={incident.type}>
								<div class="incident-marker" data-type={incident.type}></div>
								<div class="incident-info">
									<span class="incident-type mono">
										{incident.type === 'recovery' ? 'RESOLVED' : 'DEGRADATION'}
									</span>
									<span class="incident-time mono">{formatTime(incident.timestamp)}</span>
								</div>
								{#if incident.duration_seconds}
									<span class="incident-duration mono">
										{formatUptime(incident.duration_seconds)}
									</span>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</section>

			<!-- Badge embed -->
			<section class="badge-section">
				<div class="section-label mono">STATUS BADGE</div>
				<div class="badge-preview">
					<!-- svelte-ignore a11y_missing_attribute -->
					<img src="/api/status/badge" alt="Status badge" class="badge-img" />
				</div>
				<div class="badge-code">
					<div class="code-label mono">MARKDOWN</div>
					<code class="mono">![Status]({badgeUrl})</code>
				</div>
				<div class="badge-code">
					<div class="code-label mono">HTML</div>
					<code class="mono">&lt;img src="{badgeUrl}" alt="CorridorKey Status"&gt;</code>
				</div>
			</section>

			<footer class="status-footer mono">
				<span>CorridorKey &mdash; Neural Green Screen Keyer</span>
				<span class="footer-sep">&bull;</span>
				<span>Auto-refreshes every 30s</span>
			</footer>
		{/if}
	</div>
</div>

<style>
	/* ---- Page shell ---- */
	.status-page {
		min-height: 100vh;
		overflow-y: auto;
		background: var(--surface-0);
		color: var(--text-primary);
		font-family: var(--font-sans);
	}

	.status-chrome {
		max-width: 780px;
		margin: 0 auto;
		padding: var(--sp-6) var(--sp-4);
	}

	/* ---- Header ---- */
	.status-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding-bottom: var(--sp-5);
		border-bottom: 1px solid var(--border);
		margin-bottom: var(--sp-6);
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
	}

	.logo-link {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		text-decoration: none;
	}

	.logo-mark {
		font-family: var(--font-mono);
		font-weight: 700;
		font-size: 14px;
		background: var(--accent);
		color: var(--surface-0);
		padding: 2px 5px;
		border-radius: 3px;
		letter-spacing: 0.04em;
	}

	.logo-text {
		font-family: var(--font-mono);
		font-weight: 500;
		font-size: 12px;
		color: var(--text-secondary);
		letter-spacing: 0.12em;
	}

	.header-sep {
		color: var(--text-tertiary);
		font-weight: 300;
	}

	.header-title {
		font-family: var(--font-mono);
		font-size: 12px;
		font-weight: 500;
		letter-spacing: 0.14em;
		color: var(--text-secondary);
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		font-size: 11px;
		color: var(--text-tertiary);
	}

	.refresh-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--state-complete);
		animation: pulse-dot 2s ease-in-out infinite;
	}

	.refresh-dot.stale {
		background: var(--state-raw);
		animation: none;
	}

	.refresh-text {
		letter-spacing: 0.06em;
	}

	@keyframes pulse-dot {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}

	/* ---- Error / Loading ---- */
	.error-banner {
		background: rgba(255, 82, 82, 0.1);
		border: 1px solid rgba(255, 82, 82, 0.3);
		color: var(--state-error);
		padding: var(--sp-4);
		border-radius: var(--radius-md);
		font-size: 13px;
		text-align: center;
	}

	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--sp-4);
		padding: var(--sp-10) 0;
		color: var(--text-tertiary);
		font-size: 12px;
		letter-spacing: 0.1em;
	}

	.loading-pulse {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		border: 2px solid var(--surface-4);
		border-top-color: var(--accent);
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* ---- Hero status ---- */
	.hero-status {
		display: flex;
		align-items: center;
		gap: var(--sp-5);
		padding: var(--sp-6) 0;
		margin-bottom: var(--sp-4);
	}

	.status-beacon {
		position: relative;
		width: 52px;
		height: 52px;
		flex-shrink: 0;
	}

	.beacon-ring {
		position: absolute;
		inset: 0;
		border-radius: 50%;
		border: 2px solid var(--state-complete);
		opacity: 0.3;
		animation: beacon-expand 2.5s ease-out infinite;
	}

	.beacon-core {
		position: absolute;
		top: 50%;
		left: 50%;
		width: 18px;
		height: 18px;
		transform: translate(-50%, -50%);
		border-radius: 50%;
		background: var(--state-complete);
		box-shadow: 0 0 20px rgba(93, 216, 121, 0.4);
	}

	[data-status='degraded'] .beacon-ring {
		border-color: var(--accent);
	}
	[data-status='degraded'] .beacon-core {
		background: var(--accent);
		box-shadow: 0 0 20px rgba(255, 242, 3, 0.4);
	}

	[data-status='down'] .beacon-ring {
		border-color: var(--state-error);
	}
	[data-status='down'] .beacon-core {
		background: var(--state-error);
		box-shadow: 0 0 20px rgba(255, 82, 82, 0.4);
	}

	@keyframes beacon-expand {
		0% { transform: scale(0.6); opacity: 0.5; }
		100% { transform: scale(1.3); opacity: 0; }
	}

	.status-text-block {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.status-label {
		font-size: 26px;
		font-weight: 600;
		letter-spacing: 0.08em;
		color: var(--text-primary);
	}

	[data-status='operational'] .status-label { color: var(--state-complete); }
	[data-status='degraded'] .status-label { color: var(--accent); }
	[data-status='down'] .status-label { color: var(--state-error); }

	.status-sub {
		font-size: 14px;
		color: var(--text-secondary);
		font-weight: 300;
	}

	/* ---- Timeline ---- */
	.timeline-section {
		margin-bottom: var(--sp-6);
	}

	.section-label {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.16em;
		color: var(--text-tertiary);
		margin-bottom: var(--sp-2);
	}

	.timeline-bar {
		display: flex;
		height: 8px;
		border-radius: 4px;
		overflow: hidden;
		gap: 1px;
		background: var(--surface-3);
	}

	.timeline-segment {
		min-width: 2px;
		transition: opacity 0.2s;
	}

	.timeline-segment:hover {
		opacity: 0.7;
	}

	.timeline-labels {
		display: flex;
		justify-content: space-between;
		font-size: 10px;
		color: var(--text-tertiary);
		margin-top: 4px;
	}

	/* ---- Components ---- */
	.components-section {
		margin-bottom: var(--sp-6);
	}

	.components-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: var(--sp-2);
	}

	.component-card {
		display: flex;
		align-items: center;
		gap: var(--sp-2);
		padding: var(--sp-3);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		transition: border-color 0.2s;
	}

	.component-card[data-state='ok'] {
		border-color: rgba(93, 216, 121, 0.15);
	}

	.component-card[data-state='error'] {
		border-color: rgba(255, 82, 82, 0.25);
		background: rgba(255, 82, 82, 0.04);
	}

	.component-card[data-state='warning'] {
		border-color: rgba(255, 242, 3, 0.2);
	}

	.comp-icon {
		font-size: 11px;
		color: var(--text-tertiary);
		flex-shrink: 0;
		width: 26px;
		text-align: center;
	}

	.comp-info {
		display: flex;
		flex-direction: column;
		gap: 1px;
		flex: 1;
		min-width: 0;
	}

	.comp-name {
		font-size: 13px;
		font-weight: 500;
	}

	.comp-state {
		font-size: 10px;
		letter-spacing: 0.08em;
		color: var(--text-tertiary);
	}

	[data-state='ok'] .comp-state { color: var(--state-complete); }
	[data-state='error'] .comp-state { color: var(--state-error); }
	[data-state='warning'] .comp-state { color: var(--accent); }
	[data-state='skipped'] .comp-state { color: var(--text-tertiary); }

	.comp-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		flex-shrink: 0;
		background: var(--text-tertiary);
	}

	.comp-dot[data-state='ok'] { background: var(--state-complete); }
	.comp-dot[data-state='error'] { background: var(--state-error); }
	.comp-dot[data-state='warning'] { background: var(--accent); }

	/* ---- Metrics ---- */
	.metrics-section {
		margin-bottom: var(--sp-6);
	}

	.metrics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
		gap: var(--sp-2);
	}

	.metric-card {
		position: relative;
		padding: var(--sp-3) var(--sp-3) var(--sp-2);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.metric-value {
		font-size: 22px;
		font-weight: 600;
		letter-spacing: 0.02em;
		line-height: 1.1;
		color: var(--text-primary);
	}

	.metric-dim {
		font-size: 14px;
		color: var(--text-tertiary);
		font-weight: 400;
	}

	.metric-label {
		font-size: 11px;
		color: var(--text-tertiary);
		margin-top: 4px;
	}

	.metric-icon {
		position: absolute;
		top: var(--sp-3);
		right: var(--sp-3);
		font-size: 9px;
		font-weight: 600;
		letter-spacing: 0.1em;
		color: var(--text-tertiary);
		opacity: 0.5;
	}

	.metric-spark {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 32px;
		opacity: 0.35;
	}

	/* ---- Incidents ---- */
	.incidents-section {
		margin-bottom: var(--sp-6);
	}

	.no-incidents {
		font-size: 12px;
		color: var(--text-tertiary);
		letter-spacing: 0.06em;
		padding: var(--sp-4);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		text-align: center;
	}

	.incidents-list {
		display: flex;
		flex-direction: column;
		gap: var(--sp-1);
	}

	.incident-row {
		display: flex;
		align-items: center;
		gap: var(--sp-3);
		padding: var(--sp-3);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
	}

	.incident-marker {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.incident-marker[data-type='degradation'] { background: var(--state-error); }
	.incident-marker[data-type='recovery'] { background: var(--state-complete); }

	.incident-info {
		display: flex;
		flex-direction: column;
		gap: 1px;
		flex: 1;
	}

	.incident-type {
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.06em;
	}

	.incident-row[data-type='degradation'] .incident-type { color: var(--state-error); }
	.incident-row[data-type='recovery'] .incident-type { color: var(--state-complete); }

	.incident-time {
		font-size: 10px;
		color: var(--text-tertiary);
	}

	.incident-duration {
		font-size: 11px;
		color: var(--text-secondary);
		flex-shrink: 0;
	}

	/* ---- Badge ---- */
	.badge-section {
		margin-bottom: var(--sp-6);
	}

	.badge-preview {
		margin-bottom: var(--sp-3);
	}

	.badge-img {
		height: 20px;
	}

	.badge-code {
		margin-bottom: var(--sp-2);
	}

	.code-label {
		font-size: 9px;
		letter-spacing: 0.12em;
		color: var(--text-tertiary);
		margin-bottom: 3px;
	}

	.badge-code code {
		display: block;
		padding: var(--sp-2) var(--sp-3);
		background: var(--surface-2);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		font-size: 11px;
		color: var(--text-secondary);
		overflow-x: auto;
		white-space: nowrap;
		user-select: all;
		cursor: text;
	}

	/* ---- Footer ---- */
	.status-footer {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--sp-2);
		padding-top: var(--sp-5);
		border-top: 1px solid var(--border);
		font-size: 11px;
		color: var(--text-tertiary);
		letter-spacing: 0.04em;
	}

	.footer-sep {
		opacity: 0.4;
	}
</style>
