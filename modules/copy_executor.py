import os
import logging
import asyncio
from datetime import datetime
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
import telegram

from config import COPY_EXECUTION, CLOB_CONFIG, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from modules.risk_manager import RiskManager

logger = logging.getLogger(__name__)

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
        
        # ClobClient 初期化（Hardware Wallet + API Credentials 安全方式）
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Phase 4 対応：Private Key を一切渡さない安全初期化"""
        try:
            creds = {
                "apiKey": os.getenv("POLYMARKET_API_KEY"),
                "secret": os.getenv("POLYMARKET_SECRET"),
                "passphrase": os.getenv("POLYMARKET_PASSPHRASE"),
            }
            
            if not all(creds.values()):
                logger.warning("⚠️ Polymarket API Credentials が .env に設定されていません")
                return

            self.client = ClobClient(
                host=CLOB_CONFIG["HOST"],
                chain_id=CLOB_CONFIG["CHAIN_ID"],
                key=None,                    # Private Key は絶対に渡さない（Ledger + MetaMask 使用）
                creds=creds,
                signature_type=CLOB_CONFIG["SIGNATURE_TYPE"]
            )
            logger.info(f"✅ ClobClient 初期化完了 (Paper Mode: {self.paper_mode})")
        except Exception as e:
            logger.error(f"ClobClient 初期化失敗: {e}")

    async def execute_copy(self, wallet_address: str, market: dict, side: str, size: float, price: float):
        """新取引を検知 → 評価＆リスクチェック → 注文実行（Paper or Live）"""
        if not self.enabled:
            logger.info("CopyExecution is disabled in config")
            return False

        try:
            # 1. RiskManager 全チェック
            risk_check = self.risk_manager.check_trade(
                notional=size * price,
                category=market.get("category", "OTHER")
            )
            if not risk_check["approved"]:
                await self._send_notification(f"❌ Risk Check Failed: {risk_check['reason']}")
                return False

            # 2. 注文サイズ計算（COPY_RATIO または固定上限）
            notional = min(size * self.copy_ratio * price, self.max_notional)
            
            if self.paper_mode:
                # Paper Mode（シミュレーション）
                logger.info(f"[PAPER MODE] Simulated copy: {wallet_address} → {side} {notional:.2f} USDC on {market.get('question')}")
                await self._send_notification(
                    f"📋 **Paper Mode Execution**\n"
                    f"Wallet: `{wallet_address[-8:]}`\n"
                    f"Market: {market.get('question')}\n"
                    f"Side: {side} | Size: {notional:.2f} USDC\n"
                    f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                return True
            else:
                # Live Mode（本番USDC注文）
                if not self.client:
                    await self._send_notification("❌ ClobClient が初期化されていません (API Credentials確認)")
                    return False

                # 注文作成（py-clob-client 使用）
                order = self.client.create_order(
                    token_id=market["token_id"],   # 実際のマーケットに応じて調整
                    price=price,
                    size=notional,
                    side=side.lower(),             # "buy" or "sell"
                    slippage=self.max_slippage / 100
                )

                # 署名＆送信（Hardware Wallet で Blind Signing がONならLedgerで承認）
                signed_order = self.client.sign_order(order)
                response = self.client.post_order(signed_order)

                logger.info(f"Live Order Sent: {response}")
                await self._send_notification(
                    f"✅ **Live Execution Success**\n"
                    f"Wallet: `{wallet_address[-8:]}`\n"
                    f"Market: {market.get('question')}\n"
                    f"Side: {side} | Notional: {notional:.2f} USDC\n"
                    f"Order ID: {response.get('order_id', 'N/A')}\n"
                    f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
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
                await self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Telegram通知失敗: {e}")

# シングルトンインスタンス（main.py などで import して使用）
copy_executor = CopyExecutor()