# What we are building on this repository

Companion to [`README.md`](README.md). This records the design we are building on top of
this fork, the decisions taken, and the findings about **this codebase** that each decision
rests on. Every finding carries a `file:line` so it can be re-checked rather than
re-derived; anything without one is an opinion.

Findings were established against commit `7a4849c`. The fork tracks upstream, so re-verify
line numbers before relying on them.

Consumer-side detail is deliberately absent — this describes the integration contract, not
the CMS's schema or content.

## The objective

A CMS authoring health content needs every claim traceable to a source. Robots read source
artifacts, emit the facts they contain as RDF, and the CMS authors content from those facts
with claim-level provenance.

That splits into four things this repository does: hold the artifacts with their rights
metadata, dispatch robots against them, validate the facts they return, and make those
facts queryable by concept. It does **not** generate anything — see "What this repository
does not do" below.

## Decisions

### Authority

**This repository is authoritative for facts, never for identity.** It owns
bibliographic metadata and artifacts. The CMS owns which works are the same work, whether
a human has checked a record, and what cites what.

Identity stays out because the deduplication engine is not ready by its own account (F6),
and a wrong merge in health content is a clinical error rather than a tidiness bug. We
therefore configure `trusted_unique_identifier_types` so identity is decided by identifier
and the fuzzy path is never reached (F7).

The consumer holds a stable, opaque alias identifier per source record, sent as an
`OtherIdentifier` alongside native `doi`/`pmid`/`pmcid`. The alias is not derived from any
mutable key: identifiers here are append-only (F5), so an alias that can change would
strand a stale one.

### Artifacts

Artifacts live here, not in the CMS, so ingestion has to exist (F1). Storage is
S3-compatible via the Minio client, which needs the TLS and region fields to work at all
(F2).

Only what a rights basis justifies is stored. Open-access files with a recorded licence are
stored normally; anything held under a text-and-data-mining basis is stored `HIDDEN` —
*"not visible, but may be passed to data mining processes"* — and is never served onward. A
fetcher that cannot determine `is_oa` skips and logs rather than writing a null.

### Robots

Two robots, in a chain that terminates by construction:

1. **Fetcher** — no model. Fetches the artifact at the address the CMS already holds,
   honours machine-readable TDM reservations, uploads it, emits `full_text`. Built first
   because its failures are visible: either you got the right document or you didn't.

   It does **not** resolve from an identifier. Nothing here resolves anything — there is no
   Unpaywall, OpenAlex or Crossref client in this repository, and the OpenAlex references in
   the SDK document schema shape, not an integration. An identifier-driven fetcher would be
   a resolver built from scratch, and against the CMS's real corpus it would reach 4 sources
   of 44 where fetching a known URL reaches 38.

   **Every artifact is a PDF**; HTML pages are exported to PDF at fetch time, so `mime_type`
   is uniformly `application/pdf`. `mime_type` is an unconstrained string, so this is a
   choice we make rather than a limit the schema imposes: one artifact format, one extractor
   path, and `page_location` citations available everywhere. The costs are that a renderer
   lives in the robot image — so the fetcher is no longer deterministic byte-for-byte — and
   that `sha256_checksum` no longer detects that a page changed, since a renderer upgrade
   moves it too. The fetcher therefore also records the checksum of the source HTML it
   rendered from.
2. **Extractor** — model-driven. Triggered by a `full_text` arriving, reads the artifact,
   emits `linked_data`. Cannot self-trigger, because its output is not a `full_text` (F8).

The extractor emits `linked_data` directly rather than staging through `raw`, because
robots are blocked from creating `raw` (F9).

Neither robot lives in this repository. They are separate deployments holding their own
HMAC credentials.

### Facts

Facts are `linked_data` enhancements — JSON-LD validated against a fetched ontology with
SHACL (F10). Two vocabularies:

- **`evrepo`** for primary literature, whose `Investigation → Finding → EffectEstimate`
  shape fits trials and systematic reviews.
- **A vocabulary we publish** for guidance statements — recommendation, population,
  condition, strength, issuing body, region. Most of the corpus this serves is public-health
  guidance rather than primary literature, and a guidance statement is not a finding with an
  effect estimate. `vocabulary_uri` is per-enhancement, so both coexist with no new
  machinery.

