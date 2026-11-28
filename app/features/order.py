"""발주: 발주 필요 상품 조회 (UC-05, FR-003), 발주서 작성·승인·취소 (UC-06, FR-004·005). 점주 전용."""
from flask import Blueprint, g, render_template, request, url_for

from ..core.auth import login_required, owner_required
from ..core.db import BizError, query, query_one
from ..core.web import run_action, stock_summary, to_int

bp = Blueprint("order", __name__)
MENU = [(40, "발주", "order.orders", True, "clipboard", ("order.",))]


# ------------------------------------------------------------ 업무 처리
def create_po(cur, emp_id, supplier_id, items):
    """items: [(product_id, qty)] — qty > 0 인 것만. 상태 '작성'으로 저장."""
    cur.execute("SELECT trade_status FROM SUPPLIER WHERE supplier_id = %s", (supplier_id,))
    sup = cur.fetchone()
    if sup is None:
        raise BizError("공급업체를 선택하세요.")  # UC-06 A2
    if sup["trade_status"] != "ACTIVE":
        raise BizError("거래중지 공급업체에는 발주할 수 없습니다.")  # R25
    if not items:
        raise BizError("발주수량을 1개 이상 입력하세요.")  # UC-06 A1
    lines = []
    for pid, qty in items:
        cur.execute("SELECT sp.supply_price, p.sale_status, p.product_name FROM SUPPLIER_PRODUCT sp "
                    "JOIN PRODUCT p ON p.product_id = sp.product_id "
                    "WHERE sp.supplier_id = %s AND sp.product_id = %s", (supplier_id, pid))
        row = cur.fetchone()
        if row is None:
            raise BizError("해당 공급업체의 담당 상품이 아닙니다.")  # R07
        if row["sale_status"] != "ON_SALE":
            raise BizError(f"판매중지 상품은 발주할 수 없습니다: {row['product_name']}")  # R24
        lines.append((pid, qty, row["supply_price"]))
    total = sum(q * price for _, q, price in lines)  # BR-13
    cur.execute("INSERT INTO PURCHASE_ORDER (supplier_id, created_by, po_date, status, total_amount) "
                "VALUES (%s, %s, CURDATE(), 'DRAFT', %s)", (supplier_id, emp_id, total))
    po_id = cur.lastrowid
    for pid, qty, price in lines:  # 발주 시점 공급가격 저장 (BR-09)
        cur.execute("INSERT INTO PO_DETAIL (po_id, product_id, order_qty, supply_price, amount) "
                    "VALUES (%s, %s, %s, %s, %s)", (po_id, pid, qty, price, qty * price))
    return po_id


def lock_po(cur, po_id):
    cur.execute("SELECT * FROM PURCHASE_ORDER WHERE po_id = %s FOR UPDATE", (po_id,))
    po = cur.fetchone()
    if po is None:
        raise BizError("존재하지 않는 발주서입니다.")
    return po


def approve_po(cur, emp_id, po_id):
    if lock_po(cur, po_id)["status"] != "DRAFT":
        raise BizError("작성 상태의 발주서만 승인할 수 있습니다.")  # R01
    cur.execute("UPDATE PURCHASE_ORDER SET status = 'APPROVED', approved_by = %s, approved_at = NOW() "
                "WHERE po_id = %s", (emp_id, po_id))


def cancel_po(cur, emp_id, po_id, reason):
    """작성·승인·부분입고 상태만 취소. 부분입고분은 유효한 입고로 남는다 (R19)."""
    if lock_po(cur, po_id)["status"] not in ("DRAFT", "APPROVED", "PARTIAL"):
        raise BizError("입고완료·취소된 발주서는 취소할 수 없습니다.")  # UC-06 A5
    if not reason:
        raise BizError("취소 사유를 입력하세요.")
    cur.execute("UPDATE PURCHASE_ORDER SET status = 'CANCELED', canceled_by = %s, canceled_at = NOW(), "
                "cancel_reason = %s WHERE po_id = %s", (emp_id, reason, po_id))


# ------------------------------------------------------------ 화면
@bp.route("/orders")
@owner_required
def orders():
    status = request.args.get("status", "")
    where, args = ("WHERE po.status = %s", [status]) if status else ("", [])
    rows = query("SELECT po.*, s.supplier_name, e.emp_name AS created_name FROM PURCHASE_ORDER po "
                 "JOIN SUPPLIER s ON s.supplier_id = po.supplier_id JOIN EMPLOYEE e ON e.emp_id = po.created_by "
                 f"{where} ORDER BY po.po_id DESC LIMIT 100", args)
    return render_template("order/orders.html", rows=rows, status=status)


