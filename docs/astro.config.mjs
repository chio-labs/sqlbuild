import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';
import { sqlbuildDark, sqlbuildLight } from './src/code-themes.mjs';

export default defineConfig({
	site: 'https://docs.sqlbuild.com',
	integrations: [
		starlight({
			title: 'SQLBuild',
			description: 'Verify early, test properly, and refactor safely.',
			logo: {
				light: './src/assets/logo-light.png',
				dark: './src/assets/logo-dark.png',
				replacesTitle: true,
			},
			favicon: '/favicon.png',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/chio-labs/sqlbuild' },
				{ icon: 'discord', label: 'Discord', href: 'https://discord.gg/tYU4nXdsT' },
			],
			customCss: ['./src/styles/fonts.css', './src/styles/sqlbuild.css'],
			expressiveCode: {
				themes: [sqlbuildDark, sqlbuildLight],
				styleOverrides: {
					borderRadius: '2px',
					borderWidth: '1px',
					codeFontFamily: 'var(--sl-font-mono)',
					codeFontSize: '13px',
					codeLineHeight: '1.65',
					uiFontFamily: 'var(--sl-font)',
					frames: {
						shadowColor: 'transparent',
						frameBoxShadowCssValue: 'none',
						editorTabBarBackground: 'var(--sqb-code-bg)',
						editorActiveTabBackground: 'var(--sqb-code-bg)',
						editorActiveTabIndicatorTopColor: 'var(--sqb-primary)',
						editorTabBarBorderBottomColor: 'var(--sqb-line)',
						terminalTitlebarBackground: 'var(--sqb-code-bg)',
						terminalTitlebarBorderBottomColor: 'var(--sqb-line)',
						terminalTitlebarDotsOpacity: '0.35',
						terminalBackground: 'var(--sqb-code-bg)',
					},
					borderColor: 'var(--sqb-line)',
				},
			},
			sidebar: [
				{ label: 'Getting Started', items: ['index', 'quickstart'] },
				{ label: 'Concepts', items: ['concepts/interpolation'] },
				{ label: 'CLI Reference', items: ['cli/plan'] },
			],
			plugins: [
				starlightLlmsTxt({
					projectName: 'SQLBuild',
					description:
						'SQLBuild is a free, open-source framework for building SQL and Python data pipelines, with compile-time checks, tests, plans and diffs.',
				}),
			],
		}),
	],
});