The second requires the shapes change in F11. Without it our facts pass validation
*vacuously* and we keep the plumbing while losing the gate.

### Extracted works

Extraction produces references, and a robot cannot create a reference (F12). Extracted
works therefore reach this repository through the import API, driven by a separate
consumer-side process rather than by the robot — a lease-holding process must not block on
an asynchronous import.

A child arriving without a trusted identifier is **not** imported. It stays on the consumer
side as an unreviewed candidate, because a reference with no identifiers falls through to
the fuzzy matcher (F7) and that is the outcome the authority split exists to prevent.

### Reading

The CMS queries the search API live for discovery — source lookup, evidence search, fact
retrieval by concept. Everything on its own critical path reads a local projection instead:
a publish-time gate and a content build must never depend on a network call.

## What this repository does not do

- **It does not extract.** There is no PDF parser and no model client:
  `grep -rilE "grobid|pypdf|pdfminer|fitz|anystyle|openai|anthropic|litellm"` over `*.py`
  and `*.toml` returns nothing. The only parser is `parsers/eppi_parser.py`, which converts
  one structured format to another. All extraction is robot-side code.
- **It does not hold the citation graph.** `reference_association` is unusable for it (F4).
- **It does not generate content.** There is no enhancement type for an authored article;
  generation output leaves this system entirely.
- **It does not decide whether a fact is true.** SHACL checks shape, not truth. Validation
  here is a structural gate, not editorial review, and the human check happens consumer-side.

## Findings

### F1 — There is no way to put a file in, but the primitives exist

No upload endpoint: `app/domain/references/routes.py` has no file `post`. Excluding the
model, the ES exclusion list and the read-time signer, `grep -rn 'full_text\|FULL_TEXT' app/`
returns one hit — the container enum at `app/persistence/blob/models.py:32`.

The domain model requires `blob: BlobStorageFile`
(`app/domain/references/models/models.py:313`) while the SDK model carries `file_url`, and
`enhancement_from_sdk` is a plain `model_validate` over the dumped SDK dict
(`app/domain/references/services/anti_corruption_service.py:154-175`) — nothing fetches
`file_url`, nothing constructs a `BlobStorageFile`. An inbound full-text enhancement fails
validation on the missing `blob`.

Import does not help: `ImportBatchIn` is a `storage_url` the caller hosts, and the JSONL is
`ReferenceFileInput` — identifiers and enhancements only
(`libs/sdk/src/destiny_sdk/references.py:55-69`). Metadata in, no bytes.

What already exists: `BlobSignedUrlType.UPLOAD` (`app/persistence/blob/models.py:14-18`)
with `presigned_put_object` wired to it (`app/persistence/blob/clients/minio.py:117-122`);
`BlobRepository.destination()` (`app/persistence/blob/repository.py:113-131`), whose
docstring reads *"Reserve a BlobStorageFile destination without performing any I/O. Useful
for pre-allocating a location that will be written to later"*; and the two-phase
presigned-upload pattern already in production for robot result files, signed `UPLOAD` in
four places (`anti_corruption_service.py:207-291`). Only the caller is missing.

### F2 — The Minio client could not produce an https URL

`FullTextEnhancement.file_url` is validated as https
(`libs/sdk/src/destiny_sdk/enhancements.py:536-542`) and the repository populates it by
signing the blob at read time (`anti_corruption_service.py:131`), but the client hardcoded
`secure=False`. Every read of a full-text enhancement raised `DomainToSDKError`, and
presigned URLs carrying a signature and file bytes travelled unencrypted.

`MinioConfig` was `host`, `access_key`, `secret_key` only — no TLS flag, no region, no
session token, so static long-lived credentials rather than a workload identity. Addressed
by the `secure`/`region` change; the credential question is open.

Note `BlobBackendConfig` requires a name for **every** `BlobContainer`, and there are two —
`OPERATIONS` and `FULL_TEXTS` (`app/persistence/blob/models.py:28-33`). `mime_type` is a
free string defaulting to `application/pdf` (`enhancements.py:560-563`), so images store
fine.

### F3 — Import storage URLs are restricted by hostname

`allowed_import_domains` defaults to `["blob.core.windows.net"]`; a URL whose hostname does
not match is rejected with **403**, and an empty list disables the check
(`app/core/config.py:576-583`). An S3-hosted import batch fails with an error that explains
nothing until this is set.

