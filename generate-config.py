#!/usr/bin/env python3
"""Expand models.yaml -> generated/config.yaml.

Edit models.yaml (aliases, ids, and a per-model region); this builds the LiteLLM
config. For Bedrock + Mantle the model_name becomes <alias>-<region>, so the
region is declared ONCE per model and the name follows it. Each model has its own
region, so models can be scattered across regions. Do NOT edit generated/config.yaml.
"""
import os
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
alias_to_names = {}  # alias / user-facing name -> generated model_name(s); resolves fallbacks

# --- Claude -> Claude Platform on AWS (single native endpoint) ---
# The workspace id is a per-deployment secret: it lives in .env as
# ANTHROPIC_WORKSPACE_ID and is baked into the header at render time (os.environ/
# refs are not resolved inside nested extra_headers at runtime).
claude = spec.get("claude") or {}
if claude.get("models"):
    ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    if not ws:
        die("ANTHROPIC_WORKSPACE_ID must be set (in .env) when claude.models is set")
    for name in claude["models"]:
        models.append({
            "model_name": name,
            "litellm_params": {
                "model": f"anthropic/{name}",
                "api_key": "os.environ/ANTHROPIC_AWS_API_KEY",
                "api_base": "os.environ/CLAUDE_PLATFORM_AWS_BASE_URL",
                "extra_headers": {"anthropic-workspace-id": ws},
            },
        })
        alias_to_names.setdefault(name, []).append(name)


def fields(section, row, *keys):
    for k in keys:
        if not row.get(k):
            die(f"{section} entry {row!r} is missing '{k}'")
    return [row[k] for k in keys]


# --- Bedrock (SigV4): model_name = <alias>-<region> ---
for row in spec.get("bedrock") or []:
    alias, model_id, region = fields("bedrock", row, "alias", "id", "region")
    name = f"{alias}-{region}"
    models.append({
        "model_name": name,
        "litellm_params": {
            "model": f"bedrock/{model_id}",
            "aws_access_key_id": "os.environ/AWS_ACCESS_KEY_ID",
            "aws_secret_access_key": "os.environ/AWS_SECRET_ACCESS_KEY",
            "aws_region_name": region,
        },
    })
    alias_to_names.setdefault(alias, []).append(name)

# --- Mantle (GLM, OpenAI-compatible): model_name = <alias>-<region> ---
for row in spec.get("mantle") or []:
    alias, model_id, region = fields("mantle", row, "alias", "id", "region")
    name = f"{alias}-{region}"
    models.append({
        "model_name": name,
        "litellm_params": {
            "model": f"openai/{model_id}",
            "api_base": f"https://bedrock-mantle.{region}.api.aws/v1",
            "api_key": "os.environ/AWS_BEARER_TOKEN_BEDROCK",
        },
    })
    alias_to_names.setdefault(alias, []).append(name)

if not models:
    die(f"no models produced from {src}")


# --- Fallbacks: declared by ALIAS in models.yaml, resolved to generated names.
# Keeps fallbacks DRY -- change a model's region once and its fallbacks follow.
name_set = {m["model_name"] for m in models}


def resolve_fallback(token):
    if token in name_set:                 # already an exact generated model_name
        return token
    names = alias_to_names.get(token)
    if not names:
        die(f"fallbacks: '{token}' is not a known model name or alias")
    if len(names) > 1:                    # alias scattered across regions -> ambiguous
        die(f"fallbacks: alias '{token}' maps to multiple regions {names}; "
            f"reference one explicitly (e.g. '{names[0]}')")
    return names[0]


fallbacks = []
for primary, backups in (spec.get("fallbacks") or {}).items():
    if not isinstance(backups, list):
        die(f"fallbacks: '{primary}' must map to a list of fallback models")
    fallbacks.append({resolve_fallback(primary): [resolve_fallback(b) for b in backups]})

out = {"model_list": models}
for key in ("litellm_settings", "general_settings", "router_settings"):
    if spec.get(key) is not None:
        out[key] = spec[key]

if fallbacks:
    out.setdefault("router_settings", {})["fallbacks"] = fallbacks

with open(dst, "w") as f:
    f.write(f"# AUTO-GENERATED from {src} -- do not edit; edit {src} instead.\n")
    yaml.safe_dump(out, f, sort_keys=False)

print(f"[render] generated {len(models)} models:")
for m in models:
    lp = m["litellm_params"]
    where = lp.get("aws_region_name") or lp.get("api_base", "claude-platform")
    print(f"[render]   {m['model_name']:<22} -> {lp['model']}  ({where})")
if fallbacks:
    print(f"[render] {len(fallbacks)} fallback rule(s):")
    for rule in fallbacks:
        (primary, backups), = rule.items()
        print(f"[render]   {primary:<22} -> {', '.join(backups)}")
