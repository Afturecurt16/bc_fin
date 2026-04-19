from __future__ import annotations

from urllib.parse import urlparse

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


VISIBILITY_LABELS = {
    "all": "Виден везде",
    "recommendations_only": "Только в рекомендациях",
    "intro_only": "Только по запросам",
    "hidden": "Скрыт",
}


INTRO_POLICY_LABELS = {
    "all": "Все пользователи",
    "matching_only": "Только подходящие анкеты",
    "linkedin_only": "Только с подтвержденным LinkedIn",
}


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мой профиль"), KeyboardButton(text="Кого я ищу")],
            [KeyboardButton(text="Рекомендации"), KeyboardButton(text="Входящие интро")],
            [KeyboardButton(text="Мои мэтчи"), KeyboardButton(text="Приватность")],
            [KeyboardButton(text="LinkedIn"), KeyboardButton(text="Поддержка")],
        ],
        resize_keyboard=True,
    )


def profile_keyboard(has_links: bool = False, open_to_intro: bool = False) -> InlineKeyboardMarkup:
    requests_label = "Запросы: вкл" if open_to_intro else "Запросы: выкл"
    rows = [
            [
                InlineKeyboardButton(text="Имя", callback_data="profile:edit:name"),
                InlineKeyboardButton(text="Роль", callback_data="profile:edit:role"),
            ],
            [
                InlineKeyboardButton(text="Индустрия", callback_data="profile:edit:industry"),
                InlineKeyboardButton(text="Локация", callback_data="profile:edit:location"),
            ],
            [
                InlineKeyboardButton(text="Био", callback_data="profile:edit:bio"),
                InlineKeyboardButton(text="Языки", callback_data="profile:edit:languages"),
            ],
            [
                InlineKeyboardButton(text="Компания", callback_data="profile:edit:company"),
                InlineKeyboardButton(text="Навыки", callback_data="profile:edit:skills"),
            ],
            [
                InlineKeyboardButton(text="Ссылки", callback_data="profile:edit:links"),
                InlineKeyboardButton(text="Аватар", callback_data="profile:edit:avatar"),
            ],
            [InlineKeyboardButton(text="Статус", callback_data="profile:status_menu")],
        ]
    if has_links:
        rows.append([InlineKeyboardButton(text="Открыть ссылки", callback_data="links:open:profile")])
    rows[-1].append(InlineKeyboardButton(text=requests_label, callback_data="profile:toggle:open"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Черновик", callback_data="profile:set_status:draft"),
                InlineKeyboardButton(text="Активный", callback_data="profile:set_status:active"),
                InlineKeyboardButton(text="Скрытый", callback_data="profile:set_status:hidden"),
            ],
            [InlineKeyboardButton(text="Назад к профилю", callback_data="profile:status_back")],
        ]
    )


def preferences_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Тип контакта", callback_data="pref:edit:contact_types"),
                InlineKeyboardButton(text="Индустрии", callback_data="pref:edit:industries"),
            ],
            [
                InlineKeyboardButton(text="Роли", callback_data="pref:edit:roles"),
                InlineKeyboardButton(text="География", callback_data="pref:edit:geography"),
            ],
            [
                InlineKeyboardButton(text="Формат", callback_data="pref:edit:formats"),
                InlineKeyboardButton(text="Темы", callback_data="pref:edit:topics"),
            ],
            [InlineKeyboardButton(text="Прием запросов на знакомство", callback_data="pref:toggle:open")],
        ]
    )


def recommendation_keyboard(candidate_id: int, has_links: bool = False) -> InlineKeyboardMarkup:
    rows = [
            [
                InlineKeyboardButton(text="Отправить интро", callback_data=f"rec:intro:{candidate_id}"),
                InlineKeyboardButton(text="Пропустить", callback_data=f"rec:skip:{candidate_id}"),
            ],
            [InlineKeyboardButton(text="Пожаловаться", callback_data=f"rec:report:{candidate_id}")],
        ]
    if has_links:
        rows.insert(1, [InlineKeyboardButton(text="Открыть ссылки", callback_data=f"links:open:rec:{candidate_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def intro_item_keyboard(intro_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Принять", callback_data=f"intro:accept:{intro_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"intro:decline:{intro_id}"),
            ],
            [InlineKeyboardButton(text="Пожаловаться", callback_data=f"intro:report:{intro_id}")],
        ]
    )


