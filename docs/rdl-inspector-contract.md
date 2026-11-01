# Read-only RDL Semantic Inspector

This wave adds metadata inspection alongside PR-03 validation. It does not change the validator, hook, reviewer, rule catalog or Dynamics RDP workflow. Python 3.11+, standard library only. No runtime dependencies, MCP server, generator, edit planner, RDL writer, connection, rendering or deployment.

## Inspiration and independent implementation

Reviewed [rdl-mcp README](https://github.com/bethmaloney/rdl-mcp/blob/ed2b98125b0e4ae60e2e4b7002776d62df6bfaf5/README.md) and [reader.py](https://github.com/bethmaloney/rdl-mcp/blob/ed2b98125b0e4ae60e2e4b7002776d62df6bfaf5/rdl_mcp/reader.py) at `ed2b98125b0e4ae60e2e4b7002776d62df6bfaf5`. The useful idea is a small JSON view of report semantics. That reader returns queries, literal values and expressions and selects the first Tablix for columns. This implementation is independently written: no copied source, dependency, runtime integration or editing tools. It uses a metadata allowlist, all Tablix IDs, explicit omissions and resource bounds.

Basis: Microsoft [Tablix](https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/e42fb86e-799a-4202-8845-ac38831efccb), [body columns](https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/8dc4048c-caa2-4dbd-991c-d1645a0954b3) and [CellContents.ColSpan](https://learn.microsoft.com/en-us/openspecs/sql_server_protocols/ms-rdl/3ffb0387-2dd7-4b21-b36d-6df8fd0a0887). XML body column order does not prove rendered/group column order.

## Interfaces

All five Python functions in `scripts.rdl_inspect` accept a local file path and return a JSON-serializable dictionary. Invalid/unsafe input raises `InspectionError` with a fixed code; filesystem/parser details are suppressed. CLI: `python scripts/rdl_inspect.py OPERATION --file PATH [OPTIONS]`. Every successful or failed invocation emits one ASCII-escaped JSON document to stdout, except `--help`, which prints usage. Diagnostics never echo file names or XML excerpts.

| Operation | Data | Options beyond `--file` |
|---|---|---|
| `describe_report` | dataset, parameter, Tablix, XML body-column, section and legacy-region counts | none |
| `list_datasets` | IDs/names, field counts, bounded field names/data fields and calculated flags, embedded/shared/absent query kind, command type enum and data source identifier | `offset=0`, `limit=50`, `field_limit=20` |
| `list_parameters` | IDs/names, type enum, nullable/multi-value/hidden flags, presence of defaults and valid values | `offset=0`, `limit=50` |
| `list_tablix` | IDs/names, parent Tablix ID, explicit dataset identifier, direct body column/row counts and LTR/RTL enum | `offset=0`, `limit=50` |
| `list_columns` | selected Tablix ID, binding coverage, body columns with one-based index, literal size width and bounded cell summaries | required `tablix_id`, `offset=0`, `limit=50` |

CLI options use hyphens (`--field-limit`, `--tablix-id`). IDs are document order and distinct even for duplicate/missing names. They are stable only for an unchanged file; offsets likewise assume an unchanged input. No filename or source hash is returned. Dataset references are explicit declarations only; nested inherited or aggregate scope is not inferred. Shared dataset/data source paths are not followed. Missing optional properties become `null`, empty collections or presence flags; this is not schema validation.

## Envelope and bounds

Example (`list_tablix`, one region):

```json
{"schema_version":1,"operation":"list_tablix","status":"OK","rdl_version":"2016/01","warnings":[],"omitted_by_policy":["connection_properties","query_text","expressions","cell_text","parameter_values","prompts","code","custom_properties","external_references"],"data":{"tablix":[{"id":1,"name":"Sales","parent_tablix_id":null,"dataset":"Sales","column_count":2,"row_count":2,"layout_direction":null}]},"page":{"offset":0,"total":1,"returned":1,"next_offset":null}}
```

- Exit 0 / `OK`: requested page produced with no warning; **not** a validity, security or runtime verdict.
- Exit 2 / `INCOMPLETE`: a warning, truncation or unsupported legacy layout occurred. Consumers must inspect `warnings`, nested truncation flags and `page`. Deliberately omitted sensitive content is always listed in `omitted_by_policy` and is not itself a warning.
- Exit 1 / `ERROR`: `{schema_version, operation, status, error}` with a fixed error code. The operation is `null` when argument parsing failed.
- Input: one regular `.rdl` file, maximum 8 MiB, 100,000 XML elements, depth 128. No recursive directory scan. UTF-8 (optional BOM) and UTF-16 with BOM only; other encodings fail closed. UTF-16 encoding declarations are accepted after decoding; no transcoding or writes occur.
- Output: maximum 65,536 bytes **excluding the final newline**, ASCII-escaped JSON. `limit` is 1..100, `offset` is a nonnegative integer. A page may return fewer than requested when the byte cap is reached. Follow `page.next_offset`; `total` counts the full primary collection. If one item cannot fit, fail with `output-limit` rather than return a non-advancing page; request a lower `--field-limit` for a very wide dataset. Offset beyond the end returns an empty final page.
- Dataset fields: 0..50 per dataset. `field_count`, `fields_returned`, `fields_truncated` disclose omissions. No nested field pagination in this wave.
- Columns: at most 3 body-row samples each; `cells_truncated` discloses further rows. Each sample has literal/expression value counts and at most 20 distinct static field references (`references_truncated`). No cell text or expression text is returned.
- Identifiers: at most 128 Unicode identifier characters, otherwise `null` with `identifier-omitted`. Widths, booleans, types and directions use closed formats/enums; invalid values are not echoed. Width syntax is inspected, not validated for SSRS range constraints.

## Versions and layout limits

| RDL namespace version | Behavior |
|---|---|
| 2008/01 | Direct Report body, Tablix inspection |
| 2010/01, 2016/01 | ReportSections, including multiple sections and nested Tablix |
| 2003/10, 2005/01 | Dataset/parameter metadata, legacy Table/Matrix/List counts; `INCOMPLETE`, `legacy-layout-not-inspected`; no Tablix layout interpretation |
| Unknown, missing namespace or non-Report root | `ERROR`, `unsupported-report` |

Namespace matching is exact, including prefixed documents; foreign namespace elements do not become report metadata. All modern Tablix are enumerated, not just the first. A nested Tablix contributes only to its own direct columns, rows and bindings.

`list_columns` never infers a header/data/footer role. Only a rectangular body with matching cell/column counts and absent or literal `1` RowSpan/ColSpan receives positional samples. Any other span/irregular shape gets `complex-grid-bindings-omitted` and empty samples while widths remain available. Samples stop at nested Tablix. They inspect direct Textbox values and paragraph text runs through ordinary Rectangle/ReportItems containers. Charts, custom items, group headers, corners, hierarchies, expressions using dynamic/indexed field lookup and rendered matrix expansion are not modeled. `static-token-samples` is heuristic reference discovery, not expression parsing, reference resolution or evaluation.

## Security and error policy

The script uses no networking, subprocesses, writes, logging, imports from inspected files or external reference resolution. It rejects DTD/entity declarations after decoding and also rejects doctypes in the XML parser. File and ancestor symlinks and Windows reparse points are refused. It checks regular-file type before opening, uses no-follow/nonblocking flags where available, verifies the opened identity and caps the read. These checks are not a defense against a concurrent attacker replacing ancestor directories; inspect a stable trusted local path. Files can still change between calls.

Never return connection properties/ConnectStrings, query/procedure text, query parameter values, parameter defaults/valid values/prompts, literal cell text, expression strings, embedded code, custom properties, external reference paths or arbitrary XML diagnostics. The privacy guarantee concerns those excluded content channels. Identifier metadata remains visible: an identifier itself can contain confidential information and should not be published blindly. Unicode identifier filtering reduces instruction/markup injection but is not an authority boundary; treat all returned names as untrusted data.

Fixed errors: `invalid-arguments`, `invalid-limits`, `not-rdl`, `linked-path`, `not-regular-file`, `changed-file`, `file-too-large`, `unsupported-encoding`, `unsafe-xml`, `xml-limit`, `unsupported-report`, `unknown-tablix`, `output-limit`, `unreadable-or-invalid-xml`.

Warnings: `legacy-layout-not-inspected`, `identifier-omitted`, `nonliteral-or-invalid-metadata`, `fields-truncated`, `page-truncated`, `output-limit`, `cells-truncated`, `references-truncated`, `complex-grid-bindings-omitted`.

## Verification and rollback

Synthetic tests cover versions, namespaces, multiple sections/regions, nested scope isolation, missing properties, shared datasets, static field references, spans, pagination, hard output/input/node/depth limits, UTF-16 DTD refusal, hostile identifiers, redacted failures and secret canaries in excluded channels. Hash and directory snapshots verify read-only behavior. All existing tests run unchanged on Windows/Linux CI (Python 3.11/3.13). A real subprocess exercises paths with spaces and Arabic names; symlink tests may skip where Windows permissions disallow creation.

These fixtures test extraction, not designer validity. The small public designer smoke corpus does not establish broad designer coverage or SSRS compatibility, XSD validation, data retrieval, expression execution, rendering, deployment or Claude runtime behavior. See the separate [evidence report](rdl-inspector-evidence.md) for actual executed checks and remaining risks.

Rollback before merge: close the PR and retain its evidence. After merge: revert this PR's commit(s). No inspected files, settings, credentials or databases migrate; PR-03 validation and Dynamics RDP remain intact.
