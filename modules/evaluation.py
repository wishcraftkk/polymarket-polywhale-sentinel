import pandas as pd
import asyncio
import numpy as np
from .ingestion import get_user_trades, get_user_closed_positions
from config import MIN_SAMPLE_SIZE, MAX_DRAWDOWN, COMPOSITE_WEIGHTS, GAMMA_API
import httpx

CATEGORY_CACHE = {}

async def get_market_category(condition_id: str = None, market_title: str = None):
    # （前回と同じ内容、省略）
    # ... 省略（完全版が必要なら言ってください） ...

async def calculate_composite_score(wallet: str, target_category: str = "OVERALL"):
    """最終版：勝率100%はほぼペナルティなし + データ件数明示準備"""
    # （前回と同じ基本処理）...
    # 勝率ペナルティ部分だけ変更
    win_rate_penalty = 0
    if sample_size < 50:
        win_rate_penalty = (50 - sample_size) * 0.4   # 緩和
    adjusted_win_rate = max(0, win_rate - win_rate_penalty)

    # スコア計算（変更なし）
    a_score = 95 if sample_size >= MIN_SAMPLE_SIZE and total_pnl > 0 else 40
    b_score = 92 if adjusted_win_rate >= 70 else 78 if adjusted_win_rate >= 55 else 50
    recent_score = 95 if (total_pnl > 500_000 and adjusted_win_rate > 75) else 85 if (total_pnl > 100_000 and adjusted_win_rate > 65) else 60
    c_score = 85 if sample_size >= 100 else 70

    composite_score = (
        COMPOSITE_WEIGHTS["A"] * a_score +
        COMPOSITE_WEIGHTS["B"] * b_score +
        COMPOSITE_WEIGHTS["RECENT"] * recent_score +
        COMPOSITE_WEIGHTS["C"] * c_score
    )

    status = "🟢 A級候補" if composite_score >= 85 else "🟡 B級" if composite_score >= 70 else "⚪ C級"

    details = {
        "sample_size": int(sample_size),
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "adjusted_win_rate": round(adjusted_win_rate, 1),
        "max_drawdown": round(max_drawdown * 100, 1),
        "composite_score": round(composite_score, 1),
        "status": status,
        "category_stats": category_stats,
    }
    return {"score": composite_score, "status": status, "details": details}