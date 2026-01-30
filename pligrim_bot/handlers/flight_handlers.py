
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from gspread import spreadsheet
from pligrim_bot.config.settings import PALM_SHEETS

from pligrim_bot.core.parsers.package_parser import *
from pligrim_bot.core.utils.text_utils import clean
from pligrim_bot.core.voucher.builder import assemble_voucher, assemble_voucher_from_one_row_style, build_maps_smart
from pligrim_bot.core.voucher.render import generate_ticket, generate_pdf_from_png

# Кэш для хранения полных списков листов
USER_SHEETS_CACHE = {}

def get_month_sheets_buttons(sheet_titles, show_all=False):
    """Клавиатура для выбора листа с пагинацией"""
    # Фильтруем прошедшие даты
    current_date = datetime.now().strftime("%d.%m.%Y")
    filtered_titles = []

    for title in sheet_titles:
        # Извлекаем даты из названия (формат: DD.MM-DD.MM или DD.MM-YY.MM)
        date_match = re.search(r'(\d{2}\.\d{2})-(\d{2}\.\d{2})', title)
        if date_match:
            start_date_str = date_match.group(1) + f".{datetime.now().year}"
            end_date_str = date_match.group(2) + f".{datetime.now().year}"

            try:
                # Парсим даты
                start_date = datetime.strptime(start_date_str, "%d.%m.%Y")
                end_date = datetime.strptime(end_date_str, "%d.%m.%Y")
                current_dt = datetime.strptime(current_date, "%d.%m.%Y")

                # Оставляем только будущие даты или текущие
                if end_date >= current_dt:
                    filtered_titles.append(title)
            except:
                # Если не удалось распарсить даты, оставляем лист
                filtered_titles.append(title)
        else:
            # Если нет дат в формате, оставляем лист
            filtered_titles.append(title)

    # Сортируем по дате начала
    filtered_titles.sort(key=lambda x: extract_start_date(x))

    # Ограничиваем показ если не показаны все
    if not show_all and len(filtered_titles) > 8:
        display_titles = filtered_titles[:8]
        has_more = True
    else:
        display_titles = filtered_titles
        has_more = False

    # Создаем клавиатуру
    keyboard = []
    for title in display_titles:
        # Обрезаем длинные названия для кнопки
        button_text = title[:30] + "..." if len(title) > 30 else title
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"sheet:{title}")])

    # Добавляем кнопку "Показать все" если есть еще элементы
    if has_more:
        keyboard.append([InlineKeyboardButton(text=" Показать все", callback_data="show_all_sheets")])

    keyboard.append([InlineKeyboardButton(text=" Назад к месяцам", callback_data="back_to_months")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard), filtered_titles

def extract_start_date(title):
    """Извлекает дату начала для сортировки"""
    date_match = re.search(r'(\d{2}\.\d{2})-\d{2}\.\d{2}', title)
    if date_match:
        start_date_str = date_match.group(1) + f".{datetime.now().year}"
        try:
            return datetime.strptime(start_date_str, "%d.%m.%Y")
        except:
            return datetime.min
    return datetime.min

# --- Команды ---
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Приветствие и выбор сценария"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=" Ваучер для паломника",
                    callback_data="scenario:palm"
                )
            ],
        ]
    )
    await message.answer(
        "Ассаляму алейкум!\n\nЧто вы хотите сделать?",
        reply_markup=keyboard
    )


def get_month_buttons():
    """Создаёт клавиатуру с текущим и ближайшими 3 месяцами"""
    sheets = get_available_sheets()
    now = datetime.now()
    current_month = MONTHS_RU[now.strftime("%B")]
    current_year = now.strftime("%Y")
    target_name = f"{current_month} {current_year}"

    if target_name in sheets:
        start_index = sheets.index(target_name)
        short_list = sheets[start_index:start_index + 4]
    else:
        short_list = sheets[:4]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
                            [InlineKeyboardButton(text=name, callback_data=f"sheet:{name}")]
                            for name in short_list
                        ] + [
                            [InlineKeyboardButton(text=" Показать все месяцы и пакеты", callback_data="show_all")]
                        ]
    )
    return keyboard

