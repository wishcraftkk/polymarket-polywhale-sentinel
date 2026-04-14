import aiosqlite
from datetime import datetime
from config import DB_PATH

async def init_db():
    """初回起動時に必要なテーブルをすべて作成"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS last_check (
                wallet TEXT PRIMARY KEY,
                last_timestamp REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS evaluation_history (
                wallet TEXT,
                composite_score REAL,
                total_pnl REAL,
                sample_size INTEGER,
                max_drawdown REAL,
                evaluated_at TEXT,
                PRIMARY KEY (wallet, evaluated_at)
            )
        """)
        await db.commit()
    print("✅ DB初期化完了 (data/polywhale.db)")

async def parse_timestamp(ts):
    """Polymarket APIのtimestampを必ずfloat(Unix秒)に変換（超頑丈版）"""
    if isinstance(ts, (int, float)):
        # ミリ秒の場合を自動変換
        return float(ts) / 1000 if ts > 1e12 else float(ts)
    
    if isinstance(ts, str):
        try:
            # ISO形式（"2026-04-14T12:34:56Z" など）
            if 'T' in ts or 'Z' in ts:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.timestamp()
            
            # 純粋な数値文字列の場合
            return float(ts)
        except:
            pass  # 変換失敗しても次へ
    
    # それ以外は何でも0.0に強制
    return 0.0

async def get_last_trade_timestamp(wallet: str) -> float:
    """最後にチェックしたtimestampを取得（必ずfloatを返す安全版）"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_timestamp FROM last_check WHERE wallet=?", (wallet,)) as cursor:
            row = await cursor.fetchone()
            # 必ずfloatに強制（strが混入してもOK）
            return float(row[0]) if row and row[0] is not None else 0.0

async def save_last_trade_timestamp(wallet: str, timestamp: float):
    """最後にチェックしたtimestampを保存"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO last_check (wallet, last_timestamp) VALUES (?, ?)",
            (wallet, float(timestamp))
        )
        await db.commit()