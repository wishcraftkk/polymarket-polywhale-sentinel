import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+ 標準（JST対応・追加インストール不要）
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, BOT_NAME

bot = Bot(token=TELEGRAM_TOKEN)

# ==================== JSTタイムゾーン（日本時間） ====================
JST = ZoneInfo("Asia/Tokyo")

async def send_alert(message: str, level: str = "info"):
    """Phase 4: すべての通知でタイムスタンプをJSTに統一"""
    emoji_map = {
        "success": "✅", "info": "ℹ️", "warning": "⚠️",
        "error": "❌", "high": "🔥"
    }
    emoji = emoji_map.get(level, "📌")
    
    # 日本時間で統一（秒まで表示）
    jst_time = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')
    
    full_msg = f"{emoji} **{BOT_NAME}**\n{message}\n\n🕒 {jst_time}"
    
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=full_msg, parse_mode="Markdown")
        print(f"✅ Alert sent: {level} (JST統一済み)")
    except Exception as e:
        print(f"Alert送信エラー (非致命): {e}")

async def send_evaluation_alert(wallet: str, result: dict):
    """評価結果通知（JSTタイムスタンプ付き）"""
    details = result.get("details", {})
    score = details.get("composite_score", 0)
    status = details.get("status", "不明")
    pnl = details.get("total_pnl", 0)
    win_rate = details.get("win_rate", 0)
    sample = details.get("sample_size", 0)
    
    cat_info = ""
    if "category_stats" in details:
        stats = details["category_stats"]
        cat_info = "\n📍 **カテゴリ別実績**"
        for cat, data in stats.items():
            if cat != "OVERALL":
                cat_info += f"\n・{cat}: ${data.get('pnl',0):,.0f} ({data.get('count',0)}件)"
    
    level = "high" if score >= 90 else "info"
    msg = f"""
🧪 **ウォレット評価結果**
`{wallet[:8]}...`

📈 総合スコア: **{score:.1f}**
🏷️ 判定: {status}
💰 総PnL: **${pnl:,.0f}**
📊 取引数: {sample}件 | 勝率: {win_rate}%
{cat_info}
    """.strip()
    
    await send_alert(msg, level=level)