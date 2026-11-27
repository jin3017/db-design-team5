-- =========================================================
-- 01_schema.sql : 데이터베이스 및 테이블 생성
-- 실행 순서: 01_schema -> 02_seed -> 03_views
-- 여러 번 실행해도 같은 결과가 나오도록 DROP 후 CREATE 합니다.
-- =========================================================

DROP DATABASE IF EXISTS team5_db;
CREATE DATABASE team5_db
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
USE team5_db;

-- ---------------------------------------------------------
-- TODO: 설계서(ERD / 테이블 정의서) 기준으로 테이블 작성
-- 네이밍 규칙: snake_case, PK는 <테이블명>_id
-- FK 참조 순서대로(부모 테이블 먼저) 작성할 것
-- ---------------------------------------------------------

-- 예시 (실제 설계로 교체하세요)
-- CREATE TABLE member (
--   member_id   INT          NOT NULL AUTO_INCREMENT,
--   name        VARCHAR(50)  NOT NULL,
--   email       VARCHAR(100) NOT NULL UNIQUE,
--   created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
--   PRIMARY KEY (member_id)
-- ) ENGINE=InnoDB;
