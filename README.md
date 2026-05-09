# 포켓몬스토어 재입고 이메일 알림 봇

5분마다 포켓몬스토어 카테고리 페이지를 체크해서 재입고되면 이메일로 알림을 보내는 자동화 봇입니다. GitHub Actions에서 무료로 24시간 동작합니다.


## 📋 전체 흐름

```
GitHub Actions (5분마다 자동 실행)
    ↓
Playwright로 3개 페이지 크롤링
    ↓
이전 상태(state.json)와 비교
    ↓
SOLD OUT → 재고 있음 으로 바뀐 상품 발견 시
    ↓
Gmail SMTP로 이메일 발송
    ↓
📧 내 메일함으로 알림 도착 (폰 메일 앱에서 푸시)
```

## 🚀 설치 가이드 (총 10~15분)

### 1단계: Gmail 앱 비밀번호 발급 (5분)

> Gmail 계정으로 보내고 받을 거예요. 일반 비밀번호는 SMTP에 못 쓰니까 "앱 비밀번호"를 따로 발급받아야 합니다.

1. **2단계 인증 켜기 (이미 켜져 있다면 스킵)**
   - https://myaccount.google.com/security 접속
   - "2단계 인증" 항목 → 켜기
2. **앱 비밀번호 생성**
   - https://myaccount.google.com/apppasswords 접속
   - 앱 이름: 아무거나 (예: `포켓몬봇`) → 만들기
   - **16자리 비밀번호**가 표시됨 → 메모장에 저장 ⭐ (한 번만 보여줌!)
   > 이 페이지가 안 보인다면 2단계 인증이 안 켜진 거예요. 1번부터 다시.

### 2단계: GitHub 레포지토리 만들기 (3분)

1. https://github.com 가입/로그인
2. **New repository** → 이름 아무거나 (예: `pokemon-monitor`) → **Public** 선택 → Create
   > ⚠️ Public이어야 GitHub Actions가 무제한 무료. Private은 월 2000분 제한.
3. 압축 풀어서 나온 모든 파일을 레포에 업로드 (드래그 앤 드롭 가능):
   - `check_stock.py`
   - `requirements.txt`
   - `state.json`
   - `.gitignore`
   - `.github/workflows/check.yml` (폴더 구조 그대로!)

### 3단계: GitHub Secrets 등록 + 실행 (3분)

1. 레포 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
2. 다음 항목들을 등록:

   | Name | Value | 필수 |
   |---|---|---|
   | `SMTP_USER` | 본인 Gmail 주소 (예: `myname@gmail.com`) | ✅ |
   | `SMTP_PASSWORD` | 1단계에서 발급받은 16자리 앱 비밀번호 | ✅ |
   | `TO_EMAIL` | 알림 받을 이메일 (Gmail이 아닌 다른 메일로 받고 싶을 때만) | 선택 |

3. 레포 → **Actions** 탭 → 워크플로우 활성화 (처음에는 비활성화 상태)
4. **포켓몬스토어 재고 감시** 워크플로우 클릭 → **Run workflow** 버튼으로 수동 실행해서 테스트
5. 30초~1분 후 로그 확인 → "✅ 완료" 메시지가 나오면 성공
   > 첫 실행에는 이메일이 안 옵니다 (이전 상태가 없어서). 두 번째 실행부터 변화 감지.

### 4단계: 폰에서 알림 받기 (1분)

- 폰의 Gmail 앱(또는 기본 메일 앱) 알림을 켜놓으세요
- 이메일이 오면 폰 푸시 알림으로 즉시 옴 → 카톡과 비슷한 체감

## ⚙️ 커스터마이징

| 변경하고 싶은 것 | 어디를 수정 |
|---|---|
| 감시 URL 추가/변경 | `check_stock.py` 상단 `URLS` 리스트 |
| 체크 주기 | `.github/workflows/check.yml`의 `cron: '*/5 * * * *'` (`5` → `10`이면 10분) |
| 알림 받을 메일 변경 | GitHub Secret `TO_EMAIL` 수정 |
| 이메일 디자인 변경 | `check_stock.py`의 `build_email_html` 함수 |

## 🔧 다른 메일 서비스 쓰고 싶으면

Gmail이 싫거나 안 되면 다른 SMTP도 됩니다. Secret에 추가:

| Secret | Naver | Daum | Outlook |
|---|---|---|---|
| `SMTP_HOST` | `smtp.naver.com` | `smtp.daum.net` | `smtp-mail.outlook.com` |
| `SMTP_PORT` | `465` | `465` | `587` |

> Naver는 메일 설정에서 SMTP/POP3 사용 활성화 필요.

## ❓ 트러블슈팅

| 증상 | 해결 |
|---|---|
| Actions가 60일 후 멈춤 | 레포가 60일 비활성 시 cron 자동 중지됨. 아무 커밋이나 한 번 push |
| `Authentication failed` | Gmail 앱 비밀번호가 틀렸거나, 일반 비밀번호를 넣은 경우. 16자리 앱 비밀번호 사용 |
| 이메일이 안 옴 | Actions 로그에서 `✅ 이메일 전송 완료` 확인. 없으면 재고 변동이 없었던 것 |
| 스팸함으로 감 | Gmail 메일함에서 "스팸 아님" 처리 한 번 해주면 다음부터 정상 |
| `상품을 못 찾음` 오류 | 사이트 구조 변경. 알려주시면 추출 로직 수정 |
