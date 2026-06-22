# Flower AIGC Studio

花花 AIGC 的公开 skill 仓库，用来分享面向 Agent 的商用提效工作流。

这个仓库不是传统 WebUI 或 App 项目，而是给 Codex / Agent 安装和调用的 skill 集合。你可以把整个仓库地址发给 Agent，也可以只发某一个 skill 子目录地址，让 Agent 安装指定工作流。

## 当前包含的 Skill

| Skill | 用途 |
| --- | --- |
| `cloud-womenswear-workbench` | 推荐入口。一个薄客户端发现、询价并运行多个女装云 skill，当前支持对镜自拍、自动街拍和交互式定制街拍。 |

## Quick Start

### 1. 安装统一女装工作台

在 Codex 对话里直接说：

```text
请安装这个 skill：
https://github.com/leo678910/flower-aigc-studio/tree/main/cloud-womenswear-workbench
```

或者在已启用 `skill-installer` 的 Codex 环境里，用它提供的安装脚本安装：

```bash
python scripts/install-skill-from-github.py \
  --repo leo678910/flower-aigc-studio \
  --path cloud-womenswear-workbench
```

安装完成后，重启 Codex，让新 skill 生效。

### 2. 购买体验 API Key

公开仓库不包含服务器地址和 API Key。请联系服务提供方购买或开通体验：

```text
wx:catwde2
```

### 3. 在对话框完成首次配置

拿到服务地址和 API Key 后，只需要在 Codex 对话框发送：

```text
server_url=https://your-fashion-server.example.com
api_key=your_api_key
```

Agent 会自动写入该 skill 本地目录的 `config.toml`，不会回显完整 API Key。以后使用时不需要重复输入。

`config.toml` 已被 `.gitignore` 排除，它是客户本机的私密配置，禁止提交到公开仓库。

### 4. 选择女装工作流

安装并配置后，可以先查看服务器当前提供的 skill 和实时价格：

```text
用 cloud-womenswear-workbench 查看当前可用的女装技能和价格。
```

也可以直接上传女装商品图并提出需求：

```text
用自动街拍基础版处理这张女装图。
```

```text
用高级定制街拍处理这张女装图，每一步让我确认。
```

```text
用对镜自拍素材包处理这张女装图。
```

服务器以后增加新的 `skill_id` 时，薄客户端无需重写。

## 安全说明

- 仓库只发布薄客户端，不包含云端工作流提示词、模型供应商密钥、客户 API Key 或计费逻辑。
- 客户凭据保存在本地 `config.toml`。
- Agent 不应在回复中打印完整 API Key。
- 每次提交计费任务前，客户端应查询服务器当前价格，不依赖本地记忆价格。

## 许可证

本仓库使用 Apache License 2.0。
