import os
from dotenv import load_dotenv

load_dotenv()

# ==================== 基本設定 ====================
BOT_NAME = "PolyWhale Sentinel"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Polymarket API
POLYMARKET_DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"   # ← カテゴリ分析用に追加

# ==================== Grok推奨評価設定 ====================
MIN_SAMPLE_SIZE = 50                    # A級必須取引数
MAX_DRAWDOWN = 0.30                     # 最大ドローダウン閾値（30%超で赤信号）
SINGLE_MARKET_DEPENDENCY = 0.50         # 単一マーケット依存率（50%超で排除）
RECENT_INACTIVE_DAYS = 30               # 最近無活動日数

# スコアリング重み（設計書＋あなたの好みに最適化）
COMPOSITE_WEIGHTS = {
    "A": 0.40,      # Total PnL / Win Rate / Sample Size / Drawdown（最重要）
    "B": 0.35,      # Sharpe / Gain-Loss / カテゴリ別Win Rate
    "RECENT": 0.15, # 直近パフォーマンス
    "C": 0.10       # 補助指標（Volume / Streak）
}

# スケジュール
DAILY_EVAL_HOUR = 6          # 朝6時（日本時間）
POLLING_INTERVAL_SECONDS = 60

# データ保存
DB_PATH = "data/polywhale.db"
LOG_DIR = "logs"

# ==================== テスト用ウォレット ====================
TEST_WALLETS = [
    "0x0fe40e887acbd0022f89d996acce26ab428501b7",   # gobblewobble
]

# ==================== Discovery設定 ====================
DISCOVERY_LIMIT = 20
DISCOVERY_CATEGORIES = ["OVERALL", "POLITICS", "CRYPTO", "SPORTS"]

print("✅ config.py 更新完了（Grok推奨値適用）")