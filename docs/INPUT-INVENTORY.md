# Input Inventory

## Read-only sources

- `ODDROOM_ACTIVE_SOURCE`: brand, layout, copy, and licensed-asset input only.
- `PF05_REFERENCE`: optional evidence-method reference only; no runtime data, credentials, fixed workflow input, or completion claim is reused.
- `SHOWCASE_SOURCE`: the authorized public-showcase editing source. Its start baseline contained six cases; the current implementation source contains PF07 as the seventh case while the separate registration manifest remains exactly six cases.
- `REGISTRATION_MANIFEST`: six-case registration authority that must remain unchanged.

## Selected OddRoom reuse allowlist

The initial implementation records these candidates without copying them yet:

- `assets/fonts/DoHyeon-Regular.woff2` — display identity, SIL OFL.
- `assets/fonts/NotoSansKR-Regular.woff2` — Korean interface body, SIL OFL.
- `assets/fonts/NotoSansKR-Bold.woff2` — Korean interface emphasis, SIL OFL.
- `assets/photos/shopping-bags-commons.jpg` — synthetic commerce atmosphere, CC0.
- `favicon.svg` — owner-created OddRoom mark.

The implementation may reproduce palette, typography hierarchy, bordered cards, and proof-first information rhythm from the source design without copying unrelated source code.

## Preservation baseline

- OddRoom active-source manifest: `f739f6e2339b70585f824edf53ce6c6db1a1775aba9cd4bcedb84f8e6e54cf77`.
- PF05 reference manifest: `d0911e87eb3d18b3d21ed469e5c4d56531f511832750e257145ba35690e5dfd8`.
- Showcase pre-PF07 source manifest: `1064d482fbf4fb4b206d0446d51f62e8287e939bcc71d10eb7507d07569d4acf`.
- Registration manifest: `217213a472477512070a18c67355a7fcdf24d39616674d16578ea75c9a678c10`.

Git commit and tree baselines are retained in protected raw input evidence. No source listed in this section is a PF07 Git authoring worktree.
