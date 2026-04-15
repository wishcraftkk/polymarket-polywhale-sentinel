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

# ==================== 【Phase 4】 COPY_EXECUTION 設定（Live Mode 安全設計） ====================
COPY_EXECUTION = {
    "ENABLED": True,                    # コピー機能全体のオン/オフ（緊急停止用）
    "PAPER_MODE": True,                 # True = Paper Mode（検証中） / False = Live Mode（本番USDC自動注文）
    
    # ポジションサイズ制御
    "COPY_RATIO": 0.05,                 # 対象ウォレットの取引額に対するコピー比率（最初は5%超安全）
    "MAX_NOTIONAL_PER_TRADE": 10,       # 1取引あたりの絶対上限（USDC）
    
    # リスク制限
    "MAX_EXPOSURE_PERCENT": 0.25,       # 同時最大露出率（総資金の25%以内）
    "MAX_SLIPPAGE_PERCENT": 0.5,        # 許容スリッページ（%）
    "MAX_TRADES_PER_DAY": 8,            # 1日の最大取引数
    "MIN_TARGET_SCORE": 85,             # A級のみ対象（Composite Score閾値）
    "ALLOWED_CATEGORIES": ["POLITICS"], # Politics特化推奨（最初はこれで）
    
    # ドローダウン監視（RiskManager連携）
    "TRACK_DRAWDOWN": True,
    "MAX_DAILY_DRAWDOWN": 0.05,         # 1日5%で自動停止
    "MAX_TOTAL_DRAWDOWN": 0.15,         # 累積15%で自動停止
    
    # 資金設定（実際の残高に合わせて調整）
    "INITIAL_CAPITAL_USDC": 200.0,      # 運用開始資金
    "TOTAL_CAPITAL_USDC": 4000.0,       # 総資産（リスク計算用）← あなたの実際の資金に変更推奨
}

# ==================== Hardware Wallet / ClobClient 用設定（Phase 4） ====================
CLOB_CONFIG = {
    "HOST": "https://clob.polymarket.com",
    "CHAIN_ID": 137,                    # Polygon Mainnet
    "SIGNATURE_TYPE": 0,                # 0 = 標準（Ledger + MetaMask推奨）
}

print(f"✅ {BOT_NAME} config.py 読み込み完了 - Phase 4 Live Mode 準備完了 (PAPER_MODE: {COPY_EXECUTION['PAPER_MODE']})")