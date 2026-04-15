import os
from dotenv import load_dotenv

load_dotenv()

# ==================== 基本設定 ====================
BOT_NAME = "PolyWhale Sentinel"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Polymarket API
POLYMARKET_DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

# ==================== 評価設定 (Phase 3 から継続) ====================
MIN_SAMPLE_SIZE = 50
MAX_DRAWDOWN = 0.30
SINGLE_MARKET_DEPENDENCY = 0.50
RECENT_INACTIVE_DAYS = 30

COMPOSITE_WEIGHTS = {
    "A": 0.40,
    "B": 0.35,
    "RECENT": 0.15,
    "C": 0.10
}

# スケジュール
DAILY_EVAL_HOUR = 6
POLLING_INTERVAL_SECONDS = 60

# データ保存
DB_PATH = "data/polywhale.db"
LOG_DIR = "logs"

# ==================== テスト用ウォレット ====================
TEST_WALLETS = [
    "0x0fe40e887acbd0022f89d996acce26ab428501b7",
]

# ==================== Discovery設定 ====================
DISCOVERY_LIMIT = 20
DISCOVERY_CATEGORIES = ["OVERALL", "POLITICS", "CRYPTO", "SPORTS"]

# ==================== 【Phase 4】 COPY_EXECUTION 設定 ====================
COPY_EXECUTION = {
    "ENABLED": True,
    "PAPER_MODE": True,
    
    # ポジションサイズ制御
    "COPY_RATIO": 0.05,
    "MAX_NOTIONAL_PER_TRADE": 10,
    
    # リスク制限
    "MAX_EXPOSURE_PERCENT": 0.25,
    "MAX_SLIPPAGE_PERCENT": 0.5,
    "MAX_TRADES_PER_DAY": 8,
    "MIN_TARGET_SCORE": 85,
    
    # 【ここを修正】カテゴリフィルタを一時的に緩和（Paper Mode検証用）
    "ALLOWED_CATEGORIES": ["POLITICS", "CRYPTO", "SPORTS", "OTHER"],   # ← 全カテゴリ許可
    
    # ドローダウン監視
    "TRACK_DRAWDOWN": True,
    "MAX_DAILY_DRAWDOWN": 0.05,
    "MAX_TOTAL_DRAWDOWN": 0.15,
    
    "INITIAL_CAPITAL_USDC": 200.0,
    "TOTAL_CAPITAL_USDC": 4000.0,
}

# ==================== Hardware Wallet / ClobClient 用設定（Phase 4） ====================
CLOB_CONFIG = {
    "HOST": "https://clob.polymarket.com",
    "CHAIN_ID": 137,                    # Polygon Mainnet
    "SIGNATURE_TYPE": 0,                # 0 = 標準（Ledger + MetaMask推奨）
}

print(f"✅ {BOT_NAME} config.py 読み込み完了 - Phase 4 Live Mode 準備完了 (PAPER_MODE: {COPY_EXECUTION['PAPER_MODE']})")