# LiteLLM gateway → Claude Platform on AWS + Amazon Bedrock

A LiteLLM proxy that fronts:

| Models | Routed to | How |
| --- | --- | --- |
| `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` | **Claude Platform on AWS** | Anthropic's *native* Messages API, through your AWS account |
| `nova-pro`, `nova-lite`, `nova-micro` | **Amazon Bedrock** | SigV4 |
| `glm-4.7`, `glm-5` | **Amazon Bedrock "Mantle"** | OpenAI-compatible endpoint (bearer = Bedrock API key) |

Clients talk OpenAI-style to one endpoint (`http://localhost:4000`) with one key, and LiteLLM fans out to the right backend.

### Why Claude is *not* on Bedrock here

[**Claude Platform on AWS**](https://aws.amazon.com/claude-platform/) (GA May 2026) is a different product from Claude *on Amazon Bedrock*. It's Anthropic's **native** platform (Messages API, Agent Skills, code execution, web search, batch, Files API, same-day model launches), operated by Anthropic but accessed **through your AWS account** — AWS IAM auth + AWS Marketplace billing. So in LiteLLM it's the **`anthropic` provider pointed at an AWS endpoint**, not the `bedrock` provider:

- Endpoint: `https://aws-external-anthropic.<region>.api.aws` (LiteLLM appends `/v1/messages`)
- Auth: workspace API key sent as `x-api-key`
- Every request must carry an `anthropic-workspace-id` header (set in `config.yaml`)

---

## Prerequisites

1. **Docker** with Compose v2 (`docker compose`).
2. **Claude Platform on AWS** subscribed via AWS Marketplace. From the AWS Console → *Claude Platform on AWS*, grab:
   - a **workspace API key** (`sk-ant-…`) → `ANTHROPIC_AWS_API_KEY`
   - your **workspace ID** (`wrkspc_…`) → goes into `config.yaml`
   - Note: subscribing provisions a **new** Anthropic org tied to your AWS account — keys from a pre-existing Claude Console org won't work here.
3. **Amazon Bedrock** model access enabled in your region for **Amazon Nova** and **Z.AI GLM**, plus:
   - IAM access key/secret with `bedrock:InvokeModel*` → `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
   - a **Bedrock API key** for the Mantle (GLM) endpoint → `AWS_BEARER_TOKEN_BEDROCK`

---

## Setup

```bash
# 1. Fill in secrets (the repo already has a .env scaffold; or copy the example)
cp .env.example .env        # then edit .env  — replace every CHANGE-ME

# 2. Set your Claude workspace id in config.yaml
#    replace all three  wrkspc_REPLACE_ME  with your real workspace id

# 3. If you're not in us-east-1, update the region in .env:
#    AWS_REGION_NAME, CLAUDE_PLATFORM_AWS_BASE_URL, BEDROCK_MANTLE_BASE_URL,
#    and the us.* Nova model prefixes in config.yaml.

# 4. Launch
docker compose up -d
docker compose logs -f litellm     # watch it boot + run DB migrations
```

Proxy: `http://localhost:4000`  ·  Admin UI: `http://localhost:4000/ui` (log in with `LITELLM_MASTER_KEY`).

---

## Test

```bash
# List models
curl http://localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"

# Claude  -> Claude Platform on AWS
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4-8","messages":[{"role":"user","content":"Say hi in 5 words."}]}'

# Amazon Nova -> Bedrock
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model":"nova-pro","messages":[{"role":"user","content":"Say hi in 5 words."}]}'

# GLM -> Bedrock Mantle
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"model":"glm-4.7","messages":[{"role":"user","content":"Say hi in 5 words."}]}'
```

Issue scoped virtual keys (instead of handing out the master key) from the UI or:

```bash
curl http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"models":["claude-opus-4-8","nova-pro"],"max_budget":50}'
```

---

## Notes & gotchas

- **Region consistency.** The Claude, Nova, and Mantle endpoints/IDs all encode a region. Keep `.env` URLs, `AWS_REGION_NAME`, and the `us.*` Nova prefixes in the same geo.
- **Claude auth = workspace API key.** This is the LiteLLM-friendly path. Claude Platform on AWS *also* supports AWS **SigV4** auth, but LiteLLM's `anthropic` provider can't SigV4-sign this endpoint — that would need a signing sidecar in front of it. If your org forbids long-lived keys, tell me and I'll add that container.
- **GLM route.** Defaulted to the AWS-recommended **Mantle** (OpenAI-compatible) endpoint, which gives clean tool-calling. A native `bedrock/converse/zai.glm-4.7` (SigV4, no extra key) fallback is commented in `config.yaml`; on LiteLLM ≤ ~1.83 it can throw `UnsupportedParamsError` when `tools` are passed ([litellm#24993](https://github.com/BerriAI/litellm/issues/24993)).
- **Caching** is off by default. The `redis` service is wired up; uncomment the `cache:` block in `config.yaml` to turn on response caching.
- **Secrets.** `.env` is git-ignored. Rotate the `sk-ant-…` and Bedrock keys like any production credential.

## References

- [Claude Platform on AWS — product](https://aws.amazon.com/claude-platform/) · [user guide](https://docs.aws.amazon.com/claude-platform/latest/userguide/welcome.html) · [Anthropic docs](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws)
- [Introducing Claude Platform on AWS (AWS blog)](https://aws.amazon.com/blogs/machine-learning/introducing-claude-platform-on-aws-anthropics-native-platform-through-your-aws-account/)
- [Z.AI GLM on Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards-zai.html) · [LiteLLM Bedrock](https://docs.litellm.ai/docs/providers/bedrock) · [LiteLLM Anthropic](https://docs.litellm.ai/docs/providers/anthropic)
