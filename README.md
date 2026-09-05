# Меню-бот для Telegram-канала

Канал: `@abmrab`  
Бот: `@MRAB_SWE_bot`

Бот показывает меню тем (Nyheter, Aquatone, Biotrem, Monicor, Kvantresonans,
Longevity Club 100+). В канале кнопки открывают личный чат с ботом.
Каждая тема на первом экране бота — это карточка: баннер и крупное название.
По нажатию открывается: баннер этой темы, затем её текст и фото, затем
остальные карточки меню со своими баннерами.
Когда меню открывают снова («Tillbaka» или `/start`), старые баннеры и
прошлый текст рубрики бот удаляет — в чате остаётся только новый экран.
Названия рубрик в меню сами по себе не считаются «новыми». Значок 🆕
появляется только у той темы, где админ через `/redigera` менял текст,
фото или ссылки — и только два дня. Через двое суток он пропадает сам.
В посте канала значок не обновляется сам: кнопки там «заморожены», пока
админ снова не напишет `/publicera_meny`.

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
| `ADMIN_IDS` | `111111111,222222222` | Кто может писать `/redigera`. Это Telegram user id |
| `DATABASE_URL` | `postgresql://...` | На Railway появляется после добавления Postgres |

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
2. Бот уже есть: `@MRAB_SWE_bot`. Новый `/newbot` не нужен.
3. Токен этого бота лежит в `.env` / Railway как `BOT_TOKEN`.
4. У `@BotFather` выполни `/setprivacy` → `@MRAB_SWE_bot` → `Disable` (не обязательно, но удобно).
5. Открой канал `@abmrab` (не личку бота) → Administrators → Add Administrator → `@MRAB_SWE_bot`.
6. Включи права бота:
   - Post Messages
   - Edit Messages
   - Pin Messages
7. Запусти бота командой `python telegram_meny_abmrab.py`.
8. В личке `@MRAB_SWE_bot` напиши `/start` — должно появиться меню.
9. Напиши `/kolla_kanal` — бот скажет, связана ли он с `@abmrab`.
10. Если права есть, напиши `/publicera_meny` — пост с кнопками уйдёт в канал.
11. Нажми кнопку в канале: откроется личка `@MRAB_SWE_bot` с нужной темой.

Команды бота:

- `/start` и `/menu` — меню в личке
- `/kolla_kanal` — проверка связки `@abmrab` ↔ `@MRAB_SWE_bot` (только `ADMIN_IDS`)
- `/publicera_meny` — публикация меню в канал (только админ канала)
- `/redigera` — правка текстов, доп.фото и ссылок рубрик (только `ADMIN_IDS`)

## Как шеф меняет тексты бота

1. Узнай свой Telegram id: напиши `@userinfobot` команду `/start`.
2. На Railway в Variables поставь `ADMIN_IDS=этот_id` (несколько id через запятую).
3. Добавь в проект **Postgres** (New → Database → PostgreSQL).
4. У сервиса бота в Variables должна быть `DATABASE_URL` (Railway часто подставляет сам).
5. В личке бота напиши `/redigera` → выбери рубрику → напиши новый текст **как обычно** (жирный, курсив, ссылка).
6. Потом пришли фото по одному или нажми **Hoppa över**.
7. Потом пришли ссылки (YouTube и другие) по одной или нажми **Hoppa över**. Ссылки накапливаются.
8. Бот спросит: опубликовать это же обновление отдельным постом в `@abmrab`
   (**Publicera i kanalen**) или оставить только в боте (**Publicera inte nu**).
9. Баннеры-карточки из `banners/` этим не меняются.

Обычный посетитель команду не использует: сервер всё равно проверяет id.

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
| `ADMIN_IDS` | твой и шефа Telegram user id через запятую |
| `DATABASE_URL` | ссылка на Postgres, обычно появляется сама |

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
5. В личке `@MRAB_SWE_bot` напиши `/kolla_kanal` — бот скажет, хватает ли прав.
6. Если всё «ja», напиши `/publicera_meny`.

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
| `/kolla_kanal` «inte klar» | В `@abmrab` добавь `@MRAB_SWE_bot` админом с Post / Edit / Pin |
| Пост после `/redigera` не уходит в канал | Бот админ `@abmrab`. Нажми **Publicera i kanalen** или `/kolla_kanal` |
| Меню не публикуется | Бот добавлен админом канала `@abmrab` и может постить |
| Меню опубликовано, но не закреплено | Включи боту право Pin Messages |
| Кнопка в канале открывает бота, но пусто | Бот не запущен или токен от другого бота |
| Конфликт `getUpdates` / 409 | Второй экземпляр с тем же токеном: локально + Railway, два сервиса или два реплики |
| Тема без картинки | В логах `Баннеры отсутствуют`. Проверь имя файла в `banners/` |
| `/redigera` «inte behörighet» | Твой id нет в `ADMIN_IDS`. Проверь `@userinfobot` |
| Бот не стартует, нет `DATABASE_URL` | Добавь Postgres к проекту Railway |

Логи смотри в том же окне терминала: ошибки публикации пишутся с текстом исключения.
