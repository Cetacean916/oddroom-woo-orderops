# PF07 Repository Governance

## Classification and Authority

- Repository class: development.
- Delivery scope: PF07 OFFSET OrderOps only; historical `oddroom-*` identifiers remain compatibility namespaces.
- The active PF07 implementation contract controls product, evidence, release, and completion requirements.
- Git-staging root canon controls every Git operation. This file is subordinate to that canon and MUST NOT broaden it.
- Higher-priority system, developer, and current owner instructions govern conflicts.

## Source and Git Boundaries

- The canonical implementation source is the separate non-Git PF07 source tree.
- This repository is the only PF07 Git authoring worktree.
- The Git worktree receives files only from the contract's deny-by-default public builder.
- Direct ad hoc source copying, editing to hide a failed gate, and use of a scratch clone for authoring are forbidden.
- The public builder allowlist and generated build manifest define the exact candidate.

## Protected Material

- Never place credentials, secret values, credential locators, raw evidence, backups, runtime databases or volumes, private infrastructure identifiers, owner-machine paths, personal data, or unreviewed logs or media in this repository or its history.
- Public examples use synthetic placeholders only.
- The protected raw evidence tree is never a builder input, CI input, log input, or Actions artifact input.
- Public evidence must satisfy the contract's redaction, lineage, and claims-boundary rules.

## Git and Review Gates

- The prepared remote remains private through development.
- Every commit and push requires the root Commit Gate and Push Gate.
- The writer and independent reviewer must be different roles, sessions, or agents.
- Approval binds to the exact reviewed candidate, commit, tree, manifest, outgoing history, or publication action. A material change invalidates the affected approval.
- Do not force-push, rewrite history, delete a remote, or remove GitHub evidence surfaces without separate explicit authority.
- The first remote ref must be the reviewed builder-produced commit on `main`.

## Public Release Boundary

- Public visibility is allowed only at the ordered PF07 release step after every contract-required security, license, evidence, CI, history, and independent-review gate passes.
- Visibility change must preserve the exact reviewed commit and tree.
- Fresh authenticated and unauthenticated verification clones are read-only evidence paths.
- Publication alone is not completion; the deployed seventh showcase case and final live checks are also required.

## Completion Truth

- Local files, tests, private CI, a release candidate, or a public repository do not independently establish completion.
- Completion requires the active contract's actual `FINAL_PASS` with all required live, public, restore, preservation, and evidence observations.
