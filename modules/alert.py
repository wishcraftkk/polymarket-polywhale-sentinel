import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, BOT_NAME
from modules.evaluation import get_period_performance

bot = Bot(token=TELEGRAM_TOKEN)
JST = ZoneInfo("Asia/Tokyo")

def format_wallet_link(wallet: str) -> str:
    short = wallet[:8] + "..."
    url = f"https://polymarket.com/profile/{wallet}"
    return f"[{short}]({url})"

async def send_alert(message: str, level: str = "info"):
    emoji_map = {"success": "✅", "info": "ℹ️", "warning": "⚠️", "error": "❌", "high": "🔥"}
    emoji = emoji_map.get(level, "📌")
    jst_time = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')
    full_msg = f"{emoji} **{BOT_NAME}**\n{message}\n\n🕒 {jst_time}"
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=full_msg, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        print(f"Alert送信エラー: {e}")

async def send_evaluation_alert(wallet: str, result: dict):
    wallet_link = format_wallet_link(wallet)
    msg = f"🧪 **ウォレット評価結果**\n{wallet_link}\n"
    periods = ["ALL", "1M", "1W"]
    for period in periods:
        perf = await get_period_performance(wallet, period)
        cat_stats = perf["category_stats"]
        msg += f"\n**{period}** ({perf['count']}件)\n"
        msg += f"**総PnL: ${perf['pnl']:,.0f}** | 勝率 **{perf['win_rate']}%**\n"
        msg += "```\nカテゴリ     PnL          件数   勝率\n"
        msg += "------------------------------------\n"
        for cat, data in cat_stats.items():
            msg += f"{cat:<10} ${data['pnl']:>10,.0f}   {data['count']:>4}  {data.get('win_rate',0):>5.1f}%\n"
        msg += "```\n"
    await send_alert(msg, level="high" if result.get("score",0) >= 85 else "info")
