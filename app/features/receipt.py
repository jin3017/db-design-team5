"""입고·검수 (UC-07, FR-006·007): 발주입고, 직접입고, 초기재고 (SD-01). 점주·직원.
한 상품이 소비기한 여러 개로 오면 줄을 나눠 입력한다 (R16) — 입고상세 1줄 = LOT 1개."""
from collections import defaultdict
from datetime import date

from flask import Blueprint, g, render_template, request, url_for

from ..core.auth import login_required
from ..core.db import BizError, query
from ..core.inventory import add_movement
from ..core.web import run_action, to_date, to_int
from .order import lock_po

bp = Blueprint("receipt", __name__)
MENU = [(20, "입고", "receipt.receipts", False, "box-in", ("receipt.",))]

TYPES = ("PO", "DIRECT", "INITIAL")


# ------------------------------------------------------------ 업무 처리
def receive(cur, emp_id, rtype, lines, po_id=None, supplier_id=None):
    """lines: [{product_id, po_detail_id, received_qty, damaged_qty, expiry_date, memo}]
    입고 → 입고상세 → (정상수량 > 0 이면) LOT + 입고 이력. 발주입고면 누적입고수량·발주상태 갱신."""
    if any(l["received_qty"] < 0 for l in lines):
        raise BizError("입고수량은 0 이상이어야 합니다.")
    lines = [l for l in lines if l["received_qty"] > 0]
    if not lines:
        raise BizError("입고수량을 1개 이상 입력하세요.")
    po_details = {}
    if rtype == "PO":
        if lock_po(cur, po_id)["status"] not in ("APPROVED", "PARTIAL"):
            raise BizError("승인 또는 부분입고 상태의 발주서만 입고할 수 있습니다.")
        cur.execute("SELECT * FROM PO_DETAIL WHERE po_id = %s FOR UPDATE", (po_id,))
        po_details = {d["po_detail_id"]: d for d in cur.fetchall()}
        supplier_id = None
    elif rtype == "INITIAL":
        supplier_id = None
    elif rtype != "DIRECT":
        raise BizError("입고 유형을 선택하세요.")

    today = date.today()
    this_time = defaultdict(int)  # 발주상세별 이번 입고 합계 — 소비기한별로 나눈 줄을 합산
    for l in lines:
        if rtype == "PO":
            d = po_details.get(l["po_detail_id"])
            if d is None:
                raise BizError("이 발주서에 속하지 않은 상품입니다.")  # R22
            l["product_id"] = d["product_id"]  # 발주상세에서 복사 (R08)
            this_time[d["po_detail_id"]] += l["received_qty"]
            if d["received_qty"] + this_time[d["po_detail_id"]] > d["order_qty"]:
                raise BizError("누적 입고수량이 발주수량을 초과합니다.")  # BR-05, UC-07 A4
        if l["damaged_qty"] < 0 or l["damaged_qty"] > l["received_qty"]:
            raise BizError("파손수량은 0 이상, 입고수량 이하여야 합니다.")  # UC-07 A2
        cur.execute("SELECT product_name, expiry_managed FROM PRODUCT WHERE product_id = %s", (l["product_id"],))
        p = cur.fetchone()
        if p is None:
            raise BizError("상품을 선택하세요.")
        l["normal_qty"] = l["received_qty"] - l["damaged_qty"]
        if not p["expiry_managed"]:
            l["expiry_date"] = None  # 소비기한 미관리 상품 (SD-15)
        elif l["normal_qty"] > 0:
            if l["expiry_date"] is None:
                raise BizError(f"소비기한을 입력하세요: {p['product_name']}")  # R15, UC-07 A1
            if l["expiry_date"] < today:
                raise BizError(f"소비기한이 입고일보다 이전입니다: {p['product_name']}")  # UC-07 A3

    cur.execute("INSERT INTO RECEIPT (receipt_type, po_id, supplier_id, received_by, received_at) "
                "VALUES (%s, %s, %s, %s, NOW())", (rtype, po_id if rtype == "PO" else None, supplier_id, emp_id))
    receipt_id = cur.lastrowid
    for l in lines:
        cur.execute("INSERT INTO RECEIPT_DETAIL (receipt_id, po_detail_id, product_id, received_qty, damaged_qty, "
                    "normal_qty, expiry_date, memo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (receipt_id, l.get("po_detail_id") if rtype == "PO" else None, l["product_id"],
                     l["received_qty"], l["damaged_qty"], l["normal_qty"], l["expiry_date"], l.get("memo") or None))
        rd_id = cur.lastrowid
        if l["normal_qty"] > 0:  # 정상수량만 재고 반영, 입고상세 1줄 = LOT 1개 (BR-04, R-13)
            cur.execute("INSERT INTO STOCK_LOT (product_id, receipt_detail_id, received_date, expiry_date, "
                        "received_qty, remain_qty) VALUES (%s, %s, CURDATE(), %s, %s, %s)",
                        (l["product_id"], rd_id, l["expiry_date"], l["normal_qty"], l["normal_qty"]))
            add_movement(cur, cur.lastrowid, l["product_id"], "IN", l["normal_qty"], l["normal_qty"], emp_id, rd_id)
        if rtype == "PO":  # 누적입고수량은 파손 포함 (SD-19)
            cur.execute("UPDATE PO_DETAIL SET received_qty = received_qty + %s WHERE po_detail_id = %s",
                        (l["received_qty"], l["po_detail_id"]))
    if rtype == "PO":
        cur.execute("SELECT SUM(received_qty < order_qty) AS remaining FROM PO_DETAIL WHERE po_id = %s", (po_id,))
        status = "PARTIAL" if cur.fetchone()["remaining"] else "DONE"
        cur.execute("UPDATE PURCHASE_ORDER SET status = %s WHERE po_id = %s", (status, po_id))
    return receipt_id


