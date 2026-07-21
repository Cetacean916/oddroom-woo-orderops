# OFFSET Reference Application Map

This document records how the prepared PF07 reference corpus is applied to the delivered storefront, operator console, and runtime hub. External screenshots are visual research only; none of their pixels, logos, or page source is included in the product.

## Applied visual system

| Reference quality | Delivered implementation | Authoritative files |
| --- | --- | --- |
| Image-led commerce landing pages | Full-bleed responsive product/lifestyle hero, restrained text overlay, centered wordmark, collection index, and a clear first purchase action | `plugin/oddroom-orderops/includes/class-oddroom-storefront.php`, `plugin/oddroom-orderops/assets/css/storefront.css` |
| Editorial product catalog rhythm | Large image fields, asymmetric two-column stories, numbered object labels, generous whitespace, flat rules, and compact uppercase metadata | `plugin/oddroom-orderops/assets/css/storefront.css` |
| Product-detail references | Product identity and price lead the page; gallery, variation choice, quantity, and purchase action remain visually grouped without decorative dashboard cards | `plugin/oddroom-orderops/includes/class-oddroom-storefront.php`, WooCommerce templates styled by `storefront.css` |
| Operations-console references | Dense operator information, left-aligned actions, explicit state labels, flat table borders, and an orange action accent; no neon glow, gradients, floating glass cards, or generic KPI-dashboard composition | `plugin/oddroom-orderops/includes/class-oddroom-admin.php`, `plugin/oddroom-orderops/assets/css/admin.css` |
| Desktop runtime/control references | Persistent left rail, numbered operating sequence, compact status band, direct store/admin targets, and recovery actions in one flat control surface | `launcher/ui/index.ko.html`, `launcher/ui/index.en.html`, `launcher/ui/app.css` |
| Shared brand system | `OFFSET / OBJECTS / ORDER SYSTEM`, paper/ink base, rust action accent, olive support accent, squared offset-block mark, and one typographic hierarchy across store/admin/hub | `plugin/oddroom-orderops/assets/images/brand/`, `plugin/oddroom-orderops/assets/images/favicon.svg` |

## Selected tokens

- Paper: `#f6f4ef` / `#f3f0e7`
- Ink: `#141412` / `#171714`
- Rust action accent: `#a43f22`
- Olive support accent: `#475448` / `#667045`
- Interface type: bundled Noto Sans KR regular and bold as `Offset Sans`
- Shape language: square rules and offset rectangles; rounded components appear only where the source product or native control requires them

## Public image implementation

The current pages use the 20 accepted PF07 AI-generated originals prepared for `HOME-001~003`, `HOME-006~007`, `SIMPLE-001~006`, and `VARIABLE-001~009`. They were generated from text and PF07's own original master sheets, then cropped, resized, converted to sRGB WebP, stripped of metadata, and directly reviewed in the real pages. External product, website, and UI-reference images are not generation inputs and are not bundled.

Exact bundled paths, asset IDs, generation boundaries, and SHA-256 values are recorded in `ASSET-LICENSES.md`. The six current OFFSET vector assets are:

| PF07 path | SHA-256 |
| --- | --- |
| `plugin/oddroom-orderops/assets/images/favicon.svg` | `7fc58a6a879467a60ca9b8916b81d8c72ca139785d7afafe7c594195add94daa` |
| `plugin/oddroom-orderops/assets/images/brand/wordmark-horizontal.svg` | `228fc7308290d3d7ac03f13c1e8dcd7b3f01651902407dac6edc591f95f0b752` |
| `plugin/oddroom-orderops/assets/images/brand/symbol.svg` | `08ced7c45c2707a5f54192afb0aea846330624ad58d2714b6b18451e7c65b2b5` |
| `plugin/oddroom-orderops/assets/images/brand/logo-dark.svg` | `a22ba7fb6cbfe5be200a52da0f91ad83e0c796bc9d425fd6cab51adf2ae66d04` |
| `plugin/oddroom-orderops/assets/images/brand/logo-light.svg` | `fc1c68ad78094a2e12b2aa08d3cce019ad2d646bbcc9bc9fe7e1f42e79c4e642` |
| `plugin/oddroom-orderops/assets/images/brand/offset-grid-pattern.svg` | `ab18f6ebbc2ce474213faba50c28cb96c2d5af747dc5b031db0bf37c751c530e` |

Historical `OddRoom` names remain only in compatibility namespaces, class names, database keys, headers, and repository paths. They are not the selected buyer-facing visual brand.
