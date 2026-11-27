"""DB 연결 확인용 진입점. 실행: python app/main.py"""
from db import get_connection


def main() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
            print("DB 연결 성공:", cur.fetchone())


if __name__ == "__main__":
    main()
