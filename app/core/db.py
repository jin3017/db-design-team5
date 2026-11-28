"""MySQL 연결 헬퍼. 접속 정보는 프로젝트 루트의 .env 에서 읽는다."""
import os
from contextlib import contextmanager
from pathlib import Path

import pymysql
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # 프로젝트 루트


class BizError(Exception):
    """업무 규칙 위반. 메시지를 그대로 사용자에게 보여 준다."""


def get_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "team5_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextmanager
def transaction():
    """with transaction() as cur: ... 블록 전체를 하나의 트랜잭션으로 처리.
    예외가 나면 전부 롤백한다 (재고 변경 + 이력 저장 원자성, R10)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, args=None):
    with transaction() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def query_one(sql, args=None):
    rows = query(sql, args)
    return rows[0] if rows else None


def get_setting(key, default):
    row = query_one("SELECT setting_value FROM SYSTEM_SETTING WHERE setting_key = %s", (key,))
    return row["setting_value"] if row else default
