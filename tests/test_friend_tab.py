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


def load_open_friends_tab():
    tree = ast.parse(TASKS_PATH.read_text(encoding="utf-8"))
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "open_friends_tab"
        ),
        None,
    )
    if function is None:
        raise AssertionError("open_friends_tab is not defined")

    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(TASKS_PATH), "exec"), namespace)
    return namespace["open_friends_tab"]


class OpenFriendsTabTests(unittest.TestCase):
    def test_opens_visible_friends_private_message_tab_by_text(self):
        page = FakePage()

        open_friends_tab = load_open_friends_tab()
        open_friends_tab(page)

        self.assertEqual(page.text_requests, [("朋友私信", True)])
        self.assertEqual(page.friends_tab.wait_states, ["visible"])
        self.assertEqual(page.friends_tab.clicks, 1)


if __name__ == "__main__":
    unittest.main()
