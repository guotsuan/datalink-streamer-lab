# Deployment guide

## Baseline and layout

The recorded VM uses Rocky Linux 10.2 and Python 3.13.15. The files in `lab/`
are the integration-code snapshot used for the recorded tests. The original
deployment directory was `/home/gq/datalink-streamer-lab`, containing those files
directly. A repository checkout instead places them in the `lab/` subdirectory.

| Process | Binding | Environment |
|---|---|---|
| Portal and mock services | `127.0.0.1:18080` | `lab/.venv` |
| Official DataLink | `127.0.0.1:18081` | `lab/.venv-datalink` |
| Official Streamer | `127.0.0.1:18082` | `lab/.venv-streamer` |
| Optional password gateway | Original VM public IP, port 18080 | `lab/.venv` |

DataLink and Streamer are unmodified upstream packages. `supervise.py` configures
them to use local mock DMAPI/IAM/PAPI endpoints and local synthetic storage.

## Fresh private environment

Prerequisites: Linux, Python 3.13 with `venv` and pip, Git, and authorised access
to the official PyPI/SKA package indexes. Use a dedicated, empty checkout;
do not run the helper against an existing deployment.

```sh
git clone https://github.com/guotsuan/datalink-streamer-lab.git
cd datalink-streamer-lab
python3.13 scripts/prepare_environment.py --dry-run
python3.13 scripts/prepare_environment.py
lab/.venv/bin/python lab/supervise.py
```

The helper creates three separate environments, installs the recorded dependency
versions and fetches upstream source at exact commits. It replaces the two
VM-local `file:///home/gq/...` entries only in generated install inputs, leaving
the historical inventories unchanged. Package availability and platform wheels
can change; stop and investigate an install failure rather than silently updating
versions. These are version snapshots, not a fully hash-locked supply-chain build.

The helper is newly supplied packaging tooling: syntax and dry-run checks are
performed, but a complete clean-server rebuild has not been validated. The
historical results apply to the original deployed environment, not automatically
to a fresh installation. The helper does not start services, change firewall
rules, enable lingering or alter the existing VM.

## Private access and checks

From the client, forward port 18080 to the server and open `http://localhost:18080`:

```sh
ssh -N -L 127.0.0.1:18080:127.0.0.1:18080 USER@SERVER
```

Then use the portal's internal test button or run on the server:

```sh
curl -X POST http://127.0.0.1:18080/lab/run
```

The external `test_public_e2e.py` expects the password-gateway login contract;
it is not the test entry point for the private-only portal.

## Persistent process supervision

The supplied `.service` files are examples from the original VM, not portable
drop-in units. Before installing a user unit, change `WorkingDirectory` and
`ExecStart` to the absolute checkout `lab/` path. Retain the loopback bindings.
Create `lab/logs/` before starting the public unit. Review existing user-unit files
before replacing them. The private unit can be managed with:

```sh
systemctl --user daemon-reload
systemctl --user enable --now datalink-streamer-lab
systemctl --user status datalink-streamer-lab
journalctl --user -u datalink-streamer-lab
```

User lingering, if required after logout, is an administrator decision. It is not
enabled by the preparation helper.

## Optional public gateway

Public access is not needed for private tests. The included provisioning helpers,
host allow-list and public systemd unit are specific to `64.176.188.89`; do not
execute them unchanged on a different host. Review `public_gateway.py`,
`provision_public.py`, unit paths, origin and bind address together before reuse.

The original provisioning helper creates unique password/signing material in
mode-0600 local files and refuses to overwrite existing credentials. It initially
sets a 24-hour window. The original VM later had expiry explicitly disabled using
`persist_public_access.py`; this is not a recommended public deployment default.
Do not run that helper as part of ordinary setup. No existing server setting is
changed by this repository publication.

For a new publicly accessible deployment, use HTTPS and review access controls
first. HTTP cannot protect the disposable password or session cookie from network
observers. Never use real SKA credentials/data or expose ports 18081/18082.
Do not copy `public-access.json` or `public-access-credentials.txt` into Git.

## Verification boundaries

The public gateway adds origin, route and synthetic-path restrictions. These do
not establish upstream storage-boundary security or real OIDC/JWT validation.
Real discovery/authentication, interrupted-transfer recovery, large-file/load
tests and dependency-failure recovery remain outside the recorded acceptance.
