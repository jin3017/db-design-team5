"""기준정보: 상품·카테고리 (UC-03, FR-001), 공급업체·공급상품 (UC-04, FR-002).
등록·수정은 점주 전용, 상품 조회는 전체."""
from flask import Blueprint, render_template, request, url_for

from ..core.auth import login_required, owner_required
from ..core.db import BizError, query, query_one
from ..core.web import run_action, to_int

bp = Blueprint("master", __name__)
MENU = [(60, "상품관리", "master.products", True, "package", ("master.product", "master.categor")),
        (70, "공급업체관리", "master.suppliers", True, "truck", ("master.supplier",))]


# ------------------------------------------------------------ 상품
@bp.route("/products")
@login_required
def products():
    q = request.args.get("q", "").strip()
    cat = to_int(request.args.get("category"))
    where, args = ["1=1"], []
    if q:
        where.append("(p.product_name LIKE %s OR p.barcode = %s)")
        args += [f"%{q}%", q]
    if cat:
        where.append("p.category_id = %s")
        args.append(cat)
    rows = query("SELECT p.*, c.category_name FROM PRODUCT p JOIN CATEGORY c ON c.category_id = p.category_id "
                 f"WHERE {' AND '.join(where)} ORDER BY p.sale_status, p.product_name", args)
    cats = query("SELECT * FROM CATEGORY ORDER BY category_name")
    return render_template("master/products.html", rows=rows, cats=cats, q=q, cat=cat)


def product_form_values(form):
    v = {
        "product_name": form.get("product_name", "").strip(),
        "barcode": form.get("barcode", "").strip(),
        "category_id": to_int(form.get("category_id")),
        "purchase_price": to_int(form.get("purchase_price")),
        "sale_price": to_int(form.get("sale_price")),
        "safety_stock": to_int(form.get("safety_stock")),
        "expiry_managed": form.get("expiry_managed") == "1",
    }
    if not v["product_name"] or not v["barcode"] or not v["category_id"]:
        raise BizError("상품명, 바코드, 카테고리는 필수입니다.")
    for k, name in (("purchase_price", "매입가격"), ("sale_price", "판매가격"), ("safety_stock", "안전재고")):
        if v[k] is None or v[k] < 0:
            raise BizError(f"{name}은(는) 0 이상의 숫자여야 합니다.")  # UC-03 A2
    return v


