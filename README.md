# db-design-team5
2026-2 데이터베이스설계 5조

- DBMS: MySQL 8
- 언어: Python 3.10+

## 폴더 구조
```
├─ docs/            설계서, ERD, 테이블 정의서
├─ sql/
│  ├─ 01_schema.sql   DB/테이블 생성 (DROP 후 재생성)
│  ├─ 02_seed.sql     테스트 데이터
│  ├─ 03_views.sql    뷰, 트리거, 프로시저
│  └─ queries/        기능별 쿼리
├─ app/             Python 코드
│  ├─ db.py           DB 연결 (get_connection)
│  └─ main.py         연결 확인용
├─ .env.example     접속 정보 템플릿
└─ requirements.txt
```

## 처음 세팅 (한 번만)
1. MySQL 8 설치 후 실행
2. repo clone (경로에 OneDrive/한글/공백 없는 곳 권장)
   ```
   git clone https://github.com/jin3017/db-design-team5.git
   cd db-design-team5
   ```
3. Python 가상환경 + 패키지 설치
   ```
   python -m venv .venv
   .venv\Scripts\activate        # Mac: source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. `.env.example` 를 복사해서 `.env` 로 만들고 본인 MySQL 비밀번호 입력
5. DB 생성 (순서대로)
   ```
   mysql -u root -p -e "source sql/01_schema.sql"
   mysql -u root -p -e "source sql/02_seed.sql"
   mysql -u root -p -e "source sql/03_views.sql"
   ```
   확인: `mysql -u root -p -e "SHOW TABLES FROM team5_db"` → 테이블 17개
   (MySQL Workbench나 VSCode 확장에서 파일 열고 실행해도 됨)
6. 연결 확인
   ```
   python app/main.py
   ```

## 협업 규칙
- `main` 에 직접 push 금지 → `feature/이름-작업내용` 브랜치에서 작업 후 PR
- 작업 시작 전 항상 `git pull origin main`
- **테이블 구조 바꾸면 단톡방에 공유** (다른 사람 쿼리 깨짐)
- 네이밍: 테이블은 대문자(`PURCHASE_ORDER`), 속성은 `snake_case`, PK는 `<대상>_id` (스키마설계서 1.3)
- **쿼리에서 테이블명은 항상 대문자로** — Windows MySQL은 소문자로 저장하지만 Mac/Linux는 대소문자를 구분함
- Python에서 값은 `%s` 파라미터로 넘기기 (문자열 직접 연결 금지)
- `.env`(비밀번호)는 절대 커밋하지 않기
- 스키마 바꾼 뒤에는 `01 → 02 → 03` 다시 실행해서 깨끗하게 돌아가는지 확인

## 역할 분담
| 이름 | 담당 |
|---|---|
|  |  |
