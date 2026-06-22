---
name: cloud-womenswear-workbench
description: Use one Agent-facing client to discover, price, and run multiple womenswear cloud skills by skill_id, including mirror-selfie packaging, automatic street-shot packages, and interactive custom street-shot workflows with multi-turn actions. Use when Codex should route an uploaded womenswear image to the appropriate server skill, inspect available skills and point prices, poll tasks, continue required confirmations, or download final assets through one shared configuration.
---

# 通用女装云工作台

Use this as the single thin client for all womenswear skills exposed by the
configured server. The server owns workflows, prompts, providers, billing, and
task state. This client owns routing, polling, interactive actions, and local
downloads.

Never place provider credentials or a customer's filled `config.toml` in a
distributed or versioned skill.

Service/API Key purchase and trial contact: `wx:catwde2`.

## First-Run Configuration

Customers do not receive a server address or API Key with the public skill.
If credentials are missing or still placeholders:

1. Tell the customer to contact `wx:catwde2` to purchase an API Key or request
   a trial.
2. Ask them to paste both values directly into the current conversation. Accept
   compact messages such as:

   ```text
   server_url=https://your-fashion-server.example.com
   api_key=your_api_key
   ```

3. After receiving both values, automatically run:

   ```powershell
   python "$SKILL_DIR\scripts\womenswear_workbench.py" configure `
     --base-url "CUSTOMER_SERVER_URL" `
     --api-key "CUSTOMER_API_KEY"
   ```

4. Confirm only that the local configuration was saved. Never echo the complete
   API Key back to the customer.
5. Continue the original task without asking the customer to edit files or run
   commands manually.

The `configure` command saves to the skill's local `config.toml` by default.
That file is ignored by Git. A custom path can be supplied with `--config`.

## Routing

Map customer intent to the server skill:

| Customer intent | `skill_id` or alias |
| --- | --- |
| 女装对镜自拍、首帧封面素材包 | `mirror` |
| 街拍自动版、基础体验版、一键街拍 | `auto` |
| 街拍高级版、定制版、需要逐步确认 | `custom` |

Aliases resolve to:

- `mirror` → `ai-fashion-video-packager`
- `auto` → `flower-aigc-womenswear-streetshot-auto`
- `custom` → `flower-aigc-womenswear-streetshot`

For a new server skill, pass its complete `skill_id`; the client does not need
to be rewritten.

## Required Workflow

1. If intent is ambiguous, run `skills` and present the available choices.
2. Before a billable submission, run `price --skill-id ...` and tell the user
   the current database price. Do not rely on a remembered price.
3. After the user chooses the SKU, run `start`.
4. For noninteractive skills, wait until completion and present downloaded
   outputs.
5. For an interactive task, stop at `waiting_for_input`, present
   `required_action`, and only call `action` after receiving the user's choice.
6. Never invent a result or bypass a required confirmation.

## Result Delivery

When the result contains `video_prompt`, include the complete prompt directly
in the final response inside a fenced Markdown `text` code block so the UI
provides one-click copy. Do not return only a file link. Also provide the saved
prompt file link when available.

## Commands

```powershell
python "$SKILL_DIR\scripts\womenswear_workbench.py" skills --format markdown

python "$SKILL_DIR\scripts\womenswear_workbench.py" price `
  --skill-id auto --format markdown

python "$SKILL_DIR\scripts\womenswear_workbench.py" start `
  --skill-id auto `
  --image C:\path\to\product.jpg `
  --style-hint "可选风格要求" `
  --format json
```

The mirror-selfie skill also accepts:

```text
--model-image C:\path\to\model-reference.jpg
--save-model
--no-save-model
```

Continue an interactive task:

```powershell
python "$SKILL_DIR\scripts\womenswear_workbench.py" action `
  --task-id task_xxx `
  --action select_generated_model `
  --choice A `
  --format json
```

Shot and scene selection can use repeated flags:

```text
--shot A01 --shot B01 --shot C02 --shot D03 --shot G01
--scene-id SH_JINGAN_COMMUTER_STONE_STREET
```

Use `--attachment` for fixed-model images or returned videos.

## Configuration Reference

Primary environment variables:

```text
WOMENSWEAR_CLOUD_SERVER_URL
WOMENSWEAR_CLOUD_API_KEY
WOMENSWEAR_CLOUD_DOWNLOAD_DIR
WOMENSWEAR_CLOUD_CONFIG
```

The client may reuse an existing street-shot or mirror-selfie `config.toml`.
Configuration precedence is command arguments, environment variables, then
TOML configuration.

Never print the complete API Key in the final response.
