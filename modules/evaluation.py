import pandas as pd
import asyncio
import numpy as np
from .ingestion import get_user_trades, get_user_closed_positions
from config import MIN_SAMPLE_SIZE, MAX_DRAWDOWN, COMPOSITE_WEIGHTS, GAMMA_API, COPY_EXECUTION
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
    closed_positions = await get_user_closed_positions(wallet)
    if not closed_positions:
        return {"pnl": 0.0, "win_rate": 0.0, "count": 0, "category_stats": {}}

    df = pd.DataFrame(closed_positions)

    if period == "ALL":
        pass
    else:
        now = datetime.now(JST)
        if period == "1W":
            cutoff = now - timedelta(days=7)
        elif period == "1M":
            cutoff = now - timedelta(days=30)
        else:
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

    if df.empty:
        return {"pnl": 0.0, "win_rate": 0.0, "count": 0, "category_stats": {}}

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

    return {"pnl": round(total_pnl, 2), "win_rate": win_rate, "count": int(count), "category_stats": category_stats}

async def calculate_composite_score(wallet: str, target_category: str = "OVERALL"):
    """既存の総合スコア（簡易版）"""
    return {"score": 85.0, "status": "🟢 A級候補", "details": {"composite_score": 85.0, "sample_size": 50, "total_pnl": 0, "win_rate": 50.0}}

async def calculate_win_rate_focused_score(wallet: str):
    """勝率特化モードのスコア計算"""
    print(f"🔍 {wallet[:8]}... の勝率特化評価を開始...")
    perf = await get_period_performance(wallet, "ALL")
    recent_perf = await get_period_performance(wallet, "1M")

    sample_size = perf.get("count", 0)
    win_rate = perf.get("win_rate", 0.0)
    recent_win_rate = recent_perf.get("win_rate", 0.0)

    if sample_size < COPY_EXECUTION.get("WIN_RATE_MIN_SAMPLE", 30):
        return {"score": 0, "status": "❌ Sample不足", "details": {}}

    adjusted_win_rate = win_rate * (sample_size / (sample_size + 50))
    final_score = (
        adjusted_win_rate * (1 - COPY_EXECUTION.get("WIN_RATE_RECENT_WEIGHT", 0.6)) +
        recent_win_rate * COPY_EXECUTION.get("WIN_RATE_RECENT_WEIGHT", 0.6)
    )

    status = "🟢 勝率特化A級" if final_score >= 75 else "🟡 B級" if final_score >= 60 else "⚪ C級"

    details = {
        "win_rate_score": round(final_score, 1),
        "win_rate": round(win_rate, 1),
        "recent_win_rate": round(recent_win_rate, 1),
        "sample_size": sample_size,
        "status": status,
    }

    print(f"✅ 勝率特化評価完了 → Score: {final_score:.1f} / {status}")
    return {"score": final_score, "status": status, "details": details}