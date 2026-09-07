from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "apps" / "wechat-miniprogram"

failures: list[str] = []
passes: list[str] = []


def check(condition: bool, message: str) -> None:
    (passes if condition else failures).append(message)


def parse_js_string(source: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*:\s*['\"]([^'\"]+)['\"]", source)
    return match.group(1) if match else None


def parse_js_bool(source: str, key: str) -> bool | None:
    match = re.search(rf"\b{re.escape(key)}\s*:\s*(true|false)", source)
    return None if not match else match.group(1) == "true"


config_source = (MINI / "config.js").read_text(encoding="utf-8")
api_base_url = parse_js_string(config_source, "apiBaseUrl")
dev_mode = parse_js_bool(config_source, "devMode")

check(bool(api_base_url), "config.js 已配置 apiBaseUrl")
if api_base_url:
    parsed = urlparse(api_base_url)
    check(parsed.scheme == "https", "正式 API 使用 HTTPS")
    check(bool(parsed.hostname), "正式 API URL 包含有效域名")
    if parsed.hostname:
        try:
            ipaddress.ip_address(parsed.hostname)
            is_domain = False
        except ValueError:
            is_domain = parsed.hostname not in {"localhost"}
        check(is_domain, "正式 API 使用可配置为微信合法域名的域名而非 IP/localhost")
check(dev_mode is False, "正式发布配置 devMode=false")

project = json.loads((MINI / "project.config.json").read_text(encoding="utf-8"))
appid = str(project.get("appid", "")).strip()
check(appid.startswith("wx") and appid != "touristappid" and len(appid) > 10, "project.config.json 使用非游客 AppID")
check(project.get("setting", {}).get("urlCheck") is True, "发布前开启合法域名检查 urlCheck=true")

manifest = json.loads((MINI / "app.json").read_text(encoding="utf-8"))
check(manifest.get("__usePrivacyCheck__") is True, "app.json 已启用隐私检查")

privacy = json.loads((MINI / "privacy.json").read_text(encoding="utf-8"))
uses_message_file = "wx.chooseMessageFile" in "\n".join(
    path.read_text(encoding="utf-8")
    for path in MINI.rglob("*.js")
)
privacy_declared = bool(privacy.get("requiredPrivateInfos") or privacy.get("privacyItems"))
check(not uses_message_file or privacy_declared, "使用聊天文件选择能力时已同步隐私保护声明")

private_config = MINI / "project.private.config.json"
check(not private_config.exists(), "未将 project.private.config.json 纳入发布源码")

print("WeChat mini-program release preflight")
for message in passes:
    print(f"[PASS] {message}")
for message in failures:
    print(f"[FAIL] {message}")

if failures:
    print(f"\nRelease gate failed: {len(failures)} item(s).")
    sys.exit(1)
print("\nRelease gate passed for repository-checkable items.")
print("Platform-side domain, privacy guide, filing, AI compliance, experience build and review still require WeChat/CAC/MIIT verification.")
