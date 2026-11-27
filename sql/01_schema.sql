-- =========================================================
-- 01_schema.sql : 편의점 발주·재고·판매 관리 시스템 스키마
-- 기준 문서: docs/편의점_발주재고판매관리시스템_스키마설계서_v3.docx
-- DBMS     : MySQL 8.0.16 이상 (CHECK 제약 적용 버전)
-- 실행 순서: 01_schema -> 02_seed -> 03_views
--
-- 구성: 테이블 17 / PK 17 / UK 11 / FK 41 / CHECK 49
-- 외래키 동작: ON DELETE / ON UPDATE 모두 RESTRICT (설계서 5.2)
-- VARCHAR 길이는 설계서에서 물리 설계로 미룬 항목이라 임의로 정함
--   코드값 20 / 이름·아이디 50 / 상품·업체명 100 / 메모·사유 255
-- DB로 보장하지 못하는 규칙 R01~R28 은 애플리케이션에서 처리 (설계서 5.5)
-- =========================================================

DROP DATABASE IF EXISTS team5_db;
CREATE DATABASE team5_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
USE team5_db;

-- =========================================================
-- 1. 기준정보
-- =========================================================

-- 직원 (E-01)
CREATE TABLE EMPLOYEE (
  emp_id            INT          NOT NULL AUTO_INCREMENT,
  login_id          VARCHAR(50)  NOT NULL,
  password_hash     VARCHAR(255) NOT NULL,                 -- 단방향 해시 (SEC-003)
  emp_name          VARCHAR(50)  NOT NULL,
  phone             VARCHAR(20)  NULL,
  role              VARCHAR(20)  NOT NULL,                 -- OWNER/STAFF
  status            VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',-- ACTIVE/INACTIVE
  login_fail_count  INT          NOT NULL DEFAULT 0,
  unlock_at         DATETIME     NULL,
  created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_by        INT          NULL,
  updated_at        DATETIME     NULL,
  last_login_at     DATETIME     NULL,
  CONSTRAINT pk_employee PRIMARY KEY (emp_id),
  CONSTRAINT uk_employee_login_id UNIQUE (login_id),
  CONSTRAINT fk_employee_updated_by FOREIGN KEY (updated_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_employee_role   CHECK (role IN ('OWNER', 'STAFF')),
  CONSTRAINT ck_employee_status CHECK (status IN ('ACTIVE', 'INACTIVE')),
  CONSTRAINT ck_employee_fail   CHECK (login_fail_count >= 0)
) ENGINE=InnoDB;

-- 시스템설정 (E-05)
CREATE TABLE SYSTEM_SETTING (
  setting_key    VARCHAR(50)  NOT NULL,
  setting_value  VARCHAR(255) NOT NULL,
  description    VARCHAR(255) NOT NULL,
  updated_by     INT          NULL,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT pk_system_setting PRIMARY KEY (setting_key),
  CONSTRAINT fk_system_setting_updated_by FOREIGN KEY (updated_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB;

-- 카테고리 (E-02)
CREATE TABLE CATEGORY (
  category_id    INT         NOT NULL AUTO_INCREMENT,
  category_name  VARCHAR(50) NOT NULL,
  is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
  CONSTRAINT pk_category PRIMARY KEY (category_id),
  CONSTRAINT uk_category_category_name UNIQUE (category_name)
) ENGINE=InnoDB;

-- 상품 (E-03)
CREATE TABLE PRODUCT (
  product_id      INT          NOT NULL AUTO_INCREMENT,
  product_name    VARCHAR(100) NOT NULL,
  barcode         VARCHAR(50)  NOT NULL,
  category_id     INT          NOT NULL,
  purchase_price  INT          NOT NULL,                   -- 원
  sale_price      INT          NOT NULL,                   -- 원
  safety_stock    INT          NOT NULL,                   -- 낱개
  sale_status     VARCHAR(20)  NOT NULL DEFAULT 'ON_SALE', -- ON_SALE/STOPPED
  expiry_managed  BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT pk_product PRIMARY KEY (product_id),
  CONSTRAINT uk_product_barcode UNIQUE (barcode),
  CONSTRAINT fk_product_category_id FOREIGN KEY (category_id)
    REFERENCES CATEGORY (category_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_product_price  CHECK (purchase_price >= 0 AND sale_price >= 0),
  CONSTRAINT ck_product_safety CHECK (safety_stock >= 0),
  CONSTRAINT ck_product_status CHECK (sale_status IN ('ON_SALE', 'STOPPED'))
) ENGINE=InnoDB;

-- 공급업체 (E-04)
CREATE TABLE SUPPLIER (
  supplier_id    INT          NOT NULL AUTO_INCREMENT,
  supplier_name  VARCHAR(100) NOT NULL,
  phone          VARCHAR(20)  NULL,
  contact_name   VARCHAR(50)  NULL,
  trade_status   VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE/STOPPED
  CONSTRAINT pk_supplier PRIMARY KEY (supplier_id),
  CONSTRAINT uk_supplier_supplier_name UNIQUE (supplier_name),
  CONSTRAINT ck_supplier_status CHECK (trade_status IN ('ACTIVE', 'STOPPED'))
) ENGINE=InnoDB;

-- 공급상품 (R-02, N:M 연관 테이블)
CREATE TABLE SUPPLIER_PRODUCT (
  supplier_id   INT NOT NULL,
  product_id    INT NOT NULL,
  supply_price  INT NOT NULL,                              -- 원
  CONSTRAINT pk_supplier_product PRIMARY KEY (supplier_id, product_id),
  CONSTRAINT fk_supplier_product_supplier_id FOREIGN KEY (supplier_id)
    REFERENCES SUPPLIER (supplier_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_supplier_product_product_id FOREIGN KEY (product_id)
    REFERENCES PRODUCT (product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_supplier_product_price CHECK (supply_price >= 0)
) ENGINE=InnoDB;

-- =========================================================
-- 2. 발주·입고
-- =========================================================

-- 발주 (E-06)
CREATE TABLE PURCHASE_ORDER (
  po_id          INT          NOT NULL AUTO_INCREMENT,
  supplier_id    INT          NOT NULL,
  created_by     INT          NOT NULL,
  approved_by    INT          NULL,
  canceled_by    INT          NULL,
  po_date        DATE         NOT NULL,
  status         VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',    -- DRAFT/APPROVED/PARTIAL/DONE/CANCELED
  total_amount   INT          NOT NULL DEFAULT 0,          -- 발주상세 금액 합 (저장)
  approved_at    DATETIME     NULL,
  canceled_at    DATETIME     NULL,
  cancel_reason  VARCHAR(255) NULL,
  CONSTRAINT pk_purchase_order PRIMARY KEY (po_id),
  CONSTRAINT fk_purchase_order_supplier_id FOREIGN KEY (supplier_id)
    REFERENCES SUPPLIER (supplier_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_purchase_order_created_by FOREIGN KEY (created_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_purchase_order_approved_by FOREIGN KEY (approved_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_purchase_order_canceled_by FOREIGN KEY (canceled_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_po_status CHECK (status IN ('DRAFT', 'APPROVED', 'PARTIAL', 'DONE', 'CANCELED')),
  CONSTRAINT ck_po_amount CHECK (total_amount >= 0),
  CONSTRAINT ck_po_draft CHECK (
    status <> 'DRAFT' OR (approved_by IS NULL AND approved_at IS NULL)),
  CONSTRAINT ck_po_approved CHECK (
    status NOT IN ('APPROVED', 'PARTIAL', 'DONE')
    OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  CONSTRAINT ck_po_canceled CHECK (
    (status = 'CANCELED') =
    (canceled_by IS NOT NULL AND canceled_at IS NOT NULL AND cancel_reason IS NOT NULL))
) ENGINE=InnoDB;

-- 발주상세 (E-07)
CREATE TABLE PO_DETAIL (
  po_detail_id  INT NOT NULL AUTO_INCREMENT,
  po_id         INT NOT NULL,
  product_id    INT NOT NULL,
  order_qty     INT NOT NULL,                              -- 낱개
  supply_price  INT NOT NULL,                              -- 발주 시점 공급가격
  amount        INT NOT NULL,                              -- supply_price * order_qty (저장)
  received_qty  INT NOT NULL DEFAULT 0,                    -- 누적입고수량, 파손 포함 (저장)
  CONSTRAINT pk_po_detail PRIMARY KEY (po_detail_id),
  CONSTRAINT uk_po_detail_po_id_product_id UNIQUE (po_id, product_id),
  CONSTRAINT fk_po_detail_po_id FOREIGN KEY (po_id)
    REFERENCES PURCHASE_ORDER (po_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_po_detail_product_id FOREIGN KEY (product_id)
    REFERENCES PRODUCT (product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_po_detail_qty      CHECK (order_qty >= 1),
  CONSTRAINT ck_po_detail_price    CHECK (supply_price >= 0),
  CONSTRAINT ck_po_detail_amount   CHECK (amount = supply_price * order_qty),
  CONSTRAINT ck_po_detail_received CHECK (received_qty >= 0 AND received_qty <= order_qty)
) ENGINE=InnoDB;

-- 입고 (E-08)
CREATE TABLE RECEIPT (
  receipt_id    INT         NOT NULL AUTO_INCREMENT,
  receipt_type  VARCHAR(20) NOT NULL DEFAULT 'PO',         -- PO/DIRECT/INITIAL
  po_id         INT         NULL,                          -- 발주입고일 때만
  supplier_id   INT         NULL,                          -- 직접입고일 때만
  received_by   INT         NOT NULL,
  received_at   DATETIME    NOT NULL,
  CONSTRAINT pk_receipt PRIMARY KEY (receipt_id),
  CONSTRAINT fk_receipt_po_id FOREIGN KEY (po_id)
    REFERENCES PURCHASE_ORDER (po_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_receipt_supplier_id FOREIGN KEY (supplier_id)
    REFERENCES SUPPLIER (supplier_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_receipt_received_by FOREIGN KEY (received_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_receipt_type     CHECK (receipt_type IN ('PO', 'DIRECT', 'INITIAL')),
  CONSTRAINT ck_receipt_po       CHECK ((receipt_type = 'PO') = (po_id IS NOT NULL)),
  CONSTRAINT ck_receipt_supplier CHECK (receipt_type = 'DIRECT' OR supplier_id IS NULL)
) ENGINE=InnoDB;

-- 입고상세 (E-09)
CREATE TABLE RECEIPT_DETAIL (
  receipt_detail_id  INT          NOT NULL AUTO_INCREMENT,
  receipt_id         INT          NOT NULL,
  po_detail_id       INT          NULL,                    -- 발주입고일 때만
  product_id         INT          NOT NULL,                -- 발주입고는 발주상세에서 복사
  received_qty       INT          NOT NULL,                -- 파손 포함
  damaged_qty        INT          NOT NULL DEFAULT 0,
  normal_qty         INT          NOT NULL,                -- received - damaged (저장)
  expiry_date        DATE         NULL,
  memo               VARCHAR(255) NULL,
  CONSTRAINT pk_receipt_detail PRIMARY KEY (receipt_detail_id),
  CONSTRAINT fk_receipt_detail_receipt_id FOREIGN KEY (receipt_id)
    REFERENCES RECEIPT (receipt_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_receipt_detail_po_detail_id FOREIGN KEY (po_detail_id)
    REFERENCES PO_DETAIL (po_detail_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_receipt_detail_product_id FOREIGN KEY (product_id)
    REFERENCES PRODUCT (product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_receipt_detail_qty CHECK (
    received_qty >= 0 AND damaged_qty >= 0 AND damaged_qty <= received_qty),
  CONSTRAINT ck_receipt_detail_normal CHECK (normal_qty = received_qty - damaged_qty)
) ENGINE=InnoDB;

-- =========================================================
-- 3. 재고
-- =========================================================

-- 재고LOT (E-10)
CREATE TABLE STOCK_LOT (
  lot_id             INT     NOT NULL AUTO_INCREMENT,
  product_id         INT     NOT NULL,                     -- 입고상세에서 복사
  receipt_detail_id  INT     NOT NULL,
  received_date      DATE    NOT NULL,                     -- 복사값
  expiry_date        DATE    NULL,                         -- 소비기한 미관리 상품은 NULL
  received_qty       INT     NOT NULL,                     -- 정상수량 복사
  remain_qty         INT     NOT NULL,
  is_disposed        BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT pk_stock_lot PRIMARY KEY (lot_id),
  CONSTRAINT uk_stock_lot_receipt_detail_id UNIQUE (receipt_detail_id),
  CONSTRAINT fk_stock_lot_product_id FOREIGN KEY (product_id)
    REFERENCES PRODUCT (product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_lot_receipt_detail_id FOREIGN KEY (receipt_detail_id)
    REFERENCES RECEIPT_DETAIL (receipt_detail_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_lot_received CHECK (received_qty >= 1),
  CONSTRAINT ck_lot_remain   CHECK (remain_qty >= 0),
  CONSTRAINT ck_lot_disposed CHECK (is_disposed = FALSE OR remain_qty = 0)
) ENGINE=InnoDB;

-- 재고조정 (E-11)
CREATE TABLE STOCK_ADJUSTMENT (
  adjust_id      INT          NOT NULL AUTO_INCREMENT,
  lot_id         INT          NOT NULL,
  before_qty     INT          NOT NULL,
  after_qty      INT          NOT NULL,
  adjust_qty     INT          NOT NULL,                    -- after - before (저장)
  reason_type    VARCHAR(20)  NOT NULL,                    -- DAMAGED/LOST/MISINPUT/COUNT/ETC
  reason_detail  VARCHAR(255) NULL,
  input_method   VARCHAR(20)  NOT NULL DEFAULT 'LOT',      -- LOT/TOTAL
  adjusted_by    INT          NOT NULL,
  adjusted_at    DATETIME     NOT NULL,
  CONSTRAINT pk_stock_adjustment PRIMARY KEY (adjust_id),
  CONSTRAINT fk_stock_adjustment_lot_id FOREIGN KEY (lot_id)
    REFERENCES STOCK_LOT (lot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_adjustment_adjusted_by FOREIGN KEY (adjusted_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_adjust_qty    CHECK (before_qty >= 0 AND after_qty >= 0),
  CONSTRAINT ck_adjust_diff   CHECK (adjust_qty = after_qty - before_qty),
  CONSTRAINT ck_adjust_reason CHECK (reason_type IN ('DAMAGED', 'LOST', 'MISINPUT', 'COUNT', 'ETC')),
  CONSTRAINT ck_adjust_etc    CHECK (reason_type <> 'ETC' OR reason_detail IS NOT NULL),
  CONSTRAINT ck_adjust_method CHECK (input_method IN ('LOT', 'TOTAL'))
) ENGINE=InnoDB;

-- 폐기 (E-12)
CREATE TABLE DISPOSAL (
  disposal_id    INT          NOT NULL AUTO_INCREMENT,
  lot_id         INT          NOT NULL,
  disposal_qty   INT          NOT NULL,
  reason_type    VARCHAR(20)  NOT NULL,                    -- EXPIRED/SPOILED/ETC
  reason_detail  VARCHAR(255) NULL,
  disposed_by    INT          NOT NULL,
  disposed_at    DATETIME     NOT NULL,
  CONSTRAINT pk_disposal PRIMARY KEY (disposal_id),
  CONSTRAINT fk_disposal_lot_id FOREIGN KEY (lot_id)
    REFERENCES STOCK_LOT (lot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_disposal_disposed_by FOREIGN KEY (disposed_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_disposal_qty    CHECK (disposal_qty >= 1),
  CONSTRAINT ck_disposal_reason CHECK (reason_type IN ('EXPIRED', 'SPOILED', 'ETC')),
  CONSTRAINT ck_disposal_etc    CHECK (reason_type <> 'ETC' OR reason_detail IS NOT NULL)
) ENGINE=InnoDB;

-- =========================================================
-- 4. 판매
-- =========================================================

-- 판매 (E-14)
CREATE TABLE SALE (
  sale_id       INT      NOT NULL AUTO_INCREMENT,
  sold_by       INT      NOT NULL,
  sold_at       DATETIME NOT NULL,
  total_amount  INT      NOT NULL,                         -- 판매상세 금액 합 (저장)
  CONSTRAINT pk_sale PRIMARY KEY (sale_id),
  CONSTRAINT fk_sale_sold_by FOREIGN KEY (sold_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_sale_amount CHECK (total_amount >= 0)
) ENGINE=InnoDB;

-- 판매상세 (E-15)
CREATE TABLE SALE_DETAIL (
  sale_detail_id  INT NOT NULL AUTO_INCREMENT,
  sale_id         INT NOT NULL,
  product_id      INT NOT NULL,
  sale_qty        INT NOT NULL,                            -- 낱개
  unit_price      INT NOT NULL,                            -- 판매 시점 단가
  amount          INT NOT NULL,                            -- unit_price * sale_qty (저장)
  CONSTRAINT pk_sale_detail PRIMARY KEY (sale_detail_id),
  CONSTRAINT uk_sale_detail_sale_id_product_id UNIQUE (sale_id, product_id),
  CONSTRAINT fk_sale_detail_sale_id FOREIGN KEY (sale_id)
    REFERENCES SALE (sale_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_sale_detail_product_id FOREIGN KEY (product_id)
    REFERENCES PRODUCT (product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_sale_detail_qty    CHECK (sale_qty >= 1),
  CONSTRAINT ck_sale_detail_price  CHECK (unit_price >= 0),
  CONSTRAINT ck_sale_detail_amount CHECK (amount = unit_price * sale_qty)
) ENGINE=InnoDB;

-- =========================================================
-- 5. 반품
-- =========================================================

-- 반품 (E-16)
CREATE TABLE RETURN_ORDER (
  return_id      INT          NOT NULL AUTO_INCREMENT,
  supplier_id    INT          NOT NULL,
  product_id     INT          NOT NULL,                    -- LOT 지정 시 LOT에서 복사
  lot_id         INT          NULL,                        -- 재고에 있는 상품이면 필수 (R17)
  po_id          INT          NULL,
  return_qty     INT          NOT NULL,
  reason_type    VARCHAR(20)  NOT NULL,                    -- DEFECT/WRONG
  status         VARCHAR(20)  NOT NULL DEFAULT 'REQUESTED',-- REQUESTED/APPROVED/REJECTED/DONE/CANCELED
  requested_by   INT          NOT NULL,
  decided_by     INT          NULL,
  requested_at   DATETIME     NOT NULL,
  decided_at     DATETIME     NULL,
  completed_at   DATETIME     NULL,
  reject_reason  VARCHAR(255) NULL,
  canceled_by    INT          NULL,
  canceled_at    DATETIME     NULL,
  CONSTRAINT pk_return_order PRIMARY KEY (return_id),
  CONSTRAINT fk_return_order_supplier_id FOREIGN KEY (supplier_id)
    REFERENCES SUPPLIER (supplier_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_return_order_product_id FOREIGN KEY (product_id)
    REFERENCES PRODUCT (product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_return_order_lot_id FOREIGN KEY (lot_id)
    REFERENCES STOCK_LOT (lot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_return_order_po_id FOREIGN KEY (po_id)
    REFERENCES PURCHASE_ORDER (po_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_return_order_requested_by FOREIGN KEY (requested_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_return_order_decided_by FOREIGN KEY (decided_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_return_order_canceled_by FOREIGN KEY (canceled_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_return_qty    CHECK (return_qty >= 1),
  CONSTRAINT ck_return_reason CHECK (reason_type IN ('DEFECT', 'WRONG')),
  CONSTRAINT ck_return_status CHECK (
    status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'DONE', 'CANCELED')),
  CONSTRAINT ck_return_decided CHECK (
    (status IN ('REQUESTED', 'CANCELED')) = (decided_by IS NULL AND decided_at IS NULL)),
  CONSTRAINT ck_return_canceled CHECK (
    (status = 'CANCELED') = (canceled_by IS NOT NULL AND canceled_at IS NOT NULL)),
  CONSTRAINT ck_return_reject CHECK ((status = 'REJECTED') = (reject_reason IS NOT NULL)),
  CONSTRAINT ck_return_done   CHECK ((status = 'DONE') = (completed_at IS NOT NULL))
) ENGINE=InnoDB;

-- =========================================================
-- 6. 재고변동이력 (E-13) — 원천 테이블이 모두 생성된 뒤 마지막에 생성
--    추가만 허용, 수정·삭제 금지 (R11)
-- =========================================================
CREATE TABLE STOCK_MOVEMENT (
  movement_id        BIGINT       NOT NULL AUTO_INCREMENT,
  lot_id             INT          NOT NULL,
  product_id         INT          NOT NULL,                -- 반정규화, LOT에서 복사
  movement_type      VARCHAR(20)  NOT NULL,                -- IN/SALE/DISPOSE/RETURN/ADJUST
  qty_change         INT          NOT NULL,                -- ±
  remain_after       INT          NOT NULL,
  moved_by           INT          NOT NULL,
  moved_at           DATETIME     NOT NULL,
  reason             VARCHAR(255) NULL,
  receipt_detail_id  INT          NULL,                    -- 원천: 입고상세
  sale_detail_id     INT          NULL,                    -- 원천: 판매상세
  adjust_id          INT          NULL,                    -- 원천: 재고조정
  disposal_id        INT          NULL,                    -- 원천: 폐기
  return_id          INT          NULL,                    -- 원천: 반품
  CONSTRAINT pk_stock_movement PRIMARY KEY (movement_id),
  CONSTRAINT uk_stock_movement_receipt_detail_id UNIQUE (receipt_detail_id),
  CONSTRAINT uk_stock_movement_adjust_id         UNIQUE (adjust_id),
  CONSTRAINT uk_stock_movement_disposal_id       UNIQUE (disposal_id),
  CONSTRAINT uk_stock_movement_return_id         UNIQUE (return_id),
  CONSTRAINT fk_stock_movement_lot_id FOREIGN KEY (lot_id)
    REFERENCES STOCK_LOT (lot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_movement_product_id FOREIGN KEY (product_id)
    REFERENCES PRODUCT (product_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_movement_moved_by FOREIGN KEY (moved_by)
    REFERENCES EMPLOYEE (emp_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_movement_receipt_detail_id FOREIGN KEY (receipt_detail_id)
    REFERENCES RECEIPT_DETAIL (receipt_detail_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_movement_sale_detail_id FOREIGN KEY (sale_detail_id)
    REFERENCES SALE_DETAIL (sale_detail_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_movement_adjust_id FOREIGN KEY (adjust_id)
    REFERENCES STOCK_ADJUSTMENT (adjust_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_movement_disposal_id FOREIGN KEY (disposal_id)
    REFERENCES DISPOSAL (disposal_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT fk_stock_movement_return_id FOREIGN KEY (return_id)
    REFERENCES RETURN_ORDER (return_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
  CONSTRAINT ck_movement_type CHECK (
    movement_type IN ('IN', 'SALE', 'DISPOSE', 'RETURN', 'ADJUST')),
  CONSTRAINT ck_movement_remain CHECK (remain_after >= 0),
  CONSTRAINT ck_movement_sign CHECK (
       (movement_type = 'IN' AND qty_change > 0)
    OR (movement_type IN ('SALE', 'DISPOSE', 'RETURN') AND qty_change < 0)
    OR (movement_type = 'ADJUST' AND qty_change <> 0)),
  CONSTRAINT ck_movement_one_source CHECK (
      (receipt_detail_id IS NOT NULL) + (sale_detail_id IS NOT NULL)
    + (adjust_id IS NOT NULL) + (disposal_id IS NOT NULL)
    + (return_id IS NOT NULL) = 1),
  CONSTRAINT ck_movement_source_type CHECK (
        ((movement_type = 'IN')      = (receipt_detail_id IS NOT NULL))
    AND ((movement_type = 'SALE')    = (sale_detail_id IS NOT NULL))
    AND ((movement_type = 'ADJUST')  = (adjust_id IS NOT NULL))
    AND ((movement_type = 'DISPOSE') = (disposal_id IS NOT NULL))
    AND ((movement_type = 'RETURN')  = (return_id IS NOT NULL)))
) ENGINE=InnoDB;
