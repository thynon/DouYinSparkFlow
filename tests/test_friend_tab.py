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

    def error(self, message):
        self.errors.append(message)


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


if __name__ == "__main__":
    unittest.main()
