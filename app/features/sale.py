"""판매 처리 (UC-08, FR-008·009): 바코드/검색 → 판매 목록 → 판매 완료 시 FEFO 차감. 점주·직원."""
from datetime import datetime

import pymysql
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from ..core.auth import login_required
from ..core.db import BizError, query, query_one, transaction
from ..core.inventory import SELLABLE_LOTS, add_movement, sellable_qty
from ..core.web import db_error_message, stock_summary, to_int

bp = Blueprint("sale", __name__)
MENU = [(10, "판매", "sale.sale", False, "scan", ("sale.",))]

NOT_ADDED = "상품은 추가되지 않았습니다. 바코드와 판매 가능 상태를 확인해 주세요."


# ------------------------------------------------------------ 업무 처리
def sell(cur, emp_id, cart):
    """cart: {product_id: qty}. 판매·판매상세 저장 + FEFO 차감 + 이력을 한 트랜잭션으로 (FR-009).
    반환: (판매번호, 안전재고 이하가 된 상품 [{name, sellable, safety}])."""
    if not cart:
        raise BizError("판매할 상품이 없습니다.")
    plan = []
    for pid, qty in cart.items():
        cur.execute("SELECT product_name, sale_price, sale_status, safety_stock FROM PRODUCT WHERE product_id = %s",
                    (pid,))
        p = cur.fetchone()
        if p is None:
            raise BizError("등록되지 않은 상품입니다.")
        if p["sale_status"] != "ON_SALE":
            raise BizError(f"판매중지 상품입니다: {p['product_name']}")  # R24, UC-08 A2
        if qty < 1:
            raise BizError("수량은 1 이상이어야 합니다.")
        cur.execute(SELLABLE_LOTS, (pid,))  # 차감할 LOT 잠금 (동시 판매 대비)
        lots = cur.fetchall()
        if sum(l["remain_qty"] for l in lots) < qty:
            raise BizError(f"판매 가능 재고가 부족합니다: {p['product_name']}")  # BR-07, UC-08 A3
        plan.append((pid, qty, p, lots))

    total = sum(qty * p["sale_price"] for _, qty, p, _ in plan)  # BR-13
    cur.execute("INSERT INTO SALE (sold_by, sold_at, total_amount) VALUES (%s, NOW(), %s)", (emp_id, total))
    sale_id = cur.lastrowid
    low = []
    for pid, qty, p, lots in plan:  # 판매 시점 단가 저장 (BR-09)
        cur.execute("INSERT INTO SALE_DETAIL (sale_id, product_id, sale_qty, unit_price, amount) "
                    "VALUES (%s, %s, %s, %s, %s)", (sale_id, pid, qty, p["sale_price"], qty * p["sale_price"]))
        sd_id = cur.lastrowid
        need = qty
        for lot in lots:  # 소비기한 빠른 LOT부터 차감 (R02)
            if need == 0:
                break
            take = min(need, lot["remain_qty"])
            remain = lot["remain_qty"] - take
            cur.execute("UPDATE STOCK_LOT SET remain_qty = %s WHERE lot_id = %s", (remain, lot["lot_id"]))
            add_movement(cur, lot["lot_id"], pid, "SALE", -take, remain, emp_id, sd_id)
            need -= take
        left = sellable_qty(cur, pid)
        if left <= p["safety_stock"]:  # ALM-01
            low.append({"name": p["product_name"], "sellable": left, "safety": p["safety_stock"]})
    return sale_id, low


# ------------------------------------------------------------ 판매 목록 (판매 완료 전, 세션에 보관)
def get_cart():
    return {int(k): v for k, v in session.get("cart", {}).items()}


def save_cart(cart):
    session["cart"] = {str(k): v for k, v in cart.items()}


def add_to_cart(p, qty):
    """판매 목록에 추가. 판매중지·재고 부족이면 추가하지 않고 메시지 (UC-08 A2, A3)."""
    if p["sale_status"] != "ON_SALE":
        flash(f"판매가 중지된 상품입니다.|{NOT_ADDED}", "error")
        return
    cart = get_cart()
    want = cart.get(p["product_id"], 0) + qty
    available = int(query_one("SELECT COALESCE(SUM(remain_qty), 0) AS q FROM STOCK_LOT WHERE product_id = %s "
                              "AND is_disposed = FALSE AND (expiry_date IS NULL OR expiry_date >= CURDATE())",
                              (p["product_id"],))["q"])
    if want > available:
        flash(f"재고가 부족합니다. (판매 가능 수량: {available}개)|{NOT_ADDED}", "error")
        return
    session["last_scan"] = {"pid": p["product_id"], "rescan": p["product_id"] in cart}
    cart[p["product_id"]] = want
    save_cart(cart)


