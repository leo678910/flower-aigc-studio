from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib
from typing import Any, Iterator
from urllib.parse import urlparse
import uuid

try:
    import requests
except ModuleNotFoundError:
    requests = None  # type: ignore[assignment]


CLIENT_NAME = "cloud-womenswear-workbench"
CLIENT_VERSION = "1.1.0"
SERVICE_CONTACT = "wx:catwde2"
SKILL_ROOT = Path(__file__).resolve().parents[1]
CONFIG_EXAMPLE_PATH = SKILL_ROOT / "config.example.toml"

SKILL_ALIASES = {
    "mirror": "ai-fashion-video-packager",
    "selfie": "ai-fashion-video-packager",
    "对镜自拍": "ai-fashion-video-packager",
    "auto": "flower-aigc-womenswear-streetshot-auto",
    "streetshot-auto": "flower-aigc-womenswear-streetshot-auto",
    "街拍自动版": "flower-aigc-womenswear-streetshot-auto",
    "custom": "flower-aigc-womenswear-streetshot",
    "advanced": "flower-aigc-womenswear-streetshot",
    "streetshot": "flower-aigc-womenswear-streetshot",
    "街拍高级版": "flower-aigc-womenswear-streetshot",
}

STAGE_LABELS = {
    "queued": "任务已排队",
    "classifying_source": "识别商品图类型",
    "normalizing_product": "生成或确认商品白底图",
    "analyzing_product": "分析服装商品",
    "matching_model_scene": "匹配模特和场景",
    "analyzing_model": "分析用户模特",
    "building_prompts": "生成提示词和文案",
    "generating_first_frame": "生成首帧图",
    "generating_cover": "生成封面图",
    "building_model_recommendations": "生成三套模特方向",
    "awaiting_model_decision": "等待选择固定模特或 A/B/C",
    "analyzing_fixed_model": "分析固定模特",
    "generating_model_pair": "生成模特参考图",
    "regenerating_model_pair": "重新生成模特参考图",
    "awaiting_model_confirmation": "等待确认模特",
    "confirming_model": "锁定模特",
    "awaiting_route": "等待选择静态或动态路线",
    "building_route_outline": "生成路线、场景和分镜建议",
    "awaiting_shot_selection": "等待选择五个分镜和场景",
    "producing_script_assets_and_scenes": "生成脚本资产和场景",
    "regenerating_script_assets_and_scenes": "重新生成脚本资产",
    "awaiting_asset_confirmation": "等待确认资产",
    "building_final_video_prompt": "生成完整十五秒提示词",
    "analyzing_returned_video": "分析返回视频",
    "qc_completed": "返回视频质检完成",
    "auto_analyzing_product": "自动分析服装商品",
    "auto_planning_streetshot": "自动选择模特、路线、场景和分镜",
    "auto_generating_model": "生成模特多视图",
    "auto_generating_assets": "生成服装资产板和场景",
    "auto_building_final_prompt": "生成最终视频提示词",
    "succeeded": "任务完成",
    "failed": "任务失败",
}


def normalize_skill_id(value: str) -> str:
    normalized = value.strip()
    return SKILL_ALIASES.get(normalized.lower(), SKILL_ALIASES.get(normalized, normalized))


def _onboarding_message() -> str:
    return (
        "通用女装云工作台尚未配置。\n"
        f"请联系 {SERVICE_CONTACT} 购买 API Key 或申请体验，并获取 server_url。\n"
        "拿到后直接在当前对话框发送：\n"
        "server_url=https://...\n"
        "api_key=your_api_key\n"
        "Agent 会自动保存到本地 config.toml，后续无需重复输入，也不会回显完整 API Key。\n"
        f"手动配置模板：{CONFIG_EXAMPLE_PATH}"
    )


