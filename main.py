import asyncio
from datetime import datetime, date, timedelta
import csv
import os
import pandas as pd
import json
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_NAME, DAILY_EVAL_HOUR, POLLING_INTERVAL_SECONDS, TEST_WALLETS, COPY_EXECUTION
from modules.discovery import discover_top_wallets
from modules.evaluation import calculate_composite_score, get_period_performance
from modules.alert import send_alert, send_evaluation_alert, format_wallet_link
from modules.ingestion import check_new_trades
from utils.helpers import init_db
from modules.copy_executor import copy_executor
from modules.risk_manager import risk_manager

JST = ZoneInfo("Asia/Tokyo")

# グローバル変数
MONITORED_WALLETS = set(TEST_WALLETS)
FIRST_RUN = True
TRADE_LOG = []
OPPORTUNITY_LOG = []

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

STOP_FLAG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stop.flag")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_state.json")

def save_shared_state():
    """ダッシュボードと状態を共有"""
    state = {
        "MONITORED_WALLETS": list(MONITORED_WALLETS),
        "TRADE_LOG": TRADE_LOG[-100:],
        "OPPORTUNITY_LOG": OPPORTUNITY_LOG[-100:]
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)

def get_market_title(trade: dict) -> str:
    for key in ["title", "question", "marketQuestion"]:
        if key in trade and trade[key]:
            return str(trade[key])
    market = trade.get("market") or {}
    for key in ["question", "title", "market"]:
        if isinstance(market, dict) and key in market and market[key]:
            return str(market[key])
    return "Unknown Market"

def is_stop_requested():
    if os.path.exists(STOP_FLAG_FILE):
        print(f"🛑 停止フラグを検知しました → {STOP_FLAG_FILE}")
        return True
    return False

def format_wallet_link(wallet: str) -> str:
    short = wallet[:8] + "..."
    url = f"https://polymarket.com/profile/{wallet}"
    return f"[{short}]({url})"

async def daily_full_evaluation():
    global FIRST_RUN
    if is_stop_requested():
        return
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
    
    print(f"✅ 監視対象ウォレット: {len(MONITORED_WALLETS)}件に更新")
    FIRST_RUN = False
    await daily_performance_summary()
    save_shared_state()

async def daily_performance_summary():
    if is_stop_requested():
        return
    today = datetime.now(JST).date()
    today_trades = [t for t in TRADE_LOG if datetime.fromisoformat(t["time"]).date() == today]

    entry_count = len(today_trades)
    entry_total = sum(t.get("notional", 0) for t in today_trades)
    closed_count = 0
    closed_pnl = 0.0
    open_count = entry_count
    open_total = entry_total

    total_pnl = sum(t.get("pnl", 0) for t in today_trades)
    total_trades = entry_count
    avg_notional = entry_total / total_trades if total_trades > 0 else 0

    opp_pnl = sum(o.get("assumed_pnl", 0) for o in OPPORTUNITY_LOG if datetime.fromisoformat(o["time"]).date() == today)
    opp_count = len([o for o in OPPORTUNITY_LOG if datetime.fromisoformat(o["time"]).date() == today])

    summary_lines = ["📅 **日次パフォーマンスまとめ** (JST)"]

    for wallet in list(MONITORED_WALLETS):
        perf = await get_period_performance(wallet, period="1D")
        wallet_link = format_wallet_link(wallet)
        if perf["count"] > 0:
            summary_lines.append(f"{wallet_link} → **${perf['pnl']:,.0f}** | 勝率 {perf['win_rate']:.1f}% (データ: {perf['count']}件)")

    summary_lines.append("\n📊 **当日集計 (24時間分)**")
    summary_lines.append(f"👥 A級ウォレット数: {len(MONITORED_WALLETS)}件")
    summary_lines.append(f"💰 当日PnL: **${total_pnl:,.0f}**")
    summary_lines.append(f"📈 当日取引数: {total_trades}件")
    summary_lines.append(f"📊 平均Notional: **${avg_notional:,.0f}**")

    summary_lines.append("\n📍 **自己ポジション内訳**")
    summary_lines.append(f"✅ エントリー: {entry_count}件 (取得原価合計 **${entry_total:,.2f}** USDC)")
    summary_lines.append(f"🔄 クローズ: Paper Modeのため未追跡 (0件 / PnL $0.00)")
    summary_lines.append(f"📌 オープン: Paper Modeのため未追跡 ({open_count}件 / 取得原価合計 **${open_total:,.2f}** USDC)")

    summary_lines.append(f"\n📉 **機会損失** (拒絶取引)")
    summary_lines.append(f"想定PnL: **${opp_pnl:,.0f}** ({opp_count}件)")

    risk_manager.reset_daily()
    dd_daily = (-risk_manager.daily_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0
    dd_total = (-risk_manager.total_pnl / risk_manager.initial_capital * 100) if risk_manager.initial_capital else 0
    summary_lines.append(f"🛡️ 1日ドローダウン: {dd_daily:.1f}% | 累積: {dd_total:.1f}%")
    summary_lines.append(f"モード: {'🟢 Live' if not COPY_EXECUTION.get('PAPER_MODE') else '📋 Paper'}")

    full_msg = "\n".join(summary_lines)
    await send_alert(full_msg, level="success")
    print("✅ 日次レポート送信完了")

    await export_daily_csv()
    save_shared_state()

async def realtime_monitor():
    if is_stop_requested():
        print("🛑 停止フラグ検知 → realtime_monitor停止")
        return
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

            market_title = get_market_title(trade)
            side = trade.get("side", "buy").lower()
            size = trade.get("size", 0.0)
            price = trade.get("price", 0.0)
            category = trade.get("category", "OTHER")
            notional = min(size * COPY_EXECUTION.get("COPY_RATIO", 0.05) * price, 
                          COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10))

            risk_check = risk_manager.check_trade(notional=notional, category=category, wallet=wallet, market_title=market_title)

            wallet_link = format_wallet_link(wallet)

            if not risk_check.get("approved", False):
                await send_alert(f"❌ **Risk Check Failed**\nウォレット: {wallet_link}\nマーケット: {market_title}\n金額: **{notional:.2f} USDC**\n理由: {risk_check.get('reason', 'Unknown')}", level="warning")
                OPPORTUNITY_LOG.append({"time": datetime.now(JST).isoformat(), "wallet": wallet, "market": market_title, "side": side, "notional": notional, "reason": risk_check.get("reason", "Unknown"), "assumed_pnl": 0.0})
                continue

            TRADE_LOG.append({"time": datetime.now(JST).isoformat(), "wallet": wallet, "side": side, "notional": notional, "market": market_title, "pnl": 0.0})
            await copy_executor.execute_copy(wallet, trade, side, size, price)

        if new_trades:
            wallet_link = format_wallet_link(wallet)
            await send_alert(f"🔥 **新取引検知！**\nウォレット: {wallet_link}\n取引数: {len(new_trades)}件\nモード: {'🟢 Live' if not COPY_EXECUTION.get('PAPER_MODE') else '📋 Paper'}", level="high")
    
    save_shared_state()

