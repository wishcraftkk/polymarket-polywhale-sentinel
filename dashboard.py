import streamlit as st
import os
import asyncio
import sys
import json
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import BOT_NAME, COPY_EXECUTION
from modules.alert import format_wallet_link
from modules.evaluation import calculate_composite_score, get_period_performance, calculate_win_rate_focused_score

STOP_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stop.flag")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_state.json")

st.set_page_config(page_title=f"{BOT_NAME} Dashboard", layout="wide")
st.title(f"🚀 {BOT_NAME} - 管理ダッシュボード")
st.caption(f"モード: {'🟢 Live' if not COPY_EXECUTION.get('PAPER_MODE', True) else '📋 Paper'} | 最終更新: {datetime.now().strftime('%H:%M:%S JST')}")

# ==================== 状態読み込み（詳細デバッグ） ====================
st.subheader("🔍 状態読み込み状況")
if os.path.exists(STATE_FILE):
    st.success(f"✅ shared_state.json 存在確認")
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            MONITORED_WALLETS = set(state.get("MONITORED_WALLETS", []))
            TRADE_LOG = state.get("TRADE_LOG", [])
            OPPORTUNITY_LOG = state.get("OPPORTUNITY_LOG", [])
        st.success(f"📦 読み込み成功 → MONITORED_WALLETS: **{len(MONITORED_WALLETS)}件**")
        st.success(f"📊 TRADE_LOG: **{len(TRADE_LOG)}件**")
        st.success(f"📉 OPPORTUNITY_LOG: **{len(OPPORTUNITY_LOG)}件**")
    except Exception as e:
        st.error(f"❌ 読み込みエラー: {e}")
        MONITORED_WALLETS = set()
        TRADE_LOG = []
        OPPORTUNITY_LOG = []
else:
    st.error("❌ shared_state.json が存在しません")
    MONITORED_WALLETS = set()
    TRADE_LOG = []
    OPPORTUNITY_LOG = []

# ==================== 緊急停止ボタン ====================
if st.button("🛑 緊急停止", type="primary", use_container_width=True):
    with open(STOP_FLAG, "w") as f:
        f.write("stop requested by dashboard")
    st.success("✅ 緊急停止信号を発信しました！")
    st.rerun()

if os.path.exists(STOP_FLAG):
    st.error("🚨 ボットは緊急停止中です。")

# ==================== パラメータ調整パネル ====================
st.subheader("⚙️ パラメータ調整パネル")
# （省略せずそのまま残す）
col1, col2 = st.columns(2)
with col1:
    new_copy_ratio = st.slider("COPY_RATIO", 0.01, 0.20, COPY_EXECUTION.get("COPY_RATIO", 0.05), 0.01)
    new_max_notional = st.number_input("MAX_NOTIONAL_PER_TRADE (USDC)", 1, 50, COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10))
with col2:
    new_max_trades = st.number_input("MAX_TRADES_PER_DAY", 1, 50, COPY_EXECUTION.get("MAX_TRADES_PER_DAY", 8))

allowed_cats = st.multiselect("ALLOWED_CATEGORIES", ["POLITICS", "CRYPTO", "SPORTS", "OTHER"], default=COPY_EXECUTION.get("ALLOWED_CATEGORIES", ["POLITICS"]))

if st.button("💾 設定を即時反映"):
    # （省略せずそのまま残す）
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        if "COPY_RATIO" in line: new_lines.append(f'    "COPY_RATIO": {new_copy_ratio},\n')
        elif "MAX_NOTIONAL_PER_TRADE" in line: new_lines.append(f'    "MAX_NOTIONAL_PER_TRADE": {new_max_notional},\n')
        elif "MAX_TRADES_PER_DAY" in line: new_lines.append(f'    "MAX_TRADES_PER_DAY": {new_max_trades},\n')
        elif "ALLOWED_CATEGORIES" in line: new_lines.append(f'    "ALLOWED_CATEGORIES": {allowed_cats},\n')
        else: new_lines.append(line)
    with open(config_path, "w", encoding="utf-8") as f: f.writelines(new_lines)
    st.success("✅ config.py更新完了")
    st.rerun()

# ==================== 当日PnLグラフ ====================
st.subheader("📈 当日PnL推移 (グラフ)")
if TRADE_LOG:
    df_log = pd.DataFrame(TRADE_LOG)
    df_log["time"] = pd.to_datetime(df_log["time"])
    df_log = df_log.sort_values("time")
    df_log["cum_pnl"] = df_log["pnl"].cumsum()
    st.line_chart(df_log.set_index("time")["cum_pnl"])
else:
    st.info("本日の取引データがまだありません")

# ==================== 機会損失分析 ====================
st.subheader("📉 機会損失分析")
if OPPORTUNITY_LOG:
    df_opp = pd.DataFrame(OPPORTUNITY_LOG)
    st.metric("今日の機会損失", f"{len(df_opp)}件 (想定PnL ${sum(o.get('notional',0) for o in OPPORTUNITY_LOG):,.2f})")
    col1, col2 = st.columns(2)
    with col1: st.dataframe(df_opp["reason"].value_counts(), use_container_width=True)
    with col2: st.dataframe(df_opp.tail(10)[["time", "wallet", "market", "notional", "reason"]], hide_index=True, use_container_width=True)
else:
    st.info("現在、機会損失は発生していません")

# ==================== A級ウォレット一覧（同時比較モード） ====================
st.subheader("A級ウォレット一覧（総合スコア vs 勝率特化スコア）")
wallet_data = []
st.info(f"処理対象ウォレット数: **{len(MONITORED_WALLETS)}件**")

for wallet in list(MONITORED_WALLETS):
    try:
        st.info(f"処理中: {wallet[:12]}...")
        all_perf = asyncio.run(get_period_performance(wallet, "ALL"))
        m1_perf = asyncio.run(get_period_performance(wallet, "1M"))
        w1_perf = asyncio.run(get_period_performance(wallet, "1W"))

        composite_result = asyncio.run(calculate_composite_score(wallet))
        win_rate_result = asyncio.run(calculate_win_rate_focused_score(wallet))

        short_name = wallet[:8] + "..."

        wallet_data.append({
            "ウォレット名": short_name,
            "ウォレット": format_wallet_link(wallet),
            "総合スコア": round(composite_result.get("score", 0), 1),
            "勝率スコア": round(win_rate_result.get("score", 0), 1),
            "ALL PnL": f"${all_perf.get('pnl', 0):,.0f}",
            "ALL 件数": all_perf.get("count", 0),
            "ALL 勝率": f"{all_perf.get('win_rate', 0)}%",
            "1M PnL": f"${m1_perf.get('pnl', 0):,.0f}",
            "1M 件数": m1_perf.get("count", 0),
            "1M 勝率": f"{m1_perf.get('win_rate', 0)}%",
            "1W PnL": f"${w1_perf.get('pnl', 0):,.0f}",
            "1W 件数": w1_perf.get("count", 0),
            "1W 勝率": f"{w1_perf.get('win_rate', 0)}%",
        })
    except Exception as e:
        st.error(f"❌ {wallet[:12]}... でエラー: {str(e)[:100]}")

if wallet_data:
    df = pd.DataFrame(wallet_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("現在監視中のA級ウォレットはありません")

st.caption("※ ダッシュボードは60秒ごとに自動更新されます")