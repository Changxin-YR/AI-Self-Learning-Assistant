from __future__ import annotations

import ipaddress
import json
import re
import sys
import argparse
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "apps" / "wechat-miniprogram"

failures: list[str] = []
passes: list[str] = []
parser = argparse.ArgumentParser()
parser.add_argument("--code-only", action="store_true", help="validate repository release wiring without requiring external domain credentials")
args = parser.parse_args()


def check(condition: bool, message: str) -> None:
    (passes if condition else failures).append(message)


def parse_js_string(source: str, key: str) -> str | None:
    match = re.search(rf"\b{re.escape(key)}\s*:\s*['\"]([^'\"]+)['\"]", source)
    return match.group(1) if match else None


def parse_js_bool(source: str, key: str) -> bool | None:
    match = re.search(rf"\b{re.escape(key)}\s*:\s*(true|false)", source)
    return None if not match else match.group(1) == "true"


production_config = (MINI / "config.prod.js").read_text(encoding="utf-8")
config_source = production_config if args.code_only else (MINI / "config.js").read_text(encoding="utf-8")
if not args.code_only and "require('./config.dev')" in config_source:
    config_source = (MINI / "config.dev.js").read_text(encoding="utf-8")
api_base_url = parse_js_string(config_source, "apiBaseUrl")
dev_mode = parse_js_bool(config_source, "devMode")

check(bool(api_base_url), "config.js 已配置 apiBaseUrl")
if api_base_url:
    is_template = api_base_url == "__API_BASE_URL__"
    parsed = urlparse(api_base_url)
    check(is_template or parsed.scheme == "https", "正式 API 使用 HTTPS")
    check(is_template or bool(parsed.hostname), "正式 API URL 包含有效域名")
    if parsed.hostname and not is_template:
        try:
            ipaddress.ip_address(parsed.hostname)
            is_domain = False
        except ValueError:
            is_domain = parsed.hostname not in {"localhost"}
        check(args.code_only or is_domain, "正式 API 使用可配置为微信合法域名的域名而非 IP/localhost")
check(args.code_only or dev_mode is False, "正式发布配置 devMode=false")

check("devMode: false" in production_config, "生产配置模板固定 devMode=false")
check("__API_BASE_URL__" in production_config, "生产配置通过构建变量注入 API 域名")

project = json.loads((MINI / "project.config.json").read_text(encoding="utf-8"))
appid = str(project.get("appid", "")).strip()
check(appid.startswith("wx") and appid != "touristappid" and len(appid) > 10, "project.config.json 使用非游客 AppID")
check(project.get("setting", {}).get("urlCheck") is True or args.code_only, "发布前开启合法域名检查 urlCheck=true")

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

all_js_wxml = "\n".join(path.read_text(encoding="utf-8") for path in MINI.rglob("*.js")) + "\n" + "\n".join(path.read_text(encoding="utf-8") for path in MINI.rglob("*.wxml"))
check("AI 生成" in all_js_wxml, "AI 生成内容包含显式标识")
secret_patterns = [r"sk-[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"appsecret\s*[:=]"]
check(not any(re.search(pattern, all_js_wxml, re.I) for pattern in secret_patterns), "小程序源码未发现明显密钥")
package_bytes = sum(path.stat().st_size for path in MINI.rglob("*") if path.is_file() and "node_modules" not in path.parts)
check(package_bytes < 2 * 1024 * 1024, "小程序源码包小于 2MB")

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
