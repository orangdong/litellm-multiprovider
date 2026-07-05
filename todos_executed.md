# Executed — Task 1: Redis wiring + fallbacks (+ workspace-id move)

Record of work completed against [next_action.md](next_action.md) "Suggested order" step 1
(*"Redis wiring + fallbacks + backups — cheap, high impact, mostly config"*) plus an
ad-hoc request to move the Claude workspace id out of `models.yaml` into `.env`.

Status legend: ✅ done & verified · 🔜 remaining

---

## ✅ Redis wiring (router)
Redis was running but unused (no `router_settings` in the rendered config, and the
generator was silently dropping it).

- **`generate-config.py`** — added `router_settings` to the passthrough tuple so it now
  reaches `generated/config.yaml`. Previously only `litellm_settings` / `general_settings`
  passed through, so any `router_settings` in `models.yaml` was a no-op.
- **`models.yaml`** — added a `router_settings` block:
  - `redis_host` / `redis_port` → `os.environ/REDIS_HOST` / `os.environ/REDIS_PORT`
    (`.env` already had `redis` / `6379`, pointing at the compose service).
  - `routing_strategy: simple-shuffle`
  - `enable_pre_call_checks: true` (context-window + rate-limit pre-checks)
  - `allowed_fails: 3`, `cooldown_time: 30` (auto-park a failing deployment) — placed
    under `router_settings` (router-level keys; would be silent no-ops under
    `litellm_settings`).

## ✅ Fallbacks (data-driven, by alias)
Graceful degradation when a backend blips.

- **`models.yaml`** — added a `fallbacks:` map keyed by **alias**:
  ```yaml
  fallbacks:
    claude-opus-4-8:   [claude-sonnet-4-6, claude-haiku-4-5]
    claude-sonnet-4-6: [claude-haiku-4-5]
    glm-5:             [glm-4.7]
    nova-pro:          [nova-lite, nova-micro]
    nova-lite:         [nova-micro]
  ```
- **`generate-config.py`** — resolves each alias to its generated `<alias>-<region>` name
  and emits `router_settings.fallbacks` in LiteLLM's `[{model: [backups]}]` format.
  - DRY: change a model's region once and its fallbacks follow automatically.
  - Fail-fast: an alias scattered across multiple regions raises a clear
    "ambiguous across regions" error telling you to reference one explicitly; an unknown
    name/alias errors too.
  - An already-suffixed exact name (e.g. `glm-5-us-west-2`) is accepted as-is (escape hatch).

## ✅ Workspace id moved out of `models.yaml` → `.env`
- **`models.yaml`** — removed `claude.workspace_id`; left a comment pointing to `.env`.
- **`.env`** — added `ANTHROPIC_WORKSPACE_ID=wrkspc_…` (real value; gitignored).
- **`.env.example`** — added `ANTHROPIC_WORKSPACE_ID=wrkspc-CHANGE-ME` placeholder and
  updated the Claude section comments.
- **`generate-config.py`** — reads `ANTHROPIC_WORKSPACE_ID` from the environment and **bakes
  the literal** into the `anthropic-workspace-id` header at render time (dies with a clear
  message if unset). Rationale: `os.environ/` refs are reliably resolved for top-level
  `litellm_params`, but resolution inside a nested `extra_headers` dict isn't guaranteed —
  a literal `os.environ/…` leaking into a header would silently break Claude Platform auth.
  The generator already baked a literal here; only the source changed (`models.yaml` → env).
- **`README.md`** — corrected the three spots that told users to put the workspace id in
  `config.yaml`; also fixed an adjacent stale "config.yaml" region note to `models.yaml`.

---

## Files touched
| File | Change |
|------|--------|
| `generate-config.py` | router_settings passthrough; alias→name fallback resolver; workspace id from env |
| `models.yaml` | removed `workspace_id`; added `router_settings` + `fallbacks` |
| `.env` | added `ANTHROPIC_WORKSPACE_ID` (gitignored — not in `git status`) |
| `.env.example` | added `ANTHROPIC_WORKSPACE_ID` placeholder + comments |
| `README.md` | workspace-id references now point at `.env`; setup steps renumbered |
| `generated/config.yaml` | regenerated (gitignored; container also re-renders on boot) |

## Verification (static render)
Rendered the config locally in a throwaway venv (`pyyaml`); did **not** start the proxy.

- ✅ 8 models render; `router_settings.fallbacks` emitted in the exact
  `[{model: [backups]}]` shape, keyed by **real** model names
  (e.g. `glm-5-us-west-2 → glm-4.7-us-west-2`, `nova-pro-us-west-2 → nova-lite/​micro-us-west-2`).
- ✅ Missing `ANTHROPIC_WORKSPACE_ID` → `[render] ERROR …` exit 1.
- ✅ Scattered alias in `fallbacks` → clear "ambiguous across regions" error.
- ✅ Real `wrkspc_…` id present only in gitignored `.env` + `generated/` — no secret in any
  tracked file. `git status` shows only the 4 intended source files.

## To apply
`docker compose up -d` (or `make restart`) — `entrypoint.sh` re-renders on boot.
Runtime confirmation (Redis actually engaging, fallbacks triggering) still needs the
running proxy.

## ✅ Admin UI login (security baseline, step 2)
Master key no longer has to double as the dashboard password.

- **`.env`** — added `UI_USERNAME=admin` + `UI_PASSWORD=<32-char random>` (git-ignored;
  not pushed). Password generated with real entropy, not hand-picked.
- **`.env.example`** — added `UI_USERNAME` / `UI_PASSWORD=CHANGE-ME-admin-password` +
  a comment (master key still works as root).
- Takes effect on next `docker compose up -d` (env read at startup); no compose change
  needed (`env_file: .env` already loads it).

## 🔜 Next (revised order)
Per decision 2026-07-01, **backups are deferred to the very end** (was part of step 1).

1. **Apply + verify** — `docker compose up -d`; confirm boot, config loads, Redis engages.
2. **Security baseline (step 2)** — admin password ✅; remaining: **virtual keys**, **TLS** in front of `:4000`.
3. **Hardening (step 3)** — Secrets Manager, IAM rotation, PII guardrails.
4. **Scale / polish (step 4)** — workers, prompt caching, budgets, alerting.
5. **Backups (deferred → last)** — snapshot `litellm_pgdata` + securely back up
   `LITELLM_SALT_KEY` (lose the salt → stored credentials become unreadable).
