# DenOps AI

DenOps AI is starting with a deliberately small builder control plane. The
current milestone can ask OpenAI for a reviewable implementation plan, but it
does not modify application code or execute commands. It proves the parts that
must remain reliable before a GPU-backed model is connected:

- one owner-written task at a time;
- one builder process at a time;
- atomic, machine-readable status;
- an interchangeable model-provider boundary;
- fail-closed behavior when either endpoint is unavailable;
- a small authenticated administrative web interface;
- no deployment, merge, or production access.

## Current workflow

1. Replace the comments in `tasks/current.md` with one task.
2. Run `python3 -m denops_ai_builder --root .`.
3. Read `state/status.json`.

With no task, the builder records `idle`. With a task but no configured provider,
it records `blocked`. With OpenAI configured, **Ask OpenAI for plan** writes a
reviewable result to `state/latest-plan.md` and records `review-ready`.

OpenAI use is manual only. The deployed service permits one attempted API call
per UTC day and caps output at 800 tokens. There is no scheduler or background
model activity. The local limit protects this application; the OpenAI Platform
project should also have an appropriately small budget configured.

## Web interface

The web interface can view status, replace or clear the one task, run the
readiness check, and request an implementation plan. It has no shell,
deployment, merge, file-editing, or arbitrary-command feature.

Set an administrative password outside the repository and start the server:

```bash
export DENOPS_AI_ADMIN_PASSWORD='use-a-long-random-value'
PYTHONPATH=src python3 -m denops_ai_builder --root . --serve
```

It listens on `127.0.0.1:8080` by default. Binding to a non-loopback address is
refused unless the administrative password is present. The server uses HTTP
Basic authentication, so a future LAN deployment must be placed behind HTTPS.

The supplied systemd unit binds the current deployment to the DenOps AI VM's
VLAN address at `192.168.1.13:8080`. Open it directly from the trusted LAN:

`http://192.168.1.13:8080`

The username is `admin`; the password belongs in `/etc/denops-ai/web.env`,
outside version control. HTTP Basic credentials are not encrypted in transit,
so access must remain on the trusted LAN until an HTTPS reverse proxy is added.

## Configuration reserved for the GPU server

The temporary provider uses OpenAI's Responses API with `gpt-6-sol`. The future
model services will use OpenAI-compatible HTTP endpoints:

- `DENOPS_AI_MODEL_URL` for `openai/gpt-oss-20b`;
- `DENOPS_AI_SAFEGUARD_URL` for `openai/gpt-oss-safeguard-20b`.

The control server will not download model weights. When GPU hardware is added,
the provider implementation can point to that server without changing task or
state formats.

## Development

Run the tests without installing dependencies:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The next milestone is intentionally narrow: define and test the safeguard
decision contract. Model-driven file editing and command execution remain out of
scope until that contract is approved.
