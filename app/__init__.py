"""Flask 앱 생성. 실행은 프로젝트 루트의 run.py.

app/core/      공통 (DB, 로그인·권한, 재고 이력 등)
app/features/  기능 1개 = 파일 1개. 파일마다 `bp`(Blueprint)와 MENU 를 두면
               자동으로 등록·사이드 메뉴에 추가되므로, 기능을 추가해도 이 파일은 고치지 않는다.

MENU = [(순서, 표시명, endpoint, 점주전용여부, 아이콘, 선택표시 endpoint 접두어들)]
"""
import importlib
import os
import pkgutil
from datetime import date, datetime

from flask import Flask, request

from . import features
from .core import auth
from .core.labels import LABELS

STORE_NAME = os.getenv("STORE_NAME", "편의점")


def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")

    app.register_blueprint(auth.bp)
    menus = []
    for info in pkgutil.iter_modules(features.__path__):
        mod = importlib.import_module(f"{features.__name__}.{info.name}")
        if hasattr(mod, "bp"):
            app.register_blueprint(mod.bp)
            menus += getattr(mod, "MENU", [])
    menus.sort()

    @app.context_processor
    def inject_common():
        def is_active(prefixes):
            return any((request.endpoint or "").startswith(p) for p in prefixes)
        return {"menus": menus, "endpoints": set(app.view_functions), "is_active": is_active,
                "store_name": STORE_NAME, "today": date.today()}

    @app.template_filter("won")
    def won(v):
        return f"{int(v or 0):,}"

    @app.template_filter("dt")
    def dt(v):
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M")
        if isinstance(v, date):
            return v.strftime("%Y-%m-%d")
        return v or "-"

    @app.template_filter("label")
    def label(code):
        return LABELS.get(code, code)

    @app.template_filter("lot_no")
    def lot_no(lot):
        """화면 표시용 LOT(입고 묶음) 번호: 입고일자-LOT번호."""
        return f"{lot['received_date']:%Y%m%d}-{lot['lot_id']:02d}"

    return app
