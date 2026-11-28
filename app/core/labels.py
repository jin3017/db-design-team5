"""코드값 → 화면 표시명 (스키마설계서 5.4 코드 도메인)."""
LABELS = {
    "OWNER": "점주", "STAFF": "직원",
    "ACTIVE": "활성/거래중", "INACTIVE": "비활성",
    "ON_SALE": "판매중", "STOPPED": "중지",
    "DRAFT": "작성", "APPROVED": "승인", "PARTIAL": "부분입고", "DONE": "완료", "CANCELED": "취소",
    "PO": "발주입고", "DIRECT": "직접입고", "INITIAL": "초기재고",
    "DAMAGED": "파손", "LOST": "분실", "MISINPUT": "오입력", "COUNT": "실사", "ETC": "기타",
    "LOT": "LOT별", "TOTAL": "합계",
    "EXPIRED": "소비기한 경과", "SPOILED": "변질·파손",
    "IN": "입고", "SALE": "판매", "DISPOSE": "폐기", "RETURN": "반품", "ADJUST": "조정",
    "DEFECT": "불량", "WRONG": "오배송",
    "REQUESTED": "요청", "REJECTED": "반려",
}

ADJUST_REASONS = ["DAMAGED", "LOST", "MISINPUT", "COUNT", "ETC"]
DISPOSAL_REASONS = ["EXPIRED", "SPOILED", "ETC"]
RETURN_REASONS = ["DEFECT", "WRONG"]
MOVEMENT_TYPES = ["IN", "SALE", "DISPOSE", "RETURN", "ADJUST"]