def save_product(cur, pid, form, current_category=None):
    v = product_form_values(form)
    cur.execute("SELECT is_active FROM CATEGORY WHERE category_id = %s", (v["category_id"],))
    c = cur.fetchone()
    if c is None or (not c["is_active"] and v["category_id"] != current_category):
        raise BizError("사용 중지된 카테고리는 선택할 수 없습니다.")  # R26
    cols = list(v)
    if pid:
        cur.execute(f"UPDATE PRODUCT SET {', '.join(c + ' = %s' for c in cols)} WHERE product_id = %s",
                    [v[c] for c in cols] + [pid])
    else:
        cur.execute(f"INSERT INTO PRODUCT ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                    [v[c] for c in cols])


@bp.route("/products/new", methods=["GET", "POST"])
@bp.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@owner_required
def product_form(pid=None):
    product = query_one("SELECT * FROM PRODUCT WHERE product_id = %s", (pid,)) if pid else None
    if request.method == "GET":
        cats = query("SELECT * FROM CATEGORY ORDER BY category_name")
        return render_template("master/product_form.html", p=product, cats=cats)
    form = request.form
    return run_action(lambda cur: save_product(cur, pid, form, product["category_id"] if product else None),
                      "상품을 저장했습니다.", url_for("master.products"), request.url)


@bp.route("/products/<int:pid>/toggle", methods=["POST"])
@owner_required
def product_toggle(pid):
    """삭제 대신 판매중지/판매재개 (UC-03 A3, BR-10)."""
    def action(cur):
        cur.execute("UPDATE PRODUCT SET sale_status = IF(sale_status = 'ON_SALE', 'STOPPED', 'ON_SALE') "
                    "WHERE product_id = %s", (pid,))
    return run_action(action, "판매 상태를 변경했습니다.", url_for("master.products"), url_for("master.products"))


# ------------------------------------------------------------ 카테고리
@bp.route("/categories", methods=["GET", "POST"])
@owner_required
def categories():
    if request.method == "POST":
        name = request.form.get("category_name", "").strip()
        cid = to_int(request.form.get("category_id"))

        def action(cur):
            if not name:
                raise BizError("카테고리명을 입력하세요.")
            if cid:
                cur.execute("UPDATE CATEGORY SET category_name = %s WHERE category_id = %s", (name, cid))
            else:
                cur.execute("INSERT INTO CATEGORY (category_name) VALUES (%s)", (name,))
        back = url_for("master.categories")
        return run_action(action, "카테고리를 저장했습니다.", back, back)
    rows = query("SELECT c.*, COUNT(p.product_id) AS product_count FROM CATEGORY c "
                 "LEFT JOIN PRODUCT p ON p.category_id = c.category_id GROUP BY c.category_id ORDER BY c.category_name")
    return render_template("master/categories.html", rows=rows)


@bp.route("/categories/<int:cid>/toggle", methods=["POST"])
@owner_required
def category_toggle(cid):
    """삭제 대신 사용 중지 (UC-03 A5)."""
    def action(cur):
        cur.execute("UPDATE CATEGORY SET is_active = NOT is_active WHERE category_id = %s", (cid,))
    back = url_for("master.categories")
    return run_action(action, "사용 여부를 변경했습니다.", back, back)


# ------------------------------------------------------------ 공급업체
@bp.route("/suppliers")
@owner_required
def suppliers():
    rows = query("SELECT s.*, COUNT(sp.product_id) AS product_count FROM SUPPLIER s "
                 "LEFT JOIN SUPPLIER_PRODUCT sp ON sp.supplier_id = s.supplier_id "
                 "GROUP BY s.supplier_id ORDER BY s.trade_status, s.supplier_name")
    return render_template("master/suppliers.html", rows=rows)


@bp.route("/suppliers/new", methods=["GET", "POST"])
@bp.route("/suppliers/<int:sid>", methods=["GET", "POST"])
@owner_required
def supplier_form(sid=None):
    if request.method == "POST":
        f = request.form
        name = f.get("supplier_name", "").strip()

        def action(cur):
            if not name:
                raise BizError("공급업체명은 필수입니다.")  # UC-04 A1
            vals = (name, f.get("phone", "").strip() or None, f.get("contact_name", "").strip() or None)
            if sid:
                cur.execute("UPDATE SUPPLIER SET supplier_name = %s, phone = %s, contact_name = %s "
                            "WHERE supplier_id = %s", vals + (sid,))
                return sid
            cur.execute("INSERT INTO SUPPLIER (supplier_name, phone, contact_name) VALUES (%s, %s, %s)", vals)
            return cur.lastrowid
        return run_action(action, "공급업체를 저장했습니다.",
                          lambda new_id: url_for("master.supplier_form", sid=new_id), request.url)
    sup = query_one("SELECT * FROM SUPPLIER WHERE supplier_id = %s", (sid,)) if sid else None
    items = query("SELECT sp.*, p.product_name, p.barcode, p.purchase_price FROM SUPPLIER_PRODUCT sp "
                  "JOIN PRODUCT p ON p.product_id = sp.product_id WHERE sp.supplier_id = %s "
                  "ORDER BY p.product_name", (sid,)) if sid else []
    others = query("SELECT product_id, product_name FROM PRODUCT WHERE product_id NOT IN "
                   "(SELECT product_id FROM SUPPLIER_PRODUCT WHERE supplier_id = %s) ORDER BY product_name",
                   (sid,)) if sid else []
    return render_template("master/supplier_form.html", s=sup, items=items, others=others)


@bp.route("/suppliers/<int:sid>/toggle", methods=["POST"])
@owner_required
def supplier_toggle(sid):
    """삭제 대신 거래중지 (UC-04 A2)."""
    def action(cur):
        cur.execute("UPDATE SUPPLIER SET trade_status = IF(trade_status = 'ACTIVE', 'STOPPED', 'ACTIVE') "
                    "WHERE supplier_id = %s", (sid,))
    back = url_for("master.suppliers")
    return run_action(action, "거래 상태를 변경했습니다.", back, back)


@bp.route("/suppliers/<int:sid>/products", methods=["POST"])
@owner_required
def supplier_products(sid):
    """담당 상품·공급가격 추가/수정/제외."""
    pid = to_int(request.form.get("product_id"))
    price = to_int(request.form.get("supply_price"))
    remove = request.form.get("remove") == "1"
    back = url_for("master.supplier_form", sid=sid)

    def action(cur):
        if not pid:
            raise BizError("상품을 선택하세요.")
        if remove:
            cur.execute("DELETE FROM SUPPLIER_PRODUCT WHERE supplier_id = %s AND product_id = %s", (sid, pid))
            return
        if price is None or price < 0:
            raise BizError("공급가격은 0 이상의 숫자여야 합니다.")  # UC-04 A4
        cur.execute("INSERT INTO SUPPLIER_PRODUCT (supplier_id, product_id, supply_price) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE supply_price = VALUES(supply_price)", (sid, pid, price))
    return run_action(action, "담당 상품을 저장했습니다.", back, back)
