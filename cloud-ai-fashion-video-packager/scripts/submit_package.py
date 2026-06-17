from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONFIG_EXAMPLE_PATH = SKILL_ROOT / "config.example.toml"
SERVICE_CONTACT = "wx:catwde2"

STAGE_LABELS = {
    "queued": "排队中",
    "classifying_source": "第1步：识别商品图类型",
    "normalizing_product": "第2步：生成或确认商品白底图",
    "analyzing_product": "第3步：分析服装商品信息",
    "matching_model_scene": "第4步：匹配模特和场景",
    "building_prompts": "第5步：生成提示词和文案",
    "generating_first_frame": "第6步：生成首帧图",
    "generating_cover": "第7步：生成封面图",
    "succeeded": "完成",
    "failed": "失败",
}


INVALID_CREDENTIALS_MESSAGE = (
    "AI Fashion Video Packager 服务地址或 API Key 无效。\n"
    f"请联系服务提供方确认体验包是否已开通：{SERVICE_CONTACT}"
)
NO_CREDITS_MESSAGE = f"AI Fashion Video Packager 剩余额度不足，请联系服务提供方购买体验包：{SERVICE_CONTACT}"
DAILY_LIMIT_MESSAGE = f"AI Fashion Video Packager 今日额度已用完，请明天再试或联系服务提供方：{SERVICE_CONTACT}"
TASK_FAILED_MESSAGE = "任务失败，请重试。"


def _purchase_message() -> str:
    return (
        "AI Fashion Video Packager 尚未配置。\n"
        "可以直接在当前对话框发送服务地址和 API Key，例如：server_url=https://... api_key=your_api_key\n"
        "Agent 收到后应使用 --base-url / --api-key / --save-config 保存到本地 config.toml，"
        "然后继续提交任务；后续不需要重复输入。\n"
        "如果还没有体验包，请联系服务提供方获取服务器地址和 API Key："
        f"{SERVICE_CONTACT}\n"
        "也可以做持久配置：复制 config.example.toml 为 config.toml 后填写 [service].server_url / [service].api_key，"
        "或设置环境变量 AI_FASHION_SERVER_URL / AI_FASHION_API_KEY。\n"
        f"配置模板：{CONFIG_EXAMPLE_PATH}"
    )


def _default_config_paths() -> list[Path]:
    paths = [SKILL_ROOT / "config.toml"]
    appdata = os.getenv("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "ai-fashion-video-packager" / "config.toml")
    paths.append(Path.home() / ".config" / "ai-fashion-video-packager" / "config.toml")
    return paths


def _resolve_config_path(value: str | None, for_write: bool = False) -> Path | None:
    configured = value or os.getenv("AI_FASHION_CONFIG")
    if configured:
        return Path(configured).expanduser()
    existing = next((path for path in _default_config_paths() if path.exists()), None)
    if existing:
        return existing
    return SKILL_ROOT / "config.toml" if for_write else None


def _load_config(value: str | None, allow_missing: bool = False) -> dict[str, Any]:
    config_path = _resolve_config_path(value)
    if config_path is None:
        return {}
    if not config_path.exists():
        if allow_missing:
            return {}
        raise SystemExit(f"配置文件不存在：{config_path}")
    try:
        with config_path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"配置文件格式错误：{config_path}") from exc
    except OSError as exc:
        raise SystemExit(f"无法读取配置文件：{config_path}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"配置文件格式错误：{config_path}")
    return data


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _config_download_dir(config: dict[str, Any]) -> str:
    download = config.get("download") if isinstance(config.get("download"), dict) else {}
    value = download.get("dir") if isinstance(download, dict) else None
    return str(value).strip() if value else ""


def save_config(
    config_path: Path,
    base_url: str,
    api_key: str,
    existing_config: dict[str, Any],
    download_dir: str | None = None,
) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_download_dir = (download_dir or _config_download_dir(existing_config)).strip()
    lines = [
        "# Local credentials for Cloud AI Fashion Video Packager.",
        "# Do not commit this file.",
        "",
        "[service]",
        f"server_url = {_toml_string(base_url)}",
        f"api_key = {_toml_string(api_key)}",
        "",
    ]
    if resolved_download_dir:
        lines.extend(
            [
                "[download]",
                f"dir = {_toml_string(resolved_download_dir)}",
                "",
            ]
        )
    config_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"配置已保存：{config_path}", file=sys.stderr, flush=True)


def _config_service_value(config: dict[str, Any], *keys: str) -> str:
    service = config.get("service") if isinstance(config.get("service"), dict) else {}
    for key in keys:
        value = service.get(key) or config.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {
        "",
        "https://your-fashion-server.example.com",
        "your_api_key",
        "your-api-key",
    }


