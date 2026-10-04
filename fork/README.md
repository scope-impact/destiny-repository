# Scope Impact fork

This is a fork of [`destiny-evidence/destiny-repository`](https://github.com/destiny-evidence/destiny-repository),
self-hosted to serve a Scope Impact content management system.

**We do not contribute back.** Every change here is a delta we carry indefinitely, and
upstream is active, so the metric that matters is **merge cost** rather than upstream
acceptability.

**Prefer additive changes.** New files and new subclasses survive an upstream merge; edits
to existing lines conflict. Where a change can be a new module rather than surgery on an
existing one, it should be.

What we carry is not listed here — `git log` and the diff against upstream already say
that, and a hand-maintained ledger would only drift out of agreement with them. This
directory holds what a diff cannot express: why the fork exists, what the deployment needs,
what we deliberately leave alone, and what is still undecided.

`fork/` is a path upstream will never have, so nothing in here ever conflicts. It is not
registered in `docs/index.rst` for the same reason.

## What we use this for

The CMS authors health content and needs every claim traceable to a source. This
repository is the store of record for **bibliographic facts and source artifacts**, and the
dispatch layer for robots that read those artifacts and emit facts as RDF. The CMS keeps
source identity, editorial judgement and the citation graph on its own side.

Concretely, we use six of the eight enhancement types — `bibliographic`, `abstract`,
`annotation`, `location`, `full_text`, `linked_data` — the search API, the import API, and
robot dispatch. We do not use `reference_association` (excluded from indexing, and its
identifiers are never resolved) and we have deduplication shortcut to identifiers rather
than the Elasticsearch candidate search.

## Deployment configuration — no code

| Setting | Value | Why |
|---|---|---|
| `trusted_unique_identifier_types` | `{doi, pm_id, other}` | This is how deduplication is disabled for our data. `shortcut_deduplication_using_identifiers` runs first and returns early, so the Elasticsearch candidate search — whose own docstring reads *"NOT TESTED/EVALUATED. Thrown together as a proof of concept, this must be polished and evaluated before use"* — is never reached for a reference carrying one of these. Note the filter tests `identifier_type` only, so trusting `other` trusts every other-identifier regardless of its name. Acceptable single-tenant; narrow it if third-party data is ever imported. |
| `allowed_import_domains` | + our S3 hostname | Defaults to `["blob.core.windows.net"]`. We host the import JSONL on S3, and a hostname miss is a bare 403 that explains nothing. |
| `auth_provider` | `cognito` (delta 3) | See above. |
| blob backend | `MinioConfig` at S3, `secure=true`, `region` set | Both containers must be named — `OPERATIONS` and `FULL_TEXTS`. |
| Elasticsearch | exactly one auth method | More than one, or none, fails validation at startup. |

**Workloads to run:** Postgres 17, Elasticsearch, RabbitMQ, API, worker. Not MinIO (S3
instead), not Keycloak (Cognito), not Kibana, not `ui` (the CMS is the UI), and
`scheduler` only if timed automations are wanted. `infra/` is Azure Terraform, so the
Kubernetes manifests are ours to author — there is nothing to port.

Elasticsearch is not optional: `RobotAutomation` *is* a percolator query, and the search
projections are Elasticsearch-only. It carries the operational weight here — heap,
snapshots, index lifecycle — and note that `repair_robot_automation_percolation_index`
exists because the percolation index can drift.

## Deliberately unchanged

- **No extraction code belongs in this repository.** It has none and needs none: no PDF
  parser, no model client. Our robots are separate deployments that poll, read the
  artifact, and return enhancements.
- **`reference_association`** stays as it is. The citation graph lives in the CMS, because
  this type is excluded from indexing and `associated_reference_ids` is never resolved
  anywhere in `app/`.
- **The deduplication engine** is not patched, only bypassed by configuration.
- **`raw` enhancements.** Robots are blocked from creating them by design, so our
  extractor emits `linked_data` directly rather than staging through `raw`.

## Open decisions

- **How we track upstream.** Pin to a tag and upgrade deliberately, or track `main` and
  absorb merges as they come. Undecided, and it is the decision that most affects the cost
  of everything in the ledger.
- **Where the access basis for each stored artifact is recorded.** The schema offers
  `is_oa` and `license` and nothing else, so *"held under a text-and-data-mining basis via
  institutional access"* has nowhere to live here. Likely a field on the CMS side.
- **The vocabulary itself** — classes for guidance statements rather than trial findings.
  This is modelling work, it is on the critical path, and it is not code.

## Design

[`DESIGN.md`](DESIGN.md) records what we are building on this repository, the decisions
behind it, and the findings about this codebase that each decision rests on — including
the changes this fork needs and why.