### F4 — `reference_association` is a write-only stub

It is in `EXCLUDED_ENHANCEMENT_TYPES` (`app/domain/references/models/es.py:38-41`) —
excluded from Elasticsearch, with a `clean()` guard raising
`RuntimeError("This should never happen")` if one reaches the indexer (`:110-122`). And
`associated_reference_ids` appears **nowhere** in `app/`, only in the SDK model
(`libs/sdk/src/destiny_sdk/enhancements.py:454`) and its unit tests: no resolution of
external identifiers, no creation of references that do not exist.

So an association stores, and then nothing reads it, indexes it, or percolates on it.
`bibliographic`, by contrast, is indexed and dedupable.

### F5 — The repository is append-only

`grep '\.delete('` across every `app/domain/*/routes.py` returns **zero** results. No
delete endpoint for references, identifiers or enhancements. Provenance is traceable via
`source`, `robot_version` and `derived_from`
(`libs/sdk/src/destiny_sdk/enhancements.py:689-702`) but nothing is removable.

Retraction is in-band and differs by type, in opposite directions:

- **Annotations** — a scheme is assumed wholly represented in one enhancement, and a label
  missing from a later one is *treated as removed*
  (`app/domain/references/models/projections.py:91-99`). Omission retracts.
- **Bibliographic** — merged field by field with a non-null fallback (`:64-79`, ordered by
  `__priority_sorted_enhancements` at `:157-191`, on-canonical then most recent). Emitting
  `title=None` leaves the old title standing. Omission does **not** retract.

A robot emitting both must not share retraction logic between them.

### F6 — Deduplication is fuzzy and self-declared unready

`ReferenceESRepository.search_for_candidate_canonicals`
(`app/domain/references/repository.py:308-337`), verbatim: *"Fuzzy match candidate
fingerprints to existing references. This is a high-recall search strategy. NOT
TESTED/EVALUATED. Thrown together as a proof of concept, this must be polished and evaluated
before use."* Fuzzy title at 50% of terms, author `dis_max`, publication year ±1.

`DuplicateDetermination` carries `UNRESOLVED`, `DECOUPLED` and `UNSEARCHABLE`
(`app/domain/references/models/models.py:110-121`), meaning a human must look — and no queue
or UI surfaces them.

Robots read the **flattened** view: `_get_jsonl_deduplicated_references` builds "JSONL
strings for deduplicated (flattened) references by id"
(`app/domain/references/service.py:383-393`). A wrong merge therefore feeds a model a
chimera of two papers and attributes the output to the canonical.

### F7 — Deterministic deduplication is a config setting, not a patch

`trusted_unique_identifier_types` (`app/core/config.py:590-597`): *"used to shortcut
deduplication. If empty, shortcutting is essentially feature-flagged off."* Default empty.

`process_reference_duplicate_decision` calls the shortcut first and **returns early** if it
produces a decision (`app/domain/references/service.py:1045-1056`), so the fuzzy path is
never reached. The logic (`app/domain/references/services/deduplication_service.py:455-500`):

- no identifiers at all → falls through to fuzzy;
- trusted identifiers present, no existing match → `CANONICAL`, ES dedup skipped entirely;
- identifiers present but none trusted → falls through to fuzzy.

The filter tests `identifier_type` only (`:471`), so trusting `other` trusts every
other-identifier regardless of its name. Acceptable single-tenant; narrow it if third-party
data is ever imported.

### F8 — The percolated document carries a changeset

`RobotAutomationPercolationDocument` (`app/domain/references/models/es.py:423-458`) holds
the percolator query plus **two** reference contexts, both nesting identifiers and the full
enhancement list (`:179-190`): `reference` (current state) and `changeset` (what just
changed).

That second field is what makes non-self-triggering queries expressible. `skip_robot_id` is
a single UUID and matching it only logs a warning
(`app/domain/references/service.py:1256-1262`), with the comment *"this is likely a problem
in the percolation query"* — so it stops A→A and not A→B→A. Matching on the changeset
instead makes the chain terminate structurally. Any third robot must be checked against
this property by hand.

### F9 — Robots cannot create `raw` enhancements

