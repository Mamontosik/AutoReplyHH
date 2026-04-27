#!/usr/bin/env python3
"""HH.ru Auto Reply - автоматический отклик на вакансии."""

import time
import random
from pathlib import Path

from playwright.sync_api import sync_playwright

SLOW_MO = 80
SELECTOR_RESPONSE = '[data-qa="vacancy-serp__vacancy_response"]'
SELECTOR_MODAL = '[role="dialog"]'
TEXT_SKIP = frozenset({"вы откликнулись", "отклик уже отправлен"})
CLOSE_SELECTORS = (
    '[data-qa="response-popup-close"]',
    '[data-qa="modal-close"]',
    'button[aria-label*="Закрыть"]',
    '.bloko-modal-close',
)


def close_modal(page) -> bool:
    """
    Закрыть модальное окно.

    Пробует последовательно селекторы из CLOSE_SELECTORS.
    Возвращает True если удалось закрыть, False иначе.
    """
    for selector in CLOSE_SELECTORS:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1500):
                btn.click(timeout=5000)
                return True
        except Exception:
            pass
    return False


def process_page(page) -> tuple[int, int, int, int]:
    """
    Обработать все вакансии на странице.

    Для каждой кнопки "Откликнуться":
    1. Пропускает если уже откликнулись (TEXT_SKIP)
    2. Кликает и ждёт ответа
    3. Закрывает модалку если появилась
    4. Обрабатывает редирект (go_back)
    5. Считает успех/ошибки

    Returns:
        Кортеж (success, skipped, closed, errors).
    """
    buttons = page.locator(SELECTOR_RESPONSE)
    modal = page.locator(SELECTOR_MODAL)
    success = skipped = closed = errors = 0

    for i in range(buttons.count()):
        btn = buttons.nth(i)
        if not btn.is_visible():
            continue

        text = btn.inner_text().lower()
        if any(t in text for t in TEXT_SKIP):
            skipped += 1
            continue

        try:
            btn.scroll_into_view_if_needed()
            url_before = page.url
            btn.click()
            page.wait_for_timeout(random.randint(2000, 3500))

            if modal.is_visible(timeout=1000):
                closed += 1
                close_modal(page)
            elif "/vacancy" in page.url:
                page.go_back(wait_until="domcontentloaded", timeout=15000)
            else:
                success += 1

        except Exception:
            errors += 1

        page.wait_for_timeout(random.randint(1500, 2500))

    return success, skipped, closed, errors


def main() -> None:
    """
    Точка входа.

    Этапы:
    1. Запуск браузера с настройками
    2. Открытие hh.ru
    3. Ожидание загрузки вакансий (до 2 мин)
    4. Ожидание ввода пользователя (Enter)
    5. Обработка вакансий
    6. Сохранение отчёта
    7. Закрытие браузера
    """
    print("HH.RU АВТООТКЛИК")
    print("-" * 40)

    with sync_playwright() as p:
        browser = p.webkit.launch(headless=False, slow_mo=SLOW_MO)
        page = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        ).new_page()

        page.goto("https://hh.ru/", wait_until="domcontentloaded", timeout=60000)

        print("Ожидаю загрузку вакансий...")
        for _ in range(120):
            if page.locator(SELECTOR_RESPONSE).count() > 0:
                print("Вакансии загружены!")
                break
            page.wait_for_timeout(1000)
        else:
            print("Время вышло, продолжаю...")

        print("Авторизуйся и настрой фильтры")
        print("Нажми Enter когда готов...")
        input()

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

        success, skipped, closed, errors = process_page(page)

        print(f"Откликов: {success}")
        print(f"Пропущено: {skipped}")
        print(f"Закрыто: {closed}")
        print(f"Ошибок: {errors}")

        Path("hh_report.txt").write_text(
            f"Откликов: {success}\nПропущено: {skipped}\nЗакрыто: {closed}\nОшибок: {errors}\n",
            encoding="utf-8",
        )

        browser.close()
        print("Готово!")


if __name__ == "__main__":
    main()