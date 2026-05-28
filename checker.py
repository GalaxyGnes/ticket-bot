"""
ПРОВЕРКА БИЛЕТОВ НА RW.BY
Использует Playwright — настоящий браузер, который выполняет JavaScript.
Это нужно потому что rw.by загружает данные о поездах через JS.
"""

import logging
from playwright.async_api import async_playwright

WAGON_NAMES = {
    "Любое": "любом вагоне",   
    "СВ": "СВ (люкс)",
    "К":  "К (купе)",
    "П":  "П (плацкарт)",
    "О":  "О (общий)",
    "С":  "С (сидячий)",
}


async def check_tickets(train_num: str, from_city: str, to_city: str,
                        date: str, wagon_type: str) -> dict:
    """
    Открывает браузер, заходит на rw.by и проверяет наличие мест.
    headless=True — браузер работает невидимо, без окна.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Формируем URL поиска
            import urllib.parse
            params = urllib.parse.urlencode({
                "from": from_city,
                "to":   to_city,
                "date": date,
            })
            url = f"https://pass.rw.by/ru/route/?{params}"

            # Заходим на страницу и ждём пока загрузится список поездов
            await page.goto(url, timeout=30000)

            # Ждём появления результатов (либо списка поездов, либо "нет поездов")
            try:
                await page.wait_for_selector(
                    ".train-item, .sch-table__row, [class*='train'], .no-results, .alert",
                    timeout=15000
                )
            except Exception:
                # Если селектор не найден — попробуем просто подождать
                await page.wait_for_timeout(5000)

            # Получаем весь текст страницы
            content = await page.content()
            text = await page.inner_text("body")

            await browser.close()

            return parse_page(text, content, train_num, wagon_type)

    except Exception as e:
        logging.error(f"Ошибка Playwright при проверке {train_num}: {e}")
        return {"available": False, "error": str(e)}


def parse_page(text: str, html: str, train_num: str, wagon_type: str) -> dict:
    """
    Анализирует текст страницы после выполнения JavaScript.
    Ищет номер поезда и рядом с ним — статус мест.
    """
    try:
        # Нормализуем: убираем лишние пробелы
        text_clean = " ".join(text.split())

        # Ищем номер поезда в тексте
        train_upper = train_num.upper()
        idx = text_clean.upper().find(train_upper)

        if idx < 0:
            logging.info(f"Поезд {train_num} не найден на странице")
            return {"available": False, "seats": 0, "error": "not_found"}

        # Берём фрагмент текста вокруг найденного поезда (500 символов после)
        fragment = text_clean[idx:idx+500]

        logging.info(f"Найден поезд {train_num}, фрагмент: {fragment[:200]}")

        # Проверяем статус мест в этом фрагменте
        if "Мест нет" in fragment or "мест нет" in fragment:
            return {"available": False, "seats": 0}

        # Если номер поезда есть, но "Мест нет" нет — места есть!
        return {
            "available": True,
            "seats": 1,
            "details": f"Есть места в {WAGON_NAMES.get(wagon_type, wagon_type)}"
        }

    except Exception as e:
        logging.error(f"Ошибка парсинга страницы: {e}")
        return {"available": False, "error": "parse_error"}
