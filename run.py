"""편의점 관리 시스템 실행.

  python run.py          → 이 PC에서만 접속 (http://127.0.0.1:5000)
  python run.py --lan    → 매장 내부 네트워크의 다른 PC·태블릿에서도 접속
"""
import sys

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    app.run(host=host, port=5000, debug="--lan" not in sys.argv)
