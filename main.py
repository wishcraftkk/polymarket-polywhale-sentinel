import asyncio
from datetime import datetime, date
import csv
import os
import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_NAME, DAILY_EVAL_HOUR, POLLING_INTERVAL_SECONDS, TEST_WALLETS, COPY_EXECUTION
from modules.discovery import discover_top_wallets
from modules.evaluation import calculate_composite_score
from modules.alert import send_alert, send_evaluation_alert
from modules.ingestion import check_new_trades
from utils.helpers import init_db
from modules.copy_executor import copy_executor
from modules.risk_manager import risk_manager

# ==================== グローバル変数 ====================
MONITORED_WALLETS = set(TEST_WALLETS)
FIRST_RUN = True

TRADE_LOG = []          # 実際に実行した取引（Paper/Live）
OPPORTUNITY_LOG = []    # 拒絶された取引（機会損失用）

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ==================== 日次フル評価 ====================
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
            continue

        await send_evaluation_alert(wallet, result)
        
        if score >= COPY_EXECUTION.get("MIN_TARGET_SCORE", 85):
            MONITORED_WALLETS.add(wallet)
            print(f"✅ A級追加: {wallet[:8]}...")
    
    print(f"✅ 監視対象ウォレット: {len(MONITORED_WALLETS)}件に更新")
    FIRST_RUN = False
    await daily_performance_summary()

# ==================== 日次パフォーマンスまとめ（24時間分＋機会損失） ====================
async def daily_performance_summary():
    """当日24時間分の集計 + 機会損失表示"""
    today = datetime.now().date()
    
    # 当日分の実行取引
    today_trades = [t for t in TRADE_LOG if datetime.strptime(t["time"], "%H:%M:%S").date() == today]
    today_opp = [o for o in OPPORTUNITY_LOG if datetime.strptime(o["time"], "%H:%M:%S").date() == today]

    total_pnl = sum(t.get("pnl", 0) for t in today_trades)
    total_trades = len(today_trades)
    avg_notional = sum(t.get("notional", 0) for t in today_trades) / total_trades if total_trades > 0 else 0

    opp_pnl = sum(o.get("assumed_pnl", 0) for o in today_opp)
    opp_count = len(today_opp)

    summary_lines = ["📅 **日次パフォーマンスまとめ** (JST)"]

    # A級ウォレット一覧
    for wallet in list(MONITORED_WALLETS):
        result = await calculate_composite_score(wallet)
        details = result.get("details", {})
        score = details.get("composite_score", 0)
        sample_size = details.get("sample_size", 0)
        pnl = details.get("total_pnl", 0)
        win_rate = details.get("win_rate", 0)
        if score > 0 and sample_size > 0:
            summary_lines.append(
                f"`{wallet[:8]}...` → ${pnl:,.0f} | 勝率 {win_rate:.1f}% (データ: {sample_size}件)"
            )

    summary_lines.append("\n📊 **当日集計 (24時間分)**")
    summary_lines.append(f"👥 A級ウォレット数: {len(MONITORED_WALLETS)}件")
    summary_lines.append(f"💰 当日PnL: **${total_pnl:,.0f}**")
    summary_lines.append(f"📈 当日取引数: {total_trades}件")
    summary_lines.append(f"📊 平均Notional: **${avg_notional:,.0f}**")

    # 機会損失
    summary_lines.append(f"\n📉 **機会損失** (拒絶取引)")
    summary_lines.append(f"想定PnL: **${opp_pnl:,.0f}** ({opp_count}件)")

    # RiskManager
    risk_manager.reset_daily()
    dd_daily = (-risk_manager.daily_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0
    dd_total = (-risk_manager.total_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0
    summary_lines.append(f"🛡️ 1日ドローダウン: {dd_daily:.1f}% | 累積: {dd_total:.1f}%")
    summary_lines.append(f"モード: {'🟢 Live' if not COPY_EXECUTION.get('PAPER_MODE') else '📋 Paper'}")

    full_msg = "\n".join(summary_lines)
    await send_alert(full_msg, level="success")
    print("✅ 日次レポート（機会損失含む）送信完了")

    await export_daily_csv()

# ==================== リアルタイム監視 ====================
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
            category = market.get("category", "OTHER")
            market_title = market.get("question") or market.get("title") or market.get("market") or "Unknown Market"

            notional = min(size * COPY_EXECUTION.get("COPY_RATIO", 0.05) * price, 
                          COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10))

            # Risk Check
            risk_check = risk_manager.check_trade(
                notional=notional,
                category=category,
                wallet=wallet,
                market_title=market_title
            )

            if not risk_check.get("approved", False):
                # 機会損失記録
                OPPORTUNITY_LOG.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "wallet": wallet,
                    "market": market_title,
                    "side": side,
                    "notional": notional,
                    "reason": risk_check.get("reason", "Unknown"),
                    "assumed_pnl": 0.0   # 将来的に想定PnL計算を追加可能
                })
                continue

            # 実行記録
            TRADE_LOG.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "wallet": wallet,
                "side": side,
                "notional": notional,
                "market": market_title,
                "pnl": 0.0   # 後で実際のPnLを更新可能
            })

            success = await copy_executor.execute_copy(
                wallet_address=wallet,
                market=market,
                side=side,
                size=size,
                price=price
            )

        if new_trades:
            await send_alert(
                f"🔥 新取引検知！ ウォレット: `{wallet[:8]}...` | 取引数: {len(new_trades)}件 | モード: {'Live' if not COPY_EXECUTION.get('PAPER_MODE') else 'Paper'}",
                level="high"
            )

# ==================== 補助機能 ====================
async def hourly_paper_log():
    if not TRADE_LOG:
        return
    recent = TRADE_LOG[-10:]
    msg = f"📋 **Paper Mode 1時間ログ** (JST)\n直近取引数: {len(recent)}件\n"
    for t in recent[-5:]:
        msg += f"• {t['time']} | {t['wallet'][:8]}... | {t['side']} {t['notional']:.2f} USDC\n"
    await send_alert(msg, level="info")

async def export_daily_csv():
    if TRADE_LOG or OPPORTUNITY_LOG:
        filename = f"{LOG_DIR}/paper_trades_{datetime.now().strftime('%Y%m%d')}.csv"
        df = pd.DataFrame(TRADE_LOG)
        df.to_csv(filename, index=False, encoding="utf-8")
        print(f"✅ CSV出力完了: {filename}")

# ==================== メイン ====================
scheduler = AsyncIOScheduler()

async def main():
    await init_db()
    print(f"🚀 {BOT_NAME} Phase 4 完全分析版 起動...")
    await send_alert(f"{BOT_NAME} 完全分析版起動！\n・当日24時間集計\n・機会損失定量化\n・通知統一", level="success")
    
    await daily_full_evaluation()
    
    scheduler.add_job(daily_full_evaluation, 'cron', hour=DAILY_EVAL_HOUR, minute=0)
    scheduler.add_job(realtime_monitor, 'interval', seconds=POLLING_INTERVAL_SECONDS)
    scheduler.add_job(hourly_paper_log, 'interval', hours=1)
    
    print("⏰ Scheduler開始")
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 ボットを停止します...")
        scheduler.shutdown()