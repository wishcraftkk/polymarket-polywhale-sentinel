import asyncio
from datetime import datetime

from config import COPY_EXECUTION, TOTAL_CAPITAL_USDC
from modules.alert import send_alert
from modules.evaluation import get_market_category
from modules.risk_manager import risk_manager

try:
    from py_clob_client.order_builder.constants import BUY, SELL
    PY_CLOB_AVAILABLE = True
except ImportError:
    PY_CLOB_AVAILABLE = False

class CopyExecutor:
    def __init__(self):
        self.enabled = COPY_EXECUTION.get("ENABLED", False)
        self.paper_mode = COPY_EXECUTION.get("PAPER_MODE", True)
        self.live_mode = COPY_EXECUTION.get("LIVE_MODE", False)
        self.daily_trade_count = 0
        self.last_reset_date = datetime.now().date()
        
        print("🧪 CopyExecutor: Paper Mode で初期化（実際の注文は送信されません）")
        print(f"📌 対象カテゴリ: {COPY_EXECUTION.get('ALLOWED_CATEGORIES', [])}")
        print(f"🛡️ RiskManager連携: {'有効' if COPY_EXECUTION.get('TRACK_DRAWDOWN', True) else '無効'}")
    
    def reset_daily_counter(self):
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_trade_count = 0
            self.last_reset_date = today
    
    def _check_risk(self, trade: dict, wallet_score: float) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Copy Executionが無効"
        
        if risk_manager.is_stopped():
            return False, "RiskManagerにより停止中"
        
        self.reset_daily_counter()
        
        if self.daily_trade_count >= COPY_EXECUTION.get("MAX_TRADES_PER_DAY", 8):
            return False, "1日の取引上限超過"
        
        if wallet_score < COPY_EXECUTION.get("MIN_TARGET_SCORE", 85):
            return False, f"スコア不足 ({wallet_score:.1f})"
        
        # カテゴリフィルタ（シンプル版）
        title = trade.get("title") or trade.get("question") or trade.get("market") or ""
        category = "POLITICS" if "TRUMP" in title.upper() or "ELECTION" in title.upper() or "POLITICS" in title.upper() else "OTHER"
        
        allowed = COPY_EXECUTION.get("ALLOWED_CATEGORIES", [])
        if allowed and category not in allowed:
            return False, f"カテゴリ除外: {category}"
        
        size = float(trade.get("size", 0) or 0)
        price = float(trade.get("price", 0.5))
        notional = size * price * COPY_EXECUTION.get("COPY_RATIO", 0.10)
        notional = min(notional, COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 20))
        
        if notional < 2.0:
            return False, "コピー金額が小さすぎる"
        
        return True, f"OK (${notional:.1f} USDC | {category})"
    
    async def execute_copy(self, wallet: str, trade: dict, score_details: dict):
        composite_score = score_details.get("composite_score", 0)
        
        ok, reason = self._check_risk(trade, composite_score)
        if not ok:
            print(f"⛔ Copyスキップ: {reason} | Wallet: {wallet[:8]}...")
            
            # RiskManager停止時の緊急アラート（ここでasync送信 → 確実に届く）
            if "RiskManagerにより停止中" in reason:
                await send_alert(f"🚨 **緊急停止**: RiskManagerによりCopy Executionが停止されました\n理由: ドローダウン超過", level="error")
            
            return False
        
        # ... 通常のPaper Mode処理（省略せずそのまま残す）
        side_str = str(trade.get("side", "")).upper()
        action = "BUY" if side_str in ["BUY", "LONG"] else "SELL"
        
        size = float(trade.get("size", 0) or 0)
        price = float(trade.get("price", 0.5))
        copy_size = size * COPY_EXECUTION.get("COPY_RATIO", 0.10)
        estimated_usdc = copy_size * price
        
        token_id = trade.get("asset") or trade.get("token_id") or trade.get("conditionId") or "UNKNOWN"
        
        msg = f"""
🧪 **Paper Mode コピーシミュレーション**
ウォレット: `{wallet[:8]}...` (Score: {composite_score:.1f})
取引: **{action}** {copy_size:.3f} shares @ ~${price:.3f}
推定金額: **${estimated_usdc:.2f}** USDC
カテゴリ: POLITICS (テスト用)
Token: `{str(token_id)[:16]}...`
        """.strip()
        
        await send_alert(msg, level="info")
        print(f"🧪 Paper: {action} {copy_size:.3f} shares (~${estimated_usdc:.2f}) | {wallet[:8]}...")
        
        self.daily_trade_count += 1
        risk_manager.update_pnl(0.0)
        
        return True

# グローバルインスタンス
copy_executor = CopyExecutor()
