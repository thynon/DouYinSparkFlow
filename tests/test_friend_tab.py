import ast
import unittest
from pathlib import Path


TASKS_PATH = Path(__file__).resolve().parents[1] / "core" / "tasks.py"


class FakeFriendsTab:
    def __init__(self):
        self.wait_states = []
        self.clicks = 0

    def wait_for(self, *, state):
        self.wait_states.append(state)

    def click(self):
        self.clicks += 1


class FakePage:
    def __init__(self):
        self.text_requests = []
        self.friends_tab = FakeFriendsTab()

    def get_by_text(self, text, *, exact):
        self.text_requests.append((text, exact))
        return self.friends_tab


class FailingFriendsTab(FakeFriendsTab):
    def wait_for(self, *, state):
        super().wait_for(state=state)
        raise RuntimeError("friends tab is unavailable")


class FailingPage(FakePage):
    def __init__(self):
        super().__init__()
        self.friends_tab = FailingFriendsTab()
        self.url = "https://creator.douyin.com/login"
        self.screenshots = []

    def screenshot(self, *, path, full_page):
        self.screenshots.append((path, full_page))


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.infos = []

    def error(self, message):
        self.errors.append(message)

    def info(self, message):
        self.infos.append(message)


class FakeFriendRow:
    def __init__(self, text):
        self.text = text
        self.clicks = 0

    def inner_text(self):
        return self.text

    def click(self):
        self.clicks += 1


class FakeChatInput:
    def __init__(self):
        self.typed_text = []
        self.pressed_keys = []

    def type(self, text):
        self.typed_text.append(text)

    def press(self, key):
        self.pressed_keys.append(key)


def load_helpers(*names, namespace=None):
    tree = ast.parse(TASKS_PATH.read_text(encoding="utf-8"))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    found_names = {function.name for function in functions}
    missing_names = set(names) - found_names
    if missing_names:
        raise AssertionError(f"missing helpers: {', '.join(sorted(missing_names))}")

    namespace = namespace or {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(TASKS_PATH), "exec"), namespace)
    return tuple(namespace[name] for name in names)


class OpenFriendsTabTests(unittest.TestCase):
    def test_opens_visible_friends_private_message_tab_by_text(self):
        page = FakePage()

        (open_friends_tab,) = load_helpers("open_friends_tab")
        open_friends_tab(page)

        self.assertEqual(page.text_requests, [("朋友私信", True)])
        self.assertEqual(page.friends_tab.wait_states, ["visible"])
        self.assertEqual(page.friends_tab.clicks, 1)

    def test_records_page_url_and_screenshot_when_friends_tab_is_unavailable(self):
        page = FailingPage()
        logger = FakeLogger()

        open_friends_tab, _ = load_helpers(
            "open_friends_tab",
            "capture_friends_tab_diagnostics",
            namespace={"logger": logger},
        )

        with self.assertRaisesRegex(RuntimeError, "friends tab is unavailable"):
            open_friends_tab(page)

        self.assertEqual(
            page.screenshots,
            [("logs/friends-tab-unavailable.png", True)],
        )
        self.assertEqual(
            logger.errors,
            ["找不到朋友私信入口，当前页面: https://creator.douyin.com/login"],
        )

    def test_selects_short_id_target_from_visible_aria_rows(self):
        rows = [
            FakeFriendRow("其他好友\n昨天"),
            FakeFriendRow("目标好友\n刚刚"),
        ]

        (select_target_from_visible_rows,) = load_helpers(
            "select_target_from_visible_rows",
            namespace={
                "matchMode": "short_id",
                "userIDDict": {
                    "Ricardo926": {"nickname": "目标好友", "user_id": "123"},
                },
            },
        )
        found_names = set()

        target_name, target_symbol = select_target_from_visible_rows(
            rows,
            ["Ricardo926"],
            found_names,
        )

        self.assertEqual((target_name, target_symbol), ("目标好友", "Ricardo926"))
        self.assertEqual(rows[0].clicks, 0)
        self.assertEqual(rows[1].clicks, 1)
        self.assertEqual(found_names, {"其他好友", "目标好友"})

    def test_logs_after_pressing_enter_to_send_message(self):
        chat_input = FakeChatInput()
        logger = FakeLogger()

        (send_message,) = load_helpers(
            "send_message",
            namespace={"logger": logger},
        )
        send_message(chat_input, "第一行\n第二行", "目标好友")

        self.assertEqual(chat_input.typed_text, ["第一行", "第二行"])
        self.assertEqual(chat_input.pressed_keys, ["Shift+Enter", "Enter"])
        self.assertEqual(logger.errors, [])
        self.assertEqual(logger.infos, ["已向好友 目标好友 发送消息"])


if __name__ == "__main__":
    unittest.main()
