// Sidebar and redirects, first generated from the Mintlify docs.json.
export const sidebar = [
	{
		"label": "Getting Started",
		"items": [
			"docs",
			"docs/quickstart",
			"docs/feature-comparison",
			"docs/benchmarks"
		]
	},
	{
		"label": "dbt Compatibility",
		"items": [
			"docs/concepts/dbt-compatibility/overview",
			"docs/concepts/dbt-compatibility/selection",
			"docs/concepts/dbt-compatibility/adding-sqlbuild-models"
		]
	},
	{
		"label": "Concepts",
		"items": [
			"docs/concepts/project-configuration",
			"docs/concepts/resource-identities",
			{
				"label": "Adapters",
				"collapsed": true,
				"items": [
					"docs/concepts/adapters",
					"docs/concepts/adapters/duckdb",
					"docs/concepts/adapters/motherduck",
					"docs/concepts/adapters/snowflake",
					"docs/concepts/adapters/bigquery",
					"docs/concepts/adapters/databricks",
					"docs/concepts/adapters/postgres",
					"docs/concepts/adapters/sqlserver"
				]
			},
			"docs/concepts/sources",
			"docs/concepts/seeds",
			{
				"label": "Models",
				"collapsed": true,
				"items": [
					"docs/concepts/models",
					"docs/concepts/models/materializations",
					"docs/concepts/models/schemas",
					"docs/concepts/models/type-enforcement",
					"docs/concepts/models/contracts",
					"docs/concepts/models/migrations",
					{
						"label": "Hooks",
						"collapsed": true,
						"items": [
							{
								"label": "Overview",
								"slug": "docs/concepts/models/hooks"
							},
							"docs/concepts/models/hooks/sql",
							"docs/concepts/models/hooks/python"
						]
					},
					"docs/concepts/models/configuration"
				]
			},
			{
				"label": "Enums and Constants",
				"collapsed": true,
				"items": [
					"docs/concepts/enums",
					"docs/concepts/constants",
					"docs/concepts/constants/collections-and-rendering",
					"docs/concepts/enums/model-contracts",
					"docs/concepts/model-private-values"
				]
			},
			{
				"label": "Python Macros",
				"collapsed": true,
				"items": [
					"docs/concepts/macros",
					"docs/concepts/macros/composition-and-context"
				]
			},
			"docs/concepts/interpolation",
			"docs/concepts/functions",
			"docs/concepts/incremental",
			{
				"label": "Planning and Change Detection",
				"collapsed": true,
				"items": [
					"docs/concepts/planning",
					"docs/concepts/planning/cascade-propagation",
					"docs/concepts/planning/source-freshness",
					"docs/concepts/planning/selection-and-staleness"
				]
			},
			"docs/concepts/snapshots",
			"docs/concepts/audits",
			{
				"label": "Rules",
				"collapsed": true,
				"items": [
					"docs/concepts/rules",
					"docs/concepts/rules/configuration-and-selection",
					"docs/concepts/rules/findings-and-exceptions",
					"docs/concepts/rules/execution-and-caching"
				]
			},
			"docs/concepts/testing",
			"docs/concepts/scenarios",
			"docs/concepts/selectors",
			"docs/concepts/column-lineage",
			"docs/concepts/diff"
		]
	},
	{
		"label": "Advanced Concepts",
		"items": [
			{
				"label": "Observability",
				"collapsed": true,
				"items": [
					"docs/concepts/observability",
					"docs/concepts/observability/sinks"
				]
			},
			{
				"label": "Declarations and Scopes",
				"collapsed": true,
				"items": [
					"docs/concepts/declaration-scopes",
					"docs/concepts/declaration-scopes/visibility",
					"docs/concepts/declaration-scopes/placement",
					"docs/concepts/declaration-scopes/explorer"
				]
			},
			{
				"label": "Custom Rules",
				"collapsed": true,
				"items": [
					"docs/concepts/rules/custom-rules/overview",
					"docs/concepts/rules/custom-rules/rule-context",
					"docs/concepts/rules/custom-rules/testing-and-determinism"
				]
			}
		]
	},
	{
		"label": "Python Nodes",
		"items": [
			"docs/concepts/python-nodes/overview",
			"docs/concepts/python-nodes/loaders",
			"docs/concepts/python-nodes/tasks",
			"docs/concepts/python-nodes/assets",
			"docs/concepts/python-nodes/checks",
			"docs/concepts/python-nodes/factories",
			"docs/concepts/python-nodes/providers",
			"docs/concepts/python-nodes/sql-references"
		]
	},
	{
		"label": "Virtual Environments (Alpha)",
		"items": [
			"docs/concepts/virtual-environments",
			"docs/concepts/virtual-environments/setup",
			"docs/concepts/virtual-environments/building",
			"docs/concepts/virtual-environments/promotion",
			"docs/concepts/virtual-environments/rollback",
			"docs/concepts/virtual-environments/adopt-detach",
			"docs/concepts/virtual-environments/clone",
			"docs/concepts/virtual-environments/diff",
			"docs/concepts/virtual-environments/reconcile",
			"docs/concepts/virtual-environments/locks",
			"docs/concepts/virtual-environments/janitor",
			"docs/concepts/virtual-environments/recovery"
		]
	},
	{
		"label": "Integrations",
		"items": [
			{
				"label": "Dagster",
				"collapsed": true,
				"items": [
					"docs/integrations/dagster",
					"docs/integrations/dagster-reference"
				]
			},
			"docs/integrations/rivers",
			"docs/integrations/dlt",
			"docs/integrations/ingestr"
		]
	},
	{
		"label": "CLI Reference",
		"items": [
			"docs/cli/init",
			"docs/cli/playground",
			"docs/cli/skills",
			"docs/cli/compile",
			"docs/cli/format",
			"docs/cli/contract",
			"docs/cli/scope",
			"docs/cli/rules",
			"docs/cli/plan",
			"docs/cli/build",
			"docs/cli/load",
			"docs/cli/seed",
			"docs/cli/test",
			"docs/cli/scenario",
			"docs/cli/audit",
			"docs/cli/freshness",
			"docs/cli/check",
			"docs/cli/clone",
			"docs/cli/diff",
			"docs/cli/lineage",
			"docs/cli/dag",
			"docs/cli/query",
			"docs/cli/debug",
			"docs/cli/janitor",
			"docs/cli/clean",
			"docs/cli/dbt",
			"docs/cli/state",
			"docs/cli/promote",
			"docs/cli/rollback",
			"docs/cli/reconcile"
		]
	}
];

export const redirects = {
	"/docs/concepts/rules/overview": "/docs/concepts/rules",
	"/docs/concepts/rules/custom-rules": "/docs/concepts/rules/custom-rules/overview"
};
