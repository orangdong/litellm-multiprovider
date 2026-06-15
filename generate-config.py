#!/usr/bin/env python3
"""Expand models.yaml -> generated/config.yaml.

Edit models.yaml (aliases, ids, and a per-model region); this builds the LiteLLM
config. For Bedrock + Mantle the model_name becomes <alias>-<region>, so the
region is declared ONCE per model and the name follows it. Each model has its own
region, so models can be scattered across regions. Do NOT edit generated/config.yaml.
"""
import sys
import yaml


def die(msg):
    sys.exit(f"[render] ERROR: {msg}")


src, dst = sys.argv[1], sys.argv[2]
try:
    spec = yaml.safe_load(open(src)) or {}
except Exception as e:
    die(f"could not parse {src}: {e}")

models = []

# --- Claude -> Claude Platform on AWS (single native endpoint) ---
claude = spec.get("claude") or {}
for name in claude.get("models", []) or []:
    ws = claude.get("workspace_id")
    if not ws:
        die("claude.workspace_id is required when claude.models is set")
    models.append({
        "model_name": name,
        "litellm_params": {
            "model": f"anthropic/{name}",
            "api_key": "os.environ/ANTHROPIC_AWS_API_KEY",
            "api_base": "os.environ/CLAUDE_PLATFORM_AWS_BASE_URL",
            "extra_headers": {"anthropic-workspace-id": ws},
        },
    })


def fields(section, row, *keys):
    for k in keys:
        if not row.get(k):
            die(f"{section} entry {row!r} is missing '{k}'")
    return [row[k] for k in keys]


# --- Bedrock (SigV4): model_name = <alias>-<region> ---
for row in spec.get("bedrock") or []:
    alias, model_id, region = fields("bedrock", row, "alias", "id", "region")
    models.append({
        "model_name": f"{alias}-{region}",
        "litellm_params": {
            "model": f"bedrock/{model_id}",
            "aws_access_key_id": "os.environ/AWS_ACCESS_KEY_ID",
            "aws_secret_access_key": "os.environ/AWS_SECRET_ACCESS_KEY",
            "aws_region_name": region,
        },
    })

# --- Mantle (GLM, OpenAI-compatible): model_name = <alias>-<region> ---
for row in spec.get("mantle") or []:
    alias, model_id, region = fields("mantle", row, "alias", "id", "region")
    models.append({
        "model_name": f"{alias}-{region}",
        "litellm_params": {
            "model": f"openai/{model_id}",
            "api_base": f"https://bedrock-mantle.{region}.api.aws/v1",
            "api_key": "os.environ/AWS_BEARER_TOKEN_BEDROCK",
        },
    })

if not models:
    die(f"no models produced from {src}")

out = {"model_list": models}
for key in ("litellm_settings", "general_settings"):
    if spec.get(key) is not None:
        out[key] = spec[key]

with open(dst, "w") as f:
    f.write(f"# AUTO-GENERATED from {src} -- do not edit; edit {src} instead.\n")
    yaml.safe_dump(out, f, sort_keys=False)

print(f"[render] generated {len(models)} models:")
for m in models:
    lp = m["litellm_params"]
    where = lp.get("aws_region_name") or lp.get("api_base", "claude-platform")
    print(f"[render]   {m['model_name']:<22} -> {lp['model']}  ({where})")