def _default_config_paths() -> list[Path]:
    codex_home = Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")
    paths = [
        SKILL_ROOT / "config.toml",
        codex_home / "skills" / "cloud-flower-womenswear-streetshot" / "config.toml",
        codex_home / "skills" / "cloud-ai-fashion-video-packager" / "config.toml",
    ]
    appdata = os.getenv("APPDATA")
    if appdata:
        paths.append(Path(appdata) / CLIENT_NAME / "config.toml")
    paths.append(Path.home() / ".config" / CLIENT_NAME / "config.toml")
    return paths


def _config_path(value: str | None, *, for_write: bool = False) -> Path | None:
    configured = value or os.getenv("WOMENSWEAR_CLOUD_CONFIG")
    if configured:
        return Path(configured).expanduser()
    if for_write:
        return SKILL_ROOT / "config.toml"
    existing = next((path for path in _default_config_paths() if path.exists()), None)
    if existing:
        return existing
    return None


def _load_config(value: str | None) -> dict[str, Any]:
    path = _config_path(value)
    if not path:
        return {}
    if not path.exists():
        raise SystemExit(f"配置文件不存在：{path}\n{_onboarding_message()}")
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"无法读取配置文件：{path}") from exc
    return data if isinstance(data, dict) else {}


def _service_value(config: dict[str, Any], key: str) -> str:
    service = config.get("service")
    if not isinstance(service, dict):
        service = {}
    return str(service.get(key) or config.get(key) or "").strip()


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() in {
        "",
        "your_api_key",
        "your-api-key",
        "https://your-fashion-server.example.com",
    }


def _validated_credentials(base_url: str, api_key: str) -> tuple[str, str]:
    normalized_url = base_url.strip().rstrip("/")
    normalized_key = api_key.strip()
    if _is_placeholder(normalized_url) or _is_placeholder(normalized_key):
        raise SystemExit(_onboarding_message())
    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("server_url 格式不正确，必须是完整的 http:// 或 https:// 地址。")
    return normalized_url, normalized_key