# ------------------------------------------------------------ 화면
@bp.route("/sale")
@login_required
def sale():
    cart = get_cart()
    items = []
    if cart:
        info = {r["product_id"]: r for r in stock_summary(
            f"WHERE p.product_id IN ({', '.join(['%s'] * len(cart))})", list(cart))}
        for pid, qty in cart.items():
            p = info.get(pid)
            if p:
                items.append({"product_id": pid, "name": p["product_name"], "barcode": p["barcode"],
                              "price": p["sale_price"], "qty": qty, "amount": p["sale_price"] * qty,
                              "sellable": p["sellable_qty"]})
    q = request.args.get("q", "").strip()
    found = query("SELECT product_id, product_name, barcode, sale_price FROM PRODUCT WHERE sale_status = 'ON_SALE' "
                  "AND (product_name LIKE %s OR barcode = %s) ORDER BY product_name LIMIT 20",
                  (f"%{q}%", q)) if q else []
    return render_template("sale/sale.html", items=items, total=sum(i["amount"] for i in items),
                           count=sum(i["qty"] for i in items), q=q, found=found, searching="q" in request.args,
                           last_scan=session.get("last_scan"), last_sale=session.pop("last_sale", None))


@bp.route("/sale/add", methods=["POST"])
@login_required
def sale_add():
    code = request.form.get("barcode", "").strip()
    pid = to_int(request.form.get("product_id"))
    if pid:
        p = query_one("SELECT * FROM PRODUCT WHERE product_id = %s", (pid,))
    elif code:
        p = query_one("SELECT * FROM PRODUCT WHERE barcode = %s", (code,))
    else:
        return redirect(url_for("sale.sale"))
    if p is None:
        flash(f"등록되지 않은 바코드입니다.|{NOT_ADDED}", "error")  # UC-08 A1
    else:
        add_to_cart(p, 1)  # 같은 상품을 다시 스캔하면 수량 +1
    return redirect(url_for("sale.sale"))


@bp.route("/sale/update", methods=["POST"])
@login_required
def sale_update():
    """판매 완료 전 수량 변경·삭제 (UC-08 A6)."""
    cart = get_cart()
    pid = to_int(request.form.get("product_id"))
    delta = to_int(request.form.get("delta"), 0)
    session.pop("last_scan", None)  # 직접 수량을 바꾸면 '마지막 스캔' 강조 해제
    if pid in cart:
        if request.form.get("remove") or cart[pid] + delta <= 0:
            cart.pop(pid)
            save_cart(cart)
        elif delta > 0:
            add_to_cart(query_one("SELECT * FROM PRODUCT WHERE product_id = %s", (pid,)), delta)
            session.pop("last_scan", None)  # + 버튼은 스캔이 아니므로 강조하지 않음
        else:
            cart[pid] += delta
            save_cart(cart)
    return redirect(url_for("sale.sale"))


@bp.route("/sale/complete", methods=["POST"])
@login_required
def sale_complete():
    cart = get_cart()
    try:
        with transaction() as cur:
            sale_id, low = sell(cur, g.user["emp_id"], cart)
            cur.execute("SELECT total_amount FROM SALE WHERE sale_id = %s", (sale_id,))
            amount = cur.fetchone()["total_amount"]
    except BizError as e:
        flash(str(e), "error")
        return redirect(url_for("sale.sale"))
    except pymysql.err.MySQLError as e:  # 오류 시 판매·차감 전체 롤백 (UC-08 A5)
        flash(db_error_message(e), "error")
        return redirect(url_for("sale.sale"))
    save_cart({})
    session.pop("last_scan", None)
    session["last_sale"] = {"id": sale_id, "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "by": g.user["emp_name"], "kinds": len(cart), "qty": sum(cart.values()),
                            "amount": amount, "low": low}
    return redirect(url_for("sale.sale"))
