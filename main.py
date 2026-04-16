import asyncio
from datetime import datetime
import csv
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pandas as pd

from config import BOT_NAME, DAILY_EVAL_HOUR, POLLING_INTERVAL_SECONDS, TEST_WALLETS, COPY_EXECUTION
from modules.discovery import discover_top_wallets
from modules.evaluation import calculate_composite_score
from modules.alert import send_alert, send_evaluation_alert
from modules.ingestion import check_new_trades
from utils.helpers import init_db
from modules.copy_executor import copy_executor
from modules.risk_manager import risk_manager

# グローバル
MONITORED_WALLETS = set(TEST_WALLETS)
FIRST_RUN = True
TRADE_LOG = []  # Paper Mode取引履歴（時系列用）

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

async def daily_full_evaluation():
    global FIRST_RUN
    print(f"📊 {datetime.now().strftime('%H:%M')} 毎日フル評価を開始...")
    await send_alert("🔎 Discovery開始 → 新規優秀ウォレットを探します...", level="info")
    
    new_wallets = await discover_top_wallets()
    target_wallets = list(TEST_WALLETS) + new_wallets[:15]
    
    await send_alert(f"🧪 評価対象: {len(target_wallets)}件", level="info")
    
    for wallet in target_wallets:
        result = await calculate_composite_score(wallet)
        details = result.get("details", {})
        score = details.get("composite_score", 0)
        sample_size = details.get("sample_size", 0)

        if score <= 0 or sample_size == 0:
            print(f"🧹 低スコア/データなしウォレットを通知スキップ: {wallet[:8]}...")
            continue

        await send_evaluation_alert(wallet, result)
        
        if score >= COPY_EXECUTION.get("MIN_TARGET_SCORE", 85):
            MONITORED_WALLETS.add(wallet)
            print(f"✅ A級追加: {wallet[:8]}...")
    
    print(f"✅ 監視対象ウォレット: {len(MONITORED_WALLETS)}件に更新")
    FIRST_RUN = False
    await daily_performance_summary()

