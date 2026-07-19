# OddRoom Storefront Design Map

This map was fixed before PF07 storefront styling. The reuse source remains read-only at `Samples/Active/oddroom-commercial-site`; PF07 copies only the files listed below and rewrites the composition for a WooCommerce operations demonstration.

| Reused element | PF07 use | Source file |
| --- | --- | --- |
| Do Hyeon display lettering | Compact `ODDROOM!` wordmark only, preserving the source brand mark without using the coarse display face for buyer copy | `assets/fonts/DoHyeon-Regular.woff2` |
| Noto Sans KR interface typography | Hero and section headings, navigation, product names, body copy, forms, cart, checkout, account, and WooCommerce notices | `assets/fonts/NotoSansKR-Regular.woff2`, `assets/fonts/NotoSansKR-Bold.woff2` |
| Paper/ink with lime, blue, and hot-pink accents | `#fff8eb` paper, `#080604` ink, `#dbfb4f` lime, `#315dff` blue, and `#ff4f81` hot pink | `assets/css/oddroom-site.css` |
| Bordered cards and restrained offset shadows | Store promise cards, product cards, proof receipts, buttons, and form panels, reduced to two-pixel borders and compact shadows for clearer commerce hierarchy | `assets/css/oddroom-site.css` |
| Proof-first commercial rhythm and shopping image | Buyer outcome, four-fact proof strip, Korean three-step recovery story, and shop conversion scene | `README.md`, `asset-credits.json`, `assets/photos/shopping-bags-commons.jpg` |

## Copied asset allowlist

| PF07 path | Source SHA-256 | Provenance |
| --- | --- | --- |
| `plugin/oddroom-orderops/assets/fonts/DoHyeon-Regular.woff2` | `dd3c78d07352d51c122b28953367f3ef6d3ea749e6cb205d15f94933dc46fd3d` | Do Hyeon, SIL Open Font License |
| `plugin/oddroom-orderops/assets/fonts/NotoSansKR-Regular.woff2` | `1583b2052998c1e3133c742dae17300ba17de41a0ae46a313a281948ce5e3ab7` | Noto Sans KR, SIL Open Font License |
| `plugin/oddroom-orderops/assets/fonts/NotoSansKR-Bold.woff2` | `809c61dfb3cfec6af6cfabe4d51e14e57bf86452359ea97e71e64c8821efed4d` | Noto Sans KR, SIL Open Font License |
| `plugin/oddroom-orderops/assets/images/shopping-bags-commons.jpg` | `23e9e11f5ad747c6885c731d5fca553c5acdc6a9697449979297c61ce71344cd` | Wikimedia Commons `Shopping freak (Unsplash)`, CC0 |
| `plugin/oddroom-orderops/assets/images/favicon.svg` | `b6fb6feb9ed13a6d78c2430b83dc8b53d91d542a631575c354b7fee3306401c7` | Owner-controlled OddRoom brand composition; excluded from the GPL code grant |

No other OddRoom source asset or page is copied. The existing OddRoom source and both existing Git publication copies remain unchanged.
