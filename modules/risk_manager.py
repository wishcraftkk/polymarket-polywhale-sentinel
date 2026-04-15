from datetime import date
import asyncio
from config import COPY_EXECUTION  # TOTAL_CAPITAL_USDCは削除（辞書内から取得）

class RiskManager:
    def __init__(self):
        self.enabled = COPY_EXECUTION.get("TRACK_DRAWDOWN", True)
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.last_reset_date = date.today()
        # TOTAL_CAPITAL_USDC を COPY_EXECUTION から安全に取得
        self.initial_capital = COPY_EXECUTION.get("INITIAL_CAPITAL_USDC", 
                                                  COPY_EXECUTION.get("TOTAL_CAPITAL_USDC", 4000.0))
        self.stopped = False
        self.daily_trade_count = 0
        self.last_trade_date = date.today()
        print("🛡️ RiskManager initialized (Phase 4 enhanced - import fixed)")

    def reset_daily(self):
        today = date.today()
        if today > self.last_reset_date:
            self.daily_pnl = 0.0
            self.daily_trade_count = 0
            self.last_reset_date = today
            self.stopped = False

    def check_trade(self, notional: float, category: str = "OTHER") -> dict:
        """取引実行前の総合リスクチェック"""
        self.reset_daily()

        if self.stopped:
            return {"approved": False, "reason": "RiskManager stopped due to previous drawdown"}

        # カテゴリフィルタ
        allowed = COPY_EXECUTION.get("ALLOWED_CATEGORIES", ["POLITICS"])
        if allowed and category not in allowed:
            return {"approved": False, "reason": f"Category {category} not allowed"}

        # 取引数制限
        today = date.today()
        if today == self.last_trade_date:
            if self.daily_trade_count >= COPY_EXECUTION.get("MAX_TRADES_PER_DAY", 8):
                return {"approved": False, "reason": "Daily trade limit reached"}
        else:
            self.daily_trade_count = 0
            self.last_trade_date = today

        # 露出額チェック
        max_notional = COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10)
        if notional > max_notional:
            return {"approved": False, "reason": f"Notional {notional:.2f} exceeds max {max_notional}"}

        return {"approved": True, "reason": "All checks passed"}

    def update_pnl(self, realized_pnl: float):
        """約定後のPnL更新 + ドローダウン監視"""
        if not self.enabled or self.stopped:
            return False

        self.reset_daily()
        self.daily_pnl += realized_pnl
        self.total_pnl += realized_pnl

        daily_dd = (-self.daily_pnl / self.initial_capital)
        total_dd = (-self.total_pnl / self.initial_capital)

        if daily_dd > COPY_EXECUTION.get("MAX_DAILY_DRAWDOWN", 0.05):
            self.stopped = True
            msg = f"🚨 **緊急停止**: 1日ドローダウン超過 ({daily_dd*100:.1f}%)"
            print(f"🛑 {msg}")
            try:
                asyncio.create_task(send_alert(msg, level="error"))
            except:
                pass
            return False

        if total_dd > COPY_EXECUTION.get("MAX_TOTAL_DRAWDOWN", 0.15):
            self.stopped = True
            msg = f"🚨 **緊急停止**: 累積ドローダウン超過 ({total_dd*100:.1f}%)"
            print(f"🛑 {msg}")
            try:
                asyncio.create_task(send_alert(msg, level="error"))
            except:
                pass
            return False

        return True

    def is_stopped(self):
        return self.stopped

# グローバルインスタンス
risk_manager = RiskManager()