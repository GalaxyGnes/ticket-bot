import httpx
import urllib.parse
import logging
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html",
    "Referer": "https://pass.rw.by/ru/",
}


async def get_trains(from_city: str, to_city: str, date: str) -> list:
    try:
        params = urllib.parse.urlencode({"from": from_city, "to": to_city, "date": date})
        url = f"https://pass.rw.by/ru/route/?{params}"

        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)

        html = resp.text
        trains = []

        # Ищем ссылки на поезда через регулярное выражение
        pattern = r'href="/ru/train/\?train=([^&"]+)[^"]*"[^>]*>.*?(\d{1,2}:\d{2}).*?(\d{1,2}:\d{2})'
        matches = re.findall(pattern, html, re.DOTALL)

        # Альтернативный поиск — ищем номера поездов и времена
        if not matches:
            # Ищем блоки с поездами
            train_pattern = r'/ru/train/\?train=([^&"]+)'
            train_nums = re.findall(train_pattern, html)
            time_pattern = r'(\d{1,2}:\d{2})'
            
            # Находим все времена рядом с поездами
            for i, num in enumerate(train_nums[:10]):
                num_decoded = urllib.parse.unquote(num)
                # Ищем время отправления рядом с этим поездом
                pos = html.find(f'train={num}')
                if pos > 0:
                    fragment = html[pos:pos+500]
                    times = re.findall(time_pattern, fragment)
                    if len(times) >= 2:
                        trains.append({
                            "num": num_decoded,
                            "dep": times[0],
                            "arr": times[1],
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
