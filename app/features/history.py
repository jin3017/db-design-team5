"""재고 변동 이력 조회 (UC-14, FR-017). 조회만 가능, 수정·삭제 화면 없음 (R11). 점주 전용."""
from flask import Blueprint, render_template, request

from ..core.auth import owner_required
from ..core.db import query, query_one
from ..core.labels import MOVEMENT_TYPES
from ..core.web import to_date, to_int

bp = Blueprint("history", __name__)
MENU = []  # 재고 화면의 "변동 이력" 탭으로 진입

PAGE_SIZE = 50  # 페이지 단위 조회 (UC-14 A1)
SOURCES = (("receipt_detail_id", "입고상세"), ("sale_detail_id", "판매상세"), ("adjust_id", "재고조정"),
           ("disposal_id", "폐기"), ("return_id", "반품"))


@bp.route("/movements")
@owner_required
def movements():
    a = request.args
    where, args = ["1=1"], []
    d_from, d_to = to_date(a.get("from")), to_date(a.get("to"))
    if d_from:
        where.append("m.moved_at >= %s")
        args.append(d_from)
    if d_to:
        where.append("m.moved_at < %s + INTERVAL 1 DAY")
        args.append(d_to)
    q = a.get("q", "").strip()
    if q:
        where.append("(p.product_name LIKE %s OR p.barcode = %s)")
        args += [f"%{q}%", q]
    if a.get("type") in MOVEMENT_TYPES:
        where.append("m.movement_type = %s")
        args.append(a["type"])
    emp = to_int(a.get("emp"))
    if emp:
        where.append("m.moved_by = %s")
        args.append(emp)
    w = " AND ".join(where)
    page = max(to_int(a.get("page"), 1), 1)
    total = query_one("SELECT COUNT(*) AS n FROM STOCK_MOVEMENT m JOIN PRODUCT p ON p.product_id = m.product_id "
                      f"WHERE {w}", args)["n"]
    rows = query("SELECT m.*, p.product_name, e.emp_name FROM STOCK_MOVEMENT m "
                 "JOIN PRODUCT p ON p.product_id = m.product_id JOIN EMPLOYEE e ON e.emp_id = m.moved_by "
                 f"WHERE {w} ORDER BY m.movement_id DESC LIMIT %s OFFSET %s", args + [PAGE_SIZE, (page - 1) * PAGE_SIZE])
    for r in rows:  # 원천 업무 표시 (UC-14 4)
        r["source"] = next((f"{name} #{r[col]}" for col, name in SOURCES if r[col]), "-")
    emps = query("SELECT emp_id, emp_name FROM EMPLOYEE ORDER BY emp_name")
    params = {k: v for k, v in a.items() if k != "page"}
    return render_template("history/movements.html", rows=rows, emps=emps, types=MOVEMENT_TYPES, a=a, page=page,
                           pages=max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1), total=total, params=params)
