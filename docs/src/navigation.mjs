// Sidebar and redirects, first generated from the Mintlify docs.json.
export const sidebar = [
	{
		"label": "Getting Started",
		"items": [
			"index",
			"quickstart",
			"feature-comparison",
			"benchmarks"
		]
	},
	{
		"label": "dbt Compatibility",
		"items": [
			"concepts/dbt-compatibility/overview",
			"concepts/dbt-compatibility/selection",
			"concepts/dbt-compatibility/adding-sqlbuild-models"
		]
	},
	{
		"label": "Concepts",
		"items": [
			"concepts/project-configuration",
			"concepts/resource-identities",
			{
				"label": "Adapters",
				"collapsed": true,
				"items": [
					"concepts/adapters",
					"concepts/adapters/duckdb",
					"concepts/adapters/motherduck",
					"concepts/adapters/snowflake",
					"concepts/adapters/bigquery",
					"concepts/adapters/databricks",
					"concepts/adapters/postgres",
					"concepts/adapters/sqlserver"
				]
			},
			"concepts/sources",
			"concepts/seeds",
			{
				"label": "Models",
				"collapsed": true,
				"items": [
					"concepts/models",
					"concepts/models/materializations",
					"concepts/models/schemas",
					"concepts/models/type-enforcement",
					"concepts/models/contracts",
					"concepts/models/migrations",
					{
						"label": "Hooks",
						"collapsed": true,
						"items": [
							{
								"label": "Overview",
								"slug": "concepts/models/hooks"
							},
							"concepts/models/hooks/sql",
							"concepts/models/hooks/python"
						]
					},
					"concepts/models/configuration"
				]
			},
			{
				"label": "Enums and Constants",
				"collapsed": true,
				"items": [
					"concepts/enums",
					"concepts/constants",
					"concepts/constants/collections-and-rendering",
					"concepts/enums/model-contracts",
					"concepts/model-private-values"
				]
			},
			{
				"label": "Python Macros",
				"collapsed": true,
				"items": [
					"concepts/macros",
					"concepts/macros/composition-and-context"
				]
			},
			"concepts/interpolation",
			"concepts/functions",
			"concepts/incremental",
			{
				"label": "Planning and Change Detection",
				"collapsed": true,
				"items": [
					"concepts/planning",
					"concepts/planning/cascade-propagation",
					"concepts/planning/source-freshness",
					"concepts/planning/selection-and-staleness"
				]
			},
			"concepts/snapshots",
			"concepts/audits",
			{
				"label": "Rules",
				"collapsed": true,
				"items": [
					"concepts/rules",
					"concepts/rules/configuration-and-selection",
					"concepts/rules/findings-and-exceptions",
					"concepts/rules/execution-and-caching"
				]
			},
			"concepts/testing",
			"concepts/scenarios",
			"concepts/selectors",
			"concepts/column-lineage",
			"concepts/diff"
		]
	},
	{
		"label": "Advanced Concepts",
		"items": [
			{
				"label": "Observability",
				"collapsed": true,
				"items": [
					"concepts/observability",
					"concepts/observability/sinks"
				]
			},
			{
				"label": "Declarations and Scopes",
				"collapsed": true,
				"items": [
					"concepts/declaration-scopes",
					"concepts/declaration-scopes/visibility",
					"concepts/declaration-scopes/placement",
					"concepts/declaration-scopes/explorer"
				]
			},
			{
				"label": "Custom Rules",
				"collapsed": true,
				"items": [
					"concepts/rules/custom-rules/overview",
					"concepts/rules/custom-rules/rule-context",
					"concepts/rules/custom-rules/testing-and-determinism"
				]
			}
		]
	},
	{
		"label": "Python Nodes",
		"items": [
			"concepts/python-nodes/overview",
			"concepts/python-nodes/loaders",
			"concepts/python-nodes/tasks",
			"concepts/python-nodes/assets",
			"concepts/python-nodes/checks",
			"concepts/python-nodes/factories",
			"concepts/python-nodes/providers",
			"concepts/python-nodes/sql-references"
		]
	},
	{
		"label": "Virtual Environments (Alpha)",
		"items": [
			"concepts/virtual-environments",
			"concepts/virtual-environments/setup",
			"concepts/virtual-environments/building",
			"concepts/virtual-environments/promotion",
			"concepts/virtual-environments/rollback",
			"concepts/virtual-environments/adopt-detach",
			"concepts/virtual-environments/clone",
			"concepts/virtual-environments/diff",
			"concepts/virtual-environments/reconcile",
			"concepts/virtual-environments/locks",
			"concepts/virtual-environments/janitor",
			"concepts/virtual-environments/recovery"
		]
	},
	{
		"label": "Integrations",
		"items": [
			{
				"label": "Dagster",
				"collapsed": true,
				"items": [
					"integrations/dagster",
					"integrations/dagster-reference"
				]
			},
			"integrations/rivers",
			"integrations/dlt",
			"integrations/ingestr"
		]
	},
	{
		"label": "CLI Reference",
		"items": [
			"cli/init",
			"cli/playground",
			"cli/skills",
			"cli/compile",
			"cli/format",
			"cli/contract",
			"cli/scope",
			"cli/rules",
			"cli/plan",
			"cli/build",
			"cli/load",
			"cli/seed",
			"cli/test",
			"cli/scenario",
			"cli/audit",
			"cli/freshness",
			"cli/check",
			"cli/clone",
			"cli/diff",
			"cli/lineage",
			"cli/dag",
			"cli/query",
			"cli/debug",
			"cli/janitor",
			"cli/clean",
			"cli/dbt",
			"cli/state",
			"cli/promote",
			"cli/rollback",
			"cli/reconcile"
		]
	}
];

export const redirects = {
	"/concepts/rules/overview": "/concepts/rules",
	"/concepts/rules/custom-rules": "/concepts/rules/custom-rules/overview"
};