def form_lines(form):
    """입고 화면의 줄 배열(name="key[]" 등)을 lines 로 변환.
    key 는 발주입고면 발주상세번호, 직접입고·초기재고면 상품번호."""
    cols = {k: form.getlist(f"{k}[]") for k in ("key", "recv", "dmg", "exp", "memo")}

    def col(name, i):
        values = cols[name]
        return values[i] if i < len(values) else None

    return [{"po_detail_id": to_int(key), "product_id": to_int(key),
             "received_qty": to_int(col("recv", i), 0), "damaged_qty": to_int(col("dmg", i), 0),
             "expiry_date": to_date(col("exp", i)), "memo": (col("memo", i) or "").strip()}
            for i, key in enumerate(cols["key"])]


# ------------------------------------------------------------ 화면
@bp.route("/receipts", methods=["GET", "POST"])
@login_required
def receipts():
    rtype = request.values.get("type", "PO")
    rtype = rtype if rtype in TYPES else "PO"
    if request.method == "POST":
        f = request.form
        po_id = to_int(f.get("po_id"))

        def action(cur):
            if rtype == "INITIAL" and g.user["role"] != "OWNER":
                raise BizError("초기재고 등록은 점주만 할 수 있습니다.")
            if rtype == "PO" and not po_id:
                raise BizError("진행 중인 발주서를 선택하세요.")
            return receive(cur, g.user["emp_id"], rtype, form_lines(f), po_id=po_id,
                           supplier_id=to_int(f.get("supplier_id")))
        back = url_for("receipt.receipts", type=rtype, po=po_id)
        return run_action(action, lambda rid: f"입고 #{rid}를 확정했습니다.", back, back)

    pos = query("SELECT po.*, s.supplier_name FROM PURCHASE_ORDER po JOIN SUPPLIER s ON s.supplier_id = po.supplier_id "
                "WHERE po.status IN ('APPROVED', 'PARTIAL') ORDER BY po.po_id")
    po, details = None, []
    if rtype == "PO" and pos:
        po_id = to_int(request.args.get("po")) or pos[0]["po_id"]
        po = next((p for p in pos if p["po_id"] == po_id), pos[0])
        details = query("SELECT d.*, p.product_name, p.barcode, p.expiry_managed FROM PO_DETAIL d "
                        "JOIN PRODUCT p ON p.product_id = d.product_id WHERE d.po_id = %s "
                        "ORDER BY d.po_detail_id", (po["po_id"],))
        for d in details:
            d["remaining"] = d["order_qty"] - d["received_qty"]
    products = query("SELECT product_id, product_name, barcode, expiry_managed FROM PRODUCT "
                     "ORDER BY product_name") if rtype != "PO" else []
    sups = query("SELECT supplier_id, supplier_name FROM SUPPLIER ORDER BY supplier_name") if rtype == "DIRECT" else []
    recent = query("SELECT r.*, e.emp_name, s.supplier_name, COUNT(d.receipt_detail_id) AS line_count, "
                   "SUM(d.received_qty) AS qty, SUM(d.damaged_qty) AS damaged FROM RECEIPT r "
                   "JOIN EMPLOYEE e ON e.emp_id = r.received_by "
                   "LEFT JOIN PURCHASE_ORDER po ON po.po_id = r.po_id "
                   "LEFT JOIN SUPPLIER s ON s.supplier_id = COALESCE(r.supplier_id, po.supplier_id) "
                   "LEFT JOIN RECEIPT_DETAIL d ON d.receipt_id = r.receipt_id "
                   "GROUP BY r.receipt_id, e.emp_name, s.supplier_name ORDER BY r.receipt_id DESC LIMIT 10")
    return render_template("receipt/receipts.html", rtype=rtype, pos=pos, po=po, details=details,
                           products=products, sups=sups, recent=recent, today=date.today())
