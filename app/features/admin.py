"""직원·권한 관리 (UC-02, FR-016·018), 시스템 설정 (FR-019). 점주 전용."""
from datetime import datetime

from flask import Blueprint, g, render_template, request, url_for
from werkzeug.security import generate_password_hash

from ..core.auth import owner_required
from ..core.db import BizError, query, query_one
from ..core.web import run_action, to_int

bp = Blueprint("admin", __name__)
MENU = [(90, "직원관리", "admin.employees", True, "users", ("admin.employee",)),
        (99, "설정", "admin.settings", True, "gear", ("admin.settings",))]

SETTINGS = {  # 설정키: (표시명, 최소, 최대)
    "EXPIRY_ALERT_DAYS": ("소비기한 임박 기준일 (일)", 0, 60),
    "AUTO_LOGOUT_MINUTES": ("자동 로그아웃 시간 (분)", 1, 480),
}
MIN_PASSWORD = 4


# ------------------------------------------------------------ 업무 처리
def save_employee(cur, me, eid, current, form):
    name, phone = form.get("emp_name", "").strip(), form.get("phone", "").strip() or None
    role, status, pw = form.get("role"), form.get("status", "ACTIVE"), form.get("password", "")
    if not name or role not in ("OWNER", "STAFF") or status not in ("ACTIVE", "INACTIVE"):
        raise BizError("이름과 권한은 필수입니다.")
    if pw and len(pw) < MIN_PASSWORD:
        raise BizError(f"비밀번호는 {MIN_PASSWORD}자 이상이어야 합니다.")
    if eid is None:
        login_id = form.get("login_id", "").strip()
        if not login_id or not pw:
            raise BizError("아이디와 초기 비밀번호를 입력하세요.")
        cur.execute("SELECT 1 FROM EMPLOYEE WHERE login_id = %s", (login_id,))
        if cur.fetchone():
            raise BizError("이미 사용 중인 아이디입니다.")  # UC-02 A1
        cur.execute("INSERT INTO EMPLOYEE (login_id, password_hash, emp_name, phone, role) "
                    "VALUES (%s, %s, %s, %s, %s)", (login_id, generate_password_hash(pw), name, phone, role))
        return
    if eid == me and (role != "OWNER" or status != "ACTIVE"):
        raise BizError("본인 계정은 직원 권한으로 바꾸거나 비활성화할 수 없습니다.")  # UC-02 A2
    if current["role"] == "OWNER" and (role != "OWNER" or status != "ACTIVE"):
        cur.execute("SELECT COUNT(*) AS n FROM EMPLOYEE WHERE role = 'OWNER' AND status = 'ACTIVE' "
                    "AND emp_id <> %s FOR UPDATE", (eid,))
        if cur.fetchone()["n"] == 0:
            raise BizError("활성 점주 계정이 최소 1명은 있어야 합니다.")  # R13
    cur.execute("UPDATE EMPLOYEE SET emp_name = %s, phone = %s, role = %s, status = %s, updated_by = %s, "
                "updated_at = NOW() WHERE emp_id = %s", (name, phone, role, status, me, eid))
    if pw:  # 비밀번호 재설정 시 잠금도 해제
        cur.execute("UPDATE EMPLOYEE SET password_hash = %s, login_fail_count = 0, unlock_at = NULL "
                    "WHERE emp_id = %s", (generate_password_hash(pw), eid))


# ------------------------------------------------------------ 화면
@bp.route("/employees")
@owner_required
def employees():
    rows = query("SELECT e.*, u.emp_name AS updated_name FROM EMPLOYEE e "
                 "LEFT JOIN EMPLOYEE u ON u.emp_id = e.updated_by ORDER BY e.status, e.role, e.emp_name")
    return render_template("admin/employees.html", rows=rows, now=datetime.now())


@bp.route("/employees/new", methods=["GET", "POST"])
@bp.route("/employees/<int:eid>", methods=["GET", "POST"])
@owner_required
def employee_form(eid=None):
    emp = query_one("SELECT * FROM EMPLOYEE WHERE emp_id = %s", (eid,)) if eid else None
    if eid and emp is None:
        return render_template("message.html", message="존재하지 않는 직원입니다."), 404
    if request.method == "GET":
        return render_template("admin/employee_form.html", e=emp)
    form, me = request.form, g.user["emp_id"]
    return run_action(lambda cur: save_employee(cur, me, eid, emp, form), "직원 정보를 저장했습니다.",
                      url_for("admin.employees"), request.url)


@bp.route("/settings", methods=["GET", "POST"])
@owner_required
def settings():
    back = url_for("admin.settings")
    if request.method == "POST":
        def action(cur):
            for key, (name, lo, hi) in SETTINGS.items():
                v = to_int(request.form.get(key))
                if v is None or not lo <= v <= hi:
                    raise BizError(f"{name}은(는) {lo}~{hi} 사이의 숫자여야 합니다.")
                cur.execute("UPDATE SYSTEM_SETTING SET setting_value = %s, updated_by = %s, updated_at = NOW() "
                            "WHERE setting_key = %s", (str(v), g.user["emp_id"], key))
        return run_action(action, "설정을 저장했습니다.", back, back)
    rows = query("SELECT s.*, e.emp_name FROM SYSTEM_SETTING s LEFT JOIN EMPLOYEE e ON e.emp_id = s.updated_by "
                 "ORDER BY s.setting_key")
    return render_template("admin/settings.html", rows=rows, meta=SETTINGS)
