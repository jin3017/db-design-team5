-- =========================================================
-- 02_seed.sql : 개발·시연용 테스트 데이터
-- 01_schema.sql 실행 후 실행하세요. (01을 다시 실행하면 DB가 초기화됨)
--
-- 테스트 계정 (실제 운영에서는 반드시 변경)
--   점주  owner  / owner1234
--   직원  staff1 / staff1234
--   직원  staff2 / staff1234  (비활성 — 로그인 거부 확인용)
--
-- 소비기한은 CURDATE() 기준 상대값이라 언제 실행해도
-- 임박·경과·여유 LOT가 골고루 생긴다.
-- 상품·업체명은 시연용 가상 이름이다.
-- =========================================================
USE team5_db;

-- 직원 (비밀번호는 werkzeug scrypt 해시)
INSERT INTO EMPLOYEE (emp_id, login_id, password_hash, emp_name, phone, role, status) VALUES
 (1, 'owner',  'scrypt:32768:8:1$SaEarPr6QD0PxSdy$15675aae73e9b956c4f137389ac586e6918732d06b19dbde899910c6223bab3bdea5804bbf6e0021d5841171560261ed0b89a65b93e0036373bf5f7ba947a05f', '김점주', '010-0000-0001', 'OWNER', 'ACTIVE'),
 (2, 'staff1', 'scrypt:32768:8:1$zSMOMWVeHx3cZTGL$2f5bab32b6a1b575020459879457635a9ce526d27fe8a2fdf3cf47b52d4f363f22bf4af283581f154325db6b21f5255aa991b6e160c1e30d5cbe8a5e5bc72904', '이직원', '010-0000-0002', 'STAFF', 'ACTIVE'),
 (3, 'staff2', 'scrypt:32768:8:1$zSMOMWVeHx3cZTGL$2f5bab32b6a1b575020459879457635a9ce526d27fe8a2fdf3cf47b52d4f363f22bf4af283581f154325db6b21f5255aa991b6e160c1e30d5cbe8a5e5bc72904', '박퇴사', NULL, 'STAFF', 'INACTIVE');

-- 시스템 설정 (FR-019)
INSERT INTO SYSTEM_SETTING (setting_key, setting_value, description, updated_by) VALUES
 ('EXPIRY_ALERT_DAYS',   '3',  '소비기한 임박 기준일 (일)', 1),
 ('AUTO_LOGOUT_MINUTES', '30', '자동 로그아웃 시간 (분)',   1);

-- 카테고리
INSERT INTO CATEGORY (category_id, category_name, is_active) VALUES
 (1, '음료', TRUE), (2, '과자', TRUE), (3, '도시락·간편식', TRUE),
 (4, '유제품', TRUE), (5, '생활용품', TRUE), (6, '계절상품', FALSE);

-- 상품 (안전재고는 낱개 기준)
INSERT INTO PRODUCT (product_id, product_name, barcode, category_id, purchase_price, sale_price,
                     safety_stock, sale_status, expiry_managed) VALUES
 (1,  '콜라 500ml',        '8800000000011', 1, 1200, 2000, 10, 'ON_SALE', TRUE),
 (2,  '생수 2L',           '8800000000028', 1,  600, 1200, 10, 'ON_SALE', TRUE),
 (3,  '새우맛 스낵',        '8800000000035', 2,  900, 1500,  5, 'ON_SALE', TRUE),
 (4,  '감자칩 오리지널',     '8800000000042', 2, 1100, 1800,  5, 'ON_SALE', TRUE),
 (5,  '참치마요 삼각김밥',   '8800000000059', 3,  700, 1300,  5, 'ON_SALE', TRUE),
 (6,  '제육 도시락',        '8800000000066', 3, 2800, 4500,  3, 'ON_SALE', TRUE),
 (7,  '흰우유 1L',          '8800000000073', 4, 1700, 2900,  4, 'ON_SALE', TRUE),
 (8,  '바나나맛 우유',       '8800000000080', 4,  900, 1700,  6, 'ON_SALE', TRUE),
 (9,  '물티슈 80매',        '8800000000097', 5,  900, 1500,  3, 'ON_SALE', FALSE),
 (10, '칫솔',              '8800000000103', 5, 1200, 2500,  2, 'ON_SALE', FALSE),
 (11, '단종 음료 (판매중지)', '8800000000110', 1, 1000, 1800,  0, 'STOPPED', TRUE);

-- 공급업체 (가상)
INSERT INTO SUPPLIER (supplier_id, supplier_name, phone, contact_name, trade_status) VALUES
 (1, '한빛음료유통', '02-000-1001', '최담당', 'ACTIVE'),
 (2, '새벽신선식품', '02-000-1002', '정담당', 'ACTIVE'),
 (3, '바른생활물류', '02-000-1003', NULL,    'ACTIVE'),
 (4, '구거래상사',   NULL,          NULL,    'STOPPED');

