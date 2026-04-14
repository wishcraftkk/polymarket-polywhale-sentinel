import asyncio
from datetime import datetime
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, BOT_NAME

bot = Bot(token=TELEGRAM_TOKEN)

async def send_alert(message: str, level: str = "info"):
    emoji = {"success": "🚀", "info": "📊", "warning": "⚠️", "error": "❌", "high": "🔥"}.get(level, "📌")
    full_msg = f"{emoji} **{BOT_NAME}**\n{message}\n\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=full_msg, parse_mode="Markdown")
        print(f"✅ アラート送信成功: {level}")
    except Exception as e:
        print(f"⚠️ アラート送信エラー（無視可能）: {e}")

async def send_evaluation_alert(wallet: str, result: dict):
    """最終強化版：カテゴリ別情報も表示"""
    details = result.get("details", {})
    score = details.get("composite_score", 0)
    status = details.get("status", "不明")
    pnl = details.get("total_pnl", 0)
    win_rate = details.get("win_rate", 0)
    sample = details.get("sample_size", 0)
    
    # カテゴリ別情報（存在する場合）
    cat_info = ""
    if "category_stats" in details:
        stats = details["category_stats"]
        cat_info = "\n📌 **カテゴリ別実績**"
        for cat, data in stats.items():
            if cat != "OVERALL":
                cat_info += f"\n・{cat}: ${data.get('pnl',0):,.0f} ({data.get('count',0)}件)"
    
    level = "high" if score >= 90 else "info"
    msg = f"""
🧪 **ウォレット評価結果**
`{wallet[:8]}...`

📈 総合スコア: **{score}**
🏷️ 判定: {status}
💰 総PnL: **${pnl:,}**
取引数: {sample}件
勝率: {win_rate}%{cat_info}
    """.strip()
    
    await send_alert(msg, level=level)