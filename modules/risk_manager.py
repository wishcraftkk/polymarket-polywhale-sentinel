from datetime import date
import asyncio
from config import COPY_EXECUTION
from modules.alert import send_alert

class RiskManager:
    def __init__(self):
        self.enabled = COPY_EXECUTION.get("TRACK_DRAWDOWN", True)
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.last_reset_date = date.today()
        self.initial_capital = COPY_EXECUTION.get("INITIAL_CAPITAL_USDC", 200.0)
        self.stopped = False
        self.daily_trade_count = 0
        self.last_trade_date = date.today()
        print("🛡️ RiskManager initialized (機会損失記録対応)")

    def reset_daily(self):
        today = date.today()
        if today > self.last_reset_date:
            self.daily_pnl = 0.0
            self.daily_trade_count = 0
            self.last_reset_date = today
            self.stopped = False

    def check_trade(self, notional: float, category: str = "OTHER", wallet: str = None, market_title: str = None) -> dict:
        """取引前チェック + 拒絶時は機会損失として記録"""
        self.reset_daily()

        if self.stopped:
            return {"approved": False, "reason": "RiskManager stopped"}

        allowed = COPY_EXECUTION.get("ALLOWED_CATEGORIES", ["POLITICS"])
        if allowed and category not in allowed:
            reason = f"Category {category} not allowed"
            # 機会損失記録（main.py側で受け取ってOPPORTUNITY_LOGに追加）
            return {"approved": False, "reason": reason, "category": category, "wallet": wallet, "market": market_title}

        if date.today() == self.last_trade_date:
            if self.daily_trade_count >= COPY_EXECUTION.get("MAX_TRADES_PER_DAY", 8):
                return {"approved": False, "reason": "Daily trade limit reached"}
        else:
            self.daily_trade_count = 0
            self.last_trade_date = date.today()

        max_notional = COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10)
        if notional > max_notional:
            return {"approved": False, "reason": f"Notional {notional:.2f} exceeds max"}

        return {"approved": True, "reason": "All checks passed"}

    def update_pnl(self, realized_pnl: float):
        if not self.enabled or self.stopped:
            return False
        self.reset_daily()
        self.daily_pnl += realized_pnl
        self.total_pnl += realized_pnl
        # ドローダウンチェック（省略）
        return True

    def is_stopped(self):
        return self.stopped

risk_manager = RiskManager()