def match_actions_keyboard(match_id: int, match_status: str) -> InlineKeyboardMarkup:
    mute_label = "Размьютить" if match_status == "muted" else "Замьютить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Написать", callback_data=f"match:message:{match_id}")],
            [InlineKeyboardButton(text=mute_label, callback_data=f"match:toggle_mute:{match_id}")],
            [
                InlineKeyboardButton(text="Скрыть", callback_data=f"match:close:{match_id}"),
                InlineKeyboardButton(text="Заблокировать", callback_data=f"match:block:{match_id}"),
            ],
        ]
    )


def privacy_keyboard(current_intro_policy: str, current_visibility: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Видимость: {current_visibility}", callback_data="privacy:cycle:visibility")],
            [InlineKeyboardButton(text=f"Кто может отправлять запрос: {current_intro_policy}", callback_data="privacy:cycle:intro")],
            [
                InlineKeyboardButton(text="Показывать компанию", callback_data="privacy:toggle:company"),
                InlineKeyboardButton(text="Показывать LinkedIn", callback_data="privacy:toggle:linkedin"),
            ],
            [
                InlineKeyboardButton(text="Показывать город", callback_data="privacy:toggle:location"),
                InlineKeyboardButton(text="Только после мэтча", callback_data="privacy:toggle:messages"),
            ],
        ]
    )


def privacy_keyboard(current_intro_policy: str, current_visibility: str) -> InlineKeyboardMarkup:
    visibility_label = VISIBILITY_LABELS.get(current_visibility, current_visibility)
    intro_policy_label = INTRO_POLICY_LABELS.get(current_intro_policy, current_intro_policy)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Видимость анкеты: {visibility_label}", callback_data="privacy:cycle:visibility")],
            [InlineKeyboardButton(text=f"Кто может отправлять запросы: {intro_policy_label}", callback_data="privacy:cycle:intro")],
            [
                InlineKeyboardButton(text="Показывать компанию", callback_data="privacy:toggle:company"),
                InlineKeyboardButton(text="Показывать LinkedIn", callback_data="privacy:toggle:linkedin"),
            ],
            [
                InlineKeyboardButton(text="Показывать город", callback_data="privacy:toggle:location"),
                InlineKeyboardButton(text="Только после мэтча", callback_data="privacy:toggle:messages"),
            ],
        ]
    )


def linkedin_keyboard(status: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Статус: {status}", callback_data="linkedin:noop")],
            [InlineKeyboardButton(text="Указать URL профиля", callback_data="linkedin:start")],
        ]
    )


def linkedin_keyboard(status: str, has_url: bool = False) -> InlineKeyboardMarkup:
    status_label = {
        "not_started": "Не отправлен",
        "pending": "На модерации",
        "verified": "Подтвержден",
        "failed": "Отклонен",
    }.get(status, status)
    action_label = "Изменить URL профиля" if has_url else "Указать URL профиля"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Статус: {status_label}", callback_data="linkedin:noop")],
            [InlineKeyboardButton(text=action_label, callback_data="linkedin:start")],
        ]
    )


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Написать в поддержку", callback_data="support:create")],
        ]
    )


def message_report_keyboard(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пожаловаться на сообщение", callback_data=f"msg:report:{message_id}")]
        ]
    )


def linkedin_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Подтвердить", callback_data=f"admin:linkedin:verify:{user_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"admin:linkedin:fail:{user_id}"),
            ]
        ]
    )


def admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Статистика", callback_data="admin:menu:stats"),
                InlineKeyboardButton(text="LinkedIn", callback_data="admin:menu:linkedin"),
            ],
            [
                InlineKeyboardButton(text="Жалобы", callback_data="admin:menu:complaints"),
                InlineKeyboardButton(text="Админы", callback_data="admin:menu:admins"),
            ],
            [
                InlineKeyboardButton(text="Обновить", callback_data="admin:menu:home"),
            ],
        ]
    )


def admin_complaint_keyboard(complaint_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Закрыть", callback_data=f"admin:complaint:resolve:{complaint_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"admin:complaint:dismiss:{complaint_id}"),
            ],
            [InlineKeyboardButton(text="Назад в админку", callback_data="admin:menu:home")],
        ]
    )


def admin_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить админа", callback_data="admin:admins:add_prompt")],
            [InlineKeyboardButton(text="Назад в админку", callback_data="admin:menu:home")],
        ]
    )


def external_links_warning_keyboard(context: str, target_id: int | None = None) -> InlineKeyboardMarkup:
    suffix = f":{target_id}" if target_id is not None else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтверждаю", callback_data=f"links:confirm:{context}{suffix}")],
            [InlineKeyboardButton(text="Отмена", callback_data="links:cancel")],
        ]
    )


def external_links_keyboard(urls: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, url in enumerate(urls, start=1):
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path or f"Ссылка {index}"
        label = host[:40]
        rows.append([InlineKeyboardButton(text=label, url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