async def hourly_paper_log():
    if is_stop_requested():
        return
    now = datetime.now(JST)
    one_hour_ago = now - timedelta(hours=1)
    recent_entries = [t for t in TRADE_LOG if datetime.fromisoformat(t["time"]) > one_hour_ago]
    entry_count = len(recent_entries)
    entry_total = sum(t.get("notional", 0) for t in recent_entries)
    closed_count = 0
    closed_pnl = 0.0
    open_count = entry_count
    open_total = entry_total

    if entry_count == 0:
        msg = f"📋 **Paper Mode 1時間ログ** (JST)\n**エントリー**: 0件 (取得原価合計 **$0.00** USDC)\n**クローズ**: Paper Modeのため未追跡 (0件 / PnL $0.00)\n**オープン**: Paper Modeのため未追跡\n監視中ウォレット: {len(MONITORED_WALLETS)}件"
    else:
        msg = f"📋 **Paper Mode 1時間ログ** (JST)\n**エントリー**: {entry_count}件 (取得原価合計 **${entry_total:,.2f}** USDC)\n**クローズ**: Paper Modeのため未追跡 (0件 / PnL $0.00)\n**オープン**: Paper Modeのため未追跡 ({open_count}件 / 取得原価合計 **${open_total:,.2f}** USDC)\n"
    await send_alert(msg, level="info")
    print("✅ 1時間レポート送信完了")

async def export_daily_csv():
    if TRADE_LOG or OPPORTUNITY_LOG:
        filename = f"{LOG_DIR}/paper_trades_{datetime.now().strftime('%Y%m%d')}.csv"
        pd.DataFrame(TRADE_LOG).to_csv(filename, index=False, encoding="utf-8")
        print(f"✅ CSV出力完了: {filename}")

scheduler = AsyncIOScheduler()

async def main():
    await init_db()
    print(f"🚀 {BOT_NAME} 状態共有＋緊急停止対応版 起動...")

    if is_stop_requested():
        print("🛑 停止フラグが残っていたため起動を中止します")
        return

    await send_alert(f"{BOT_NAME} 状態共有＋緊急停止対応版起動！", level="success")
    
    await daily_full_evaluation()
    await hourly_paper_log()
    
    scheduler.add_job(daily_full_evaluation, 'cron', hour=DAILY_EVAL_HOUR, minute=0)
    scheduler.add_job(realtime_monitor, 'interval', seconds=POLLING_INTERVAL_SECONDS)
    scheduler.add_job(hourly_paper_log, 'cron', minute=0)
    scheduler.add_job(save_shared_state, 'interval', seconds=5)
    
    print("⏰ Scheduler開始")
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 ボットを停止します...")
        if os.path.exists(STOP_FLAG_FILE):
            os.remove(STOP_FLAG_FILE)
        scheduler.shutdown()