import logging
import httpx
import urllib.parse

WAGON_NAMES = {
    "Любое": "любом вагоне",
    "СВ": "СВ (люкс)",
    "К":  "К (купе)",
    "П":  "П (плацкарт)",
    "О":  "О (общий)",
    "С":  "С (сидячий)",
}

STATION_CODES = {
    "минск":        "2100000",
    "брест":        "2100035",
    "гродно":       "2100070",
    "витебск":      "2100050",
    "гомель":       "2100100",
    "могилев":      "2100150",
    "молодечно":    "2100020",
    "барановичи":   "2100280",
    "бобруйск":     "2100120",
    "борисов":      "2100305",
    "жлобин":       "2100105",
    "калинковичи":  "2100090",
    "лида":         "2100065",
    "орша":         "2100055",
    "пинск":        "2100095",
    "полоцк":       "2100045",
    "осиповичи":    "2100130",
    "лунинец":      "2100085",
}

# car_type коды
CAR_TYPES = {
    "СВ": "1",
    "К":  "3",
    "П":  "4",
    "О":  "6",
    "С":  "2",
    "Любое": "2",  # по умолчанию сидячий, потом проверим все
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en=q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://pass.rw.by/ru/order/places/",
    "Connection": "keep-alive",
}


# Кэш кодов станций чтобы не запрашивать каждый раз
_station_cache = {}

async def get_station_code(city: str) -> str:
    """Получает код станции через автодополнение rw.by"""
    city_clean = city.strip()
    city_lower = city_clean.lower()

    # Сначала проверяем кэш
    if city_lower in _station_cache:
        return _station_cache[city_lower]

    # Жёстко заданные коды для основных городов
    hardcoded = {
        "минск": "2100000",
        "брест": "2100035",
        "гродно": "2100070",
        "витебск": "2100050",
        "гомель": "2100100",
        "могилев": "2100150",
        "молодечно": "2100020",
        "барановичи": "2100280",
        "бобруйск": "2100120",
        "борисов": "2100305",
        "жлобин": "2100105",
        "калинковичи": "2100090",
        "лида": "2100065",
        "орша": "2100055",
        "пинск": "2100095",
        "полоцк": "2100045",
        "осиповичи": "2100130",
        "лунинец": "2100085",
        "кричев": "2100155",
        "новогрудок": "2100075",
        "слоним": "2100068",
        "волковыск": "2100067",
        "береза": "2100040",
        "кобрин": "2100038",
        "слуцк": "2100025",
        "солигорск": "2100027",
        "несвиж": "2100026",
        "вилейка": "2100021",
        "сморгонь": "2100022",
        "лепель": "2100052",
        "новополоцк": "2100046",
        "глубокое": "2100048",
        "поставы": "2100049",
        "светлогорск": "2100102",
        "речица": "2100103",
        "мозырь": "2100092",
        "петриков": "2100093",
        "дрогичин": "2100086",
        "ивацевичи": "2100282",
        "микашевичи": "2100088",
        "коммунары": "2100001",
        "минск-пассажирский": "2100000",
        "брест-центральный": "2100035",
        "орша-центральная": "2100055",
        "барановичи-полесские": "2100280",
        "юратишки": "2100059",
    }

    if city_lower in hardcoded:
        _station_cache[city_lower] = hardcoded[city_lower]
        return hardcoded[city_lower]

    # Если нет в словаре — запрашиваем у rw.by
    try:
        url = f"https://pass.rw.by/ru/ajax/autocomplete/search?term={urllib.parse.quote(city_clean)}&gid=&by_only=1&non_multistation=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://pass.rw.by/ru/",
        }
        async with httpx.AsyncClient(headers=headers, timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
            if data and len(data) > 0:
                code = str(data[0].get("exp", "0"))
                logging.info(f"Найден код станции {city_clean}: {code}")
                _station_cache[city_lower] = code
                return code
    except Exception as e:
        logging.warning(f"Не удалось получить код станции {city_clean}: {e}")

    logging.warning(f"Станция не найдена: {city_clean}")
    return "0"


async def check_tickets(train_num: str, from_city: str, to_city: str,
                        date: str, wagon_type: str) -> dict:
    try:
        parts = date.split(".")
        date_api = f"{parts[2]}-{parts[1]}-{parts[0]}"

        from_code = await get_station_code(from_city)
        to_code   = await get_station_code(to_city)

        import time as time_module

        # Если "Любое" — перебираем все типы вагонов
        if wagon_type == "Любое":
            car_types_to_check = ["1", "2", "3", "4", "6"]
        else:
            car_types_to_check = [CAR_TYPES.get(wagon_type, "2")]

        total_seats = 0
        min_price = None
        found_train = False

        for car_type in car_types_to_check:
            params = {
                "from":              from_code,
                "to":                to_code,
                "date":              date_api,
                "train_number":      train_num,
                "car_type":          car_type,
                "apply_modificator": "",
                "from_time":         int(time_module.time()),
                "_":                 int(time_module.time() * 1000),
            }

            url = "https://pass.rw.by/ru/ajax/route/car_places/?" + urllib.parse.urlencode(params)

            async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
                response = await client.get(url)

            if response.status_code != 200:
                continue

            data = response.json()

            if data.get("trainNumber"):
                found_train = True

            for tariff in data.get("tariffs", []):
                price_byn = tariff.get("price_byn", "")
                if price_byn and min_price is None:
                    min_price = price_byn
                for car in tariff.get("cars", []):
                    seats = car.get("totalPlaces", 0)
                    total_seats += seats
                    logging.info(f"Вагон {car.get('number')} (тип {car_type}): {seats} мест")

        logging.info(f"Итого: поезд найден={found_train}, мест={total_seats}")

        buy_url = f"https://pass.rw.by/ru/route/?from={urllib.parse.quote(from_city)}&to={urllib.parse.quote(to_city)}&date={date}"

        if total_seats > 0:
            price_str = f"от {min_price} BYN" if min_price else "уточните на сайте"
            return {
                "available": True,
                "seats": total_seats,
                "details": f"{total_seats} мест в любом вагоне",
                "price": price_str,
                "url": buy_url,
            }

        # Если ни один тип вагона не вернул данные о поезде —
        # это может быть просто "мест нет", а не "поезд не существует"
        # Считаем что поезд существует если хоть один запрос вернул 200
        return {"available": False, "seats": 0}

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        return {"available": False, "error": str(e)}
