# Credential Handling

- Secret values are resolved from protected runtime files or dedicated n8n credentials.
- Public configuration names aliases only; it never contains a real token, channel, portal, webhook, hostname, or credential locator.
- Authorization headers, cookies, exact webhook URLs, raw payloads, and private identifiers are excluded from logs and public evidence.
- The n8n workflow export is credential-free. Restore remaps credential references from authorized protected inputs.
- Raw evidence, databases, volumes, secret inputs, and backups never enter Git or GitHub Actions.

