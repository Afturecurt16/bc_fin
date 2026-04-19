# Finclub Telegram Bot

Telegram-бот для нетворкинга, знакомств по интересам и обмена контактами. Проект реализован на `aiogram` с хранением данных в `SQLite` и готовым запуском через `Docker`.

## Что умеет бот

- обязательная пошаговая регистрация при первом входе
- все поля можно заполнить значением или пропустить через `-` / `нет`
- профиль пользователя с фото, статусом и ручным редактированием полей
- блок `Кого я ищу` с настройкой критериев поиска
- рекомендации подходящих анкет
- отправка запроса на знакомство
- входящие запросы на знакомство: принять или отклонить
- мэтчи и переписка после принятия запроса
- настройки приватности
- жалобы и тикеты поддержки
- простая LinkedIn-верификация через админа
- админ-панель `/admin`
- добавление новых админов по `@username`

## Что значит "запрос на знакомство"

Раньше в интерфейсе использовалось слово `интро`. В текущей версии для пользователя это называется `запрос на знакомство`.

Смысл такой:

- один пользователь отправляет другому запрос на знакомство
- получатель видит этот запрос во входящих
- если получатель принимает запрос, создается мэтч
- после этого пользователи могут общаться в боте

## Стек

- Python 3.11+
- `aiogram`
- SQLite
- Docker / Docker Compose

## Структура проекта

- [main.py](/C:/Users/ilyag/PycharmProjects/Finclub/main.py) — точка входа
- [app/bot.py](/C:/Users/ilyag/PycharmProjects/Finclub/app/bot.py) — роутеры, тексты, сценарии бота
- [app/db.py](/C:/Users/ilyag/PycharmProjects/Finclub/app/db.py) — работа с SQLite и бизнес-логика
- [app/keyboards.py](/C:/Users/ilyag/PycharmProjects/Finclub/app/keyboards.py) — reply и inline клавиатуры
- [app/states.py](/C:/Users/ilyag/PycharmProjects/Finclub/app/states.py) — FSM-состояния
- [Dockerfile](/C:/Users/ilyag/PycharmProjects/Finclub/Dockerfile) — сборка контейнера
- [docker-compose.yml](/C:/Users/ilyag/PycharmProjects/Finclub/docker-compose.yml) — локальный запуск в Docker

## Переменные окружения

Создайте файл `.env` на основе `.env.example`.

Минимально нужно указать:

```env
BOT_TOKEN=your_telegram_bot_token
```

Опционально:

```env
ADMIN_IDS=123456789,987654321
```

`ADMIN_IDS` — стартовый список админов. После запуска новые админы могут добавляться через `/admin` по `@username`.

## Локальный запуск

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Запуск через Docker

```bash
cp .env.example .env
docker compose up --build -d
```

На Windows:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Проверка статуса:

```powershell
docker compose ps
```

Логи:

```powershell
docker compose logs --tail=200
```

## База данных

SQLite-база хранится в файле:

`./data/bot.db`

Если нужно полностью сбросить данные:

1. Остановите бота.
2. Удалите файл `data/bot.db`.
3. Запустите проект заново.

После этого база создастся заново с пустыми таблицами.

## Админка

Поддерживаемые команды:

- `/admin`
- `/admin_stats`
- `/admin_pending_linkedin`

Через `/admin` доступны:

- сводка по системе
- очередь LinkedIn-заявок
- очередь жалоб и тикетов
- обработка жалоб
- управление администраторами
- добавление новых админов по `@username`

В жалобах админ видит:

- кто отправил жалобу
- на кого отправлена жалоба
- на что именно пожаловались
- текст сообщения или контент жалобы, если он доступен

## Внешние ссылки

- на шаге регистрации можно указать ссылки на резюме или портфолио
- в своем профиле ссылки отображаются сразу
- в чужих анкетах ссылки открываются через отдельную кнопку
- перед первым переходом по чужим внешним ссылкам пользователь видит предупреждение

## Примечания

- фото профиля хранится как `file_id` Telegram
- статусы профиля отображаются на русском
- изменение статуса выполняется через inline-кнопки под сообщением
