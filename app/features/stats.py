"""매출·판매 통계 (UC-13, FR-015). 통계 테이블 없이 판매·판매상세에서 집계 (DP-06). 점주 전용."""
from datetime import date, timedelta

from flask import Blueprint, flash, render_template, request

from ..core.auth import owner_required
from ..core.db import query
from ..core.web import stock_summary, to_date

bp = Blueprint("stats", __name__)
MENU = [(80, "통계", "stats.stats", True, "chart", ("stats.",))]


@bp.route("/stats")
@owner_required
def stats():
    unit = "month" if request.args.get("unit") == "month" else "day"
    today = date.today()
    default_from = today.replace(day=1) if unit == "day" else today.replace(month=1, day=1)
    d_from = to_date(request.args.get("from")) or default_from
    d_to = to_date(request.args.get("to")) or today
    if d_from > d_to:
        flash("시작일이 종료일보다 늦습니다.", "error")  # UC-13 A1
        d_from, d_to = d_to, d_from
    fmt = "%%Y-%%m-%%d" if unit == "day" else "%%Y-%%m"  # 파라미터와 함께 쓰므로 % 이스케이프
    rng = (d_from, d_to + timedelta(days=1))
    periods = query(f"SELECT DATE_FORMAT(s.sold_at, '{fmt}') AS period, COUNT(DISTINCT s.sale_id) AS sale_count, "
                    "SUM(d.amount) AS revenue, SUM(d.sale_qty) AS qty FROM SALE s "
                    "JOIN SALE_DETAIL d ON d.sale_id = s.sale_id WHERE s.sold_at >= %s AND s.sold_at < %s "
                    "GROUP BY period ORDER BY period", rng)
    top = query("SELECT p.product_name, SUM(d.sale_qty) AS qty, SUM(d.amount) AS revenue FROM SALE s "
                "JOIN SALE_DETAIL d ON d.sale_id = s.sale_id JOIN PRODUCT p ON p.product_id = d.product_id "
                "WHERE s.sold_at >= %s AND s.sold_at < %s GROUP BY p.product_id, p.product_name "
                "ORDER BY qty DESC, revenue DESC LIMIT 10", rng)
    max_rev = max((int(r["revenue"]) for r in periods), default=0) or 1
    total = sum(int(r["revenue"]) for r in periods)
    total_qty = sum(int(r["qty"]) for r in periods)
    stock = stock_summary("WHERE p.sale_status = 'ON_SALE'")  # 재고 현황 함께 표시 (UC-13 5)
    return render_template("stats/stats.html", periods=periods, top=top, max_rev=max_rev, total=total, total_qty=total_qty,
                           unit=unit, d_from=d_from, d_to=d_to, stock=stock)
