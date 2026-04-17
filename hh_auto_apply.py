import time
import random
import sys
import requests
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def close_response_modal(page) -> bool:
    """Закрывает любое всплывающее модальное окно hh.ru"""
    closed = False
    try:
        close_selectors = [
            '[data-qa="response-popup-close"]',
            '[data-qa="modal-close"]',
            'button[aria-label*="Закрыть"]',
            '.bloko-modal-close',
            '[role="dialog"] button:has-text("Закрыть")',
            '[role="dialog"] button:has-text("Отмена")',
            '[role="dialog"] [data-qa*="close"]'
        ]

        for selector in close_selectors:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=5000)
                page.wait_for_timeout(800)
                print("   🛑 Модальное окно закрыто")
                closed = True
                break

        if page.locator('[role="dialog"]').is_visible(timeout=1000):
            page.locator('[role="dialog"]').first.evaluate("el => el.style.display = 'none'")
            closed = True
    except:
        pass
    return closed

def handle_vacancy_form(page):
    """Обрабатывает форму отклика через n8n + Ollama (финальная версия)"""
    try:
        page.wait_for_selector('div[role="dialog"], .vacancy-response-modal, [data-qa*="response"]', timeout=12000)
        print("✅ Обнаружена форма отклика — отправляем в n8n...")

        # Только текстовые поля (исключаем radio, checkbox, select, hidden)
        fields = page.locator(
            'textarea, input[type="text"], input[type="email"], input[type="tel"], input:not([type])'
        ).all()

        questions = []
        for i, field in enumerate(fields):
            if not field.is_visible(timeout=500):
                continue

            label = field.locator('xpath=preceding::label[1] | ..//label | ..//span[contains(@class,"bloko-form-label")]').first.inner_text().strip() or ""
            placeholder = field.get_attribute("placeholder") or ""
            question_text = label or placeholder or f"Поле {i+1}"

            if len(question_text.strip()) < 3:
                continue

            questions.append({
                "label": question_text[:400],
                "type": field.get_attribute("type") or "text",
                "index": i
            })

        if len(questions) < 2:
            print(f"⚠️ Мало реальных полей ({len(questions)}) — пропускаем AI")
            return False

        print(f"Найдено {len(questions)} реальных текстовых полей для AI")

        payload = {
            "questions": questions,
            "vacancy_title": page.title() or "Вакансия на HH"
        }

        print("   📤 Запрос в n8n (максимум 3 минуты)...")
        response = requests.post(
            "http://localhost:5678/webhook/hh-form-reply",
            json=payload,
            timeout=180
        )
        response.raise_for_status()

        data = response.json()
        answers = data.get("answers", [])

        print(f"   📥 AI вернул {len(answers)} ответов")

        if len(answers) == 0 or answers == ["не указано"]:
            print("   ⚠️ AI вернул пустой или бесполезный ответ")
            return False

        # Заполняем только текстовые поля
        for i, answer in enumerate(answers):
            if i >= len(fields) or not str(answer).strip():
                continue
            try:
                field = fields[i]
                field.fill(str(answer)[:800])
                print(f"   ✅ Заполнено поле {i+1}: {str(answer)[:70]}...")
            except Exception as e:
                print(f"   ⚠️ Не удалось заполнить поле {i+1}: {e}")

        # Ждём, пока кнопка станет активной
        submit_btn = page.locator('button:has-text("Откликнуться"), button:has-text("Отправить"), [data-qa*="submit"]').first
        submit_btn.wait_for(state="visible", timeout=15000)
        
        # Если кнопка disabled — ждём до 10 секунд
        for _ in range(20):
            if not submit_btn.get_attribute("disabled"):
                break
            page.wait_for_timeout(500)

        if submit_btn.get_attribute("disabled"):
            print("⚠️ Кнопка отправки всё ещё disabled")
            return False

        submit_btn.click()
        print("✅ Форма отправлена через AI!")
        page.wait_for_timeout(2000)
        return True

    except requests.exceptions.Timeout:
        print("❌ Таймаут n8n (Ollama думает слишком долго)")
        return False
    except Exception as e:
        print(f"❌ Ошибка при обработке формы: {e}")
        return False

