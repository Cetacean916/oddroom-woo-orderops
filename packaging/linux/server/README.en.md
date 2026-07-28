# OFFSET OrderOps · Linux server baseline

This package is an isolated baseline for a prepared Linux server with a
dedicated operator account and Docker Engine. Use the Linux local package for a
desktop walkthrough. The server package does not automatically install
systemd or nginx and does not issue TLS certificates.

## Safety boundary

- WordPress binds only to the selected loopback port on `127.0.0.1` by
  default.
- MariaDB, n8n, the Docker API, evidence, logs, and metrics have no public
  route.
- The nginx example proxies the WordPress storefront and authenticated
  `/wp-admin/` on one origin. It contains no authentication bypass.
- Default `DEMO_MODE` uses synthetic orders and does not contact real payment,
  email, HubSpot, or Slack services. `CONNECTED_MODE` can send a real Slack
  setup message and create real HubSpot and Slack effects; read the common
  guide first.

## 1. Download and first start

Prerequisites are Python 3.10 or newer, Docker Engine, the Docker Compose
plugin, internet access for initial image acquisition, and a dedicated operator
account authorized to use Docker. Docker-socket access can be equivalent to
high privilege on the host, so do not share this account with unrelated work.

Download `pf07-linux-server-1.0.8.tar.gz` and `SHA256SUMS.txt` from the same
GitHub Release. Compare the archive before extraction:

```sh
sha256sum pf07-linux-server-1.0.8.tar.gz
```

Do not run a file whose name or SHA-256 differs. Extract the complete verified
archive into a new stable path owned by the dedicated account. Run the
following from the package root:

```sh
cp server/pf07-server.env.example server/pf07-server.env
# choose an unused port from 1024 through 65535 in server/pf07-server.env
set -a
. ./server/pf07-server.env
set +a
server/pf07-server preflight
server/pf07-server start
server/pf07-server status
```

`PF07_WORDPRESS_PORT` is fixed when the first `start` creates
`.pf07/runtime.env`; later starts use that stored port. The store URL and Ready
state printed by `status` are authoritative. If the requested port is occupied,
choose another port before first start in a state-free extraction.

## 2. Operation and data

```sh
server/pf07-server status
server/pf07-server stop
server/pf07-server start
server/pf07-server restart
server/pf07-server recover
server/pf07-server diagnostics
server/pf07-server evidence-export
```

`stop` stops services while preserving orders, settings, `.pf07/`, and
package-owned volumes. A later `start` from the same path uses the same state.
`uninstall --data-choice preserve` also retains data;
`--data-choice remove` is irreversible without an external encrypted backup.

For exact confirmation phrases and data effects for backup, restore, removal,
controlled update, connected mode, and tunnel operation, read
[`packaging/common/PACKAGE-README.en.md`](packaging/common/PACKAGE-README.en.md).
The server wrapper exposes the supported server-operation commands; use
`launcher/bin/pf07` from the package root for a common-CLI action not exposed
by the wrapper.

Never overwrite a running extraction to update it. Extract the reviewed new
archive into a separate stable path, create an external encrypted backup of the
current state, then use Controlled update from the new package with the exact
supported predecessor extraction.

## 3. systemd installation

First establish that manual `preflight`, `start`, and `status` pass. Then review
and replace `User`, `Group`, `SupplementaryGroups`, `WorkingDirectory`,
`EnvironmentFile`, `ExecStart`, and `ExecStop` in
`pf07-orderops.service.example` with the dedicated account, Docker group, and
absolute deployment path. If the example `/opt/pf07-orderops` path is exact:

```sh
sudo install -m 0644 server/pf07-orderops.service.example \
  /etc/systemd/system/pf07-orderops.service
sudo systemctl daemon-reload
sudo systemctl enable --now pf07-orderops.service
sudo systemctl status pf07-orderops.service
server/pf07-server status
```

If the Docker daemon unit is not `docker.service`, change `Requires` and
`After` to the actual unit. The service reads its port from `EnvironmentFile`
but does not replace a port already stored in `.pf07/runtime.env`. After any
edit, run `systemd-analyze verify` and exercise actual start, stop, and restart
on the target server.

## 4. nginx and public HTTPS

Replace the hostname, certificate paths, and upstream port in
`nginx-pf07.conf.example`, then install it in the host's reviewed nginx include
path. The upstream port must match the URL shown by `status`. Test the nginx
configuration before reload and expose only the required HTTPS port through
the firewall. Never expose the WordPress loopback port, MariaDB, n8n, or the
Docker socket.

TLS issuance and renewal, DNS, firewall policy, public access control, and
browser validation on the actual server remain operator responsibilities
outside this package. Until those are complete, use loopback-only mode. The
optional tunnel is a separate exposure path; do not combine it casually with a
public nginx deployment, and confirm shutdown with `tunnel-off` and
`tunnel-status`.
