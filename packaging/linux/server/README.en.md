# OFFSET OrderOps · Linux server baseline

This package is an isolated baseline that a prepared Linux server can deploy without redesign. WordPress binds to `127.0.0.1` by default; MariaDB, n8n, and the Docker API are never published. The nginx example proxies the WordPress storefront and authenticated `/wp-admin/` on one origin and contains no authentication bypass.

1. Extract the full archive into a new directory owned by a dedicated operator account.
2. Run `server/pf07-server preflight`, then `server/pf07-server start`.
3. Use `status`, `stop`, `restart`, `recover`, `diagnostics`, `evidence-export`, `backup`, `restore`, `update`, and `tunnel-on/status/off` through the same wrapper.
4. To install a service, replace `/opt/pf07-orderops` in the example unit with the reviewed absolute deployment path before installation.
5. Enable public HTTPS only after the separate canonical-CI tunnel/reverse-proxy validation. Local mode continues without public exposure.

Never overwrite a running extraction for updates. Extract a reviewed new archive into a new directory and use the encrypted package-local backup plus controlled update/restore path.