def get_palm_month_buttons() -> InlineKeyboardMarkup:
    """Кнопки выбора месяца (по PALM_SHEETS)."""
    rows = [[InlineKeyboardButton(text=mk, callback_data=f"palm_month:{mk}")] for mk in PALM_SHEETS.keys()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Выбор сценария ---
@dp.callback_query(F.data.startswith("scenario:"))
async def choose_scenario(callback: CallbackQuery):
    scenario = callback.data.split(":", 1)[1]

    if scenario == "palm":
        # 1) показываем месяцы паломников
        await callback.message.answer(
            " Выберите месяц для паломников:",
            reply_markup=get_palm_month_buttons()
        )
    elif scenario == "flight":
        await callback.message.answer(
            "️ Вы выбрали Flight Vaucher.\n\nВыберите месяц (показаны текущий и ближайшие 3):",
            reply_markup=get_month_buttons()
        )
    await callback.answer()

# --- Выбор листа ---
@dp.callback_query(F.data.startswith("sheet:"))
async def sheet_selected(callback: CallbackQuery):
    sheet_name = callback.data.split(":", 1)[1]

    ws = spreadsheet.worksheet(sheet_name)
    packages = find_existing_packages(ws)

    if not packages:
        await callback.message.answer(f" В листе '{sheet_name}' не найдено пакетов.")
        await callback.answer()
        return

    keyboard = build_package_keyboard(sheet_name, packages)
    await callback.message.answer(
        f" Лист: {sheet_name}\n Выберите пакет:",
        reply_markup=keyboard
    )
    await callback.answer()

# --- Обработчик для кнопки "Показать все" листы ---
@dp.callback_query(F.data == "show_all_sheets")
async def show_all_sheets_handler(callback: CallbackQuery):
    all_titles = USER_SHEETS_CACHE.get(callback.from_user.id, [])

    if not all_titles:
        await callback.answer(" Данные устарели")
        return

    # Создаем клавиатуру со всеми листами
    keyboard, _ = get_month_sheets_buttons(all_titles, show_all=True)

    await callback.message.edit_text(
        f" Все доступные листы ({len(all_titles)}):",
        reply_markup=keyboard
    )
    await callback.answer()

# --- Обработчик для кнопки "Назад к месяцам" ---
@dp.callback_query(F.data == "back_to_months")
async def back_to_months(callback: CallbackQuery):
    await callback.message.edit_text(
        "️ Выберите месяц (показаны текущий и ближайшие 3):",
        reply_markup=get_month_buttons()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("package:"))
async def package_selected(callback: CallbackQuery):
    _, sheet_name, package_name = callback.data.split(":", 2)
    ws = spreadsheet.worksheet(sheet_name)

    flights = find_flight_dates(ws, package_name)
    if not flights:
        await callback.message.answer(f"️ Даты для пакета '{package_name}' не найдены.")
        await callback.answer()
        return

    ws_sched = spreadsheet.worksheet("расписание рейсов")
    OUT_AJ, OUT_AM, RET_JA, RET_MA = build_maps_smart(ws_sched)

    kb = InlineKeyboardBuilder()
    data_pkg = ws.get_all_values()

    for f in flights:
        # 1) пробуем достать явный заголовок маршрута около строк пакета
        token = token_from_package_context(data_pkg, f["row"])
        # 2) если нет — единственный возможный вариант по расписанию
        if token is None:
            token = infer_token_by_unique_match(f["dep"], f["ret"], OUT_AJ, OUT_AM, RET_JA, RET_MA)
        # 3) последний fallback
        if token is None:
            direction_guess = extract_direction_for_row(data_pkg, f["row"], ws.title)
            token = dir_to_token(direction_guess)

        btn_text = f"{f['dep']} → {f['ret']} · {token_to_dir(token)}"
        cb = f"d|{f['dep']}|{f['ret']}|{token}"
        kb.button(text=btn_text, callback_data=cb)

    kb.adjust(1)
    await callback.message.answer(
        f" Пакет: {package_name}\n Выберите даты:",
        reply_markup=kb.as_markup()
    )
    await callback.answer()

def dir_to_token(direction_text: str) -> str:
    # понимает и "ALA → MED / JED → ALA", и "ALA MED - JED ALA 7 DAYS"
    s = (direction_text or "").upper()
    s = s.replace("→", " ").replace("/", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)

    has_aj = "ALA JED" in s
    has_am = "ALA MED" in s
    has_ja = "JED ALA" in s
    has_ma = "MED ALA" in s

    if has_aj and has_ja: return "AJJA"
    if has_aj and has_ma: return "AJMA"
    if has_am and has_ja: return "AMJA"
    # "AMMA" нам не нужен, но оставим дефолт на самый частый кейс
    return "AJJA"

def token_to_dir(token: str) -> str:
    mapping = {
        "AJJA": "ALA → JED / JED → ALA",
        "AJMA": "ALA → JED / MED → ALA",
        "AMJA": "ALA → MED / JED → ALA",
    }
    return mapping.get(token, "ALA → JED / JED → ALA")

@dp.callback_query(F.data.startswith("d|"))
async def flight_date_selected(callback: CallbackQuery):
    parts = callback.data.split("|")
    if len(parts) < 4:
        await callback.message.answer("️ Некорректные данные кнопки.")
        return
    _, dep, ret, token = parts

    # Извлечём имя пакета из предыдущего сообщения
    # (например, из " Пакет: HIKMA 7 DAYS")
    prev_text = callback.message.text or ""
    match = re.search(r"Пакет:\s*([A-ZА-Яa-zа-я0-9\s]+)", prev_text)
    package_name = match.group(1).strip().replace(" ", "_") if match else "VOUCHER"

    ws = spreadsheet.worksheet("расписание рейсов")

    # 1️⃣ Собираем данные рейса
    data = assemble_voucher_from_one_row_style(ws, dep, ret, token)
    if not data:
        OUT_AJ, OUT_AM, RET_JA, RET_MA = build_maps_smart(ws)
        data = assemble_voucher(OUT_AJ, OUT_AM, RET_JA, RET_MA, dep, ret, token)

    if not data:
        await callback.message.answer("️ В расписании нет данных для этого направления.")
        return

    # 2️⃣ Текст для пользователя
    text = (
        f" Найден рейс:\n\n"
        f"️ {data['depart_flight']}\n"
        f"{data['depart_date1']} {data['depart_time1']} → {data['depart_time2']}\n\n"
        f"↩️ {data['return_flight']}\n"
        f"{data['return_date1']} {data['return_time1']} → {data['return_time2']}"
    )
    await callback.message.answer(text)

    # 3️⃣ Генерация красивого имени PDF
    file_name = f"{package_name}_{dep}-{ret}.pdf".replace("..", ".").replace(" ", "")
    output_png = f"temp_{dep.replace('.', '')}_{ret.replace('.', '')}.png"

    # 4️⃣ Генерация PNG + PDF
    generate_ticket(output_png, data)
    pdf_path = generate_pdf_from_png(output_png)

    # Переименуем PDF в красивое имя
    pretty_pdf = os.path.join(os.getcwd(), file_name)
    os.rename(pdf_path, pretty_pdf)

    # 5️⃣ Отправляем PDF пользователю
    await callback.message.answer_document(
        types.FSInputFile(pretty_pdf),
        caption=f" Ваш ваучер: {package_name.replace('_', ' ')}"
    )

    # 6️⃣ Удаляем временные файлы
    os.remove(output_png)
    os.remove(pretty_pdf)

# --- Показ всех месяцев ---
@dp.callback_query(F.data == "show_all")
async def show_all_sheets(callback: CallbackQuery):
    sheets = get_available_sheets()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"sheet:{name}")]
            for name in sheets
        ]
    )
    await callback.message.answer(" Все доступные месяцы и пакеты:", reply_markup=keyboard)
    await callback.answer()

def get_available_sheets():
    """Возвращает все актуальные месяцы без исключённых листов"""
    all_sheets = [ws.title for ws in spreadsheet.worksheets()]
    return [s for s in all_sheets if s not in EXCLUDE_SHEETS and "(копия" not in s.lower()]

def find_existing_packages(ws):
    """Находит все пакеты в первых строках (горизонтально расположенные)"""
    values = ws.get_all_values()
    # Берём первые 10 строк, проверяем каждую ячейку
    found = set()

    for row in values[:10]:
        for cell in row:
            text = clean(cell)
            for pkg in PACKAGE_NAMES:
                if pkg.lower() in text.lower():
                    found.add(pkg)
    return sorted(found)

def build_package_keyboard(sheet_name, packages):
    """Создаёт кнопки для найденных пакетов"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p, callback_data=f"package:{sheet_name}:{p}")]
            for p in packages
        ]
    )