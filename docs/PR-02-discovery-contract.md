# PR-02 — Discovery and questions contract

Status: Implementation proposed for review.

## Boundaries

Offline filesystem-only scanning. RDL files are identified by .rdl/.rds/.rsd/.rptproj, X++ by .xpp/.axreport; generic XML is a candidate, not automatically a Dynamics RDP artifact. No XML parsing, X++ semantic analysis, SQL connection, report rendering, or schema upgrade in this PR.

## Inventory format

`schema_version=1`, `mode=read-only`, sorted `files` keys with kind, extension, size, SHA-256; counts for rdl/rdp/candidate; warnings; removed files compared to optional prior index; stats indicating matching content digests.

Incremental reuse means *logical classification reuse* when SHA-256 matches. Every included file is rehashed on each run to avoid relying on timestamp/size alone; performance optimization is intentionally limited in PR-02.

## Safety and failure semantics

Directory symlinks are not traversed, file symlinks skipped; common generated folders skipped; maximum 10,000 candidates and 8 MiB per file; oversize files produce warnings, not reports of comprehensive coverage. Scan errors produce warnings. Output to stdout only, never writes to target project. No file content appears in JSON except hashes and relative file names; filenames can still be sensitive and must be kept local.

## Wizard

JSON-based questions run on a previously saved index. Target technology is *suggested* by counts; report server version, Dynamics version, language preference and Dev/Test authorization remain unverified and must not be invented. This is a noninteractive machine-readable wizard; no UI is implemented yet.

## Acceptance

Python standard-library unit tests, Python 3.11+/Windows/Linux CI, previous PR-01 tests unchanged, read-only workspace guarantees, no authenticated connections.
