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
from modules.evaluation import calculate_composite_score

STOP_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stop.flag")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared_state.json")

st.set_page_config(page_title=f"{BOT_NAME} Dashboard", layout="wide")
st.title(f"🚀 {BOT_NAME} - 管理ダッシュボード")
st.caption(f"モード: {'🟢 Live' if not COPY_EXECUTION.get('PAPER_MODE', True) else '📋 Paper'} | 最終更新: {datetime.now().strftime('%H:%M:%S JST')}")

# 状態読み込み
if os.path.exists(STATE_FILE):
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            MONITORED_WALLETS = set(state.get("MONITORED_WALLETS", []))
            TRADE_LOG = state.get("TRADE_LOG", [])
            OPPORTUNITY_LOG = state.get("OPPORTUNITY_LOG", [])
    except:
        MONITORED_WALLETS = set()
        TRADE_LOG = []
        OPPORTUNITY_LOG = []
else:
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
    st.error("🚨 ボットは緊急停止中です。screenで再起動してください。")

# ==================== パラメータ調整パネル（実際の反映機能） ====================
st.subheader("⚙️ パラメータ調整パネル (Live Mode時のみ有効)")

col1, col2 = st.columns(2)
with col1:
    new_copy_ratio = st.slider("COPY_RATIO", 0.01, 0.20, COPY_EXECUTION.get("COPY_RATIO", 0.05), 0.01)
    new_max_notional = st.number_input("MAX_NOTIONAL_PER_TRADE (USDC)", 1, 50, COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10))
with col2:
    new_max_trades = st.number_input("MAX_TRADES_PER_DAY", 1, 50, COPY_EXECUTION.get("MAX_TRADES_PER_DAY", 8))

allowed_cats = st.multiselect(
    "ALLOWED_CATEGORIES",
    ["POLITICS", "CRYPTO", "SPORTS", "OTHER"],
    default=COPY_EXECUTION.get("ALLOWED_CATEGORIES", ["POLITICS"])
)

if st.button("💾 設定を即時反映", type="secondary"):
    # config.pyを動的に更新
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if "COPY_RATIO" in line:
            new_lines.append(f'    "COPY_RATIO": {new_copy_ratio},\n')
        elif "MAX_NOTIONAL_PER_TRADE" in line:
            new_lines.append(f'    "MAX_NOTIONAL_PER_TRADE": {new_max_notional},\n')
        elif "MAX_TRADES_PER_DAY" in line:
            new_lines.append(f'    "MAX_TRADES_PER_DAY": {new_max_trades},\n')
        elif "ALLOWED_CATEGORIES" in line:
            new_lines.append(f'    "ALLOWED_CATEGORIES": {allowed_cats},\n')
        else:
            new_lines.append(line)
    
    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    st.success("✅ config.pyを更新しました！\nボットを再起動すると新しい設定が反映されます。")
    st.rerun()

# ==================== 当日PnLグラフ ====================
st.subheader("📈 当日PnL推移 (グラフ)")
if TRADE_LOG:
    df_log = pd.DataFrame(TRADE_LOG)
    df_log["time"] = pd.to_datetime(df_log["time"])
    df_log = df_log.sort_values("time")
    df_log["cum_pnl"] = df_log["pnl"].cumsum()
    st.line_chart(df_log.set_index("time")["cum_pnl"], use_container_width=True)
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("本日エントリー数", len(df_log))
    with col2: st.metric("取得原価合計", f"${df_log['notional'].sum():,.2f}")
    with col3: st.metric("累積PnL", f"${df_log['cum_pnl'].iloc[-1]:,.2f}" if not df_log.empty else "$0")
else:
    st.info("本日の取引データがまだありません")

# ==================== 機会損失分析 ====================
st.subheader("📉 機会損失分析")
if OPPORTUNITY_LOG:
    df_opp = pd.DataFrame(OPPORTUNITY_LOG)
    st.metric("今日の機会損失", f"{len(df_opp)}件 (想定PnL ${sum(o.get('notional',0) for o in OPPORTUNITY_LOG):,.2f})")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**拒否理由別**")
        st.dataframe(df_opp["reason"].value_counts(), use_container_width=True)
    with col2:
        st.write("**最近の拒否取引**")
        st.dataframe(df_opp.tail(10)[["time", "wallet", "market", "notional", "reason"]], use_container_width=True, hide_index=True)
else:
    st.info("現在、機会損失は発生していません")

# ==================== A級ウォレット一覧 ====================
st.subheader("A級ウォレット一覧")
wallet_data = []
for wallet in list(MONITORED_WALLETS):
    try:
        result = asyncio.run(calculate_composite_score(wallet))
        details = result.get("details", {})
        wallet_data.append({
            "ウォレット": format_wallet_link(wallet),
            "総合スコア": round(details.get("composite_score", 0), 1),
            "データ件数": details.get("sample_size", 0),
        })
    except:
        pass

if wallet_data:
    df = pd.DataFrame(wallet_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("現在監視中のA級ウォレットはありません")

st.caption("※ ダッシュボードは5秒ごとに自動更新されます")