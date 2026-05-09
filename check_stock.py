"""
포켓몬스토어 재입고 감시 스크립트
- 카테고리 페이지를 5분마다 체크
- 품절 → 재입고 전환되면 이메일 알림
"""
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from playwright.sync_api import sync_playwright

# 감시할 URL 목록 (필요 시 수정)
URLS = [
    "https://www.pokemonstore.co.kr/pages/product/list.html?depth=2&categoryNo=488359&page=1",
    "https://www.pokemonstore.co.kr/pages/product/list.html?depth=2&categoryNo=488359&page=2",
    "https://www.pokemonstore.co.kr/pages/product/list.html?depth=2&categoryNo=488359&page=3",
]

STATE_FILE = Path("state.json")


def fetch_products(url: str) -> list[dict]:
    """카테고리 페이지에서 상품 목록 추출.

    각 상품에 대해 productNo, name, soldOut 정보를 반환.
    페이지가 JavaScript로 렌더링되므로 Playwright 사용.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        products = page.evaluate(
            """
            () => {
                const links = document.querySelectorAll('a[href*="productNo="]');
                const seen = new Map();
                links.forEach(link => {
                    const href = link.getAttribute('href') || '';
                    const m = href.match(/productNo=(\\d+)/);
                    if (!m) return;
                    const productNo = m[1];

                    const container =
                        link.closest('li') ||
                        link.closest('[class*="product"]') ||
                        link.closest('div');
                    if (!container) return;

                    const text = (container.innerText || '').trim();
                    const soldOut = /SOLD\\s*OUT|품절/i.test(text);

                    const lines = text.split('\\n')
                        .map(s => s.trim())
                        .filter(s => s && !/^\\d+원$|^SOLD\\s*OUT$|^품절$|^\\d+%$/i.test(s));
                    const name = lines.sort((a, b) => b.length - a.length)[0] || `상품 ${productNo}`;

                    const img = container.querySelector('img');
                    const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';

                    if (!seen.has(productNo)) {
                        seen.set(productNo, { productNo, name, soldOut, imageUrl });
                    }
                });
                return Array.from(seen.values());
            }
            """
        )
        browser.close()
        return products


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
    )


def build_email_html(items: list[dict]) -> str:
    """재입고 상품 목록으로 HTML 이메일 본문 생성."""
    cards = ""
    for item in items:
        img_html = (
            f'<img src="{item["imageUrl"]}" alt="" '
            f'style="width:120px;height:120px;object-fit:cover;border-radius:8px;float:left;margin-right:16px;">'
            if item.get("imageUrl") else ""
        )
        cards += f"""
        <div style="border:1px solid #e5e7eb;padding:20px;margin:12px 0;border-radius:12px;background:#fff;overflow:hidden;">
          {img_html}
          <div style="overflow:hidden;">
            <div style="font-size:12px;color:#ee0000;font-weight:bold;margin-bottom:6px;">
              {item['prefix']}
            </div>
            <h3 style="margin:0 0 12px 0;font-size:16px;color:#1f2937;line-height:1.4;">
              {item['name']}
            </h3>
            <a href="{item['url']}"
               style="display:inline-block;padding:10px 20px;background:#ee0000;color:#fff;
                      text-decoration:none;border-radius:6px;font-weight:bold;font-size:14px;">
              🛒 바로 사러 가기
            </a>
          </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f9fafb;padding:20px;margin:0;">
  <div style="max-width:600px;margin:0 auto;">
    <h1 style="color:#1f2937;font-size:24px;">🎉 포켓몬스토어 재입고 알림!</h1>
    <p style="color:#6b7280;font-size:14px;">{len(items)}개 상품이 입고되었습니다. 빨리 확인하세요!</p>
    {cards}
    <p style="color:#9ca3af;font-size:12px;text-align:center;margin-top:32px;">
      포켓몬스토어 재고 감시 봇 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </p>
  </div>
</body>
</html>"""


def send_email(items: list[dict]) -> None:
    """SMTP로 이메일 발송."""
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    to_email = os.environ.get("TO_EMAIL", smtp_user)

    subject = f"🎉 포켓몬스토어 재입고 ({len(items)}개)"
    body_html = build_email_html(items)

    body_text = f"포켓몬스토어 재입고 알림 ({len(items)}개)\n\n"
    for item in items:
        body_text += f"• {item['name']}\n  {item['url']}\n\n"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("포켓몬 재고봇", smtp_user))
    msg["To"] = to_email
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, [to_email], msg.as_string())


def main() -> int:
    if not os.environ.get("SMTP_USER") or not os.environ.get("SMTP_PASSWORD"):
        sys.exit("❌ SMTP_USER, SMTP_PASSWORD 환경변수를 설정하세요.")

    print(f"🔍 {len(URLS)}개 페이지 크롤링 중...")
    current = {}
    for i, url in enumerate(URLS, 1):
        try:
            products = fetch_products(url)
            print(f"  [{i}/{len(URLS)}] {len(products)}개 상품 발견")
            for p in products:
                current[p["productNo"]] = {
                    "name": p["name"],
                    "soldOut": p["soldOut"],
                    "imageUrl": p.get("imageUrl", ""),
                    "url": f"https://www.pokemonstore.co.kr/pages/product/view.html?productNo={p['productNo']}",
                }
        except Exception as e:
            print(f"  [{i}/{len(URLS)}] ❌ 오류: {e}")

    if not current:
        print("⚠️ 상품을 하나도 못 찾았습니다. 페이지 구조가 바뀌었을 수 있습니다.")
        return 1

    previous = load_state()
    notifications = []
    for product_no, data in current.items():
        prev = previous.get(product_no)
        if prev is None:
            # 처음 보는 상품: 첫 실행이 아니고 재고 있을 때만 (노이즈 방지)
            if previous and not data["soldOut"]:
                notifications.append({**data, "prefix": "🆕 신규 입고"})
        elif prev.get("soldOut") and not data["soldOut"]:
            notifications.append({**data, "prefix": "🎉 재입고"})

    print(f"📊 상품 {len(current)}개 / 이전 {len(previous)}개 / 알림 {len(notifications)}개")

    if notifications:
        try:
            send_email(notifications)
            print(f"  ✅ 이메일 전송 완료: {len(notifications)}개 상품")
        except Exception as e:
            print(f"  ❌ 이메일 전송 실패: {e}")
            return 1
    else:
        print("  변동 없음, 이메일 안 보냄")

    save_state(current)
    print("✅ 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
