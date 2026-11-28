"""로그인/로그아웃, 권한 데코레이터 (UC-01, FR-016, SEC-001)."""
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .db import get_setting, query_one, transaction

bp = Blueprint("auth", __name__)

LOCK_LIMIT = 5        # 연속 실패 허용 횟수 (UC-01 A4 제안값)
LOCK_MINUTES = 10     # 잠금 시간


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def owner_required(view):
    """점주 전용. 메뉴 숨김과 별개로 서버에서 차단한다 (FR-016)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        if g.user["role"] != "OWNER":
            flash("점주만 사용할 수 있는 기능입니다.", "error")
            return redirect(url_for("home.index"))
        return view(*args, **kwargs)
    return wrapped


@bp.before_app_request
def load_user():
    g.user = None
    emp_id = session.get("emp_id")
    if emp_id is None:
        return
    timeout = int(get_setting("AUTO_LOGOUT_MINUTES", 30))
    last = session.get("last_seen")
    now = datetime.now().timestamp()
    if last and now - last > timeout * 60:
        session.clear()
        flash(f"{timeout}분 동안 사용하지 않아 자동 로그아웃되었습니다.", "info")
        return
    user = query_one("SELECT emp_id, emp_name, role, status FROM EMPLOYEE WHERE emp_id = %s", (emp_id,))
    if user is None or user["status"] != "ACTIVE":
        session.clear()
        return
    session["last_seen"] = now
    g.user = user


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    login_id = request.form.get("login_id", "").strip()
    password = request.form.get("password", "")
    if not login_id or not password:
        flash("아이디와 비밀번호를 모두 입력하세요.", "error")
        return render_template("login.html", login_id=login_id)

    with transaction() as cur:
        cur.execute("SELECT * FROM EMPLOYEE WHERE login_id = %s FOR UPDATE", (login_id,))
        emp = cur.fetchone()
        now = datetime.now()
        if emp and emp["unlock_at"] and emp["unlock_at"] > now:
            flash(f"로그인 실패가 반복되어 {emp['unlock_at']:%H:%M}까지 잠겼습니다.", "error")
            return render_template("login.html", login_id=login_id)
        if emp is None or not check_password_hash(emp["password_hash"], password):
            if emp:
                fails = emp["login_fail_count"] + 1
                unlock = None
                if fails >= LOCK_LIMIT:
                    fails, unlock = 0, now + timedelta(minutes=LOCK_MINUTES)
                cur.execute("UPDATE EMPLOYEE SET login_fail_count = %s, unlock_at = %s WHERE emp_id = %s",
                            (fails, unlock, emp["emp_id"]))
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
            return render_template("login.html", login_id=login_id)
        if emp["status"] != "ACTIVE":
            flash("비활성화된 계정입니다. 점주에게 문의하세요.", "error")
            return render_template("login.html", login_id=login_id)
        cur.execute("UPDATE EMPLOYEE SET login_fail_count = 0, unlock_at = NULL, last_login_at = NOW() "
                    "WHERE emp_id = %s", (emp["emp_id"],))

    session.clear()
    session["emp_id"] = emp["emp_id"]
    session["last_seen"] = datetime.now().timestamp()
    return redirect(url_for("home.index"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