@bp.route("/orders/needed")
@owner_required
def needed():
    """판매 가능 재고 ≤ 안전재고인 판매중 상품 (R18). 진행 중 발주가 있으면 표시 (UC-05 A2)."""
    rows = [r for r in stock_summary("WHERE p.sale_status = 'ON_SALE'") if r["low"]]
    in_progress = {r["product_id"] for r in query(
        "SELECT DISTINCT d.product_id FROM PO_DETAIL d JOIN PURCHASE_ORDER po ON po.po_id = d.po_id "
        "WHERE po.status IN ('DRAFT', 'APPROVED', 'PARTIAL')")}
    sups = {}
    for r in query("SELECT sp.product_id, s.supplier_id, s.supplier_name FROM SUPPLIER_PRODUCT sp "
                   "JOIN SUPPLIER s ON s.supplier_id = sp.supplier_id WHERE s.trade_status = 'ACTIVE'"):
        sups.setdefault(r["product_id"], []).append(r)
    for r in rows:
        r["in_progress"] = r["product_id"] in in_progress
        r["suppliers"] = sups.get(r["product_id"], [])
        r["shortage"] = r["safety_stock"] - r["sellable_qty"]
    return render_template("order/orders_needed.html", rows=rows)


@bp.route("/orders/new", methods=["GET", "POST"])
@owner_required
def order_new():
    sid = to_int(request.values.get("supplier_id"))
    if request.method == "POST":
        items = [(to_int(k[4:]), to_int(v, 0)) for k, v in request.form.items() if k.startswith("qty_")]

        def action(cur):
            if any(q < 0 for _, q in items):
                raise BizError("발주수량은 0 이상이어야 합니다.")
            return create_po(cur, g.user["emp_id"], sid, [(p, q) for p, q in items if q > 0])
        return run_action(action, lambda po_id: f"발주서 #{po_id}를 작성했습니다.",
                          lambda po_id: url_for("order.order_detail", po_id=po_id), request.url)
    sups = query("SELECT supplier_id, supplier_name FROM SUPPLIER WHERE trade_status = 'ACTIVE' "
                 "ORDER BY supplier_name")
    items = []
    if sid:  # 선택한 업체의 담당 상품만 표시 (R07)
        summary = {r["product_id"]: r for r in stock_summary("WHERE p.sale_status = 'ON_SALE'")}
        for r in query("SELECT sp.product_id, sp.supply_price, p.product_name FROM SUPPLIER_PRODUCT sp "
                       "JOIN PRODUCT p ON p.product_id = sp.product_id "
                       "WHERE sp.supplier_id = %s AND p.sale_status = 'ON_SALE' ORDER BY p.product_name", (sid,)):
            s = summary.get(r["product_id"], {})
            r.update(sellable_qty=s.get("sellable_qty", 0), safety_stock=s.get("safety_stock", 0),
                     low=s.get("low", False))
            r["suggest"] = max(r["safety_stock"] * 2 - r["sellable_qty"], 0) if r["low"] else 0
            items.append(r)
    return render_template("order/order_new.html", sups=sups, sid=sid, items=items)


@bp.route("/orders/<int:po_id>")
@login_required
def order_detail(po_id):
    """직원도 입고를 위해 조회할 수 있다. 승인·취소 버튼은 점주에게만."""
    po = query_one("SELECT po.*, s.supplier_name, c.emp_name AS created_name, a.emp_name AS approved_name, "
                   "x.emp_name AS canceled_name FROM PURCHASE_ORDER po "
                   "JOIN SUPPLIER s ON s.supplier_id = po.supplier_id JOIN EMPLOYEE c ON c.emp_id = po.created_by "
                   "LEFT JOIN EMPLOYEE a ON a.emp_id = po.approved_by "
                   "LEFT JOIN EMPLOYEE x ON x.emp_id = po.canceled_by WHERE po.po_id = %s", (po_id,))
    if po is None:
        return render_template("message.html", message="존재하지 않는 발주서입니다."), 404
    details = query("SELECT d.*, p.product_name, p.expiry_managed FROM PO_DETAIL d "
                    "JOIN PRODUCT p ON p.product_id = d.product_id WHERE d.po_id = %s ORDER BY d.po_detail_id",
                    (po_id,))
    return render_template("order/order_detail.html", po=po, details=details)


@bp.route("/orders/<int:po_id>/approve", methods=["POST"])
@owner_required
def order_approve(po_id):
    back = url_for("order.order_detail", po_id=po_id)
    return run_action(lambda cur: approve_po(cur, g.user["emp_id"], po_id), "발주서를 승인했습니다.", back, back)


@bp.route("/orders/<int:po_id>/cancel", methods=["POST"])
@owner_required
def order_cancel(po_id):
    back = url_for("order.order_detail", po_id=po_id)
    reason = request.form.get("reason", "").strip()
    return run_action(lambda cur: cancel_po(cur, g.user["emp_id"], po_id, reason), "발주서를 취소했습니다.",
                      back, back)
