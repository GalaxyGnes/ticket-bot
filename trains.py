"""
ПОЛУЧЕНИЕ СПИСКА ПОЕЗДОВ
Запрашивает rw.by и возвращает список поездов на маршруте
"""

import httpx
import urllib.parse
import logging
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html",
    "Referer": "https://pass.rw.by/ru/",
}


async def get_trains(from_city: str, to_city: str, date: str) -> list:
    try:
        params = urllib.parse.urlencode({
            "from": from_city,
            "to":   to_city,
            "date": date,
        })
        url = f"https://pass.rw.by/ru/route/?{params}"

        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)

        soup = BeautifulSoup(resp.text, "html.parser")
        trains = []
        import re

        # Ищем ссылки на конкретные поезда — /ru/train/?train=...
        train_links = soup.find_all("a", href=lambda h: h and "/ru/train/" in str(h))

        for link in train_links:
            href = link.get("href", "")
            match = re.search(r'train=([^&]+)', href)
            if not match:
                continue

            train_num = urllib.parse.unquote(match.group(1))

            # Ищем ближайший родительский блок поезда
            # Идём вверх пока не найдём блок именно с этим поездом
            parent = link.find_parent()
            train_block = None
            for _ in range(15):
                if parent is None:
                    break
                text = parent.get_text(" ", strip=True)
                times = re.findall(r'\b(\d{1,2}:\d{2})\b', text)
                # Проверяем что блок содержит время и не слишком большой
                if len(times) >= 2 and len(text) < 600:
                    train_block = parent
                    break
                parent = parent.find_parent()

            if not train_block:
                continue

            block_text = train_block.get_text(" ", strip=True)
            times = re.findall(r'\b(\d{1,2}:\d{2})\b', block_text)

            # Определяем статус мест — ищем именно в этом блоке
            if "Мест нет" in block_text:
                seats_str = "Мест нет"
            else:
                seats_match = re.search(r'(\d+)\s*(?:мест|место|места)', block_text)
                if seats_match:
                    seats_str = f"{seats_match.group(1)} мест"
                else:
                 # Статус не показываем — он неточный в статическом HTML
            # Реальную проверку делает планировщик
                    seats_str = "нажми чтобы мониторить"

            trains.append({
                "num":   train_num,
                "dep":   times[0] if times else "?",
                "arr":   times[1] if len(times) > 1 else "?",
                "seats": seats_str,
            })

        # Убираем дубликаты
        seen = set()
        unique = []
        for t in trains:
            if t["num"] not in seen:
                seen.add(t["num"])
                unique.append(t)

        logging.info(f"Найдено поездов {from_city}→{to_city} {date}: {len(unique)}")
        return unique[:10]

    except Exception as e:
        logging.error(f"Ошибка получения поездов: {e}")
        return []