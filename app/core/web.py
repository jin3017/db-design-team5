"""화면 모듈 공용 도우미: 입력값 변환, 처리 결과 메시지, 재고 집계 쿼리."""
from datetime import date

import pymysql
from flask import flash, redirect

from .db import BizError, get_setting, query, transaction


def to_int(v, default=None):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def to_date(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def db_error_message(e):
    code = e.args[0] if e.args else None
    if code == 1062:
        return "이미 등록된 값입니다 (중복)."
    if code == 3819:
        return "입력값이 허용 범위를 벗어났습니다."
    if code in (1451, 1452):
        return "연결된 데이터 때문에 처리할 수 없습니다."
    return f"DB 오류: {e}"


def run_action(action, ok_msg, ok_url, err_url):
    """action(cur)를 트랜잭션으로 실행하고 결과에 따라 메시지 + 이동."""
    try:
        with transaction() as cur:
            result = action(cur)
    except BizError as e:
        flash(str(e), "error")
        return redirect(err_url)
    except pymysql.err.MySQLError as e:
        flash(db_error_message(e), "error")
        return redirect(err_url)
    flash(ok_msg(result) if callable(ok_msg) else ok_msg, "success")
    return redirect(ok_url(result) if callable(ok_url) else ok_url)


def alert_days():
    return int(get_setting("EXPIRY_ALERT_DAYS", 3))


# 상품별 현재고(폐기 안 된 LOT 합, BR-01) / 판매가능재고(경과 LOT 제외) / 가장 빠른 소비기한
STOCK_SUMMARY = """
SELECT p.product_id, p.product_name, p.barcode, p.safety_stock, p.sale_status, p.sale_price,
       p.category_id, c.category_name,
       COALESCE(SUM(CASE WHEN l.is_disposed = FALSE THEN l.remain_qty END), 0) AS current_qty,
       COALESCE(SUM(CASE WHEN l.is_disposed = FALSE AND (l.expiry_date IS NULL OR l.expiry_date >= CURDATE())
                         THEN l.remain_qty END), 0) AS sellable_qty,
       MIN(CASE WHEN l.is_disposed = FALSE AND l.remain_qty > 0 THEN l.expiry_date END) AS earliest_expiry
FROM PRODUCT p
JOIN CATEGORY c ON c.category_id = p.category_id
LEFT JOIN STOCK_LOT l ON l.product_id = p.product_id
{where}
GROUP BY p.product_id, c.category_name
{having}
ORDER BY p.product_name
"""


def stock_summary(where="", args=(), having=""):
    rows = query(STOCK_SUMMARY.format(where=where, having=having), args)
    days = alert_days()
    today = date.today()
    for r in rows:
        r["current_qty"] = int(r["current_qty"])
        r["sellable_qty"] = int(r["sellable_qty"])
        r["low"] = r["sale_status"] == "ON_SALE" and r["sellable_qty"] <= r["safety_stock"]  # R18
        e = r["earliest_expiry"]
        r["expired"] = bool(e and e < today)
        r["imminent"] = bool(e and 0 <= (e - today).days <= days)
    return rows
