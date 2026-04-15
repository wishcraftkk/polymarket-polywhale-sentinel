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

# ==================== Phase 3: Copy Execution ====================
COPY_EXECUTION = {
    "ENABLED": False,                    # 本番運用時は True（最初は必ず False）
    "PAPER_MODE": True,                  # Paper Modeをデフォルト（安全最優先）
    "COPY_RATIO": 0.10,                  # 対象ウォレットの取引額に対するコピー割合（資金200で控えめ）
    "MAX_NOTIONAL_PER_TRADE": 20,        # 1取引あたりの最大USDC金額（資金の10%以内）
    "MAX_EXPOSURE_PERCENT": 0.25,        # 同時最大露出率（総資金の25% = 50 USDC程度）
    "MAX_SLIPPAGE_PERCENT": 0.05,        # 最大許容スリッページ（5%）
    "MAX_DAILY_DRAWDOWN": 0.05,          # 1日の最大損失率（5% = 10 USDCで停止）
    "MAX_TOTAL_DRAWDOWN": 0.15,          # 累積最大損失率
    "MIN_TARGET_SCORE": 85,              # 最低Composite Score
    "ALLOWED_CATEGORIES": ["POLITICS"],  # 最初はPoliticsのみ推奨（安定性が高い）
    "MAX_TRADES_PER_DAY": 8,             # 資金が少ないので1日8回以内に制限

    # 新規追加：ドローダウン監視用
    "TRACK_DRAWDOWN": True,
    "INITIAL_CAPITAL": 200.0,        # 開始時資金（実際の残高と同期させる予定）

    # Live Mode設定（まだ使用しない）
    "LIVE_MODE": False,                  # 絶対にTrueにしない（Paper Mode検証後）
    "CL OB_HOST": "https://clob.polymarket.com",
    "CHAIN_ID": 137,                     # Polygon Mainnet
    "SIGNATURE_TYPE": 0,                 # 0 = 標準EOA（MetaMask/Hardware Wallet推奨）
    # FUNDER_ADDRESS と PRIVATE_KEY は .env やハードウェアから動的に読み込む（コードに絶対書かない）
}

# 総運用資金（USDC）
TOTAL_CAPITAL_USDC = 200.0
