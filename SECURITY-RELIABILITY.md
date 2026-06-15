# Security & Reliability Checklist — LiteLLM Gateway

Stack: LiteLLM proxy + Postgres + Redis, fronting **Claude Platform on AWS** (Claude) and
**Amazon Bedrock** (Nova via SigV4, GLM via Mantle). Based on LiteLLM's official
[production](https://docs.litellm.ai/docs/proxy/prod) and
[reliability](https://docs.litellm.ai/docs/proxy/reliability) docs.

Priority: 🔴 P0 = do before any shared/non-local use · 🟠 P1 = production hardening · 🟡 P2 = operational polish.

---

## 🔴 P0 — Critical

### Security
- [ ] **Stop using the master key as an app credential.** It's admin-level. Mint per-app
      [virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys) scoped to models + budget; hand those out.
      ```bash
      curl http://localhost:4000/key/generate -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
        -H "Content-Type: application/json" \
        -d '{"models":["claude-opus-4-8","claude-haiku-4-5","nova-pro"],"max_budget":50,"rpm_limit":100}'
      ```
- [ ] **Put TLS in front of `:4000`.** It's plain HTTP today. Terminate HTTPS at a reverse proxy
      (Caddy/Nginx) or cloud LB/ALB; never expose the raw port to anything but localhost.
- [ ] **Lock down the admin UI.** Today the master key is the UI login. Set a dedicated login
      (`UI_USERNAME` / `UI_PASSWORD` in `.env`) or wire SSO.
- [ ] **Protect `.env`.** It holds your real AWS secret key, Claude workspace key, and Bedrock API key in plaintext.
      `chmod 600 .env`; confirm it's gitignored (✅ it is); never bake it into an image or commit it.

### Reliability
- [ ] **Wire Redis into the router** — it's running but unused. Required for correct rate limiting / state
      across workers & instances. Add to `config.yaml`:
      ```yaml
      router_settings:
        redis_host: os.environ/REDIS_HOST
        redis_port: os.environ/REDIS_PORT
        routing_strategy: simple-shuffle   # recommended
        enable_pre_call_checks: true       # context-window + rate-limit pre-checks
      ```

---

## 🟠 P1 — Production hardening

### Security
- [ ] **Move secrets to AWS Secrets Manager** (you're already on AWS) instead of plaintext `.env`.
      [Docs](https://docs.litellm.ai/docs/secret_managers/aws_secret_manager):
      ```yaml
      general_settings:
        key_management_system: "aws_secret_manager"
        key_management_settings:
          store_virtual_keys: true
          access_mode: "read_and_write"
      ```
- [ ] **Add PII guardrails** so prompts/responses can't leak secrets/PII.
      [content_filter](https://docs.litellm.ai/docs/proxy/guardrails/litellm_content_filter):
      ```yaml
      guardrails:
        - guardrail_name: "pii-filter"
          litellm_params:
            guardrail: litellm_content_filter
            mode: "pre_call"
            patterns:
              - { pattern_type: prebuilt, pattern_name: us_ssn,         action: BLOCK }
              - { pattern_type: prebuilt, pattern_name: aws_access_key, action: BLOCK }
              - { pattern_type: prebuilt, pattern_name: email,          action: MASK }
      ```
- [ ] **Rotate the long-lived AWS access key** (`.env:29-30`) → use a scoped IAM role / short-lived creds.
      Trim the IAM policy to least-privilege (the inference-only subset we discussed).
- [ ] **Log hygiene** — never leak request bodies/keys in logs:
      ```yaml
      litellm_settings:
        set_verbose: False
        json_logs: true
      ```
- [ ] **Pin the image tag.** You're on `ghcr.io/berriai/litellm:main-stable` (moving). Pin to a specific
      `vX.Y.Z-stable` for reproducible, supply-chain-safe deploys.

### Reliability
- [ ] **Define fallbacks** so a backend blip degrades gracefully:
      ```yaml
      litellm_settings:
        num_retries: 2          # already set
        request_timeout: 600    # already set
        allowed_fails: 3        # cooldown a model after >3 fails/min
        cooldown_time: 30
        fallbacks:
          - {"claude-opus-4-8":  ["claude-sonnet-4-6", "claude-haiku-4-5"]}
          - {"glm-5":            ["glm-4.7"]}
          - {"nova-pro":         ["nova-lite"]}
      ```
- [ ] **Per-key / per-model budgets + rpm/tpm limits** to cap spend and abuse (set at key-gen, see P0 snippet, or per model in `model_list`).
- [ ] **Tune DB writes & pool** for spend logging under load:
      ```yaml
      general_settings:
        proxy_batch_write_at: 60
        database_connection_pool_limit: 10   # total = limit × workers × instances
      ```
- [ ] **Alerting** on exceptions / budget / slow responses:
      ```yaml
      general_settings:
        alerting: ["slack"]   # set SLACK_WEBHOOK_URL in .env
      ```

---

## 🟡 P2 — Operational excellence
- [ ] **Backups** — snapshot the `litellm_pgdata` volume (holds virtual keys + spend) and **securely back up
      `LITELLM_SALT_KEY`**; lose the salt and the encrypted creds in the DB become unreadable.
- [ ] **Metrics** — enable the Prometheus endpoint + Grafana; watch p95 latency, error rate, and spend per model.
- [ ] **Scale out** — raise `--num_workers` and/or run multiple replicas behind the LB (Redis keeps rate limits consistent).
- [ ] **Container limits** — set mem/cpu limits and log rotation (`json-file` `max-size`/`max-file`) so a runaway can't starve the host.
- [ ] **Claude data residency** — Claude Platform on AWS processed our test with `inference_geo: not_available`
      (unpinned, may leave AWS boundary). If you have residency requirements, pass `inference_geo` per request.
- [ ] **DB-down resilience** — if running on a private VPC, `allow_requests_on_db_unavailable: True` keeps inference
      serving through DB blips (only safe when not publicly reachable).
- [ ] **Active health checks** — `/health` pings every model (costs tokens); schedule it externally to catch a dead backend before users do.

---

### Reference
- Production config: https://docs.litellm.ai/docs/proxy/prod
- Reliability (retries/fallbacks/cooldowns): https://docs.litellm.ai/docs/proxy/reliability
- Virtual keys & budgets: https://docs.litellm.ai/docs/proxy/virtual_keys
- Secret managers: https://docs.litellm.ai/docs/secret_managers/aws_secret_manager
- Guardrails: https://docs.litellm.ai/docs/proxy/guardrails/litellm_content_filter
- Alerting: https://docs.litellm.ai/docs/proxy/alerting
