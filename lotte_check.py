"""
롯데마트 모바일 도와센터 재고 감시 스크립트
- 5개 지점에서 키워드 매칭 상품의 재고 확인
- 품절 → 재고 있음으로 변하면 이메일 알림

DEBUG_MODE=1 환경변수 설정 시 단계별 스크린샷을 debug/ 폴더에 저장 (디버그용).
"""
import json
import os
import re
import smtplib
import sys
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# ====== 설정 ======
SEARCH_QUERY = "포켓몬 카드"

PRODUCT_KEYWORDS = [
    "테라스탈페스타",
    "닌자스피너",
    "니힐제로",
    "초전브레이커",
    "확장팩 151",
    "드림EX",
    "인페르노X",
]

STORES = [
    {"region": "경기", "name": "장암점"},
    {"region": "서울", "name": "중계점"},
    {"region": "서울", "name": "토이저러스중계점"},
    {"region": "서울", "name": "강변점"},
    {"region": "서울", "name": "청량리점"},
]

LOTTE_URL = "https://company.lottemart.com/mobiledowa/product/search_product.asp"
# ==================

STATE_FILE = Path("lotte_state.json")
DEBUG_DIR = Path("debug")
DEBUG_MODE = os.environ.get("DEBUG_MODE", "0") == "1"


def store_key(store: dict) -> str:
    return f"{store['region']}_{store['name']}"


def normalize(s: str) -> str:
    """공백 제거 + 소문자 변환 (매칭 robust 하게)"""
    return re.sub(r"\s+", "", s).lower()


def take_screenshot(page: Page, name: str) -> None:
    if DEBUG_MODE:
        DEBUG_DIR.mkdir(exist_ok=True)
        path = DEBUG_DIR / f"{name}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            print(f"    📸 {path}")
        except Exception as e:
            print(f"    ⚠️ 스크린샷 실패: {e}")


def select_store(page: Page, store: dict) -> bool:
    """지역 + 매장 선택"""
    sk = store_key(store)
    try:
        # 매장선택 드롭다운 열기
        page.click("text=매장선택", timeout=10000)
        page.wait_for_timeout(700)
        take_screenshot(page, f"01_dropdown_{sk}")

        # 지역 선택 (서울/경기)
        page.click(f'text="{store["region"]}"', timeout=5000)
        page.wait_for_timeout(700)
        take_screenshot(page, f"02_region_{sk}")

        # 매장 선택 (정확한 매칭)
        page.click(f'text="{store["name"]}"', timeout=5000)
        page.wait_for_timeout(1500)
        take_screenshot(page, f"03_store_{sk}")
        return True
    except Exception as e:
        print(f"  ❌ 매장 선택 실패 [{sk}]: {e}")
        take_screenshot(page, f"FAIL_select_{sk}")
        return False


def perform_search(page: Page, query: str) -> bool:
    """검색어 입력 + 검색 실행"""
    try:
        search_input = page.locator(
            'input[type="search"], input[type="text"]'
        ).first
        search_input.fill(query)
        page.wait_for_timeout(300)
        search_input.press("Enter")
        page.wait_for_timeout(2500)
        take_screenshot(page, "04_search_results")
        return True
    except Exception as e:
        print(f"  ❌ 검색 실패: {e}")
        take_screenshot(page, "FAIL_search")
        return False


def get_matching_products(page: Page) -> list[dict]:
    """검색 결과 중 키워드와 매칭되는 상품 목록 반환"""
    return page.evaluate(
        """
        (keywords) => {
            const normalize = s => s.replace(/\\s+/g, '').toLowerCase();
            const candidates = document.querySelectorAll(
                'li, .product-item, .item, [class*="product"], a'
            );
            const seen = new Set();
            const matches = [];
            candidates.forEach(el => {
                const text = (el.innerText || '').trim();
                if (!text) return;
                const firstLine = text.split('\\n')[0].trim();
                if (!firstLine || firstLine.length < 3 || seen.has(firstLine)) return;

                const nName = normalize(firstLine);
                for (const kw of keywords) {
                    if (nName.includes(normalize(kw))) {
                        seen.add(firstLine);
                        matches.push({ name: firstLine, keyword: kw });
                        break;
                    }
                }
            });
            return matches;
        }
        """,
        PRODUCT_KEYWORDS,
    )


def check_product_stock(page: Page, product_name: str, store: dict) -> dict | None:
    """상품 클릭 → 팝업에서 재고 읽기 → 닫기"""
    sk = store_key(store)
    safe_name = re.sub(r"[^\w가-힣]", "_", product_name)[:30]
    try:
        page.locator(f'text="{product_name}"').first.click(timeout=5000)
        page.wait_for_timeout(1000)
        take_screenshot(page, f"05_popup_{sk}_{safe_name}")

        # 팝업 텍스트에서 '재고' 줄 찾기
        popup_text = page.evaluate(
            """
            () => {
                // 가장 최근에 보이는 모달/팝업 컨테이너 찾기
                const all = document.querySelectorAll('div, section');
                let best = '';
                for (const el of all) {
                    const text = el.innerText || '';
                    if (text.includes('재고') && text.includes('닫기')
                        && text.length < 1500 && text.length > best.length) {
                        best = text;
                    }
                }
                return best || document.body.innerText;
            }
            """
        )

        sold_out = False
        for line in popup_text.split("\n"):
            if "재고" in line:
                sold_out = "품절" in line
                break

        # 팝업 닫기
        try:
            page.click("text=닫기", timeout=3000)
        except Exception:
            page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        return {"soldOut": sold_out}
    except Exception as e:
        print(f"    ⚠️ 상품 확인 실패 [{product_name}]: {e}")
        take_screenshot(page, f"FAIL_product_{sk}_{safe_name}")
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
        return None


