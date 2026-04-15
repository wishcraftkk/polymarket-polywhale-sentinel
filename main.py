import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # ← Blocking → AsyncIOに変更

from config import BOT_NAME, DAILY_EVAL_HOUR, POLLING_INTERVAL_SECONDS, TEST_WALLETS
from modules.discovery import discover_top_wallets
from modules.evaluation import calculate_composite_score
from modules.alert import send_alert, send_evaluation_alert
from modules.ingestion import check_new_trades
from utils.helpers import init_db  # ← 追加
from modules.copy_executor import copy_executor

# グローバル監視対象
MONITORED_WALLETS = set(TEST_WALLETS)
FIRST_RUN = True  # 初回大量通知防止フラグ

async def daily_full_evaluation():
    global FIRST_RUN
    print(f"📊 {datetime.now().strftime('%H:%M')} 毎日評価を開始...")
    await send_alert("🔎 Discovery開始 → 新規優秀ウォレットを探します...", level="info")
    
    new_wallets = await discover_top_wallets()
    target_wallets = list(TEST_WALLETS) + new_wallets[:15]
    
    await send_alert(f"🧪 評価対象: {len(target_wallets)}件", level="info")
    
    for wallet in target_wallets:
        result = await calculate_composite_score(wallet)
        await send_evaluation_alert(wallet, result)
        
        if result["details"].get("composite_score", 0) >= 85:
            MONITORED_WALLETS.add(wallet)
    
    print(f"✅ 監視対象ウォレット: {len(MONITORED_WALLETS)}件に更新")
    FIRST_RUN = False  # 初回完了

async def realtime_monitor():
    print(f"🔍 {datetime.now().strftime('%H:%M:%S')} リアルタイム監視中...（{len(MONITORED_WALLETS)}件）")
    for wallet in list(MONITORED_WALLETS):
        new_trades = await check_new_trades(wallet)
        if new_trades and not FIRST_RUN:  # 初回は通知抑制
            # Phase 3: Copy Execution を呼び出す
            for trade in new_trades:
                result = await calculate_composite_score(wallet)
                await copy_executor.execute_copy(wallet, trade, result.get("details", {}))

            msg = f"""
🔥 **新取引検知！** 
ウォレット: `{wallet[:8]}...`
取引数: {len(new_trades)}件
            """.strip()
            await send_alert(msg, level="high")
            print(f"🚨 新取引 {len(new_trades)}件 を通知しました！")

# ------------------- スケジューラー（Async版） -------------------
scheduler = AsyncIOScheduler()

async def main():
    await init_db()  # 確実にDB初期化
    
    print(f"🚀 {BOT_NAME} を起動しています...")
    startup_msg = f"""
{BOT_NAME} が正常に起動しました！
・毎日 {DAILY_EVAL_HOUR}時に Discovery + 評価
・A級候補の新取引を1分ごとにリアルタイム監視
準備完了！
    """
    await send_alert(startup_msg, level="success")
    
    print("🚀 起動直後にDiscovery + 評価を実行します...")
    await daily_full_evaluation()
    
    # スケジュール登録
    scheduler.add_job(daily_full_evaluation, 'cron', hour=DAILY_EVAL_HOUR, minute=0)
    scheduler.add_job(realtime_monitor, 'interval', seconds=POLLING_INTERVAL_SECONDS)
    
    print("⏰ AsyncIOScheduler開始（Ctrl+Cで停止）")
    scheduler.start()
    await asyncio.Event().wait()  # 永続稼働

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 ボットを停止します...")
        scheduler.shutdown()