def _credentials(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> tuple[str, str]:
    base_url = (
        args.base_url
        or os.getenv("WOMENSWEAR_CLOUD_SERVER_URL")
        or os.getenv("FLOWER_STREETSHOT_SERVER_URL")
        or os.getenv("AI_FASHION_SERVER_URL")
        or _service_value(config, "server_url")
    )
    api_key = (
        args.api_key
        or os.getenv("WOMENSWEAR_CLOUD_API_KEY")
        or os.getenv("FLOWER_STREETSHOT_API_KEY")
        or os.getenv("AI_FASHION_API_KEY")
        or _service_value(config, "api_key")
    )
    return _validated_credentials(base_url, api_key)


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _save_config(path: Path, base_url: str, api_key: str, download_dir: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Local credentials for Cloud Womenswear Workbench.",
        "# Do not commit this file.",
        "",
        "[service]",
        f"server_url = {_toml_string(base_url)}",
        f"api_key = {_toml_string(api_key)}",
        "",
    ]
    if download_dir:
        lines.extend(["[download]", f"dir = {_toml_string(download_dir)}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _headers(api_key: str, idempotency_key: str = "") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _require_requests() -> None:
    if requests is None:
        raise SystemExit(
            "缺少 Python 依赖 requests。请先运行：python -m pip install requests"
        )


def _error_message(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = response.text
    if isinstance(detail, dict):
        return json.dumps(detail, ensure_ascii=False)
    return str(detail or response.text or f"HTTP {response.status_code}")


def _check_response(response: requests.Response) -> None:
    if response.status_code < 400:
        return
    message = _error_message(response)
    if response.status_code in {401, 403}:
        raise SystemExit(
            "服务地址或 API Key 无效，或当前 Key 无权使用该技能。"
            f"如需开通请联系 {SERVICE_CONTACT}。"
        )
    if response.status_code == 402:
        raise SystemExit(f"积分不足：{message}")
    if response.status_code == 409:
        raise SystemExit(f"当前任务状态不接受该操作：{message}")
    if response.status_code == 429:
        raise SystemExit(f"已达到并发或每日限额：{message}")
    raise SystemExit(f"服务请求失败（HTTP {response.status_code}）：{message}")


def _request_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    _require_requests()
    try:
        response = requests.request(method, url, **kwargs)
    except requests.RequestException as exc:
        raise SystemExit(f"无法连接女装云服务：{exc}") from exc
    _check_response(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit("服务器返回了无法解析的响应。") from exc
    if not isinstance(payload, dict):
        raise SystemExit("服务器返回格式错误。")
    return payload


def _catalog(base_url: str, api_key: str) -> list[dict[str, Any]]:
    payload = _request_json(
        "GET",
        f"{base_url}/v1/skills",
        headers=_headers(api_key),
        timeout=30,
    )
    skills = payload.get("skills")
    if not isinstance(skills, list):
        raise SystemExit("服务器技能目录格式错误。")
    return [item for item in skills if isinstance(item, dict)]


def _skill(
    base_url: str,
    api_key: str,
    skill_id: str,
) -> dict[str, Any]:
    return _request_json(
        "GET",
        f"{base_url}/v1/skills/{normalize_skill_id(skill_id)}",
        headers=_headers(api_key),
        timeout=30,
    )


def _print_progress(payload: dict[str, Any], started_at: float) -> None:
    stage = str(payload.get("stage") or payload.get("status") or "")
    print(
        f"[{int(time.time() - started_at):>4}s] "
        f"{payload.get('task_id', '')} "
        f"{payload.get('status', '')}/{stage} - "
        f"{STAGE_LABELS.get(stage, stage)}",
        file=sys.stderr,
        flush=True,
    )


def _poll(
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: int,
    interval: float,
    show_progress: bool,
) -> dict[str, Any]:
    terminal = {"waiting_for_input", "succeeded", "failed"}
    started_at = time.time()
    deadline = started_at + timeout
    current = payload
    last_seen: tuple[str, str] | None = None
    while True:
        seen = (str(current.get("status", "")), str(current.get("stage", "")))
        if show_progress and seen != last_seen:
            _print_progress(current, started_at)
            last_seen = seen
        if current.get("status") in terminal:
            if current.get("status") == "failed":
                raise SystemExit(
                    f"任务失败：{current.get('error_message') or '服务器未提供错误详情'}"
                )
            return current
        if time.time() >= deadline:
            raise SystemExit(
                f"等待任务超时；最后状态={current.get('status')}/{current.get('stage')}"
            )
        time.sleep(interval)
        current = _request_json(
            "GET",
            f"{base_url}/v1/tasks/{current['task_id']}",
            headers=_headers(api_key),
            timeout=60,
        )


def _start_task(
    args: argparse.Namespace,
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    skill_id = normalize_skill_id(args.skill_id)
    definition = _skill(base_url, api_key, skill_id)
    accepted = set(definition.get("accepted_inputs") or [])
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise SystemExit(f"商品图不存在：{image}")
    model = Path(args.model_image).expanduser().resolve() if args.model_image else None
    if model and not model.is_file():
        raise SystemExit(f"模特图不存在：{model}")
    if model and "model_image" not in accepted:
        raise SystemExit(f"技能 {skill_id} 不接受 --model-image。")
    operation = str(definition.get("initial_operation") or "")
    points = (definition.get("pricing") or {}).get(operation, definition.get("price_points"))
    print(
        f"提交技能：{definition.get('name', skill_id)}；当前起始价格：{points} 积分。",
        file=sys.stderr,
        flush=True,
    )
    idempotency_key = args.idempotency_key or f"workbench-start-{uuid.uuid4().hex}"
    with ExitStack() as stack:
        files: dict[str, tuple[str, Any, str]] = {
            "image": (
                image.name,
                stack.enter_context(image.open("rb")),
                "application/octet-stream",
            )
        }
        if model:
            files["model_image"] = (
                model.name,
                stack.enter_context(model.open("rb")),
                "application/octet-stream",
            )
        payload = _request_json(
            "POST",
            f"{base_url}/v1/skills/{skill_id}/tasks",
            headers=_headers(api_key, idempotency_key),
            data={
                "style_hint": args.style_hint,
                "save_model": "true" if args.save_model else "false",
                "client_name": CLIENT_NAME,
                "client_version": CLIENT_VERSION,
            },
            files=files,
            timeout=120,
        )
    payload["idempotency_key"] = idempotency_key
    payload["quoted_price_points"] = points
    return payload


def _action_task(
    args: argparse.Namespace,
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    payload_text = args.payload_json or "{}"
    if args.payload_file:
        payload_path = Path(args.payload_file).expanduser().resolve()
        if not payload_path.is_file():
            raise SystemExit(f"payload 文件不存在：{payload_path}")
        payload_text = payload_path.read_text(encoding="utf-8")
    try:
        action_payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise SystemExit("--payload-json/--payload-file 必须包含 JSON 对象。") from exc
    if not isinstance(action_payload, dict):
        raise SystemExit("--payload-json/--payload-file 必须包含 JSON 对象。")
    if args.shot:
        action_payload["shots"] = args.shot
    if args.scene_id:
        action_payload["scene_ids"] = args.scene_id
    if args.notes:
        action_payload["notes"] = args.notes
    attachments = [Path(item).expanduser().resolve() for item in args.attachment]
    missing = [str(path) for path in attachments if not path.is_file()]
    if missing:
        raise SystemExit("附件不存在：" + "；".join(missing))
    idempotency_key = args.idempotency_key or f"workbench-action-{uuid.uuid4().hex}"
    with ExitStack() as stack:
        files = [
            (
                "attachments",
                (
                    path.name,
                    stack.enter_context(path.open("rb")),
                    "application/octet-stream",
                ),
            )
            for path in attachments
        ]
        payload = _request_json(
            "POST",
            f"{base_url}/v1/tasks/{args.task_id}/actions",
            headers=_headers(api_key, idempotency_key),
            data={
                "action": args.action,
                "choice": args.choice,
                "payload_json": json.dumps(action_payload, ensure_ascii=False),
            },
            files=files or None,
            timeout=120,
        )
    payload["idempotency_key"] = idempotency_key
    return payload


def _download_root(args: argparse.Namespace, config: dict[str, Any]) -> Path:
    download = config.get("download")
    if not isinstance(download, dict):
        download = {}
    configured = (
        args.download_dir
        or os.getenv("WOMENSWEAR_CLOUD_DOWNLOAD_DIR")
        or os.getenv("FLOWER_STREETSHOT_DOWNLOAD_DIR")
        or os.getenv("AI_FASHION_DOWNLOAD_DIR")
        or download.get("dir")
    )
    if configured:
        return Path(str(configured)).expanduser()
    return Path.cwd() / "temp" / "cloud-womenswear-results"


def _iter_urls(
    value: Any,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_urls(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_urls(item, (*path, str(index)))
    elif isinstance(value, str) and value.startswith(("http://", "https://")):
        key = path[-1].lower() if path else ""
        parent = path[-2].lower() if len(path) > 1 else ""
        if key == "url" or key.endswith("_url") or parent.endswith("_urls"):
            yield path, value


def _safe_name(path: tuple[str, ...], url: str) -> str:
    raw = "-".join(path[-4:]) or "artifact"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._") or "artifact"
    suffix = Path(urlparse(url).path).suffix or ".bin"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{stem[:100]}-{digest}{suffix}"


def _download_outputs(
    payload: dict[str, Any],
    api_key: str,
    root: Path,
) -> dict[str, Any]:
    _require_requests()
    target = (root / str(payload["task_id"])).resolve()
    target.mkdir(parents=True, exist_ok=True)
    local_files: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    for json_path, url in _iter_urls(payload.get("result", {})):
        if url not in seen:
            output = target / _safe_name(json_path, url)
            try:
                response = requests.get(url, headers=_headers(api_key), timeout=120)
            except requests.RequestException as exc:
                raise SystemExit(f"下载结果文件失败：{url} ({exc})") from exc
            _check_response(response)
            output.write_bytes(response.content)
            seen[url] = str(output)
        local_files.append(
            {
                "json_path": ".".join(json_path),
                "url": url,
                "path": seen[url],
            }
        )
    result = payload.get("result")
    prompt = result.get("video_prompt") if isinstance(result, dict) else None
    if isinstance(prompt, str) and prompt.strip():
        prompt_path = target / "video-prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        payload["local_prompt_path"] = str(prompt_path)
    payload["local_files"] = local_files
    payload["local_download_dir"] = str(target)
    return payload


def _render_skills(skills: list[dict[str, Any]]) -> str:
    lines = [
        "# 可用女装云技能",
        "",
        "| 名称 | skill_id | 类型 | 起始价格 |",
        "| --- | --- | --- | ---: |",
    ]
    for item in skills:
        operation = str(item.get("initial_operation") or "")
        points = (item.get("pricing") or {}).get(operation, item.get("price_points", ""))
        mode = "交互定制" if item.get("interactive") else "一次完成"
        lines.append(
            f"| {item.get('name', '')} | `{item.get('id', '')}` | {mode} | {points} 积分 |"
        )
    return "\n".join(lines)


def _render_price(skill: dict[str, Any]) -> str:
    operation = str(skill.get("initial_operation") or "")
    points = (skill.get("pricing") or {}).get(operation, skill.get("price_points"))
    return "\n".join(
        [
            f"# {skill.get('name', skill.get('id', ''))}",
            "",
            f"- skill_id：`{skill.get('id', '')}`",
            f"- 类型：{'交互定制' if skill.get('interactive') else '一次完成'}",
            f"- 起始价格：{points} 积分",
            f"- 计费项：`{operation}`",
        ]
    )


def _markdown_code_block(value: str, language: str = "text") -> str:
    longest_run = max(
        (len(match.group(0)) for match in re.finditer(r"`+", value)),
        default=0,
    )
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}{language}\n{value}\n{fence}"


def _render_task(payload: dict[str, Any]) -> str:
    stage = str(payload.get("stage") or "")
    lines = [
        f"# 女装云任务 {payload.get('task_id', '')}",
        "",
        f"- skill_id：`{payload.get('skill_id', '')}`",
        f"- 状态：{payload.get('status', '')}",
        f"- 阶段：{stage} / {STAGE_LABELS.get(stage, stage)}",
        f"- 已计费积分：{payload.get('points_charged', 0)}",
    ]
    required = payload.get("required_action")
    if required:
        lines.extend(
            [
                "",
                "## 等待用户操作",
                "",
                "```json",
                json.dumps(required, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    local_files = payload.get("local_files") or []
    if local_files:
        lines.extend(["", "## 本地产物", ""])
        shown: set[str] = set()
        for item in local_files:
            path = str(item.get("path", ""))
            if path and path not in shown:
                lines.append(f"- {item.get('json_path', '')}: {path}")
                shown.add(path)
    if payload.get("local_prompt_path"):
        lines.append(f"- video_prompt: {payload['local_prompt_path']}")
    result = payload.get("result")
    prompt = result.get("video_prompt") if isinstance(result, dict) else None
    if isinstance(prompt, str) and prompt.strip():
        lines.extend(
            [
                "",
                "## 图生视频提示词",
                "",
                _markdown_code_block(prompt.strip()),
            ]
        )
    if isinstance(result, dict):
        rendered_result = dict(result)
        rendered_result.pop("video_prompt", None)
    else:
        rendered_result = result
    if rendered_result:
        lines.extend(
            [
                "",
                "## 当前结果",
                "",
                "```json",
                json.dumps(rendered_result, ensure_ascii=False, indent=2),
                "```",
            ]
        )
    return "\n".join(lines)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--download-dir", default=None)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Universal womenswear cloud skill client.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure")
    configure.add_argument("--config", default=None)
    configure.add_argument("--base-url", required=True)
    configure.add_argument("--api-key", required=True)
    configure.add_argument("--download-dir", default="")

    for command in ("skills", "quota"):
        current = subparsers.add_parser(command)
        _add_common(current)

    price = subparsers.add_parser("price")
    _add_common(price)
    price.add_argument("--skill-id", required=True)

    start = subparsers.add_parser("start")
    _add_common(start)
    start.add_argument("--skill-id", required=True)
    start.add_argument("--image", required=True)
    start.add_argument("--model-image", default="")
    start.add_argument("--style-hint", default="")
    start.add_argument("--save-model", dest="save_model", action="store_true", default=True)
    start.add_argument("--no-save-model", dest="save_model", action="store_false")
    start.add_argument("--idempotency-key", default="")
    start.add_argument("--no-wait", action="store_true")

    status_parser = subparsers.add_parser("status")
    _add_common(status_parser)
    status_parser.add_argument("--task-id", required=True)

    action = subparsers.add_parser("action")
    _add_common(action)
    action.add_argument("--task-id", required=True)
    action.add_argument("--action", required=True)
    action.add_argument("--choice", default="")
    action.add_argument("--payload-json", default="{}")
    action.add_argument("--payload-file", default="")
    action.add_argument("--shot", action="append", default=[])
    action.add_argument("--scene-id", action="append", default=[])
    action.add_argument("--notes", default="")
    action.add_argument("--attachment", action="append", default=[])
    action.add_argument("--idempotency-key", default="")
    action.add_argument("--no-wait", action="store_true")

    args = parser.parse_args()
    if args.command == "configure":
        base_url, api_key = _validated_credentials(args.base_url, args.api_key)
        path = _config_path(args.config, for_write=True) or (SKILL_ROOT / "config.toml")
        _save_config(
            path,
            base_url,
            api_key,
            args.download_dir.strip(),
        )
        print(json.dumps({"configured": True, "config_path": str(path)}, ensure_ascii=False))
        return

    config = _load_config(args.config)
    base_url, api_key = _credentials(args, config)
    if args.command == "skills":
        skills = _catalog(base_url, api_key)
        if args.format == "markdown":
            sys.stdout.write(_render_skills(skills))
        else:
            print(json.dumps({"skills": skills}, ensure_ascii=False, indent=2))
        return
    if args.command == "price":
        skill = _skill(base_url, api_key, args.skill_id)
        if args.format == "markdown":
            sys.stdout.write(_render_price(skill))
        else:
            print(json.dumps(skill, ensure_ascii=False, indent=2))
        return
    if args.command == "quota":
        payload = _request_json(
            "GET",
            f"{base_url}/v1/account/balance",
            headers=_headers(api_key),
            timeout=30,
        )
    elif args.command == "start":
        payload = _start_task(args, base_url, api_key)
        if not args.no_wait:
            payload = _poll(
                base_url,
                api_key,
                payload,
                args.timeout,
                args.poll_interval,
                not args.no_progress,
            )
    elif args.command == "status":
        payload = _request_json(
            "GET",
            f"{base_url}/v1/tasks/{args.task_id}",
            headers=_headers(api_key),
            timeout=60,
        )
        payload = _poll(
            base_url,
            api_key,
            payload,
            args.timeout,
            args.poll_interval,
            not args.no_progress,
        )
    else:
        payload = _action_task(args, base_url, api_key)
        if not args.no_wait:
            payload = _poll(
                base_url,
                api_key,
                payload,
                args.timeout,
                args.poll_interval,
                not args.no_progress,
            )

    if (
        args.command in {"start", "status", "action"}
        and payload.get("status") in {"waiting_for_input", "succeeded"}
        and not args.no_download
    ):
        payload = _download_outputs(
            payload,
            api_key,
            _download_root(args, config),
        )
    if args.format == "markdown" and args.command in {"start", "status", "action"}:
        sys.stdout.write(_render_task(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
