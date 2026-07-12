import traceback
from utils.logger import setup_logger
from utils.config import get_config, get_userData
from core.msg_builder import build_message, build_message_with_openai
from core.browser import get_browser
from playwright.sync_api import Response
import time
import json


complates = {}

config = get_config()
userData = get_userData()
logger = setup_logger(level=config.get("logLevel", "Info"))
matchMode = config.get("matchMode", "nickname")
userIDDict = {}

def handle_response(response: Response):
    """
    只监听你要的那个接口响应
    """
    global userIDDict
    # 精准匹配目标接口 URL
    if "aweme/v1/creator/im/user_detail/" in response.url:
        # print(f"URL: {response.url}")
        # print(f"状态码: {response.status}")
        try:
            # 获取接口返回的 JSON 数据（就是你在 Network 里看到的内容）
            json_data = response.json()
            # print("\n📦 响应 JSON 数据：")
            # print(json.dumps(json_data, indent=4, ensure_ascii=False))
            for item in json_data.get("user_list", []):
                short_id = item.get("user", {}).get("ShortId")
                nickname = item.get("user", {}).get("nickname")
                user_id = item.get("user_id", "")
                userIDDict[str(short_id)] = {"nickname": nickname, "user_id": user_id}
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            last = tb[-1]
            print(f"解析响应失败: {e}")
            print(f"文件: {last.filename}, 行号: {last.lineno}, 函数: {last.name}")


def retry_operation(name, operation, retries=3, delay=2, *args, **kwargs):
    """
    通用的重试逻辑
    :param name: 操作名称（用于日志记录）
    :param operation: 要执行的异步操作
    :param retries: 最大重试次数
    :param delay: 每次重试之间的延迟（秒）
    :param args: 传递给操作的参数
    :param kwargs: 传递给操作的关键字参数
    """
    for attempt in range(retries):
        try:
            return operation(*args, **kwargs)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"{name} 失败，正在重试第 {attempt + 1} 次，错误：{e}")
                time.sleep(delay)
            else:
                logger.error(f"{name} 失败，已达到最大重试次数，错误：{e}")
                raise


def capture_friends_tab_diagnostics(page):
    logger.error(f"找不到朋友私信入口，当前页面: {page.url}")
    page.screenshot(path="logs/friends-tab-unavailable.png", full_page=True)


def open_friends_tab(page):
    friends_tab = page.get_by_text("朋友私信", exact=True)
    try:
        friends_tab.wait_for(state="visible")
    except Exception:
        capture_friends_tab_diagnostics(page)
        raise
    friends_tab.click()


def select_target_from_visible_rows(rows, targets, found_names):
    for row in rows:
        row_lines = row.inner_text().splitlines()
        if not row_lines:
            continue

        target_name = row_lines[0]
        if target_name in found_names:
            continue
        found_names.add(target_name)

        if matchMode == "short_id":
            target_symbol = next(
                (
                    short_id
                    for short_id, info in userIDDict.items()
                    if info.get("nickname") == target_name
                ),
                None,
            )
        else:
            target_symbol = target_name

        if target_symbol in targets:
            row.click()
            return target_name, target_symbol

    return None, None


def send_message(chat_input, message, friend_name):
    message_lines = message.split("\n")
    for index, line in enumerate(message_lines):
        chat_input.type(line)
        if index < len(message_lines) - 1:
            chat_input.press("Shift+Enter")

    chat_input.press("Enter")
    logger.info(f"已向好友 {friend_name} 发送消息")