-- 공급상품 (업체별 담당 상품과 공급가격)
INSERT INTO SUPPLIER_PRODUCT (supplier_id, product_id, supply_price) VALUES
 (1, 1, 1200), (1, 2, 600), (1, 3, 900), (1, 4, 1100), (1, 11, 1000),
 (2, 5, 700), (2, 6, 2800), (2, 7, 1700), (2, 8, 900),
 (3, 9, 900), (3, 10, 1200),
 (4, 1, 1300);

-- ---------------------------------------------------------
-- 초기재고 (입고유형 INITIAL): 입고 → 입고상세 → LOT → 입고 이력
-- 입고상세 1줄 = LOT 1개, 번호를 맞춰 둠
-- ---------------------------------------------------------
INSERT INTO RECEIPT (receipt_id, receipt_type, po_id, supplier_id, received_by, received_at) VALUES
 (1, 'INITIAL', NULL, NULL, 1, NOW() - INTERVAL 5 DAY);

INSERT INTO RECEIPT_DETAIL (receipt_detail_id, receipt_id, po_detail_id, product_id,
                            received_qty, damaged_qty, normal_qty, expiry_date, memo) VALUES
 (1,  1, NULL, 1,  24, 0, 24, CURDATE() + INTERVAL 180 DAY, NULL),
 (2,  1, NULL, 2,  12, 0, 12, CURDATE() + INTERVAL 300 DAY, NULL),
 (3,  1, NULL, 3,   4, 0,  4, CURDATE() + INTERVAL 90 DAY,  NULL),  -- 부족 (4 ≤ 5)
 (4,  1, NULL, 4,  15, 0, 15, CURDATE() + INTERVAL 120 DAY, NULL),
 (5,  1, NULL, 5,   6, 0,  6, CURDATE() + INTERVAL 1 DAY,   NULL),  -- 임박
 (6,  1, NULL, 5,   3, 0,  3, CURDATE() - INTERVAL 1 DAY,   NULL),  -- 경과 (판매 불가)
 (7,  1, NULL, 6,   2, 0,  2, CURDATE() + INTERVAL 2 DAY,   NULL),  -- 임박 + 부족
 (8,  1, NULL, 7,   8, 0,  8, CURDATE() + INTERVAL 5 DAY,   NULL),
 (9,  1, NULL, 8,  10, 0, 10, CURDATE() + INTERVAL 3 DAY,   NULL),  -- 임박 (기준일 경계)
 (10, 1, NULL, 9,  20, 0, 20, NULL, '소비기한 미관리 상품'),
 (11, 1, NULL, 10,  1, 0,  1, NULL, '소비기한 미관리 상품');        -- 부족

INSERT INTO STOCK_LOT (lot_id, product_id, receipt_detail_id, received_date, expiry_date,
                       received_qty, remain_qty, is_disposed)
SELECT rd.receipt_detail_id, rd.product_id, rd.receipt_detail_id, DATE(r.received_at), rd.expiry_date,
       rd.normal_qty, rd.normal_qty, FALSE
FROM RECEIPT_DETAIL rd JOIN RECEIPT r ON r.receipt_id = rd.receipt_id
WHERE rd.receipt_id = 1;

INSERT INTO STOCK_MOVEMENT (lot_id, product_id, movement_type, qty_change, remain_after,
                            moved_by, moved_at, reason, receipt_detail_id)
SELECT l.lot_id, l.product_id, 'IN', l.received_qty, l.remain_qty, 1, NOW() - INTERVAL 5 DAY, NULL,
       l.receipt_detail_id
FROM STOCK_LOT l WHERE l.receipt_detail_id BETWEEN 1 AND 11;

-- ---------------------------------------------------------
-- 발주 시연용: 승인된 발주 1건 (입고 대기), 작성 상태 1건 (승인 대기)
-- ---------------------------------------------------------
INSERT INTO PURCHASE_ORDER (po_id, supplier_id, created_by, approved_by, po_date, status,
                            total_amount, approved_at) VALUES
 (1, 2, 1, 1,    CURDATE() - INTERVAL 1 DAY, 'APPROVED', 42000, NOW() - INTERVAL 1 DAY),
 (2, 1, 1, NULL, CURDATE(),                  'DRAFT',     9000, NULL);

INSERT INTO PO_DETAIL (po_detail_id, po_id, product_id, order_qty, supply_price, amount, received_qty) VALUES
 (1, 1, 6, 10, 2800, 28000, 0),
 (2, 1, 5, 20,  700, 14000, 0),
 (3, 2, 3, 10,  900,  9000, 0);
