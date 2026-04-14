import httpx
import asyncio
from datetime import datetime
from config import POLYMARKET_DATA_API

async def fetch_leaderboard(category: str = "OVERALL", time_period: str = "DAY", limit: int = 20):
    """Polymarket公式Leaderboardからトップウォレットを取得（公式API /v1/leaderboard）"""
    url = f"{POLYMARKET_DATA_API}/v1/leaderboard"
    params = {
        "category": category,
        "timePeriod": time_period,
        "orderBy": "PNL",      # PnL順（利益順）
        "limit": limit
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            wallets = []
            for entry in data:
                if "proxyWallet" in entry or "wallet" in entry:
                    wallet = entry.get("proxyWallet") or entry.get("wallet")
                    wallets.append(wallet)
            
            print(f"✅ Discovery成功: {category} {time_period} Top {len(wallets)}件")
            return wallets[:limit]
        except Exception as e:
            print(f"❌ Leaderboard取得エラー: {e}")
            return []

# ------------------- メイン発見関数 -------------------
async def discover_top_wallets():
    """複数カテゴリから優秀ウォレットを自動発見"""
    print(f"🔎 {datetime.now().strftime('%H:%M')} Discovery Module 開始...")
    
    all_wallets = []
    
    # 全体 + カテゴリ別トップを取得
    categories = ["OVERALL", "POLITICS", "CRYPTO", "SPORTS"]
    for cat in categories:
        wallets = await fetch_leaderboard(category=cat, time_period="DAY", limit=8)
        all_wallets.extend(wallets)
    
    # 重複削除
    unique_wallets = list(dict.fromkeys(all_wallets))
    
    print(f"🚀 新規発見ウォレット: {len(unique_wallets)}件（重複除去後）")
    return unique_wallets

# テスト用
if __name__ == "__main__":
    asyncio.run(discover_top_wallets())