// Code colours mirror the SQLBuild UI's --syn-* tokens.
function theme(name, type, c) {
	return {
		name,
		type,
		colors: {
			'editor.background': c.bg,
			'editor.foreground': c.fg,
			'editorGroupHeader.tabsBackground': c.bg,
			'tab.activeBackground': c.bg,
			'tab.activeForeground': c.fg,
			'tab.border': c.line,
			'tab.activeBorderTop': c.primary,
			'editorGroupHeader.tabsBorder': c.line,
			'panel.border': c.line,
			'titleBar.border': c.line,
			'terminal.background': c.bg,
			'terminal.foreground': c.fg,
		},
		tokenColors: [
			{ scope: ['comment', 'punctuation.definition.comment'], settings: { foreground: c.comment } },
			{
				scope: ['keyword', 'storage', 'storage.type', 'keyword.control', 'keyword.other'],
				settings: { foreground: c.keyword },
			},
			{ scope: ['keyword.operator'], settings: { foreground: c.fg } },
			{ scope: ['string', 'string.quoted', 'markup.inline.raw'], settings: { foreground: c.string } },
			{ scope: ['constant.numeric', 'constant.language', 'constant'], settings: { foreground: c.number } },
			{
				scope: ['entity.name.function', 'support.function', 'meta.function-call.generic'],
				settings: { foreground: c.function },
			},
			{
				scope: ['entity.name.type', 'support.type', 'support.class', 'entity.name.class', 'entity.name.tag'],
				settings: { foreground: c.type },
			},
			{ scope: ['variable.parameter'], settings: { foreground: c.fg } },
			{ scope: ['variable.other.key', 'support.type.property-name'], settings: { foreground: c.keyword } },
			{ scope: ['entity.name.section', 'entity.name.tag'], settings: { foreground: c.type } },
			{ scope: ['entity.other.attribute-name', 'support.type.property-name'], settings: { foreground: c.type } },
		],
	};
}

export const sqlbuildDark = theme('sqlbuild-dark', 'dark', {
	bg: '#111418',
	fg: '#c9cdd4',
	line: '#1f232a',
	primary: '#3788e8',
	keyword: '#5aa9e6',
	string: '#79c98a',
	number: '#e3b341',
	comment: '#5c606b',
	function: '#c79bf0',
	type: '#4dd6c4',
});

export const sqlbuildLight = theme('sqlbuild-light', 'light', {
	bg: '#fbfcfe',
	fg: '#2b3038',
	line: '#e6e8eb',
	primary: '#2677d9',
	keyword: '#1a56c4',
	string: '#0a7a3f',
	number: '#9a6700',
	comment: '#8a909c',
	function: '#7c3aed',
	type: '#0f766e',
});
