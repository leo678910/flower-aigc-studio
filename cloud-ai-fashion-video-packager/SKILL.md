---
name: cloud-ai-fashion-video-packager
description: Upload women's clothing product images to the configured AI fashion video package server and return ready-to-use assets. Use when Codex should call a local or cloud fashion service to create a normalized product image, cover image, first-frame image, image-to-video prompt, and Xiaohongshu/Douyin title-description-hashtag block from a product image, especially when the user wants an Agent-facing workflow instead of a Web UI.
---

# Cloud AI Fashion Video Packager

## Overview

Use this skill as a thin Agent client for the AI fashion video package server. The server owns authentication, credits, product normalization, model/scene matching, prompts, image generation, and result storage; this skill only submits product images and returns the completed package.

Do not place provider API keys in distributed or versioned skill files. A filled `config.toml` is user-specific local configuration and should not be bundled for customers.

Service contact: `wx:catwde2`.

## Configuration

Recommended for repeated use: copy `config.example.toml` to `config.toml` in this skill folder and fill in the values from the service provider:

```text
[service]
server_url = "https://your-fashion-server.example.com"
api_key = "your_api_key"

[download]
# Optional.
# dir = "C:/path/to/cloud-fashion-results"
```

Configuration precedence is: command arguments, environment variables, then TOML config file.

Supported environment variables:

```text
AI_FASHION_CONFIG=C:\path\to\config.toml
AI_FASHION_SERVER_URL=https://your-fashion-server.example.com
AI_FASHION_API_KEY=your_api_key
AI_FASHION_DOWNLOAD_DIR=C:\path\to\cloud-fashion-results
```

If credentials are missing or still placeholders, ask the user to provide the service URL and API Key directly in the current conversation. Accept short messages such as `server_url=... api_key=...`, then call the script with `--base-url`, `--api-key`, and `--save-config` so the values are saved to local `config.toml` for future runs. Do not print the full API key back to the user.

If the user does not have credentials yet, tell them to contact the service provider: `wx:catwde2`.

## Workflow

1. Confirm the product image path is local and readable. If the image is on a network path, copy it into the workspace first when needed.
2. Call `scripts/submit_package.py` with the image path and optional style hint.
3. The script loads config from `--config`, `AI_FASHION_CONFIG`, the skill `config.toml`, or a user config directory; then it checks the server URL and API key.
4. The script calls `/v1/account/quota` to confirm the account is active and has remaining credits.
5. Wait for the task to finish. The script polls `/v1/tasks/{task_id}` and then fetches `/v1/tasks/{task_id}/result`.
6. Download returned image URLs into a local result directory, then render local image paths in markdown so Codex Desktop can display them reliably.
7. Return only the package outputs by default:
   - normalized product image URL/path
   - cover image URL/path
   - first-frame image URL/path
   - image-to-video prompt
   - title, description, and hashtags
8. If configuration is missing, ask the user to paste the service URL and API Key in chat, save them with `--save-config`, then continue the task. If they do not have credentials, contact `wx:catwde2` for a trial package. If the service returns `failed`, report `任务失败，请重试。` and do not invent outputs.

## Script Usage

```powershell
python $SKILL_DIR\scripts\submit_package.py `
  --image C:\path\to\product.jpg `
  --base-url https://your-fashion-server.example.com `
  --api-key your_api_key `
  --save-config `
  --style-hint "summer cafe outfit" `
  --format markdown
```

Optional arguments:

- `--config`: path to a TOML config file; overrides `AI_FASHION_CONFIG`
- `--base-url`: overrides `AI_FASHION_SERVER_URL`
- `--api-key`: overrides `AI_FASHION_API_KEY`
- `--save-config`: saves the resolved service URL and API key to local `config.toml`
- `--save-config-only`: saves config and exits without submitting a task
- `--timeout`: total seconds to wait
- `--poll-interval`: seconds between status checks
- `--download-dir`: local directory for downloaded result images; defaults to `./temp/cloud-fashion-results`
- `--no-download`: disables local image download and renders remote URLs directly
- `--no-progress`: disables Chinese task-stage progress logs on stderr
- `--format json|markdown`

## Output Rules

When answering the user after a successful call, keep the response compact. Prefer five sections:

```markdown
## Product Image
...
## Cover Image
...
## First Frame
...
## Image-To-Video Prompt
...
## Title Description Tags
...
```

If returned image URLs point to the local service `/files/...`, keep the full URL returned by the server.
