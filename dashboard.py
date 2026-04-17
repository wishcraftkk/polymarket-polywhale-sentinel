import streamlit as st
import pandas as pd
import asyncio
import sys
import os
from datetime import datetime
import threading

# プロジェクトのパスを設定
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import BOT_NAME, COPY_EXECUTION
from modules.evaluation import calculate_composite_score
from modules.alert import format_wallet_link  # リンク生成用

st.set_page_config(page_title=f"{BOT_NAME} Dashboard", layout="wide")
st.title(f"🚀 {BOT_NAME} - 管理ダッシュボード")
st.caption(f"モード: {'🟢 Live' if not COPY_EXECUTION.get('PAPER_MODE', True) else '📋 Paper'} | 最終更新: {datetime.now().strftime('%H:%M:%S')}")

# グローバル変数（main.pyと共有）
try:
    from main import MONITORED_WALLETS, TRADE_LOG, OPPORTUNITY_LOG
except:
    MONITORED_WALLETS = set()
    TRADE_LOG = []
    OPPORTUNITY_LOG = []

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("監視中ウォレット", len(MONITORED_WALLETS))
with col2:
    st.metric("当日PnL", "$0")  # 後で実装
with col3:
    st.metric("機会損失", f"{len(OPPORTUNITY_LOG)}件")
with col4:
    st.button("🛑 緊急停止", type="primary", use_container_width=True, key="emergency_stop")

st.subheader("A級ウォレット一覧")
wallet_data = []
for wallet in list(MONITORED_WALLETS):
    result = asyncio.run(calculate_composite_score(wallet))
    details = result.get("details", {})
    wallet_data.append({
        "ウォレット": format_wallet_link(wallet),
        "総合スコア": details.get("composite_score", 0),
        "データ件数": details.get("sample_size", 0),
        "操作": "除外"
    })

if wallet_data:
    df = pd.DataFrame(wallet_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("現在監視中のA級ウォレットはありません")

st.caption("※ ダッシュボードは5秒ごとに自動更新されます（開発中）")
