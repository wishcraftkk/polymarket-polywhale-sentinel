import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_NAME, DAILY_EVAL_HOUR, POLLING_INTERVAL_SECONDS, TEST_WALLETS, COPY_EXECUTION
from modules.discovery import discover_top_wallets
from modules.evaluation import calculate_composite_score
from modules.alert import send_alert, send_evaluation_alert
from modules.ingestion import check_new_trades
from utils.helpers import init_db
from modules.copy_executor import copy_executor
from modules.risk_manager import risk_manager

# グローバル監視対象
MONITORED_WALLETS = set(TEST_WALLETS)
FIRST_RUN = True  # 初回大量通知防止

async def daily_full_evaluation():
    global FIRST_RUN
    print(f"📊 {datetime.now().strftime('%H:%M')} 毎日フル評価を開始...")
    await send_alert("🔎 Discovery開始 → 新規優秀ウォレットを探します...", level="info")
    
    new_wallets = await discover_top_wallets()
    target_wallets = list(TEST_WALLETS) + new_wallets[:15]
    
    await send_alert(f"🧪 評価対象: {len(target_wallets)}件", level="info")
    
    for wallet in target_wallets:
        result = await calculate_composite_score(wallet)
        await send_evaluation_alert(wallet, result)
        
        if result.get("details", {}).get("composite_score", 0) >= COPY_EXECUTION.get("MIN_TARGET_SCORE", 85):
            MONITORED_WALLETS.add(wallet)
            print(f"✅ A級追加: {wallet[:8]}...")
    
    print(f"✅ 監視対象ウォレット: {len(MONITORED_WALLETS)}件に更新")
    FIRST_RUN = False

async def realtime_monitor():
    """リアルタイム新取引監視 → 評価 → リスクチェック → Copy Execution"""
    print(f"🔍 {datetime.now().strftime('%H:%M:%S')} リアルタイム監視中...（監視中: {len(MONITORED_WALLETS)}件）")
    
    if risk_manager.is_stopped():
        print("🛑 RiskManager が停止中です。新しい取引はスキップされます。")
        return

    for wallet in list(MONITORED_WALLETS):
        new_trades = await check_new_trades(wallet)
        if not new_trades or FIRST_RUN:
            continue

        for trade in new_trades:
            # 再評価（最新スコア確認）
            eval_result = await calculate_composite_score(wallet)
            score = eval_result.get("details", {}).get("composite_score", 0)
            
            if score < COPY_EXECUTION.get("MIN_TARGET_SCORE", 85):
                continue  # A級未満はスキップ

            # 取引詳細取得（ingestion モジュールから想定される構造に合わせ調整）
            market = trade.get("market", {})
            side = trade.get("side", "buy").lower()
            size = trade.get("size", 0.0)
            price = trade.get("price", 0.0)
            category = market.get("category", "OTHER")

            # Copy Execution 呼び出し（Paper/Live自動）
            success = await copy_executor.execute_copy(
                wallet_address=wallet,
                market=market,
                side=side,
                size=size,
                price=price
            )
            
            if success:
                # PnL更新は約定後フィードバックで後ほど強化（現在はPaper Mode中心）
                pass

        if new_trades:
            msg = f"""
🔥 **新取引検知！** 
ウォレット: `{wallet[:8]}...`
スコア: {score:.1f} (A級)
取引数: {len(new_trades)}件
モード: {'Live' if not COPY_EXECUTION.get('PAPER_MODE', True) else 'Paper'}
            """.strip()
            await send_alert(msg, level="high")
            print(f"🚨 新取引 {len(new_trades)}件 を処理しました！")

# ------------------- スケジューラー -------------------
scheduler = AsyncIOScheduler()

async def main():
    await init_db()
    
    print(f"🚀 {BOT_NAME} Phase 4 Live Mode 準備版 を起動...")
    startup_msg = f"""
{BOT_NAME} Phase 4 起動完了！
・Paper Mode: {COPY_EXECUTION.get('PAPER_MODE', True)}
・毎日 {DAILY_EVAL_HOUR}時 Discovery + 評価
・A級ウォレットの新取引を1分ごとに監視・自動コピー
・RiskManager ドローダウン監視有効
    """
    await send_alert(startup_msg, level="success")
    
    # 起動直後評価
    await daily_full_evaluation()
    
    # スケジュール
    scheduler.add_job(daily_full_evaluation, 'cron', hour=DAILY_EVAL_HOUR, minute=0)
    scheduler.add_job(realtime_monitor, 'interval', seconds=POLLING_INTERVAL_SECONDS)
    
    print("⏰ AsyncIOScheduler 開始（Ctrl+C で停止）")
    scheduler.start()
    await asyncio.Event().wait()  # 永続稼働

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 ボットを停止します...")
        scheduler.shutdown()
        print("✅ 正常終了")