Stated in the docstring — *"These enhancements cannot be created by robots"*
(`libs/sdk/src/destiny_sdk/enhancements.py:610-618`) — and enforced: a `raw` enhancement in
a robot result becomes a `LinkedRobotError`, *"Robot returned illegal raw enhancement type"*
(`app/domain/references/models/validators.py:304-312`).

So the `raw → linked_data` mapping pattern that `LinkedDataEnhancement`'s docstring
describes applies to **imported** raw data, which is why `eppi_parser.py` emits it. Robot
work goes straight to `linked_data`.

### F10 — Linked data is the semantic layer and the only real validation gate

`LinkedDataEnhancement` (`libs/sdk/src/destiny_sdk/enhancements.py:470-519`) carries a
`vocabulary_uri` and JSON-LD `data` with a mandatory `@context`.
`LinkedDataValidationService` (`app/domain/references/services/linked_data_validation_service.py`)
expands the JSON-LD, converts it to an `rdflib.Graph`, and validates with `pyshacl`, merging
the fetched ontology so `sh:class` constraints resolve. Vocabularies are fetched by URI and
cached indefinitely, version being part of the URI
(`app/external/vocabulary/client.py`).

Its presence in `EXCLUDED_ENHANCEMENT_TYPES` denies it only a *nested* enhancement document.
It gets three dedicated top-level search fields instead (`es.py:319-334`), populated through
`ReferenceSynchronizer._to_indexable`
(`app/domain/references/services/synchronizer_service.py:58-65`): `linked_data_concepts`
(concept URIs), `linked_data_labels` (SKOS `prefLabel`, text-searchable), and
`linked_data_evaluated_properties`.

Everywhere else — annotations, bibliographic, full text — validation is schema-only. This is
the one place a robot's output is checked structurally against an ontology.

### F11 — SHACL shapes are hardcoded, so a second vocabulary conforms vacuously

`_SHAPES_PATH` is `project_root / "app" / "static" / "evrepo-core-shapes.ttl"`
(`linked_data_validation_service.py:15`), parsed behind `@functools.cache` and bound in
`__init__` (`:19-38`). The **ontology** is fetched per enhancement; the **shapes** are not.

Every bundled shape is `sh:targetClass evrepo:…`, and SHACL validates by target class. JSON-LD
built from another vocabulary's classes therefore has no target nodes and **conforms
trivially** — the non-empty-graph check still applies, the structural check does not.

The change: make shapes fetchable by URI alongside the ontology, or make the path
configurable. Without it, publishing our own vocabulary keeps the plumbing and silently
discards the gate in F10.

### F12 — A robot cannot create a reference

`EnhancementResultEntry = Enhancement | LinkedRobotError`
(`libs/sdk/src/destiny_sdk/robots.py:93-96`), and `Enhancement` requires a `reference_id`
naming an existing reference (`libs/sdk/src/destiny_sdk/enhancements.py:686-688`). A result
can only attach enhancements to references that were in the batch.

Extraction produces references, so writing them needs the import API — an import record plus
a batch pointing at a JSONL the caller hosts
(`libs/sdk/src/destiny_sdk/imports.py:124-138`) — on a different auth surface and an
asynchronous lifecycle (`CREATED → STARTED → COMPLETED | PARTIALLY_FAILED | FAILED`,
`:26-38`).

### F13 — Robots poll; they do not subscribe

`RobotClient.poll_robot_enhancement_batch()` → `send_robot_enhancement_batch_result()` →
`renew_robot_enhancement_batch_lease()` (`libs/sdk/src/destiny_sdk/client.py`). Work arrives
as JSONL over a signed blob URL; results return the same way. `RobotAutomation` is a
percolator query, so "subscription" means a stored query matched against incoming
references — not a push.

`Robot` is `name`, `description`, `owner`, `client_secret` with `extra="forbid"`
(`app/domain/robots/models/models.py:8-29`). The batch docstring says references arrive "as
required by the robot" (`libs/sdk/src/destiny_sdk/robots.py:130-145`) but no field expresses
that requirement, so the input contract is out of band.

### F14 — Batch size and lease are both caller-chosen

`max_pending_enhancements_batch_size` defaults to **10000** (`app/core/config.py:448`),
which is also the poll route's default `limit` (`app/domain/references/routes.py:522-527`);
a larger request is silently clamped with a warning (`:541-546`).

