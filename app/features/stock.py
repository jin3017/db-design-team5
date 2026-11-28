"""재고 조회·조정 (UC-09, FR-010·011), 소비기한 임박 (UC-10, FR-012), 폐기 (UC-11, FR-013). 점주·직원.
상품 행을 펼치면 LOT(입고 묶음)별 잔여수량이 나오고, LOT 단위로 조정·폐기한다."""
from datetime import date

from flask import Blueprint, g, redirect, render_template, request, url_for

from ..core.auth import login_required
from ..core.db import BizError, query, query_one
from ..core.inventory import add_movement, lock_lot
from ..core.labels import ADJUST_REASONS, DISPOSAL_REASONS
from ..core.web import alert_days, run_action, stock_summary, to_int

bp = Blueprint("stock", __name__)
MENU = [(30, "재고", "stock.stock", False, "boxes", ("stock.", "history."))]  # 소비기한·이력은 재고 화면의 탭


# ------------------------------------------------------------ 업무 처리
def check_reason(reason_type, reason_detail, allowed, what):
    if reason_type not in allowed:
        raise BizError(f"{what} 사유를 선택하세요.")  # BR-11
    if reason_type == "ETC" and not reason_detail:
        raise BizError("기타 사유는 상세 사유를 입력하세요.")


def adjust(cur, emp_id, lot_id, after_qty, reason_type, reason_detail):
    """LOT 하나의 장부 수량을 실제 수량(after_qty)으로 맞춘다. 조정 전·후 수량 저장 (SD-02)."""
    lot = lock_lot(cur, lot_id)  # 폐기된 LOT 조정 불가 (UC-09 A3)
    if after_qty is None or after_qty < 0:
        raise BizError("조정 후 수량은 0 이상이어야 합니다.")  # UC-09 A2
    check_reason(reason_type, reason_detail, ADJUST_REASONS, "조정")
    before = lot["remain_qty"]
    if after_qty == before:
        raise BizError("현재 수량과 같아 조정할 내용이 없습니다.")
    cur.execute("INSERT INTO STOCK_ADJUSTMENT (lot_id, before_qty, after_qty, adjust_qty, reason_type, "
                "reason_detail, input_method, adjusted_by, adjusted_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'LOT', %s, NOW())",
                (lot_id, before, after_qty, after_qty - before, reason_type, reason_detail or None, emp_id))
    adj_id = cur.lastrowid
    cur.execute("UPDATE STOCK_LOT SET remain_qty = %s WHERE lot_id = %s", (after_qty, lot_id))
    add_movement(cur, lot_id, lot["product_id"], "ADJUST", after_qty - before, after_qty, emp_id, adj_id)


def dispose(cur, emp_id, lot_id, qty, reason_type, reason_detail):
    """지정한 LOT에서 폐기 (R03). 잔여가 0이 되면 폐기여부 TRUE (R20)."""
    lot = lock_lot(cur, lot_id)  # UC-11 A3
    if qty is None or qty < 1 or qty > lot["remain_qty"]:
        raise BizError("폐기수량은 1 이상, 잔여수량 이하여야 합니다.")  # UC-11 A1
    check_reason(reason_type, reason_detail, DISPOSAL_REASONS, "폐기")
    cur.execute("INSERT INTO DISPOSAL (lot_id, disposal_qty, reason_type, reason_detail, disposed_by, disposed_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW())", (lot_id, qty, reason_type, reason_detail or None, emp_id))
    disp_id = cur.lastrowid
    remain = lot["remain_qty"] - qty
    cur.execute("UPDATE STOCK_LOT SET remain_qty = %s, is_disposed = %s WHERE lot_id = %s",
                (remain, remain == 0, lot_id))
    add_movement(cur, lot_id, lot["product_id"], "DISPOSE", -qty, remain, emp_id, disp_id)


