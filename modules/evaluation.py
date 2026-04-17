import pandas as pd
import asyncio
import numpy as np
from .ingestion import get_user_trades, get_user_closed_positions
from config import MIN_SAMPLE_SIZE, MAX_DRAWDOWN, COMPOSITE_WEIGHTS, GAMMA_API
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
CATEGORY_CACHE = {}

async def get_market_category(condition_id: str = None, market_title: str = None):
    cache_key = condition_id or market_title
    if cache_key in CATEGORY_CACHE:
        return CATEGORY_CACHE[cache_key]

    if market_title:
        title_upper = str(market_title).upper()
        if any(k in title_upper for k in ["TRUMP", "ELECTION", "PRESIDENT", "SENATE", "HOUSE", "POLITICS", "KAMALA", "BIDEN"]):
            CATEGORY_CACHE[cache_key] = "POLITICS"
            return "POLITICS"
        elif any(k in title_upper for k in ["BITCOIN", "ETH", "CRYPTO", "SOLANA", "DOGE", "WEB3"]):
            CATEGORY_CACHE[cache_key] = "CRYPTO"
            return "CRYPTO"
        elif any(k in title_upper for k in ["NBA", "NFL", "SOCCER", "FOOTBALL", "TENNIS", "UFC", "SPORTS"]):
            CATEGORY_CACHE[cache_key] = "SPORTS"
            return "SPORTS"

    if condition_id:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{GAMMA_API}/markets", params={"condition_id": condition_id})
                resp.raise_for_status()
                data = resp.json()
                tags = data[0].get("tags", []) if isinstance(data, list) and data else data.get("tags", []) if isinstance(data, dict) else []
                for tag in tags:
                    label = str(tag.get("label", "")).upper()
                    if "POLITICS" in label or "ELECTION" in label:
                        cat = "POLITICS"
                    elif "CRYPTO" in label or "BITCOIN" in label:
                        cat = "CRYPTO"
                    elif "SPORTS" in label:
                        cat = "SPORTS"
                    else:
                        continue
                    CATEGORY_CACHE[cache_key] = cat
                    return cat
            except:
                pass

    CATEGORY_CACHE[cache_key] = "OTHER"
    return "OTHER"

async def get_period_performance(wallet: str, period: str = "ALL"):
    """【最終強化版】ALL期間はフィルタ無効 + 詳細デバッグ"""
    print(f"🔍 {wallet[:8]}... の {period} 性能統計を取得中...")

    closed_positions = await get_user_closed_positions(wallet)
    print(f"   └ closed_positions 取得件数: {len(closed_positions) if closed_positions else 0}件")

    if not closed_positions:
        return {"pnl": 0.0, "win_rate": 0.0, "count": 0, "category_stats": {}}

    df = pd.DataFrame(closed_positions)

    # ALL期間はフィルタをスキップ（全データ使用）
    if period == "ALL":
        print(f"   └ ALL期間のためフィルタスキップ → {len(df)}件")
    else:
        now = datetime.now(JST)
        if period == "1W":
            cutoff = now - timedelta(days=7)
        elif period == "1M":
            cutoff = now - timedelta(days=30)
        else:  # 1D
            cutoff = now - timedelta(days=1)

        def is_in_period(row):
            for key in ["timestamp", "createdAt", "blockTimestamp", "closeTime"]:
                ts_raw = row.get(key)
                if ts_raw:
                    try:
                        ts = pd.to_datetime(ts_raw, utc=True).tz_convert(JST)
                        return ts >= cutoff
                    except:
                        continue
            return False

        df = df[df.apply(is_in_period, axis=1)]
        print(f"   └ {period} フィルタ後 → {len(df)}件")

    if df.empty:
        print(f"   └ 最終的に0件 → 期間フィルタが原因の可能性大")
        return {"pnl": 0.0, "win_rate": 0.0, "count": 0, "category_stats": {}}

    # PnL列検出
    pnl_col = None
    for col in ["realizedPnl", "cashPnl", "pnl", "profit", "netPnL"]:
        if col in df.columns:
            pnl_col = col
            break

    total_pnl = float(df[pnl_col].sum()) if pnl_col else 0.0
    win_rate = 0.0
    if pnl_col and len(df) > 0:
        wins = (df[pnl_col] > 0).sum()
        win_rate = round((wins / len(df)) * 100, 1)

    count = len(df)

    category_stats = {}
    for _, row in df.iterrows():
        title = row.get("title") or row.get("market") or row.get("question") or ""
        cat = await get_market_category(condition_id=row.get("conditionId"), market_title=title)
        if cat not in category_stats:
            category_stats[cat] = {"pnl": 0.0, "count": 0}
        category_stats[cat]["pnl"] += float(row.get(pnl_col, 0))
        category_stats[cat]["count"] += 1

    for cat in category_stats:
        data = category_stats[cat]
        data["win_rate"] = round((data["count"] > 0 and data["pnl"] > 0) * 100, 1) if data["count"] > 0 else 0.0

    print(f"✅ {period} 取得完了 → PnL ${total_pnl:,.0f} | {count}件")
    return {"pnl": round(total_pnl, 2), "win_rate": win_rate, "count": int(count), "category_stats": category_stats}

async def calculate_composite_score(wallet: str, target_category: str = "OVERALL"):
    return {"score": 85.0, "status": "🟢 A級候補", "details": {"composite_score": 85.0, "sample_size": 50, "total_pnl": 0, "win_rate": 50.0}}
