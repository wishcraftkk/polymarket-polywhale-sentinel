from datetime import date
from config import COPY_EXECUTION, TOTAL_CAPITAL_USDC
from modules.alert import send_alert

class RiskManager:
    def __init__(self):
        self.enabled = COPY_EXECUTION.get("TRACK_DRAWDOWN", True)
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.last_reset_date = date.today()
        self.initial_capital = COPY_EXECUTION.get("INITIAL_CAPITAL", TOTAL_CAPITAL_USDC)
        self.stopped = False
        print("🛡️ RiskManager: ドローダウン監視を初期化（Paper Mode対応）")
    
    def reset_daily(self):
        today = date.today()
        if today > self.last_reset_date:
            self.daily_pnl = 0.0
            self.last_reset_date = today
            self.stopped = False
    
    def update_pnl(self, realized_pnl: float):
        """PnL更新 + ドローダウン監視（アラートをシンプル同期呼び出し）"""
        if not self.enabled or self.stopped:
            return False
        
        self.reset_daily()
        self.daily_pnl += realized_pnl
        self.total_pnl += realized_pnl
        
        daily_dd_percent = (-self.daily_pnl / self.initial_capital) * 100
        total_dd_percent = (-self.total_pnl / self.initial_capital) * 100
        
        max_daily = COPY_EXECUTION.get("MAX_DAILY_DRAWDOWN", 0.05) * 100
        max_total = COPY_EXECUTION.get("MAX_TOTAL_DRAWDOWN", 0.15) * 100
        
        if daily_dd_percent > max_daily:
            self.stopped = True
            msg = f"🚨 **緊急停止**: 1日ドローダウン超過 ({daily_dd_percent:.1f}% > {max_daily:.1f}%)"
            print(f"🛑 {msg}")
            # シンプル同期呼び出し
            try:
                import asyncio
                asyncio.get_event_loop().create_task(send_alert(msg, level="error"))
            except:
                print("アラート送信試行（メインループ使用）")
            return False
        
        if total_dd_percent > max_total:
            self.stopped = True
            msg = f"🚨 **緊急停止**: 累積ドローダウン超過 ({total_dd_percent:.1f}% > {max_total:.1f}%)"
            print(f"🛑 {msg}")
            try:
                import asyncio
                asyncio.get_event_loop().create_task(send_alert(msg, level="error"))
            except:
                print("アラート送信試行（メインループ使用）")
            return False
        
        return True
    
    def is_stopped(self):
        return self.stopped

# グローバルインスタンス
risk_manager = RiskManager()
