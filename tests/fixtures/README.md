# Test fixtures

Everything under this directory is synthetic and hand-written for the offline validator tests. It contains no real customer data, no real server names and no real credentials; the deliberately broken files use placeholder values only.

`rules/` holds one broken and one fixed report per rule that was added after a real Report Builder refusal (RDL015 parameter panel, RDL070 RepeatOnNewPage parity) or a reported rendering defect (RDL055 mixed direction: `mixed_direction_joined` warns, `mixed_direction_marked` is clean). It is kept apart from `rdl/` so the `--root tests/fixtures/rdl` results stay fixed.