The lease is **not** fixed at ten minutes — `PT10M` is only the default
(`app/core/config.py:540-546`) and the route takes `lease` as an ISO-8601 duration
(`routes.py:528-534`). There is **no maximum**: the value flows to
`apply_positive_timedelta(lease_duration)` (`app/domain/references/service.py:1127`), which
only requires it to be positive. Renewal exists (`:1159-1168`) and results after expiry are
rejected 422.

So the constraint is that the duration is chosen *before* inference starts. Small batch with
a generous lease needs no heartbeat but holds work hostage if the robot dies; a large batch
needs a renewal heartbeat concurrent with inference. Nothing here is cron-shaped: a robot is
a process holding a lease.

### F15 — The search API is two-stage and returns provenance

`GET /references/search/` (`app/domain/references/routes.py:285-359`) takes a Lucene query
string over title/abstract/authors, `AnnotationFilter` entries with `scheme`, optional
`label` and a minimum score (`libs/sdk/src/destiny_sdk/search.py:28-44`), and a
publication-year range. Paged 20 at a time to a hard 10,000 ceiling.

Elasticsearch returns hit ids, then `get_deduplicated_references` hydrates full `Reference`
objects from Postgres in the same request (`routes.py:343-357`). So results carry
per-enhancement `source`, `robot_version`, `derived_from` and `visibility` with no second
round trip — the ES document itself is lean and holds no enhancements (`es.py:367-381`).

Hydration returns the flattened view (F6); with deduplication shortcut by identifier that is
a no-op, which is a useful consistency check.

### F16 — Annotation shape is narrow, and only positive booleans are searchable

`AnnotationType` is `BOOLEAN | SCORE` only
(`libs/sdk/src/destiny_sdk/enhancements.py:263-276`). Both classes carry a free-form
`data: dict` (`:307`, `:330`), but `AnnotationDocument` indexes only `scheme`, `label`,
`annotation_type` and `value` (`app/domain/references/models/es.py:83-89`) — `score` and
`data` are **not** indexed, so anything placed there is invisible to search and to
percolation.

Only *positive boolean* annotations reach the searchable `annotations` keyword field
(`__positive_boolean_annotations`, `projections.py:113`). A pure `ScoreAnnotation` appears in
`evaluated_schemes` and nowhere else, except `inclusion_destiny` — a hardcoded `ScaledFloat`
fed by a hardcoded lookup for `("inclusion:destiny", None)` (`es.py:305`,
`projections.py:115-117`). The search schema carries upstream project semantics.

Practical rule: emit booleans with confidence in `score`.

### F17 — Nothing here plays the role of a confirmation flag

Enhancements carry good provenance but validation is schema-only, never truth. The closest
staging state is `Visibility.HIDDEN` — *"is not visible, but may be passed to data mining
processes"* (`libs/sdk/src/destiny_sdk/visibility.py:18-19`).

With F5 there is no undo, so the human gate has to sit **before** the write, on the consumer
side. Nothing in this repository can be relied on to provide it.

### F18 — Deployment is Azure-only, so the manifests are ours

`infra/` is Terraform against Azure — `azurerm_container_app`, `azurerm_container_app_job`,
`azurerm_servicebus_namespace`, `azurerm_postgresql_flexible_server`,
`azurerm_cdn_frontdoor_*`, `azurerm_storage_account` — wired to Terraform Cloud org
`destiny-evidence` (`infra/app/terraform.tf:5-7`). No Kubernetes manifests, no Helm chart,
no Kustomize; compose is dev-only.

`Settings.azure_application_id: str` has no default (`app/core/config.py:404`) and
`auth_provider` defaults to `"azure"` (`:395`). Keycloak is a supported path (`:407-436`)
behind an opt-in compose profile. The auth layer is generic OIDC underneath —
`KeycloakJwtAuth.__init__` takes a JWKS base URL, realm, audience and optional issuer
(`app/api/auth.py:437-453`), `AzureJwtAuth` the same shape with Microsoft endpoints
(`:280-339`) — and `AuthScope` (`:59-68`) maps onto any provider's custom scopes. Note
`cli/auth.py:46-55` carries its own client-side flow, so adding a provider is two-sided.
