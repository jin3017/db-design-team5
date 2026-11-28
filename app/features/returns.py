"""업체 반품 (UC-12, FR-014): 요청 → 승인(재고 차감) → 완료, 요청 → 반려/취소. 점주 전용."""
from flask import Blueprint, g, render_template, request, url_for

from ..core.auth import owner_required
from ..core.db import BizError, query
from ..core.inventory import add_movement, lock_lot
from ..core.labels import RETURN_REASONS
from ..core.web import run_action, to_int

bp = Blueprint("returns", __name__)
MENU = [(45, "반품", "returns.returns", True, "undo", ("returns.",))]


# ------------------------------------------------------------ 업무 처리
def lock_return(cur, return_id):
    cur.execute("SELECT * FROM RETURN_ORDER WHERE return_id = %s FOR UPDATE", (return_id,))
    r = cur.fetchone()
    if r is None:
        raise BizError("존재하지 않는 반품입니다.")
    return r


def create_return(cur, emp_id, supplier_id, product_id, lot_id, po_id, qty, reason_type):
    """재고에 있는 상품은 LOT 지정 (R17). LOT 없이는 검수 파손분처럼 재고에 없던 수량만."""
    if not supplier_id:
        raise BizError("공급업체를 선택하세요.")
    if qty is None or qty < 1:
        raise BizError("반품수량은 1 이상이어야 합니다.")
    if reason_type not in RETURN_REASONS:
        raise BizError("반품 사유를 선택하세요.")
    if lot_id:
        lot = lock_lot(cur, lot_id)
        product_id = lot["product_id"]  # LOT에서 복사 (R08)
        if qty > lot["remain_qty"]:
            raise BizError("반품수량이 LOT 잔여수량을 초과합니다.")  # UC-12 A1
    if not product_id:
        raise BizError("상품 또는 LOT를 선택하세요.")
    if po_id:
        cur.execute("SELECT supplier_id FROM PURCHASE_ORDER WHERE po_id = %s", (po_id,))
        po = cur.fetchone()
        if po is None or po["supplier_id"] != supplier_id:
            raise BizError("연결한 발주서의 공급업체와 반품 공급업체가 다릅니다.")  # R23
    cur.execute("INSERT INTO RETURN_ORDER (supplier_id, product_id, lot_id, po_id, return_qty, reason_type, "
                "status, requested_by, requested_at) VALUES (%s, %s, %s, %s, %s, %s, 'REQUESTED', %s, NOW())",
                (supplier_id, product_id, lot_id or None, po_id or None, qty, reason_type, emp_id))
    return cur.lastrowid


def approve_return(cur, emp_id, return_id):
    r = lock_return(cur, return_id)
    if r["status"] != "REQUESTED":
        raise BizError("요청 상태의 반품만 승인할 수 있습니다.")  # R01
    if r["lot_id"]:  # 재고에 반영돼 있던 수량만 LOT에서 차감 (UC-12 A3)
        lot = lock_lot(cur, r["lot_id"])
        if r["return_qty"] > lot["remain_qty"]:
            raise BizError("LOT 잔여수량이 반품수량보다 적습니다.")
        remain = lot["remain_qty"] - r["return_qty"]
        cur.execute("UPDATE STOCK_LOT SET remain_qty = %s WHERE lot_id = %s", (remain, r["lot_id"]))
        add_movement(cur, r["lot_id"], r["product_id"], "RETURN", -r["return_qty"], remain, emp_id, return_id)
    cur.execute("UPDATE RETURN_ORDER SET status = 'APPROVED', decided_by = %s, decided_at = NOW() "
                "WHERE return_id = %s", (emp_id, return_id))


def reject_return(cur, emp_id, return_id, reason):
    if lock_return(cur, return_id)["status"] != "REQUESTED":
        raise BizError("요청 상태의 반품만 반려할 수 있습니다.")
    if not reason:
        raise BizError("반려 사유를 입력하세요.")
    cur.execute("UPDATE RETURN_ORDER SET status = 'REJECTED', decided_by = %s, decided_at = NOW(), "
                "reject_reason = %s WHERE return_id = %s", (emp_id, reason, return_id))


def complete_return(cur, return_id):
    if lock_return(cur, return_id)["status"] != "APPROVED":
        raise BizError("승인된 반품만 완료 처리할 수 있습니다.")
    cur.execute("UPDATE RETURN_ORDER SET status = 'DONE', completed_at = NOW() WHERE return_id = %s", (return_id,))


def cancel_return(cur, emp_id, return_id):
    if lock_return(cur, return_id)["status"] != "REQUESTED":
        raise BizError("요청 상태의 반품만 취소할 수 있습니다.")  # R28
    cur.execute("UPDATE RETURN_ORDER SET status = 'CANCELED', canceled_by = %s, canceled_at = NOW() "
                "WHERE return_id = %s", (emp_id, return_id))


# ------------------------------------------------------------ 화면
@bp.route("/returns", methods=["GET", "POST"])
@owner_required
def returns():
    back = url_for("returns.returns")
    if request.method == "POST":
        f = request.form
        return run_action(
            lambda cur: create_return(cur, g.user["emp_id"], to_int(f.get("supplier_id")), to_int(f.get("product_id")),
                                      to_int(f.get("lot_id")), to_int(f.get("po_id")), to_int(f.get("return_qty")),
                                      f.get("reason_type")),
            lambda rid: f"반품 #{rid}를 요청했습니다.", back, back)
    rows = query("SELECT r.*, s.supplier_name, p.product_name, e.emp_name AS requested_name, "
                 "d.emp_name AS decided_name FROM RETURN_ORDER r JOIN SUPPLIER s ON s.supplier_id = r.supplier_id "
                 "JOIN PRODUCT p ON p.product_id = r.product_id JOIN EMPLOYEE e ON e.emp_id = r.requested_by "
                 "LEFT JOIN EMPLOYEE d ON d.emp_id = r.decided_by ORDER BY r.return_id DESC LIMIT 100")
    sups = query("SELECT supplier_id, supplier_name FROM SUPPLIER ORDER BY supplier_name")
    products = query("SELECT product_id, product_name FROM PRODUCT ORDER BY product_name")
    lots = query("SELECT l.lot_id, l.remain_qty, l.expiry_date, p.product_name FROM STOCK_LOT l "
                 "JOIN PRODUCT p ON p.product_id = l.product_id WHERE l.is_disposed = FALSE AND l.remain_qty > 0 "
                 "ORDER BY p.product_name, l.expiry_date")
    return render_template("returns/returns.html", rows=rows, sups=sups, products=products, lots=lots,
                           reasons=RETURN_REASONS, pre_lot=to_int(request.args.get("lot")))


@bp.route("/returns/<int:rid>/<action>", methods=["POST"])
@owner_required
def return_action(rid, action):
    emp = g.user["emp_id"]
    reason = request.form.get("reason", "").strip()
    handlers = {
        "approve": (lambda cur: approve_return(cur, emp, rid), "반품을 승인했습니다."),
        "reject": (lambda cur: reject_return(cur, emp, rid, reason), "반품을 반려했습니다."),
        "complete": (lambda cur: complete_return(cur, rid), "반품을 완료 처리했습니다."),
        "cancel": (lambda cur: cancel_return(cur, emp, rid), "반품 요청을 취소했습니다."),
    }
    if action not in handlers:
        return render_template("message.html", message="잘못된 요청입니다."), 400
    fn, msg = handlers[action]
    back = url_for("returns.returns")
    return run_action(fn, msg, back, back)
