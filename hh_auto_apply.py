import time
import random
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def close_response_modal(page) -> bool:
    """Закрывает любое всплывающее модальное окно hh.ru"""
    closed = False
    try:
        # Основные селекторы hh.ru для модалок отклика
        close_selectors = [
            '[data-qa="response-popup-close"]',      # самый частый
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

        # Дополнительно скрываем сам диалог, если он остался
        if page.locator('[role="dialog"]').is_visible(timeout=1000):
            page.locator('[role="dialog"]').first.evaluate("el => el.style.display = 'none'")
            closed = True

    except:
        pass
    return closed


def main():
    print("=" * 80)
    print("🚀 HH.ru Автоотклики — Playwright (исправленная версия)")
    print(f"🐍 Python: {sys.executable}")
    print(f"📁 Папка: {Path.cwd()}")
    print("=" * 80)

    with sync_playwright() as p:
        # === ВЫБОР БРАУЗЕРА ===
        choice = input("\nВыберите браузер (1 — Chromium, 2 — WebKit): ").strip()
        if choice == "2":
            browser = p.webkit.launch(headless=False, slow_mo=80)
            print("✅ WebKit (нативный для M1/M2/M3/M4)")
        else:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-extensions",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
                ]
            )
            print("✅ Chromium")

        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        page = context.new_page()

        # === ОБРАБОТКА ВСПЛЫВАЮЩИХ ОКОН И ДИАЛОГОВ ===
        skipped_popup = 0

        def handle_new_page(new_page):
            nonlocal skipped_popup
            print(f"🔴 Новая вкладка открыта → закрываем ({new_page.url})")
            try:
                new_page.close()
                skipped_popup += 1
                # Возвращаем фокус на главную страницу
                context.pages[0].bring_to_front()
            except:
                pass

        def handle_dialog(dialog):
            print(f"🛑 JS-диалог: {dialog.message} → закрываем")
            dialog.dismiss()

        context.on("page", handle_new_page)
        context.on("dialog", handle_dialog)

        # === СЧЁТЧИКИ ===
        total_applied = 0
        skipped_redirect = 0
        errors = 0
        page_number = 1
        max_pages = 25

        page.goto("https://hh.ru/", wait_until="domcontentloaded", timeout=60000)

        print("\n✅ Браузер открыт.")
        print("👉 Залогинься и настрой фильтры.")
        input("Когда будешь готов — нажми Enter...")

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

                    # === КЛИК ===
                    btn.click(timeout=10000)
                    page.wait_for_timeout(random.randint(2200, 3800))

                    # === ЗАКРЫВАЕМ МОДАЛКУ (главное исправление) ===
                    modal_closed = close_response_modal(page)

                    # === ПРОВЕРКА РЕДИРЕКТА ===
                    if page.url != current_url:
                        print("   🔄 Произошёл редирект → возвращаемся назад")
                        skipped_redirect += 1
                        try:
                            page.go_back(wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(1200)
                            close_response_modal(page)  # на всякий случай
                        except:
                            # Если go_back не сработал — просто обновляем текущую страницу
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

            # === СЛЕДУЮЩАЯ СТРАНИЦА ===
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

        # === ОТЧЁТ ===
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