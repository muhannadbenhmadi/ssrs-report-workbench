# Security Policy

## Safe defaults

The PR-01 diagnostics must remain offline and read-only. They do not connect to SQL Server, SSRS, Power BI Report Server or Dynamics 365 and do not execute reports, scripts discovered in a user workspace, or deployments.

Do not commit connection strings with secrets, API keys, report data, real employee information, or production database exports. Use synthetic test fixtures and scrub local diagnostic logs. Runtime adapters in future PRs will require explicit authorization and independent access reviews.

The static diagnostic does not evaluate the security of an RDL or an X++ reporting implementation. A pass means only that the foundation manifest and skill passed their local checks.

## RDL validator

`scripts/rdl_validate.py` rejects any file containing `<!DOCTYPE` or `<!ENTITY` before parsing, so entity expansion and external entity attacks are not possible. It never writes into inspected directories, refuses symlinks and caps file size. Rule `RDL040` reports that a connection string carries a credential key such as `Password` or `User ID` but never echoes the value; the same applies to the hook output.

## Reporting vulnerabilities

Report suspected vulnerabilities privately to the repository owner rather than including exploit details or credentials in public issues. There is no guaranteed response SLA.
