# Next Actions — Performance, Security & Reliability

Forward-looking plan to harden this LiteLLM gateway. Detailed config snippets live in
[SECURITY-RELIABILITY.md](SECURITY-RELIABILITY.md); this file is the prioritized "what next".

**Where it stands today:** single LiteLLM proxy + Postgres (host `5433`) + Redis (running but
**unused**), plain HTTP on `:4000`, the master key doubles as admin + client key, secrets in
plaintext `.env`, models managed via `models.yaml` → `generate-config.py` (per-model regions).

Legend: 🔴 do first · 🟠 next · 🟢 later

---

## 🚀 Performance
- 🔴 **Put the idle Redis to work.** Add `router_settings` (redis host/port, `simple-shuffle`,
  `enable_pre_call_checks: true`) for cross-worker rate limiting + optional response caching.
  Note: `generate-config.py` currently passes through only `litellm_settings`/`general_settings` —
  add `router_settings` to its passthrough tuple to enable this.
- 🟠 **Prompt caching** on Claude (and Bedrock where supported) — big latency/cost win on repeated
  system prompts and long context.
- 🟠 **Scale workers + DB pool:** raise `--num_workers`, set `database_connection_pool_limit`
  (total conns = limit × workers × instances).
- 🟢 **Batch spend writes:** `proxy_batch_write_at: 60` to cut DB write pressure under load.
- 🟢 **Right-size containers:** CPU/memory limits + log rotation so a runaway can't starve the host.

## 🔒 Security
- 🔴 **Stop using the master key as the app key.** Issue scoped **virtual keys** (per app/team,
  model allowlist + budget) via the UI or `/key/generate`. Master key = admin only.
- 🔴 **TLS in front of `:4000`** (reverse proxy / LB) — it's plain HTTP today.
- 🔴 **Real admin login:** set `UI_USERNAME` / `UI_PASSWORD` in `.env` (master key still works as root).
- 🟠 **Secrets out of plaintext `.env` → AWS Secrets Manager** (`key_management_system: aws_secret_manager`).
- 🟠 **Rotate the long-lived AWS access key** → scoped IAM role / short-lived creds; trim to least-privilege.
- 🟠 **PII guardrails** (`litellm_content_filter`): block SSN / AWS keys, mask emails.
- 🟢 **Pin the image tag** (not `main-stable`) and `chmod 600 .env`.

## 🛡️ Reliability
- 🔴 **Backups:** snapshot the `litellm_pgdata` volume + securely back up `LITELLM_SALT_KEY`
  (lose the salt → stored credentials become unreadable).
- 🔴 **Fallbacks** so a backend blip degrades gracefully (e.g. opus→sonnet→haiku, glm-5→glm-4.7).
- 🟠 **Cooldowns:** `allowed_fails` + `cooldown_time` to auto-park a failing deployment.
- 🟠 **Budgets + rpm/tpm limits** per key/model to cap spend and abuse.
- 🟠 **Alerting:** `alerting: ["slack"]` for exceptions / budget / slow responses.
- 🟢 **Multi-region readiness:** enable model access in **every** region you scatter into; add
  external `/health` monitoring (note: `/health` pings each model and costs tokens).

---

## Suggested order
1. **Redis wiring + fallbacks + backups** — cheap, high impact, mostly config.
2. **Virtual keys + TLS + admin password** — the security baseline before any shared use.
3. **Secrets Manager + IAM rotation + guardrails** — real hardening.
4. **Workers + prompt caching + budgets + alerting** — scale and operational polish.