def check_store(page: Page, store: dict) -> dict:
    sk = store_key(store)
    print(f"\n📍 [{store['region']} > {store['name']}]")

    if not select_store(page, store):
        return {}
    if not perform_search(page, SEARCH_QUERY):
        return {}

    matches = get_matching_products(page)
    print(f"  🔍 매칭 상품 {len(matches)}개")
    for m in matches:
        print(f"    - {m['name']} (키워드: {m['keyword']})")

    results = {}
    for prod in matches:
        info = check_product_stock(page, prod["name"], store)
        if info is not None:
            results[prod["name"]] = {**info, "keyword": prod["keyword"]}
            status = "❌ 품절" if info["soldOut"] else "✅ 재고있음"
            print(f"    {status}: {prod['name']}")
    return results


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_email_html(notifications: list[dict]) -> str:
    cards = ""
    for n in notifications:
        cards += f"""
        <div style="border:1px solid #e5e7eb;padding:20px;margin:12px 0;border-radius:12px;background:#fff;">
          <div style="font-size:12px;color:#dc2626;font-weight:bold;margin-bottom:6px;">
            🎉 재입고 · {n['store']}
          </div>
          <h3 style="margin:0 0 12px 0;font-size:16px;color:#1f2937;line-height:1.4;">
            {n['product']}
          </h3>
          <a href="{LOTTE_URL}"
             style="display:inline-block;padding:10px 20px;background:#dc2626;color:#fff;
                    text-decoration:none;border-radius:6px;font-weight:bold;font-size:14px;">
            🛒 사이트에서 재확인
          </a>
        </div>
        """
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f9fafb;padding:20px;margin:0;">
  <div style="max-width:600px;margin:0 auto;">
    <h1 style="color:#1f2937;font-size:24px;">🛒 롯데마트 재입고 알림</h1>
    <p style="color:#6b7280;font-size:14px;">{len(notifications)}건의 재입고가 감지되었습니다.</p>
    <p style="color:#9ca3af;font-size:12px;background:#fef3c7;padding:10px;border-radius:6px;">
      ⚠️ 사이트 재고는 실제 매장과 다를 수 있어요. 가시기 전 매장 전화 확인 추천!
    </p>
    {cards}
    <p style="color:#9ca3af;font-size:12px;text-align:center;margin-top:32px;">
      롯데마트 재고 감시 봇 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </p>
  </div>
</body>
</html>"""


def send_email(notifications: list[dict]) -> None:
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    to_email = os.environ.get("TO_EMAIL", smtp_user)

    subject = f"🛒 롯데마트 포켓몬카드 재입고 ({len(notifications)}건)"

    body_text = f"롯데마트 재입고 알림 ({len(notifications)}건)\n\n"
    for n in notifications:
        body_text += f"• [{n['store']}] {n['product']}\n"
    body_text += f"\n매장 재고 확인: {LOTTE_URL}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("롯데마트 재고봇", smtp_user))
    msg["To"] = to_email
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(build_email_html(notifications), "html", "utf-8"))

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())


def main() -> int:
    if not os.environ.get("SMTP_USER") or not os.environ.get("SMTP_PASSWORD"):
        sys.exit("❌ SMTP_USER, SMTP_PASSWORD 환경변수를 설정하세요.")

    if DEBUG_MODE:
        DEBUG_DIR.mkdir(exist_ok=True)
        print("🐛 DEBUG MODE 활성화 - 스크린샷이 debug/에 저장됩니다.")

    print(f"🔍 검색어: '{SEARCH_QUERY}'")
    print(f"🏪 매장 {len(STORES)}개")
    print(f"🎯 키워드 {len(PRODUCT_KEYWORDS)}개: {', '.join(PRODUCT_KEYWORDS)}")

    current = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        for store in STORES:
            sk = store_key(store)
            try:
                # 매장마다 페이지 새로 로드 (안정성)
                page.goto(LOTTE_URL, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)
                take_screenshot(page, f"00_loaded_{sk}")
                current[sk] = check_store(page, store)
            except Exception as e:
                print(f"  ❌ [{sk}] 처리 중 오류: {e}")
                if DEBUG_MODE:
                    print(traceback.format_exc())
                current[sk] = {}

        browser.close()

    # 이전 상태와 비교
    previous = load_state()
    notifications = []

    for sk, products in current.items():
        prev_store = previous.get(sk, {})
        for product_name, info in products.items():
            prev_info = prev_store.get(product_name)
            store_display = sk.replace("_", " > ")
            if prev_info and prev_info.get("soldOut") and not info["soldOut"]:
                notifications.append({"store": store_display, "product": product_name})
            elif prev_info is None and not info["soldOut"] and previous:
                # 첫 실행 아닐 때만 신규 입고 알림
                notifications.append({"store": store_display, "product": product_name})

    print(f"\n📊 알림 {len(notifications)}건")

    if notifications:
        try:
            send_email(notifications)
            print(f"✅ 이메일 전송 완료 ({len(notifications)}건)")
        except Exception as e:
            print(f"❌ 이메일 전송 실패: {e}")
            if DEBUG_MODE:
                print(traceback.format_exc())
            return 1
    else:
        print("  변동 없음, 이메일 안 보냄")

    save_state(current)
    print("✅ 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
