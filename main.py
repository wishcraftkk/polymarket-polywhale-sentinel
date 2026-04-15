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
FIRST_RUN = True

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
    
    # 【新規追加】評価終了後に日次パフォーマンスまとめ通知
    await daily_performance_summary()

async def daily_performance_summary():
    """Phase 4 強化版：スコア0.0・データなしウォレットを自動スキップ"""
    global MONITORED_WALLETS   # ← ここに関数の最初に移動（重要！）

    if not MONITORED_WALLETS:
        await send_alert("📉 本日のパフォーマンス集計対象なし", level="info")
        return

    total_pnl = 0.0
    total_trades = 0
    active_wallets = 0
    summary_lines = ["📅 **日次パフォーマンスまとめ** (JST)"]

    cleaned_wallets = []  # 無効ウォレットを除外

    for wallet in list(MONITORED_WALLETS):
        result = await calculate_composite_score(wallet)
        details = result.get("details", {})
        score = details.get("composite_score", 0)
        sample_size = details.get("sample_size", 0)

        # スコア0.0 または データ0件はスキップ＋監視対象から除外
        if score <= 0 or sample_size == 0:
            print(f"🧹 低スコア/データなしウォレットを監視対象から除外: {wallet[:8]}...")
            continue

        cleaned_wallets.append(wallet)
        pnl = details.get("total_pnl", 0)
        win_rate = details.get("win_rate", 0)
        trades = sample_size

        total_pnl += pnl
        total_trades += trades
        if trades > 0:
            active_wallets += 1

        summary_lines.append(
            f"`{wallet[:8]}...` → ${pnl:,.0f} | 勝率 {win_rate:.1f}% | {trades}件"
        )

    # 監視対象をクリーンアップ
    MONITORED_WALLETS = set(cleaned_wallets)

    # RiskManagerデータ
    risk_manager.reset_daily()
    dd_daily = (-risk_manager.daily_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0
    dd_total = (-risk_manager.total_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0

    summary_lines.append("\n📊 **全体集計**")
    summary_lines.append(f"👥 A級ウォレット数: {len(cleaned_wallets)}件（アクティブ {active_wallets}）")
    summary_lines.append(f"💰 総PnL: **${total_pnl:,.0f}**")
    summary_lines.append(f"📈 総取引数: {total_trades}件")
    summary_lines.append(f"🛡️ 1日ドローダウン: {dd_daily:.1f}%")
    summary_lines.append(f"🛡️ 累積ドローダウン: {dd_total:.1f}%")
    summary_lines.append(f"モード: {'🟢 Live' if not COPY_EXECUTION.get('PAPER_MODE') else '📋 Paper'}")

    full_msg = "\n".join(summary_lines)
    await send_alert(full_msg, level="success")
    print("✅ 日次パフォーマンスまとめ通知送信完了（低スコアウォレット除外済み）")
    
# realtime_monitor は変更なし（前回版のまま）
async def realtime_monitor():
    print(f"🔍 {datetime.now().strftime('%H:%M:%S')} リアルタイム監視中...（監視中: {len(MONITORED_WALLETS)}件）")
    
    if risk_manager.is_stopped():
        print("🛑 RiskManager が停止中です。新しい取引はスキップされます。")
        return

    for wallet in list(MONITORED_WALLETS):
        new_trades = await check_new_trades(wallet)
        if not new_trades or FIRST_RUN:
            continue

        for trade in new_trades:
            eval_result = await calculate_composite_score(wallet)
            score = eval_result.get("details", {}).get("composite_score", 0)
            
            if score < COPY_EXECUTION.get("MIN_TARGET_SCORE", 85):
                continue

            market = trade.get("market", {})
            side = trade.get("side", "buy").lower()
            size = trade.get("size", 0.0)
            price = trade.get("price", 0.0)
            category = market.get("category", "OTHER")

            success = await copy_executor.execute_copy(
                wallet_address=wallet,
                market=market,
                side=side,
                size=size,
                price=price
            )
            
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

scheduler = AsyncIOScheduler()

async def main():
    await init_db()
    
    print(f"🚀 {BOT_NAME} Phase 4 Live Mode 準備版 を起動...")
    startup_msg = f"""
{BOT_NAME} Phase 4 起動完了！
・Paper Mode: {COPY_EXECUTION.get('PAPER_MODE', True)}
・毎日 {DAILY_EVAL_HOUR}時 Discovery + 評価 + **日次パフォーマンスまとめ**
・A級ウォレットの新取引を1分ごとに監視・自動コピー
    """
    await send_alert(startup_msg, level="success")
    
    await daily_full_evaluation()
    
    scheduler.add_job(daily_full_evaluation, 'cron', hour=DAILY_EVAL_HOUR, minute=0)
    scheduler.add_job(realtime_monitor, 'interval', seconds=POLLING_INTERVAL_SECONDS)
    
    print("⏰ AsyncIOScheduler 開始（Ctrl+C で停止）")
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 ボットを停止します...")
        scheduler.shutdown()
        print("✅ 正常終了")