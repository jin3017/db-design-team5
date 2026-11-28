"""DB 연결 확인. 실행: python scripts/check_db.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 프로젝트 루트

from app.core.db import get_connection  # noqa: E402


def main() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
            print("DB 연결 성공:", cur.fetchone())


if __name__ == "__main__":
    main()
