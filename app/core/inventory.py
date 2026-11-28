"""재고 공통 처리: LOT 잠금, 판매 가능 재고, 재고변동이력 저장.
재고를 바꾸는 기능(입고·판매·조정·폐기·반품)은 모두 이 함수들을 같은
트랜잭션 안에서 호출해 재고 변경과 이력 저장을 묶는다 (R09, R10)."""
from .db import BizError

SOURCE_COL = {"IN": "receipt_detail_id", "SALE": "sale_detail_id", "ADJUST": "adjust_id",
              "DISPOSE": "disposal_id", "RETURN": "return_id"}

# 판매 가능 LOT: 폐기 안 됨, 잔여 > 0, 소비기한 미경과 (R04)
# FEFO 순서: 소비기한 빠른 순, 소비기한 없는 LOT은 입고일 순으로 뒤에 (R02, R05)
SELLABLE_LOTS = """
    SELECT lot_id, remain_qty FROM STOCK_LOT
    WHERE product_id = %s AND is_disposed = FALSE AND remain_qty > 0
      AND (expiry_date IS NULL OR expiry_date >= CURDATE())
    ORDER BY expiry_date IS NULL, expiry_date, received_date, lot_id
    FOR UPDATE"""


def add_movement(cur, lot_id, product_id, mtype, qty_change, remain_after, emp_id, source_id, reason=None):
    """재고변동이력 1건 추가. 원천 FK는 변동유형에 맞는 칸 하나만 채운다 (ck_movement_source_type)."""
    col = SOURCE_COL[mtype]
    cur.execute(
        f"INSERT INTO STOCK_MOVEMENT (lot_id, product_id, movement_type, qty_change, remain_after, "
        f"moved_by, moved_at, reason, {col}) VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,%s)",
        (lot_id, product_id, mtype, qty_change, remain_after, emp_id, reason, source_id))


def lock_lot(cur, lot_id):
    """LOT 행을 잠그고 반환. 폐기된 LOT은 조정·폐기·반품 대상이 아니다 (R20)."""
    cur.execute("SELECT * FROM STOCK_LOT WHERE lot_id = %s FOR UPDATE", (lot_id,))
    lot = cur.fetchone()
    if lot is None:
        raise BizError("존재하지 않는 LOT입니다.")
    if lot["is_disposed"]:
        raise BizError("이미 폐기된 LOT입니다.")
    return lot


def sellable_qty(cur, product_id):
    cur.execute("SELECT COALESCE(SUM(remain_qty), 0) AS q FROM STOCK_LOT WHERE product_id = %s "
                "AND is_disposed = FALSE AND (expiry_date IS NULL OR expiry_date >= CURDATE())", (product_id,))
    return int(cur.fetchone()["q"])
