"""메인 화면 (INT-014): 재고 부족·소비기한 임박/경과 건수와 확인할 상품 (ALM-01~03, UC-10 A2)."""
from datetime import date, timedelta

from flask import Blueprint, redirect, render_template, url_for

from ..core.auth import login_required
from ..core.db import query
from ..core.web import alert_days, stock_summary

bp = Blueprint("home", __name__)


@bp.route("/")
@login_required
def index():
    days = alert_days()
    low = [r for r in stock_summary("WHERE p.sale_status = 'ON_SALE'") if r["low"]]
    lots = query("SELECT l.lot_id, l.expiry_date, l.remain_qty, p.product_id, p.product_name, "
                 "DATEDIFF(l.expiry_date, CURDATE()) AS days_left FROM STOCK_LOT l "
                 "JOIN PRODUCT p ON p.product_id = l.product_id "
                 "WHERE l.is_disposed = FALSE AND l.remain_qty > 0 AND l.expiry_date IS NOT NULL "
                 "AND l.expiry_date <= CURDATE() + INTERVAL %s DAY ORDER BY l.expiry_date", (days,))
    expired = [l for l in lots if l["days_left"] < 0]
    imminent = [l for l in lots if l["days_left"] >= 0]

    # 확인할 상품: 부족 → 경과 → 임박 순
    checks = [{"pid": r["product_id"], "name": r["product_name"], "kind": "low", "label": "부족",
               "detail": f"판매 가능 {r['sellable_qty']}개 / 안전재고 {r['safety_stock']}개"} for r in low]
    checks += [{"pid": l["product_id"], "name": l["product_name"], "kind": kind, "label": label,
                "detail": f"{l['expiry_date']:%Y-%m-%d} · 잔여 {l['remain_qty']}개"}
               for group, kind, label in ((expired, "expired", "경과"), (imminent, "imminent", "임박"))
               for l in group]
    return render_template("home.html", days=days, low=low, expired=expired, imminent=imminent, checks=checks,
                           until=date.today() + timedelta(days=days))


@bp.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.svg"))
