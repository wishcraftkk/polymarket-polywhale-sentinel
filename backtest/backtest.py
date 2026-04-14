import asyncio
import pandas as pd
from datetime import datetime, timedelta
from modules.evaluation import calculate_composite_score
from config import TEST_WALLETS

async def run_backtest(days: int = 180):
    """過去180日（6ヶ月）分のバックテストを実行"""
    print(f"📊 バックテスト開始（過去{days}日間）...")
    start_date = datetime.now() - timedelta(days=days)
    
    results = []
    for wallet in TEST_WALLETS:
        print(f"🔍 バックテスト中: {wallet[:8]}...")
        result = await calculate_composite_score(wallet)
        
        results.append({
            "wallet": wallet[:8] + "...",
            "composite_score": result["details"].get("composite_score", 0),
            "total_pnl": result["details"].get("total_pnl", 0),
            "sample_size": result["details"].get("sample_size", 0),
            "status": result["status"]
        })
    
    df = pd.DataFrame(results)
    print("\n" + "="*60)
    print("📈 バックテスト結果（過去6ヶ月）")
    print(df.to_string(index=False))
    print("="*60)
    
    # 高スコアウォレットのみ抽出
    top = df[df["composite_score"] >= 85].sort_values("composite_score", ascending=False)
    print(f"\n🏆 A級候補（スコア85以上）: {len(top)}件")
    print(top.to_string(index=False))
    
    return df

# 手動実行用
if __name__ == "__main__":
    asyncio.run(run_backtest())