async def daily_performance_summary():
    """Phase 4 詳細版：取引数・平均Notional・カテゴリ別内訳追加"""
    global MONITORED_WALLETS
    if not MONITORED_WALLETS:
        await send_alert("📉 本日のパフォーマンス集計対象なし", level="info")
        return

    total_pnl = 0.0
    total_trades = 0
    total_notional = 0.0
    category_breakdown = {}

    summary_lines = ["📅 **日次パフォーマンスまとめ** (JST)"]

    for wallet in list(MONITORED_WALLETS):
        result = await calculate_composite_score(wallet)
        details = result.get("details", {})
        score = details.get("composite_score", 0)
        sample_size = details.get("sample_size", 0)

        if score <= 0 or sample_size == 0:
            continue

        pnl = details.get("total_pnl", 0)
        win_rate = details.get("win_rate", 0)
        trades = sample_size

        total_pnl += pnl
        total_trades += trades
        total_notional += pnl  # 簡易NotionalとしてPnL使用（後で本当の取引額に強化可）

        # カテゴリ別内訳
        for cat, data in details.get("category_stats", {}).items():
            if cat != "OVERALL":
                if cat not in category_breakdown:
                    category_breakdown[cat] = {"pnl": 0, "count": 0}
                category_breakdown[cat]["pnl"] += data.get("pnl", 0)
                category_breakdown[cat]["count"] += data.get("count", 0)

        summary_lines.append(
            f"`{wallet[:8]}...` → ${pnl:,.0f} | 勝率 {win_rate:.1f}% | {trades}件"
        )

    # クリーンアップ
    MONITORED_WALLETS = set([w for w in MONITORED_WALLETS if True])  # 将来的にフィルタ強化

    avg_notional = total_notional / total_trades if total_trades > 0 else 0

    summary_lines.append("\n📊 **詳細集計**")
    summary_lines.append(f"👥 A級ウォレット数: {len(MONITORED_WALLETS)}件")
    summary_lines.append(f"💰 総PnL: **${total_pnl:,.0f}**")
    summary_lines.append(f"📈 総取引数: {total_trades}件")
    summary_lines.append(f"📊 平均Notional: **${avg_notional:,.0f}**")
    
    # カテゴリ別内訳
    summary_lines.append("\n📍 **カテゴリ別内訳**")
    for cat, data in category_breakdown.items():
        summary_lines.append(f"・{cat}: ${data['pnl']:,.0f} ({data['count']}件)")

    # RiskManager
    risk_manager.reset_daily()
    dd_daily = (-risk_manager.daily_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0
    dd_total = (-risk_manager.total_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0
    summary_lines.append(f"\n🛡️ 1日ドローダウン: {dd_daily:.1f}% | 累積: {dd_total:.1f}%")
    summary_lines.append(f"モード: 📋 Paper")

    full_msg = "\n".join(summary_lines)
    await send_alert(full_msg, level="success")
    print("✅ 詳細日次まとめ送信完了")

    # 毎日終了時にCSV出力
    await export_daily_csv()

async def hourly_paper_log():
    """Paper Mode専用：1時間ごとの簡易サマリーログ"""
    if not TRADE_LOG:
        return
    recent = TRADE_LOG[-10:]  # 直近10件
    msg = f"📋 **Paper Mode 1時間ログ** (JST)\n直近取引数: {len(recent)}件\n"
    for t in recent[-5:]:
        msg += f"• {t['time']} | {t['wallet'][:8]}... | {t['side']} {t['notional']:.2f} USDC\n"
    await send_alert(msg, level="info")

async def export_daily_csv():
    """毎日終了時にCSV出力"""
    if not TRADE_LOG:
        return
    df = pd.DataFrame(TRADE_LOG)
    filename = f"{LOG_DIR}/paper_trades_{datetime.now().strftime('%Y%m%d')}.csv"
    df.to_csv(filename, index=False, encoding="utf-8")
    print(f"✅ Paper Mode取引ログCSV出力完了: {filename}")

# 時系列テキスト表（毎日まとめに追加済み）
async def realtime_monitor():
    print(f"🔍 {datetime.now().strftime('%H:%M:%S')} リアルタイム監視中...（{len(MONITORED_WALLETS)}件）")
    
    if risk_manager.is_stopped():
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
            notional = min(size * COPY_EXECUTION.get("COPY_RATIO", 0.05) * price, COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10))

            # Paper Mode取引をログに記録（時系列グラフ用）
            TRADE_LOG.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "wallet": wallet,
                "side": side,
                "notional": notional,
                "market": market.get("question", "Unknown")
            })

            success = await copy_executor.execute_copy(
                wallet_address=wallet,
                market=market,
                side=side,
                size=size,
                price=price
            )

        if new_trades:
            await send_alert(f"🔥 新取引検知！ ウォレット: `{wallet[:8]}...` | 取引数: {len(new_trades)}件 | モード: Paper", level="high")

scheduler = AsyncIOScheduler()

async def main():
    await init_db()
    print(f"🚀 {BOT_NAME} Phase 4 Paper Mode分析強化版 を起動...")
    await send_alert(f"{BOT_NAME} Paper Mode分析強化版起動！\n・詳細日次まとめ\n・1時間ログ\n・取引CSV出力", level="success")
    
    await daily_full_evaluation()
    
    scheduler.add_job(daily_full_evaluation, 'cron', hour=DAILY_EVAL_HOUR, minute=0)
    scheduler.add_job(realtime_monitor, 'interval', seconds=POLLING_INTERVAL_SECONDS)
    scheduler.add_job(hourly_paper_log, 'interval', hours=1)   # 1時間ごとPaperログ
    
    print("⏰ Scheduler開始（分析機能強化済み）")
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 ボットを停止します...")
        scheduler.shutdown()