def _server_url(value: str | None, config: dict[str, Any]) -> str:
    base_url = (
        value
        or os.getenv("AI_FASHION_SERVER_URL")
        or _config_service_value(config, "server_url", "base_url", "url")
        or ""
    ).strip().rstrip("/")
    if _is_placeholder(base_url):
        raise SystemExit(_purchase_message())
    return base_url


def _api_key(value: str | None, config: dict[str, Any]) -> str:
    key = (value or os.getenv("AI_FASHION_API_KEY") or _config_service_value(config, "api_key") or "").strip()
    if _is_placeholder(key):
        raise SystemExit(_purchase_message())
    return key


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _raise_for_http_error(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = response.status_code
        if status_code in (401, 403):
            raise SystemExit(INVALID_CREDENTIALS_MESSAGE) from exc
        if status_code == 402:
            raise SystemExit(NO_CREDITS_MESSAGE) from exc
        raise


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def check_quota(base_url: str, api_key: str, show_progress: bool = True) -> dict[str, Any]:
    try:
        response = requests.get(f"{base_url}/v1/account/quota", headers=_headers(api_key), timeout=30)
        _raise_for_http_error(response)
    except requests.RequestException as exc:
        raise SystemExit(
            "无法连接 AI Fashion Video Packager 服务器，请检查 AI_FASHION_SERVER_URL，"
            "或联系服务提供方确认体验包是否已开通。"
        ) from exc

    try:
        quota = response.json()
    except ValueError as exc:
        raise SystemExit("额度检查失败，请联系服务提供方确认服务器配置。") from exc
    status = str(quota.get("status") or "").lower()
    if status and status != "active":
        raise SystemExit(INVALID_CREDENTIALS_MESSAGE)

    remaining_credits = _as_int(quota.get("remaining_credits"))
    if remaining_credits is not None and remaining_credits <= 0:
        raise SystemExit(NO_CREDITS_MESSAGE)

    daily_limit = _as_int(quota.get("daily_limit"))
    daily_used = _as_int(quota.get("daily_used"))
    if daily_limit is not None and daily_limit > 0 and daily_used is not None and daily_used >= daily_limit:
        raise SystemExit(DAILY_LIMIT_MESSAGE)

    if show_progress and remaining_credits is not None:
        frozen_credits = _as_int(quota.get("frozen_credits")) or 0
        print(
            f"额度检查通过：剩余额度={remaining_credits}，冻结额度={frozen_credits}",
            file=sys.stderr,
            flush=True,
        )
    return quota


def submit_task(base_url: str, api_key: str, image_path: Path, style_hint: str) -> str:
    try:
        with image_path.open("rb") as image_file:
            response = requests.post(
                f"{base_url}/v1/tasks",
                headers=_headers(api_key),
                data={"style_hint": style_hint},
                files={"image": (image_path.name, image_file, "application/octet-stream")},
                timeout=60,
            )
        _raise_for_http_error(response)
    except requests.RequestException as exc:
        raise SystemExit("任务提交失败，请稍后重试。") from exc
    return response.json()["task_id"]


def _print_progress(task_id: str, payload: dict[str, Any], started_at: float) -> None:
    status = payload.get("status", "")
    stage = payload.get("stage") or status
    label = STAGE_LABELS.get(stage, stage)
    elapsed = int(time.time() - started_at)
    print(f"[{elapsed:>4}s] {task_id} {status}/{stage} - {label}", file=sys.stderr, flush=True)


def poll_task(
    base_url: str,
    api_key: str,
    task_id: str,
    timeout: int,
    poll_interval: float,
    show_progress: bool = True,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    started_at = time.time()
    last_status: dict[str, Any] = {}
    last_seen: tuple[str | None, str | None] = (None, None)
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/v1/tasks/{task_id}", headers=_headers(api_key), timeout=60)
            _raise_for_http_error(response)
        except requests.RequestException as exc:
            raise SystemExit(TASK_FAILED_MESSAGE) from exc
        last_status = response.json()
        status = last_status.get("status")
        stage = last_status.get("stage")
        seen = (status, stage)
        if show_progress and seen != last_seen:
            _print_progress(task_id, last_status, started_at)
            last_seen = seen
        if status == "succeeded":
            try:
                result = requests.get(f"{base_url}/v1/tasks/{task_id}/result", headers=_headers(api_key), timeout=60)
                _raise_for_http_error(result)
            except requests.RequestException as exc:
                raise SystemExit(TASK_FAILED_MESSAGE) from exc
            return result.json()
        if status == "failed":
            raise SystemExit(TASK_FAILED_MESSAGE)
        time.sleep(poll_interval)
    raise SystemExit(f"Timed out waiting for task {task_id}; last status: {last_status}")


def _download_root(value: str | None, config: dict[str, Any]) -> Path:
    download_config = config.get("download") if isinstance(config.get("download"), dict) else {}
    configured = value or os.getenv("AI_FASHION_DOWNLOAD_DIR") or download_config.get("dir")
    if configured:
        return Path(configured)
    return Path.cwd() / "temp" / "cloud-fashion-results"


def _image_suffix(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix else ".png"


def download_result_images(result: dict[str, Any], task_id: str, download_root: Path) -> dict[str, Any]:
    task_dir = download_root / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "product_image_url": ("product_image_path", "product-white"),
        "cover_image_url": ("cover_image_path", "cover"),
        "first_frame_url": ("first_frame_path", "first-frame"),
    }
    for url_key, (path_key, stem) in targets.items():
        url = result.get(url_key)
        if not url:
            continue
        output_path = task_dir / f"{stem}{_image_suffix(str(url))}"
        try:
            response = requests.get(str(url), timeout=90)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SystemExit("结果图片下载失败，请重试。") from exc
        output_path.write_bytes(response.content)
        result[path_key] = str(output_path.resolve())
    result["local_download_dir"] = str(task_dir.resolve())
    return result


def _display_path(result: dict[str, Any], local_key: str, url_key: str) -> str:
    value = result.get(local_key) or result.get(url_key) or ""
    if local_key in result and value:
        return Path(str(value)).as_posix()
    return str(value)


def render_markdown(result: dict[str, Any]) -> str:
    copy = result.get("copywriting") or {}
    hashtags = copy.get("hashtags") or []
    hashtags_text = " ".join(str(tag) for tag in hashtags) if isinstance(hashtags, list) else str(hashtags)
    return "\n".join(
        [
            "## Product Image",
            f"![product]({_display_path(result, 'product_image_path', 'product_image_url')})",
            f"Path: {result.get('product_image_path', '')}",
            f"URL: {result.get('product_image_url', '')}",
            "",
            "## Cover Image",
            f"![cover]({_display_path(result, 'cover_image_path', 'cover_image_url')})",
            f"Path: {result.get('cover_image_path', '')}",
            f"URL: {result.get('cover_image_url', '')}",
            "",
            "## First Frame",
            f"![first frame]({_display_path(result, 'first_frame_path', 'first_frame_url')})",
            f"Path: {result.get('first_frame_path', '')}",
            f"URL: {result.get('first_frame_url', '')}",
            "",
            "## Image-To-Video Prompt",
            str(result.get("video_prompt", "")),
            "",
            "## Title Description Tags",
            f"Title: {copy.get('title', '')}",
            "",
            "Description:",
            str(copy.get("description", "")),
            "",
            f"Tags: {hashtags_text}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a fashion video package task to the server.")
    parser.add_argument("--image", required=True, help="Local product image path.")
    parser.add_argument("--style-hint", default="", help="Optional style/scene hint.")
    parser.add_argument("--config", default=None, help="Path to config.toml. Defaults to the skill config.toml.")
    parser.add_argument("--base-url", default=None, help="Override AI_FASHION_SERVER_URL.")
    parser.add_argument("--api-key", default=None, help="Override AI_FASHION_API_KEY.")
    parser.add_argument("--save-config", action="store_true", help="Save --base-url/--api-key to config.toml.")
    parser.add_argument("--save-config-only", action="store_true", help="Save config and exit without submitting a task.")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--download-dir", default=None, help="Directory for downloaded result images.")
    parser.add_argument("--no-download", action="store_true", help="Do not download result images locally.")
    parser.add_argument("--no-progress", action="store_true", help="Do not print task stage updates to stderr.")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image does not exist: {image_path}")

    config = _load_config(args.config, allow_missing=args.save_config or args.save_config_only)
    base_url = _server_url(args.base_url, config)
    api_key = _api_key(args.api_key, config)
    if args.save_config or args.save_config_only:
        save_config(
            _resolve_config_path(args.config, for_write=True) or (SKILL_ROOT / "config.toml"),
            base_url,
            api_key,
            config,
            args.download_dir,
        )
    if args.save_config_only:
        return
    check_quota(base_url, api_key, show_progress=not args.no_progress)
    task_id = submit_task(base_url, api_key, image_path, args.style_hint)
    if not args.no_progress:
        print(f"submitted task: {task_id}", file=sys.stderr, flush=True)
    result = poll_task(
        base_url,
        api_key,
        task_id,
        args.timeout,
        args.poll_interval,
        show_progress=not args.no_progress,
    )
    if not args.no_download:
        result = download_result_images(result, task_id, _download_root(args.download_dir, config))

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_markdown(result))


if __name__ == "__main__":
    main()
