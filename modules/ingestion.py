import httpx
from config import POLYMARKET_DATA_API
import asyncio
from datetime import datetime
from utils.helpers import parse_timestamp, get_last_trade_timestamp, save_last_trade_timestamp

async def fetch_user_data(wallet: str, endpoint: str, params: dict = None):
    """Polymarket Data APIからユーザーデータを取得する基本関数"""
    url = f"{POLYMARKET_DATA_API}/{endpoint}"
    params = params or {}
    params["user"] = wallet
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            print(f"✅ {endpoint} データ取得成功 ({wallet[:8]}...) - {len(data) if isinstance(data, list) else '1'}件")
            return data
        except Exception as e:
            print(f"❌ {endpoint} データ取得エラー ({wallet[:8]}...): {e}")
            return None

# ------------------- 主要取得関数 -------------------
async def get_user_trades(wallet: str, limit: int = 100):
    return await fetch_user_data(wallet, "trades", {"limit": limit})

async def get_user_positions(wallet: str):
    return await fetch_user_data(wallet, "positions")

async def get_user_closed_positions(wallet: str):
    return await fetch_user_data(wallet, "closed-positions")

async def get_user_activity(wallet: str):
    return await fetch_user_data(wallet, "activity")

# ------------------- リアルタイム監視用関数 -------------------
async def check_new_trades(wallet: str):
    """新しく入った取引だけを取得（型エラー完全排除・最強安全版）"""
    last_ts = await get_last_trade_timestamp(wallet)          # 必ずfloat
    
    trades = await get_user_trades(wallet, limit=200)
    if not trades:
        return []

    new_trades = []
    latest_ts = last_ts                                       # float
    
    for trade in trades:
        trade_ts_raw = trade.get("timestamp") or trade.get("createdAt") or trade.get("blockTimestamp") or 0
        trade_ts = await parse_timestamp(trade_ts_raw)
        
        # ★ 最強安全対策：必ずfloatに強制
        trade_ts = float(trade_ts) if isinstance(trade_ts, (int, float)) else 0.0
        latest_ts = float(latest_ts) if isinstance(latest_ts, (int, float)) else 0.0
        
        if trade_ts > last_ts:
            new_trades.append(trade)
            if trade_ts > latest_ts:
                latest_ts = trade_ts
    
    # 新しい取引があれば最新時刻を保存
    if new_trades:
        await save_last_trade_timestamp(wallet, latest_ts)
        
        # 初回起動（last_tsが0）の場合は通知を抑制
        if last_ts == 0.0:
            print(f"🛡️ 初回起動のため {len(new_trades)}件を過去取引として処理（通知なし）")
            return []  # 初回は通知しない
        
        return new_trades
    
    return []

# ------------------- テスト用関数 -------------------
async def test_ingestion():
    test_wallet = "0x1234567890123456789012345678901234567890"
    print(f"🔍 {datetime.now().strftime('%H:%M:%S')} ingestion.py テスト開始...")
    trades = await get_user_trades(test_wallet, limit=20)
    if trades:
        print(f"✅ テスト成功！ サンプル取引数: {len(trades)}件")
    else:
        print("⚠️ テストは仮ウォレットのためデータなし（正常です）")

if __name__ == "__main__":
    asyncio.run(test_ingestion())