# Claims Boundary

## What the evidence supports

- WooCommerce custom plugin with durable event tracking.
- Tested duplicate suppression and bounded retries.
- Signed n8n adapter to HubSpot and Slack.
- Fault-injection and reconciliation evidence.
- Staging backup/restore drill completed.

These statements describe one synthetic staging acceptance run and the linked public evidence records. The on-demand runtime is not a continuously hosted service.

## What this does not prove

- Production load, scale, uptime, availability target, or SLA.
- Real payment, customer, revenue, refund, tax, or settlement processing.
- Partial refund, chargeback, reopened or reversed terminal order, marketplace, subscription, multi-currency, or every WooCommerce edge case.
- Reconstruction of a cancellation timestamp when PF07 never observed and persisted the first transition fact.
- Formal exactly-once delivery across WordPress, HubSpot, and Slack.
- Resistance to replay of a captured, still-valid signed request. Timestamp freshness, sender-side duplicate suppression, and forged-request rejection do not prove authenticated transport replay prevention.
- Elimination of the Slack accepted/response-lost window; an ambiguous transmission requires protected operator resolution.
- Protection against unrelated external writers changing the same HubSpot Deal.
- Customer deployment, real revenue, enterprise scale, Make, Zapier, Shopify, penetration testing, PCI certification, or legal certification.

n8n is an external source-available dependency governed by its own Sustainable Use License. This project does not describe n8n itself as OSI open source and does not redistribute n8n source code.

## Buyer fit

Suitable for custom WooCommerce order-to-CRM operations where immutable capture, bounded recovery, operator visibility, and evidence-backed handoff matter.

Not a fit as proof of high-scale production operations, real-money commerce, every WooCommerce lifecycle, formal exactly-once delivery, or a turnkey multi-tenant SaaS.
