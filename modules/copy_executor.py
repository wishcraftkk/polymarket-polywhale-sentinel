import os
import logging
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from py_clob_client.client import ClobClient
import telegram

from config import COPY_EXECUTION, CLOB_CONFIG, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from modules.risk_manager import RiskManager

logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")

class CopyExecutor:
    def __init__(self):
        self.enabled = COPY_EXECUTION.get("ENABLED", False)
        self.paper_mode = COPY_EXECUTION.get("PAPER_MODE", True)
        self.copy_ratio = COPY_EXECUTION.get("COPY_RATIO", 0.05)
        self.max_notional = COPY_EXECUTION.get("MAX_NOTIONAL_PER_TRADE", 10)
        self.max_slippage = COPY_EXECUTION.get("MAX_SLIPPAGE_PERCENT", 0.5)
        
        self.risk_manager = RiskManager()
        
        # Telegram通知用
        self.bot = telegram.Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None
        
        # ClobClient 初期化（専用EOA + private_key方式）
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """専用EOA + private_key方式（API Credentials手動不要）"""
        try:
            private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
            if not private_key:
                logger.error("❌ POLYMARKET_PRIVATE_KEY が .env にありません")
                return

            self.client = ClobClient(
                host=CLOB_CONFIG["HOST"],
                chain_id=CLOB_CONFIG["CHAIN_ID"],
                key=private_key,                    # 専用EOAのprivate_keyを直接渡す
                signature_type=CLOB_CONFIG["SIGNATURE_TYPE"]
            )
            logger.info(f"✅ ClobClient 初期化完了 (Dedicated EOA Mode | Paper Mode: {self.paper_mode})")
        except Exception as e:
            logger.error(f"ClobClient 初期化失敗: {e}")

    async def execute_copy(self, wallet_address: str, market: dict, side: str, size: float, price: float):
        if not self.enabled:
            return False

        try:
            # RiskManagerチェック
            risk_check = self.risk_manager.check_trade(
                notional=size * price,
                category=market.get("category", "OTHER")
            )
            if not risk_check["approved"]:
                await self._send_notification(f"❌ Risk Check Failed: {risk_check['reason']}")
                return False

            notional = min(size * self.copy_ratio * price, self.max_notional)
            market_title = market.get("question") or market.get("title") or market.get("market") or "Unknown Market"

            if self.paper_mode:
                logger.info(f"[PAPER MODE] Simulated copy → {wallet_address[:8]}... | {side.upper()} {notional:.2f} USDC")
                await self._send_notification(
                    f"📋 **Paper Mode Execution**\n"
                    f"Wallet: `{wallet_address[:8]}...`\n"
                    f"Market: {market_title}\n"
                    f"Side: {side.upper()} | Notional: **{notional:.2f} USDC**\n"
                    f"Original Size: {size:.2f} | Price: {price:.4f}"
                )
                return True
            else:
                # Live Mode（本番USDC注文）
                if not self.client:
                    await self._send_notification("❌ ClobClient が初期化されていません")
                    return False

                order = self.client.create_order(
                    token_id=market.get("token_id"),
                    price=price,
                    size=notional,
                    side=side.lower(),
                    slippage=self.max_slippage / 100
                )
                signed_order = self.client.sign_order(order)
                response = self.client.post_order(signed_order)

                logger.info(f"✅ Live Order Success: {response}")
                await self._send_notification(
                    f"✅ **Live Execution Success**\n"
                    f"Wallet: `{wallet_address[:8]}...`\n"
                    f"Market: {market_title}\n"
                    f"Side: {side.upper()} | Notional: **{notional:.2f} USDC**"
                )
                return True

        except Exception as e:
            error_msg = f"❌ Copy Execution Error: {str(e)}"
            logger.error(error_msg)
            await self._send_notification(error_msg)
            return False

    async def _send_notification(self, message: str):
        if self.bot and TELEGRAM_CHAT_ID:
            try:
                jst_time = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')
                full_msg = f"{message}\n\n🕒 {jst_time}"
                await self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=full_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Telegram通知失敗: {e}")

# シングルトン
copy_executor = CopyExecutor()