def attach_lots(rows):
    """상품 목록에 남아 있는 LOT(폐기 안 됨, 잔여 > 0)를 FEFO 순서로 붙인다."""
    if not rows:
        return
    ids = [r["product_id"] for r in rows]
    today, days = date.today(), alert_days()
    lots = query("SELECT * FROM STOCK_LOT WHERE is_disposed = FALSE AND remain_qty > 0 "
                 f"AND product_id IN ({', '.join(['%s'] * len(ids))}) "
                 "ORDER BY expiry_date IS NULL, expiry_date, received_date, lot_id", ids)
    by_product = {}
    for l in lots:
        e = l["expiry_date"]
        l["days_left"] = (e - today).days if e else None
        l["expired"] = bool(e and e < today)
        l["imminent"] = bool(e and 0 <= (e - today).days <= days)
        by_product.setdefault(l["product_id"], []).append(l)
    for r in rows:
        r["lots"] = by_product.get(r["product_id"], [])


# ------------------------------------------------------------ 화면
@bp.route("/stock")
@login_required
def stock():
    a = request.args
    name, barcode = a.get("name", "").strip(), a.get("barcode", "").strip()
    cat, state = to_int(a.get("category")), a.get("state", "")
    where, args = ["1=1"], []
    if name:
        where.append("p.product_name LIKE %s")
        args.append(f"%{name}%")
    if barcode:
        where.append("p.barcode = %s")
        args.append(barcode)
    if cat:
        where.append("p.category_id = %s")
        args.append(cat)
    rows = stock_summary("WHERE " + " AND ".join(where), args)
    if state == "low":
        rows = [r for r in rows if r["low"]]
    elif state == "imminent":
        rows = [r for r in rows if r["imminent"]]
    elif state == "expired":
        rows = [r for r in rows if r["expired"]]
    attach_lots(rows)
    cats = query("SELECT * FROM CATEGORY ORDER BY category_name")
    return render_template("stock/stock.html", rows=rows, cats=cats, a=a, days=alert_days(),
                           open_pid=to_int(a.get("open")), reasons=ADJUST_REASONS)


@bp.route("/stock/<int:pid>")
@login_required
def stock_detail(pid):
    """메인 화면 등에서 상품 하나로 이동 — 재고 목록에서 그 상품을 펼친 상태로 보여 준다."""
    p = query_one("SELECT product_name FROM PRODUCT WHERE product_id = %s", (pid,))
    if p is None:
        return render_template("message.html", message="존재하지 않는 상품입니다."), 404
    return redirect(url_for("stock.stock", name=p["product_name"], open=pid))


@bp.route("/stock/lot/<int:lot_id>/adjust", methods=["POST"])
@login_required
def lot_adjust(lot_id):
    f = request.form
    lot = query_one("SELECT product_id FROM STOCK_LOT WHERE lot_id = %s", (lot_id,))
    back = url_for("stock.stock", open=lot["product_id"]) if lot else url_for("stock.stock")
    return run_action(lambda cur: adjust(cur, g.user["emp_id"], lot_id, to_int(f.get("after_qty")),
                                         f.get("reason_type"), f.get("reason_detail", "").strip()),
                      "재고를 조정했습니다.", back, back)


@bp.route("/expiry")
@login_required
def expiry():
    days = alert_days()
    lots = query("SELECT l.*, p.product_name, p.barcode, DATEDIFF(l.expiry_date, CURDATE()) AS days_left "
                 "FROM STOCK_LOT l JOIN PRODUCT p ON p.product_id = l.product_id "
                 "WHERE l.is_disposed = FALSE AND l.remain_qty > 0 AND l.expiry_date IS NOT NULL "
                 "AND l.expiry_date <= CURDATE() + INTERVAL %s DAY ORDER BY l.expiry_date, p.product_name", (days,))
    return render_template("stock/expiry.html", lots=lots, days=days, reasons=DISPOSAL_REASONS,
                           expired=sum(1 for l in lots if l["days_left"] < 0))


@bp.route("/dispose/<int:lot_id>", methods=["POST"])
@login_required
def lot_dispose(lot_id):
    f = request.form
    back = url_for("stock.expiry") if f.get("back") == "expiry" else url_for("stock.stock")
    return run_action(lambda cur: dispose(cur, g.user["emp_id"], lot_id, to_int(f.get("disposal_qty")),
                                          f.get("reason_type"), f.get("reason_detail", "").strip()),
                      "폐기 처리했습니다.", back, back)
