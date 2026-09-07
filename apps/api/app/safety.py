from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Risk(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SafetyDecision:
    risk: Risk
    reason: str = ""


class ContentSafetyProvider(Protocol):
    def check_input(self, text: str) -> SafetyDecision: ...
    def check_output(self, text: str) -> SafetyDecision: ...
    def check_upload_text(self, text: str) -> SafetyDecision: ...


class LocalRuleSafetyProvider:
    _injection = re.compile(r"忽略(?:之前|所有)?(?:的)?(?:系统|指令|规则)|ignore\s+(?:all|previous)\s+(?:system\s+)?instructions?|disregard\s+the\s+system|override\s+(?:the\s+)?(?:system|safety)", re.I)
    _blocked = re.compile(r"制作(?:炸弹|爆炸物)|制造毒品|自杀方法|儿童色情|窃取(?:密码|密钥)|steal\s+(?:password|api key)", re.I)
    _review = re.compile(r"绕过审核|绕过安全|攻击系统|exploit\s+the\s+system", re.I)

    def _check(self, text: str) -> SafetyDecision:
        value = (text or "").strip()
        if self._blocked.search(value):
            return SafetyDecision(Risk.BLOCK, "DANGEROUS_CONTENT")
        if self._injection.search(value):
            return SafetyDecision(Risk.BLOCK, "PROMPT_INJECTION")
        if self._review.search(value):
            return SafetyDecision(Risk.REVIEW, "SAFETY_REVIEW")
        return SafetyDecision(Risk.PASS)

    def check_input(self, text: str) -> SafetyDecision:
        return self._check(text)

    def check_output(self, text: str) -> SafetyDecision:
        return self._check(text)

    def check_upload_text(self, text: str) -> SafetyDecision:
        return self._check(text)


def get_content_safety_provider() -> ContentSafetyProvider:
    provider = os.getenv("CONTENT_SAFETY_PROVIDER", "local_rules" if os.getenv("DEV_MODE", "true").lower() == "true" else "").strip().lower()
    if provider in {"local_rules", "rules"}:
        if os.getenv("DEV_MODE", "true").lower() != "true":
            raise RuntimeError("CONTENT_SAFETY_LOCAL_FORBIDDEN")
        return LocalRuleSafetyProvider()
    if provider == "test_rules":
        if os.getenv("TEST_LLM_PROVIDER", "false").lower() != "true":
            raise RuntimeError("TEST_CONTENT_SAFETY_NOT_ENABLED")
        return LocalRuleSafetyProvider()
    if provider == "external":
        raise RuntimeError("CONTENT_SAFETY_PROVIDER_ADAPTER_REQUIRED")
    raise RuntimeError("CONTENT_SAFETY_PROVIDER_REQUIRED")
