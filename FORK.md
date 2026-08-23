# Scope Impact fork

This is a fork of [`destiny-evidence/destiny-repository`](https://github.com/destiny-evidence/destiny-repository),
self-hosted to serve [Halla Health](https://github.com/scope-impact/halla-health-content).

**We do not contribute back.** Every change here is a delta we carry indefinitely, and
upstream is active, so the metric that matters is **merge cost** rather than upstream
acceptability. Two consequences shape everything below:

1. **Prefer additive changes.** New files and new subclasses survive an upstream merge;
   edits to existing lines conflict. Where a change can be a new module rather than
   surgery on an existing one, it should be.
2. **Keep this ledger current.** After every upstream merge, walk the table below and
   confirm each delta still applies. A delta that silently disappears in a conflict
   resolution is a defect that will surface in production, not in review.

This file lives at the repository root deliberately: upstream will never have this path,
so it never conflicts. It is not registered in `docs/index.rst` for the same reason.

## What we use this for

Halla Health authors consumer health content and needs its claims traceable to sources.
This repository is the store of record for **bibliographic facts and source artifacts**,
and the dispatch layer for robots that read those artifacts and emit facts as RDF. Halla
keeps identity, editorial judgement and the citation graph on its own side.

Concretely, we use six of the eight enhancement types — `bibliographic`, `abstract`,
`annotation`, `location`, `full_text`, `linked_data` — the search API, the import API, and
robot dispatch. We do not use `reference_association` (excluded from indexing, and its
identifiers are never resolved) and we have deduplication shortcut to identifiers rather
than the Elasticsearch candidate search.

## Delta ledger

| # | Status | Change | Files | Why |
|---|---|---|---|---|
| 1 | **open — PR #1** | `MinioConfig` gains `secure` (default true) and `region`, threaded into `Minio(...)` | `app/core/config.py`, `app/persistence/blob/clients/minio.py`, `docker-compose.yml`, `.env.example` | `secure=False` was hardcoded while `FullTextEnhancement.file_url` is validated as https, so every read of a full text enhancement raised `DomainToSDKError`. Also stopped presigned URLs travelling unencrypted. |
| 2 | planned | SHACL shapes fetchable by URI, or a configurable shapes path | `app/domain/references/services/linked_data_validation_service.py` | `_SHAPES_PATH` is hardcoded to `evrepo-core-shapes.ttl` and SHACL validates by target class. Data built from any other vocabulary has no target nodes and **conforms vacuously** — the machinery runs and validates nothing, silently. We publish our own vocabulary, so without this we lose the only place in the platform where robot output is checked beyond its schema. |
| 3 | planned | A Cognito auth strategy: a `JwtAuth` subclass, a `"cognito"` arm on the `auth_provider` Literal, and a client-side flow | `app/api/auth.py`, `app/core/config.py`, `cli/auth.py` | We already operate a Cognito pool; standing up Keycloak solely so two machine clients can get tokens is a stateful service and a second identity system for no gain. The auth layer is generic OIDC underneath — JWKS fetch, issuer and audience checks — so this generalises two hardcoded providers into three. **Two-sided:** `cli/auth.py` carries its own `KeycloakAuthCodeFlow`, so robot registration needs the client arm too. Write the strategy as a new module, not as surgery on `auth.py`. |
| 4 | planned | Full-text ingestion: an SDK→domain converter, a reserve-and-presign endpoint, a confirm endpoint, checksum and byte-size verification | `app/domain/references/services/anti_corruption_service.py`, `app/domain/references/routes.py` | There is no way to put a file into the repository. `enhancement_from_sdk` is a plain `model_validate`, so an inbound `FullTextEnhancement` fails on the missing `blob`. The primitives are all shipped and in use for robot result files — `BlobSignedUrlType.UPLOAD`, `presigned_put_object`, `BlobRepository.destination()` — only the caller is missing. Both `sha256_checksum` and `byte_size` already promise in their docstrings that they are verified on import; that code does not exist. |

## Deployment configuration — no code

| Setting | Value | Why |
|---|---|---|
| `trusted_unique_identifier_types` | `{doi, pm_id, other}` | This is how deduplication is disabled for our data. `shortcut_deduplication_using_identifiers` runs first and returns early, so the Elasticsearch candidate search — whose own docstring reads *"NOT TESTED/EVALUATED. Thrown together as a proof of concept, this must be polished and evaluated before use"* — is never reached for a reference carrying one of these. Note the filter tests `identifier_type` only, so trusting `other` trusts every other-identifier regardless of its name. Acceptable single-tenant; narrow it if third-party data is ever imported. |
| `allowed_import_domains` | + our S3 hostname | Defaults to `["blob.core.windows.net"]`. We host the import JSONL on S3, and a hostname miss is a bare 403 that explains nothing. |
| `auth_provider` | `cognito` (delta 3) | See above. |
| blob backend | `MinioConfig` at S3, `secure=true`, `region` set | Both containers must be named — `OPERATIONS` and `FULL_TEXTS`. |
| Elasticsearch | exactly one auth method | More than one, or none, fails validation at startup. |

**Workloads to run:** Postgres 17, Elasticsearch, RabbitMQ, API, worker. Not MinIO (S3
instead), not Keycloak (Cognito), not Kibana, not `ui` (Halla Studio is the UI), and
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
- **`reference_association`** stays as it is. The citation graph lives in Halla, because
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
  institutional access"* has nowhere to live here. Likely a Halla-side field.
- **The vocabulary itself** — classes for guidance statements rather than trial findings.
  This is modelling work, it is on the critical path, and it is not code.

## Where the full design lives

The decisions behind all of the above, with the findings each rests on, are recorded in
the Halla Health repository at `dhf/architecture/DESTINY-Robot-Exploration.md`. That
document is the reasoning; this file is only the ledger of what we change here.