def main():
    print("=" * 80)
    print("🚀 HH.ru Автоотклики — Playwright + n8n AI")
    print(f"🐍 Python: {sys.executable}")
    print(f"📁 Папка: {Path.cwd()}")
    print("=" * 80)

    with sync_playwright() as p:
        choice = input("\nВыберите браузер (1 — Chromium, 2 — WebKit): ").strip()
        if choice == "2":
            browser = p.webkit.launch(headless=False, slow_mo=80)
            print("✅ WebKit (нативный для M1)")
        else:
            browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        page = context.new_page()

        # Обработка всплывающих окон
        skipped_popup = 0
        def handle_new_page(new_page):
            nonlocal skipped_popup
            print(f"🔴 Новая вкладка → закрываем")
            try:
                new_page.close()
                skipped_popup += 1
                context.pages[0].bring_to_front()
            except:
                pass

        context.on("page", handle_new_page)
        context.on("dialog", lambda dialog: dialog.dismiss())

        # Счётчики
        total_applied = 0
        skipped_redirect = 0
        errors = 0
        page_number = 1
        max_pages = 25

        page.goto("https://hh.ru/", wait_until="domcontentloaded", timeout=60000)

        print("\n✅ Браузер готов.")
        print("👉 Залогинься и настрой фильтры.")
        input("Когда готов — нажми Enter...")

        print("\n🚀 Запускаем автоотклики...\n")

        while page_number <= max_pages:
            print(f"📄 Страница {page_number}")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(random.randint(1500, 2500))

            buttons = page.locator('[data-qa="vacancy-serp__vacancy_response"]')
            count = buttons.count()
            print(f"   Найдено {count} кнопок «Откликнуться»")

            for i in range(count):
                try:
                    btn = buttons.nth(i)
                    if not btn.is_visible():
                        continue

                    btn_text = btn.inner_text().lower()
                    if "откликнуться" not in btn_text or "вы откликнулись" in btn_text:
                        continue

                    btn.scroll_into_view_if_needed()
                    page.wait_for_timeout(random.randint(700, 1200))

                    current_url = page.url

                    # === КЛИК ПО КНОПКЕ «ОТКЛИКНУТЬСЯ» ===
                    btn.click(timeout=10000)
                    page.wait_for_timeout(random.randint(2200, 3800))

                    # === AI-ОБРАБОТКА ФОРМЫ ===
                    form_processed = handle_vacancy_form(page)

                    if form_processed:
                        total_applied += 1
                        print(f"   ✅ Отклик отправлен через AI! (Всего: {total_applied})")
                        continue

                    # === СТАРАЯ ЛОГИКА (если формы не было) ===
                    modal_closed = close_response_modal(page)

                    if page.url != current_url:
                        print("   🔄 Редирект → возвращаемся")
                        skipped_redirect += 1
                        try:
                            page.go_back(wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(1200)
                        except:
                            page.reload(wait_until="domcontentloaded", timeout=15000)
                    elif modal_closed:
                        print("   ✅ Модалка закрыта — вакансия пропущена")
                    else:
                        total_applied += 1
                        print(f"   ✅ Отклик отправлен! (Всего: {total_applied})")

                    page.wait_for_timeout(random.randint(1800, 3200))

                except Exception as e:
                    errors += 1
                    print(f"   ❌ Ошибка: {type(e).__name__}")
                    continue

            # Следующая страница
            try:
                next_btn = page.locator('a[data-qa="pager-next"], button:has-text("Дальше")').first
                if next_btn.is_visible() and not next_btn.get_attribute("disabled"):
                    next_btn.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    page.wait_for_timeout(random.randint(2500, 4000))
                    page_number += 1
                else:
                    print("   ✅ Конец списка вакансий")
                    break
            except:
                break

        # === ФИНАЛЬНЫЙ ОТЧЁТ ===
        print("\n" + "="*80)
        print("🎉 РАБОТА ЗАВЕРШЕНА")
        print("="*80)
        print(f"📊 Страниц обработано:       {page_number}")
        print(f"✅ Успешных откликов:        {total_applied}")
        print(f"⏭️  Пропущено (редирект):     {skipped_redirect}")
        print(f"🔴 Закрыто всплывающих окон: {skipped_popup}")
        print(f"❌ Ошибок:                   {errors}")
        print("="*80)

        report = f"""Отчёт автооткликов hh.ru
Дата: {time.strftime("%Y-%m-%d %H:%M:%S")}
Успешных откликов: {total_applied}
Пропущено редиректов: {skipped_redirect}
Закрыто модалок: {skipped_popup}
Ошибок: {errors}
"""
        Path("hh_report.txt").write_text(report, encoding="utf-8")
        print("📄 Отчёт сохранён в hh_report.txt")

        input("\nНажми Enter, чтобы закрыть браузер...")
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⛔ Скрипт остановлен вручную")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")