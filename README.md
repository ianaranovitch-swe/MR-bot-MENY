# Меню-бот для Telegram-канала

Бот показывает меню тем (Nyheter, Aquatone, Biotrem, Monicor, Kvantresonans,
Longevity Club 100+). В канале кнопки открывают личный чат с ботом.
Каждая тема в личке показывается с картинкой-баннером, если файл лежит в `banners/`.

## Что нужно заранее

- Python 3.10 или новее
- Аккаунт Telegram
- Права администратора в канале `@abmrab` (или другом канале из `.env`)

## Переменные окружения

Скопируй `.env.example` в `.env` и заполни:

| Переменная | Пример | Зачем |
|---|---|---|
| `BOT_TOKEN` | `123456789:AAH...` | Секретный ключ бота от `@BotFather` |
| `CHANNEL` | `@abmrab` | Куда публиковать меню |
| `BANNERS_DIR` | `banners` | Папка с картинками тем. Необязательно |

Токен — как ключ от квартиры. Не публикуй его в чатах, GitHub и скриншотах.

## Запуск локально

В PowerShell из папки проекта:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

Открой `.env`, вставь настоящий `BOT_TOKEN`, затем:

```powershell
python telegram_meny_abmrab.py
```

Остановка: `Ctrl+C`.

## Картинки тем (баннеры)

Положи 6 файлов в папку `banners/` рядом со скриптом:

| Тема | Имя файла |
|---|---|
| Nyheter | `nyheter.png` |
| Aquatone | `aquatone.png` |
| Biotrem | `biotrem.png` |
| Monicor | `monicor.png` |
| Kvantresonans | `kvantresonans.png` |
| Longevity Club 100+ | `longevity_club_100.png` |

Если файла нет, бот покажет только текст — не упадёт.

**Рекомендуемый путь:** положи png в `banners/`, сделай `git push`. Railway скачает картинки вместе с кодом. Volume и `railway volume` не нужны.

Запасной путь (если не хочешь класть картинки в Git): Railway Volume, mount `/data`, переменная `BANNERS_DIR=/data/banners`.

Проверка тестов:

```powershell
pytest
```

## Пошаговый запуск в Telegram

1. Открой Telegram и найди `@BotFather`.
2. Напиши `/newbot`, придумай имя и username (например `ABMRAB Meny` и `abmrab_meny_bot`).
3. Скопируй токен в `.env` как `BOT_TOKEN=...`.
4. У `@BotFather` выполни `/setprivacy` → выбери бота → `Disable` (не обязательно, но удобно).
5. Открой свой канал `@abmrab` → Administrators → Add Administrator → найди бота.
6. Включи права бота:
   - Post Messages
   - Edit Messages
   - Pin Messages
7. Запусти бота командой `python telegram_meny_abmrab.py`.
8. В личке с ботом напиши `/start` — должно появиться меню.
9. Напиши `/publicera_meny` — пост с кнопками уйдёт в канал и бот попробует закрепить его.
10. Нажми кнопку в канале: откроется личка бота с нужной темой.

Команды бота:

- `/start` и `/menu` — меню в личке
- `/publicera_meny` — публикация меню в канал (только админ канала)

## Деплой на Railway

Бот должен работать постоянно. Railway держит его включённым в облаке,
даже когда твой компьютер выключен.

Файл `.env` на Railway **не загружается**. Токен и канал задаются
во вкладке **Variables**. Локальный `.env` в Git не попадает.

Перед заливкой останови локальный запуск (`Ctrl+C`). Два бота с одним
токеном одновременно дают ошибку 409.

### 1. Залей код на GitHub

Репозиторий лучше сделать **private**.

```powershell
git add railway.toml .python-version .railwayignore requirements.txt requirements-dev.txt README.md
git add -u
git status
```

Убедись, что в списке **нет** `.env`. Затем закоммить и отправь:

```powershell
git commit -m "Prepare bot for Railway worker deploy."
git push -u origin HEAD
```

### 2. Создай проект на Railway

1. Открой [railway.com](https://railway.com) и войди (удобно через GitHub).
2. **New Project** → **Deploy from GitHub repo**.
3. Выбери репозиторий `MR-bot-MENY`.
4. Если GitHub ещё не подключён — нажми **Configure GitHub App** и дай доступ к репо.

Railway сам найдёт Python. Старт уже прописан в `railway.toml`:
`python telegram_meny_abmrab.py`.

### 3. Добавь переменные (это вместо `.env`)

1. Открой сервис (карточка проекта).
2. Вкладка **Variables**.
3. **+ New Variable** и добавь две штуки:

| Имя | Значение |
|---|---|
| `BOT_TOKEN` | тот же токен, что в твоём `.env` |
| `CHANNEL` | `@abmrab` (или username твоего канала) |
| `BANNERS_DIR` | не нужна, если картинки лежат в `banners/` в репозитории |

4. Нажми **Deploy** / дождись автоматического редеплоя после сохранения переменных.

**Не нажимай Generate Domain.** Это не сайт, публичный адрес не нужен.

### 4. Проверь, что бот живой

1. Вкладка **Deployments** — статус **Success**.
2. Вкладка **Logs** — строка вроде: `Бот запущен. Канал: @abmrab`.
3. В Telegram напиши `@MRAB_SWE_bot` команду `/start`.

Если в логах `ValueError` про токен — переменная `BOT_TOKEN` пустая или с пробелом.

### 5. Права в канале — после того как бот уже крутится

Это делается **в канале**, не в BotFather:

1. Открой канал → название сверху → **Manage**.
2. **Administrators** → **Add Administrator**.
3. Найди `@MRAB_SWE_bot`.
4. Включи Post Messages, Edit Messages, Pin Messages.
5. В личке бота напиши `/publicera_meny`.

## Откат

**Railway**

1. Открой сервис → **Deployments**.
2. Найди прошлый успешный деплой → **Rollback** / Redeploy.
3. Если сломались переменные — верни старые `BOT_TOKEN` и `CHANNEL` и задеплой снова.

**Локально**

1. Останови процесс (`Ctrl+C`).
2. Верни предыдущий `telegram_meny_abmrab.py`.
3. Запусти снова и проверь `/start`.

Плохой пост в канале удали вручную и снова вызови `/publicera_meny`.

## Диагностика

| Симптом | Что проверить |
|---|---|
| `ValueError` про `BOT_TOKEN` | Локально: файл `.env`. На Railway: Variables → `BOT_TOKEN` |
| Бот молчит | Локально окно запущено. На Railway деплой Success и есть логи |
| «Bara en administratör...» | Команду пишет не админ канала |
| Меню не публикуется | Бот добавлен админом канала и может постить |
| Меню опубликовано, но не закреплено | Включи боту право Pin Messages |
| Кнопка в канале открывает бота, но пусто | Бот не запущен или токен от другого бота |
| Конфликт `getUpdates` / 409 | Второй экземпляр с тем же токеном (локально + Railway) |
| Тема без картинки | В логах `Баннеры отсутствуют`. Проверь имя файла в `banners/` |

Логи смотри в том же окне терминала: ошибки публикации пишутся с текстом исключения.