def scroll_and_select_user(page, username, targets):
    """尝试滚动并查找用户名"""
    # [修复] 使用模糊匹配 no-more-tip- 前缀，不再依赖精确哈希后缀
    # 同时增加文本匹配作为兜底
    no_more_selector = 'xpath=//div[contains(@class, "no-more-tip-")]'
    loading_selector = 'xpath=//div[contains(@class, "semi-spin")]'

    logger.debug(f"账号 {username} 开始查找目标好友列表")
    logger.debug(f"账号 {username} 目标好友列表: {targets}")

    logger.debug(f"账号 {username} 点击进入好友标签页")
    open_friends_tab(page)

    logger.debug(f"账号 {username} 进入好友列表页面")

    logger.debug(f"账号 {username} 已激活好友列表，开始滚动查找目标好友")

    time.sleep(config["friendListTimeout"] / 1000)  # 等待好友列表加载

    friend_rows = page.get_by_role("row")
    found_targets = set()
    # [修改] 复制一份目标列表用于追踪进度
    remaining_targets = set(targets)

    # [修复] 新增：连续空滚动计数器（滚动后没有发现新好友的次数）
    empty_scroll_count = 0
    MAX_EMPTY_SCROLLS = 10  # 连续10次滚动没有新好友，认为到底了

    while True:
        prev_found_count = len(found_targets)
        target_name, target_symbol = select_target_from_visible_rows(
            friend_rows.all(),
            targets,
            found_targets,
        )

        if target_name:
            logger.debug(f"账号 {username} 选中目标好友 {target_name} 准备开始交互")
            yield target_name

            if target_symbol in remaining_targets:
                remaining_targets.remove(target_symbol)
            if not remaining_targets:
                logger.debug(f"账号 {username} 所有目标好友均已找到，停止搜索")
                return
            continue

        if len(found_targets) > prev_found_count:
            empty_scroll_count = 0
        else:
            empty_scroll_count += 1

        if page.locator(no_more_selector).count() > 0:
            logger.info(f"账号 {username} 检测到'没有更多了'标志，已到达底部")
            if remaining_targets:
                logger.warning(f"账号 {username} 搜索结束，仍有以下好友未找到: {remaining_targets}")
            break

        if empty_scroll_count >= MAX_EMPTY_SCROLLS:
            logger.warning(f"账号 {username} 连续 {MAX_EMPTY_SCROLLS} 次滚动未发现新好友，判定已到达底部")
            if remaining_targets:
                logger.warning(f"账号 {username} 搜索结束，仍有以下好友未找到: {remaining_targets}")
            break

        if page.locator(loading_selector).count() > 0:
            logger.debug(f"账号 {username} 列表正在加载中 (Loading)...")
            time.sleep(1.5)

        if friend_rows.count() == 0:
            logger.error(f"账号 {username} 未找到好友列表，退出")
            break

        friend_rows.nth(friend_rows.count() - 1).scroll_into_view_if_needed()
        time.sleep(1.5)


def do_user_task(browser, username, cookies, targets):
        context = browser.new_context()  # 每个任务使用独立的上下文
        context.set_default_navigation_timeout(config["browserTimeout"])  # 设置导航超时时间为 120 秒
        context.set_default_timeout(config["browserTimeout"])  # 设置所有操作的默认超时时间为 120 秒

        page = context.new_page()
        
        if matchMode == "short_id":  # 使用抖音号进行匹配
            page.on("response", handle_response)
        
        # 打开抖音创作者中心
        retry_operation(
            "打开抖音创作者中心",
            page.goto,
            retries=config["taskRetryTimes"],
            delay=5,
            url="https://creator.douyin.com/",
        )
        # 注入 Cookie
        context.add_cookies(cookies)

        # 导航到消息页面
        retry_operation(
            "导航到消息页面",
            page.goto,
            retries=config["taskRetryTimes"],
            delay=5,
            url="https://creator.douyin.com/creator-micro/data/following/chat",
        )

        logger.debug(f"账号 {username} 开始发送消息")
        # 滚动并选择用户
        for username in scroll_and_select_user(page, username, targets):
            logger.debug(f"账号 {username} 已选中好友 {username} 发送消息")
            # 等待聊天输入框元素加载完成，使用更稳定的属性选择器
            chat_input_selector = "xpath=//div[contains(@class, 'chat-input-')]"
            page.wait_for_selector(chat_input_selector, timeout=config["browserTimeout"])
            chat_input = page.locator(chat_input_selector)

            message = build_message()
            send_message(chat_input, message, username)
            time.sleep(2)  # 发送完等待一会儿

        context.close()  # 任务完成后关闭上下文


def runTasks():
    playwright, browser = get_browser()
    try:
        # 检查是否启用多任务和任务数量
        # 创建信号量以限制并发任务数量
        logger.info("开始执行任务")
        logger.debug(f"当前配置如下：")
        logger.debug(f"消息模板: {config.get('messageTemplate', '未找到消息模板')}")
        logger.debug(f"一言类型: {config['hitokotoTypes']}")
        for user in userData:
            logger.debug(f"用户: {user.get('username', '未知用户')}, 目标好友: {user['targets']}")

        for user in userData:
            cookies = user["cookies"]
            targets = user["targets"]
            complates[user["unique_id"]] = []  # 初始化该用户的已完成列表
            username = user.get("username", "未知用户")
            logger.info(f"开始处理账号 {username}")
            # 创建任务
            do_user_task(browser, username, cookies, targets)
            logger.info(f"账号 {username} 任务完成")
    finally:
        # 关闭浏览器实例
        browser.close()
        
        playwright.stop()

        
