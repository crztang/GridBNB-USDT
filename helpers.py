import asyncio
import logging
import requests
from telegram import Bot
from telegram.request import HTTPXRequest
from tenacity import retry, stop_after_attempt, wait_exponential
from config import settings
import time
import psutil
import os
from logging.handlers import TimedRotatingFileHandler
from telegram.ext import Application


def format_trade_message(side, symbol, price, amount, total, grid_size, base_asset, quote_asset, retry_count=None):
    """格式化交易消息为美观的文本格式

    Args:
        side (str): 交易方向 ('buy' 或 'sell')
        symbol (str): 交易对
        price (float): 交易价格
        amount (float): 交易数量
        total (float): 交易总额
        grid_size (float): 网格大小
        base_asset (str): 基础货币名称
        quote_asset (str): 计价货币名称
        retry_count (tuple, optional): 重试次数，格式为 (当前次数, 最大次数)

    Returns:
        str: 格式化后的消息文本
    """
    # 使用emoji增加可读性
    direction_emoji = "🟢" if side == 'buy' else "🔴"
    direction_text = "买入" if side == 'buy' else "卖出"

    # 构建消息主体
    message = f"""
{direction_emoji} {direction_text} {symbol}
━━━━━━━━━━━━━━━━━━━━
💰 价格：{price:.2f} {quote_asset}
📊 数量：{amount:.4f} {base_asset}
💵 金额：{total:.2f} {quote_asset}
📈 网格：{grid_size}%
"""

    # 如果有重试信息，添加重试次数
    if retry_count:
        current, max_retries = retry_count
        message += f"🔄 尝试：{current}/{max_retries}次\n"

    # 添加时间戳
    message += f"⏰ 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}"

    return message


# 异步：发送 telegram 消息
async def send_telegram_message_async(content, title="交易信号通知"):
    try:
        logging.info(f"正在发送 Telegram 通知: {title}")
        proxy = os.getenv('HTTP_PROXY')
        request = HTTPXRequest(proxy=proxy)
        bot = Bot(token=settings.TELEGRAM_TOKEN, request=request)
        chat_id = settings.TELEGRAM_CHANNEL_ID
        await bot.send_message(chat_id=chat_id, text=content)
    except Exception as e:
        logging.exception(f"Telegram 推送失败: {e}")


# 同步：发送 pushplus 消息（http）
def send_pushplus_message_http(content, title="交易信号通知"):
    if not settings.PUSHPLUS_TOKEN:
        logging.warning("未配置 PUSHPLUS_TOKEN，跳过推送")
        return

    url = os.getenv('PUSHPLUS_URL', 'https://www.pushplus.plus/send')
    data = {
        "token": settings.PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "txt"
    }


def send_message(content, title="交易信号通知"):
    if settings.NOTIFICATION_PLATFORM == "1":
        # 如果在事件循环中则 create_task，否则 run
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message_async(content, title))
        except RuntimeError:
            asyncio.run(send_telegram_message_async(content, title))
    elif settings.NOTIFICATION_PLATFORM == "2":
        send_pushplus_message_http(content, title)
        url = os.getenv('PUSHPLUS_URL', 'https://www.pushplus.plus/send')
        data = {
            "token": settings.PUSHPLUS_TOKEN,
            "title": title,
            "content": content,
            "template": "txt"  # 使用文本模板
        }
        try:
            logging.info(f"正在发送推送通知: {title}")
            response = requests.post(url, data=data, timeout=settings.PUSHPLUS_TIMEOUT)
            response_json = response.json()
            if response.status_code == 200 and response_json.get('code') == 200:
                logging.info(f"消息推送成功: {content}")
            else:
                logging.error(f"消息推送失败: 状态码={response.status_code}, 响应={response_json}")
        except Exception as e:
            logging.error(f"消息推送异常: {str(e)}", exc_info=True)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def safe_fetch(method, *args, **kwargs):
    try:
        return await method(*args, **kwargs)
    except Exception as e:
        logging.error(f"请求失败: {str(e)}")
        raise


def debug_watcher():
    """资源监控装饰器"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            mem_before = psutil.virtual_memory().used
            logging.debug(f"[DEBUG] 开始执行 {func.__name__}")

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                cost = time.time() - start
                mem_used = psutil.virtual_memory().used - mem_before
                logging.debug(
                    f"[DEBUG] {func.__name__} 执行完成 | 耗时: {cost:.3f}s | 内存变化: {mem_used / 1024 / 1024:.2f}MB")

        return wrapper

    return decorator


class LogConfig:
    SINGLE_LOG = True  # 强制单文件模式
    BACKUP_DAYS = 2  # 保留2天日志
    LOG_DIR = os.path.dirname(__file__)  # 与main.py相同目录
    LOG_LEVEL = logging.INFO

    @staticmethod
    def setup_logger():
        logger = logging.getLogger()
        logger.setLevel(LogConfig.LOG_LEVEL)

        # 清理所有现有处理器
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # 文件处理器
        file_handler = TimedRotatingFileHandler(
            os.path.join(LogConfig.LOG_DIR, 'trading_system.log'),
            when='midnight',
            interval=1,
            backupCount=LogConfig.BACKUP_DAYS,
            encoding='utf-8',
            delay=True
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(message)s'))

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    @staticmethod
    def clean_old_logs():
        if not os.path.exists(LogConfig.LOG_DIR):
            return
        now = time.time()
        for fname in os.listdir(LogConfig.LOG_DIR):
            if LogConfig.SINGLE_LOG and fname != 'trading_system.log':
                continue
            path = os.path.join(LogConfig.LOG_DIR, fname)
            if os.stat(path).st_mtime < now - LogConfig.BACKUP_DAYS * 86400:
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"删除旧日志失败 {fname}: {str(e)}")
