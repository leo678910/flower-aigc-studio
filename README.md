# Flower AIGC Studio

花花 AIGC 的公开 skill 仓库，用来分享面向 Agent 的商用提效工作流。

这个仓库不是传统 WebUI 或 App 项目，而是给 Codex / Agent 安装和调用的 skill 集合。你可以把整个仓库地址发给 Agent，也可以只发某一个 skill 子目录地址，让 Agent 安装指定工作流。

## 当前包含的 Skill

| Skill | 用途 |
| --- | --- |
| `cloud-ai-fashion-video-packager` | 上传女装商品图到云端服务，返回商品白底图、封面图、首帧图、图生视频提示词、小红书/抖音标题文案标签。 |

## Quick Start

### 1. 安装 Skill

在 Codex 对话里直接说：

```text
请安装这个 skill：
https://github.com/leo678910/flower-aigc-studio/tree/main/cloud-ai-fashion-video-packager
```

或者在已启用 `skill-installer` 的 Codex 环境里，用它提供的安装脚本安装：

```bash
python scripts/install-skill-from-github.py \
  --repo leo678910/flower-aigc-studio \
  --path cloud-ai-fashion-video-packager
```

安装完成后，重启 Codex，让新 skill 生效。

### 2. 首次配置服务地址和 API Key

第一次使用时，如果还没有配置服务地址和 API Key，Agent 会让你在对话框里直接发送：

```text
server_url=https://your-fashion-server.example.com
api_key=your_api_key
```

Agent 会自动把这两个值保存到本地 `config.toml`，以后就不用每次重复输入。

也可以手动复制 skill 目录里的 `config.example.toml` 为 `config.toml`，然后填写：

```toml
[service]
server_url = "https://your-fashion-server.example.com"
api_key = "your_api_key"
```

注意：`config.toml` 是本地私密配置，不要提交到公开仓库。

### 3. 使用云端女装工作流

安装并配置后，在 Codex 对话里上传或指定一张女装商品图，然后说：

```text
用 cloud-ai-fashion-video-packager 跑一遍云端女装工作流。
```

正常会返回：

- 商品白底图
- 封面图
- 9:16 首帧图
- 图生视频提示词
- 标题、描述、标签文案

## 联系方式

体验包、API Key、服务开通：

```text
wx:catwde2
```

## 许可证

本仓库使用 Apache License 2.0。
