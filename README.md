# DenOps AI

DenOps AI is starting with a deliberately small builder control plane. The first
milestone does not run a model or modify application code. It proves the parts
that must remain reliable before a GPU-backed model is connected:

- one owner-written task at a time;
- one builder process at a time;
- atomic, machine-readable status;
- explicit model and safeguard endpoint configuration;
- fail-closed behavior when either endpoint is unavailable;
- a small authenticated administrative web interface;
- no deployment, merge, or production access.

## Current workflow

1. Replace the comments in `tasks/current.md` with one task.
2. Run `python3 -m denops_ai_builder --root .`.
3. Read `state/status.json`.

With no task, the builder records `idle`. With a task but no configured model
services, it records `blocked` and names the missing configuration. This is the
expected state on the current CPU-only VM.

## Web interface

The web interface can view status, replace or clear the one task, and run the
same readiness check as the command line. It has no shell, deployment, merge, or
arbitrary-command feature.

Set an administrative password outside the repository and start the server:

```bash
export DENOPS_AI_ADMIN_PASSWORD='use-a-long-random-value'
PYTHONPATH=src python3 -m denops_ai_builder --root . --serve
```

It listens on `127.0.0.1:8080` by default. Binding to a non-loopback address is
refused unless the administrative password is present. The server uses HTTP
Basic authentication, so a future LAN deployment must be placed behind HTTPS.

The supplied systemd unit keeps the first deployment loopback-only. An operator
can reach it with an SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 pingpassport@denops-ai
```

Then open `http://127.0.0.1:8080`. The username is `admin`; the password belongs
in `/etc/denops-ai/web.env`, outside version control.

## Configuration reserved for the GPU server

The future model services will use OpenAI-compatible HTTP endpoints:

- `DENOPS_AI_MODEL_URL` for `openai/gpt-oss-20b`;
- `DENOPS_AI_SAFEGUARD_URL` for `openai/gpt-oss-safeguard-20b`.

The control server will not download model weights. When GPU hardware is added,
the endpoints can point to that server without changing task or state formats.

## Development

Run the tests without installing dependencies:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The next milestone is intentionally narrow: define and test the safeguard
decision contract. Model-driven file editing and command execution remain out of
scope until that contract is approved.
