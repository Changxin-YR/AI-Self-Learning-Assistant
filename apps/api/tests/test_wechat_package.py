import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "wechat-miniprogram"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wechat_package_has_publishable_manifest_and_four_tabs():
    manifest = json.loads(read("app.json"))
    assert manifest["pages"][:4] == ["pages/home/home", "pages/library/library", "pages/learning/learning", "pages/profile/profile"]
    assert len(manifest["tabBar"]["list"]) == 4
    assert (ROOT / "utils/request.js").exists()
    assert "wx.login" in read("app.js")
    assert "wx.uploadFile" in read("utils/request.js")


def test_explicit_logout_does_not_immediately_auto_login():
    app = read("app.js")
    profile = read("pages/profile/profile.js")
    home = read("pages/home/home.js")
    assert "MANUAL_SIGN_OUT_KEY" in app
    assert "clearAuth(manual = true)" in app
    assert "resumeAuth()" in app
    assert "getApp().clearAuth(true)" in profile
    assert "await app.ensureAuth(true)" not in profile
    assert "async login()" in home


def test_library_polling_is_scoped_and_destructive_actions_are_confirmed():
    library = read("pages/library/library.js")
    library_wxml = read("pages/library/library.wxml")
    assert "pollGeneration" in library
    assert "pollInFlight" in library
    assert "detailError" in library
    assert "wx.showModal" in library
    assert "deleteKnowledgeBase" in library
    assert "inputSearch" in library
    assert "generateQuiz" in library
    assert "生成计划" in library_wxml
    assert "搜索知识库" in library_wxml


def test_library_detail_tabs_use_real_existing_apis():
    library = read("pages/library/library.js")
    library_wxml = read("pages/library/library.wxml")
    assert "switchDetailTab" in library
    assert "loadMastery" in library
    assert "loadHistory" in library
    assert "/mastery`" in library
    assert "request.get('/conversations')" in library
    assert "conversationId=${item.id}" in library
    assert "知识点" in library_wxml
    assert "历史对话" in library_wxml


def test_chat_can_recover_and_citations_are_inspectable():
    chat = read("pages/chat/chat.js")
    chat_wxml = read("pages/chat/chat.wxml")
    assert "messages: result.items || [], scrollTop: 999999, error: ''" in chat
    assert "if (this.data.conversationId === id) await this.createConversation()" in chat
    assert "openCitation" in chat
    assert "查看来源" in chat_wxml


def test_learning_uses_active_plan_native_date_picker_and_real_analytics():
    learning = read("pages/learning/learning.js")
    learning_wxml = read("pages/learning/learning.wxml")
    assert "find(item => item.status === 'ACTIVE')" in learning
    assert "const planKbId = this.data.plan?.knowledge_base_id" in learning
    assert "'SHORT'" in learning
    assert "request.get('/dashboard')" in learning
    assert "dashboard.mastery" in learning
    assert "dashboard.trend" in learning
    assert 'mode="date"' in learning_wxml
    assert 'type="date"' not in learning_wxml
    assert "学习分析" in learning_wxml
    assert "薄弱知识点" in learning_wxml
    assert "学习趋势" in learning_wxml


def test_quiz_prevents_double_submit_and_profile_uses_native_text_nodes():
    quiz = read("pages/quiz/quiz.js")
    quiz_wxml = read("pages/quiz/quiz.wxml")
    profile_wxml = read("pages/profile/profile.wxml")
    assert "submitting" in quiz
    assert "if (this.data.submitting || this.data.submitted) return" in quiz
    assert "正在交卷" in quiz_wxml
    assert "正确" in quiz
    assert "<strong>" not in profile_wxml


def test_home_bounds_recent_libraries_and_exposes_short_answer_quiz():
    home = read("pages/home/home.js")
    home_wxml = read("pages/home/home.wxml")
    assert "items.slice(0, 3)" in home
    assert "'SHORT'" in home
    assert "学习概览" in home_wxml
