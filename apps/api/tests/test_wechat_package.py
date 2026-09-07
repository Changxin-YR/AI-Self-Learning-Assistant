import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "wechat-miniprogram"


def test_wechat_package_has_publishable_manifest_and_four_tabs():
    manifest = json.loads((ROOT / "app.json").read_text(encoding="utf-8"))
    assert manifest["pages"][:4] == ["pages/home/home", "pages/library/library", "pages/learning/learning", "pages/profile/profile"]
    assert len(manifest["tabBar"]["list"]) == 4
    assert (ROOT / "utils/request.js").exists()
    assert "wx.login" in (ROOT / "app.js").read_text(encoding="utf-8")
    assert "wx.uploadFile" in (ROOT / "utils/request.js").read_text(encoding="utf-8")
