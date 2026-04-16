import pandas as pd
import asyncio
import numpy as np
from .ingestion import get_user_trades, get_user_closed_positions
from config import MIN_SAMPLE_SIZE, MAX_DRAWDOWN, COMPOSITE_WEIGHTS, GAMMA_API, DISCOVERY_CATEGORIES
import httpx
from datetime import datetime

# Gamma APIキャッシュ
CATEGORY_CACHE = {}

async def get_market_category(condition_id: str = None, market_title: str = None):
    """Gamma API + タイトルキーワードフォールバックで高精度カテゴリ判定"""
    cache_key = condition_id or market_title
    if cache_key in CATEGORY_CACHE:
        return CATEGORY_CACHE[cache_key]

    if market_title:
        title_upper = market_title.upper()
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
                url = f"{GAMMA_API}/markets"
                resp = await client.get(url, params={"condition_id": condition_id})
                resp.raise_for_status()
                data = resp.json()
                tags = []
                if isinstance(data, list) and data:
                    tags = data[0].get("tags", []) or []
                elif isinstance(data, dict):
                    tags = data.get("tags", []) or []
                for tag in tags:
                    label = tag.get("label", "").upper()
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

async def calculate_composite_score(wallet: str, target_category: str = "OVERALL"):
    """Phase 4 強化版：勝率過剰評価を防止（サンプルサイズ補正＋ペナルティ追加）"""
    print(f"🔍 {wallet[:8]}... の評価を開始（カテゴリ別最終強化版）...")

    trades = await get_user_trades(wallet, limit=300)
    closed_positions = await get_user_closed_positions(wallet)

    if not trades and not closed_positions:
        return {"score": 0, "status": "データなし", "details": {}}

    df_closed = pd.DataFrame(closed_positions) if closed_positions else pd.DataFrame()

    # --- 基本指標 ---
    sample_size = len(df_closed) + len(trades)
    total_pnl = 0.0
    if not df_closed.empty:
        for col in ["realizedPnl", "cashPnl", "pnl"]:
            if col in df_closed.columns:
                total_pnl = float(df_closed[col].sum())
                break

    # 勝率計算（closed_positionsのみ）
    win_rate = 0.0
    if not df_closed.empty and "realizedPnl" in df_closed.columns:
        wins = (df_closed["realizedPnl"] > 0).sum()
        win_rate = (wins / len(df_closed)) * 100

    # Max Drawdown
    max_drawdown = 0.0
    if not df_closed.empty and "realizedPnl" in df_closed.columns:
        cum_pnl = df_closed["realizedPnl"].cumsum()
        peak = cum_pnl.cummax()
        drawdown = (cum_pnl - peak) / peak.abs().replace(0, 1)
        max_drawdown = float(drawdown.min())

    # カテゴリ別分析
    category_stats = {"OVERALL": {"pnl": total_pnl, "win_rate": win_rate, "count": sample_size}}
    if not df_closed.empty:
        for _, row in df_closed.iterrows():
            title = row.get("title") or row.get("market") or row.get("question") or ""
            cat = await get_market_category(condition_id=row.get("conditionId"), market_title=title)
            if cat not in category_stats:
                category_stats[cat] = {"pnl": 0, "win_rate": 0, "count": 0}
            category_stats[cat]["pnl"] += row.get("realizedPnl", 0)
            category_stats[cat]["count"] += 1

    if target_category != "OVERALL" and target_category in category_stats:
        cat_data = category_stats[target_category]
        sample_size = cat_data["count"]
        total_pnl = cat_data["pnl"]
        win_rate = cat_data.get("win_rate", 0)

    # 赤信号排除
    red_flags = []
    if sample_size < MIN_SAMPLE_SIZE:
        red_flags.append("Sample Size不足")
    if max_drawdown < -MAX_DRAWDOWN:
        red_flags.append("Max Drawdown超過")
    if red_flags:
        status = f"❌ 排除: {', '.join(red_flags)}"
        return {"score": 0, "status": status, "details": {"red_flags": red_flags}}

     # 【Phase 4 強化版】勝率ペナルティ（より厳しく）
    win_rate_penalty = 0
    if sample_size < 100:
        win_rate_penalty = (100 - sample_size) * 1.2   # ペナルティを大幅強化
    elif sample_size < 200:
        win_rate_penalty = (200 - sample_size) * 0.6
    adjusted_win_rate = max(0, win_rate - win_rate_penalty)

    # recent_scoreも調整
    recent_score = 95 if (total_pnl > 500_000 and adjusted_win_rate > 75) else \
                   85 if (total_pnl > 100_000 and adjusted_win_rate > 65) else 60 

    # A/B/C級スコア（より現実的に）
    a_score = 95 if sample_size >= MIN_SAMPLE_SIZE and total_pnl > 0 else 40
    b_score = 92 if adjusted_win_rate >= 70 else 78 if adjusted_win_rate >= 55 else 50
    # recent_score：直近PnLだけでなく「勝率」も考慮
    recent_score = 95 if (total_pnl > 500_000 and adjusted_win_rate > 70) else \
                   85 if (total_pnl > 100_000 and adjusted_win_rate > 60) else 65

    c_score = 85 if sample_size >= 100 else 70

    composite_score = (
        COMPOSITE_WEIGHTS["A"] * a_score +
        COMPOSITE_WEIGHTS["B"] * b_score +
        COMPOSITE_WEIGHTS["RECENT"] * recent_score +
        COMPOSITE_WEIGHTS["C"] * c_score
    )

    status = "🟢 A級候補" if composite_score >= 85 else "🟡 B級要確認" if composite_score >= 70 else "⚪ C級"

    details = {
        "sample_size": int(sample_size),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),           # 表示は実測値
        "adjusted_win_rate": round(adjusted_win_rate, 1),  # 内部調整値
        "max_drawdown": round(max_drawdown * 100, 1),
        "composite_score": round(composite_score, 1),
        "status": status,
        "category_stats": category_stats,
        "red_flags": red_flags
    }

    print(f"✅ 評価完了 → Score: {composite_score:.1f} / {status} (PnL ${total_pnl:,.0f} | DD {max_drawdown*100:.1f}% | 勝率 {win_rate:.1f}%)")
    return {"score": composite_score, "status": status, "details": details}