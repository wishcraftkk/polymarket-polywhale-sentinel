import os
import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from py_clob_client.client import ClobClient
import telegram

from config import COPY_EXECUTION, CLOB_CONFIG, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from modules.risk_manager import risk_manager

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")

class CopyExecutor:
    def __init__(self):
        self.enabled = COPY_EXECUTION.get("ENABLED", False)
        self.paper_mode = COPY_EXECUTION.get("PAPER_MODE", True)
        self.copy_ratio = COPY_EXECUTION.get("COPY_RATIO", 0.05)
        self.max_notional = COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10)
        self.max_slippage = COPY_EXECUTION.get("MAX_SLIPPAGE_PERCENT", 0.5)
        self.risk_manager = risk_manager
        self.bot = telegram.Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        try:
            private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
            if not private_key:
                logger.error("❌ POLYMARKET_PRIVATE_KEY が .env にありません")
                return
            self.client = ClobClient(
                host=CLOB_CONFIG["HOST"],
                chain_id=CLOB_CONFIG["CHAIN_ID"],
                key=private_key,
                signature_type=CLOB_CONFIG["SIGNATURE_TYPE"]
            )
            logger.info(f"✅ ClobClient 初期化完了 (Dedicated EOA Mode)")
        except Exception as e:
            logger.error(f"ClobClient初期化失敗: {e}")

    async def execute_copy(self, wallet_address: str, market: dict, side: str, size: float, price: float):
        if not self.enabled:
            return False

        try:
            market_title = market.get("question") or market.get("title") or market.get("market") or "Unknown Market"
            notional = min(size * self.copy_ratio * price, self.max_notional)

            risk_check = self.risk_manager.check_trade(
                notional=notional,
                category=market.get("category", "OTHER"),
                wallet=wallet_address,
                market_title=market_title
            )

            if not risk_check["approved"]:
                # 機会損失として詳細通知
                await self._send_notification(
                    f"❌ Risk Check Failed: {risk_check['reason']}\n"
                    f"Wallet: `{wallet_address[:8]}...`\n"
                    f"Market: {market_title}\n"
                    f"Side: {side.upper()} | Notional: **{notional:.2f} USDC**"
                )
                return False

            # 以降はPaper/Live実行（前回版と同じ）
            if self.paper_mode:
                await self._send_notification(
                    f"📋 **Paper Mode Execution**\n"
                    f"Wallet: `{wallet_address[:8]}...`\n"
                    f"Market: {market_title}\n"
                    f"Side: {side.upper()} | Notional: **{notional:.2f} USDC**"
                )
                return True
            # Live Mode部分は省略（必要なら追加）
            return True

        except Exception as e:
            await self._send_notification(f"❌ Copy Execution Error: {str(e)}")
            return False

    async def _send_notification(self, message: str):
        if self.bot and TELEGRAM_CHAT_ID:
            try:
                jst_time = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')
                full_msg = f"{message}\n\n🕒 {jst_time}"
                await self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=full_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"通知失敗: {e}")

copy_executor = CopyExecutor()