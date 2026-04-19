from __future__ import annotations

import asyncio
import logging
import re
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.config import Settings
from app.db import Database
from app.keyboards import (
    admin_complaint_keyboard,
    admin_dashboard_keyboard,
    admin_management_keyboard,
    external_links_keyboard,
    external_links_warning_keyboard,
    intro_item_keyboard,
    linkedin_admin_keyboard,
    linkedin_keyboard,
    main_menu_keyboard,
    match_actions_keyboard,
    message_report_keyboard,
    preferences_keyboard,
    privacy_keyboard,
    profile_keyboard,
    profile_status_keyboard,
    recommendation_keyboard,
    support_keyboard,
)
from app.states import (
    AdminStates,
    IntroStates,
    LinkedinStates,
    MatchMessageStates,
    PreferenceStates,
    ProfileStates,
    RegistrationStates,
    SupportStates,
)


logger = logging.getLogger(__name__)


PROFILE_STATUS_LABELS = {
    "draft": "Черновик",
    "active": "Активный",
    "hidden": "Скрытый",
}


def extract_links(raw_links: str | None) -> list[str]:
    if not raw_links or raw_links.strip() in {"", "-"}:
        return []
    parts = [chunk.strip() for chunk in re.split(r"[\s,;]+", raw_links) if chunk.strip()]
    result: list[str] = []
    for item in parts:
        normalized = item
        if not re.match(r"^https?://", normalized, flags=re.IGNORECASE):
            if "." not in normalized:
                continue
            normalized = f"https://{normalized}"
        result.append(normalized)
    return result


def has_external_links(raw_links: str | None) -> bool:
    return bool(extract_links(raw_links))


VISIBILITY_LABELS = {
    "all": "Виден везде",
    "recommendations_only": "Только в рекомендациях",
    "intro_only": "Только по запросам на знакомство",
    "hidden": "Скрыт",
}


INTRO_POLICY_LABELS = {
    "all": "Все пользователи",
    "matching_only": "Только подходящие анкеты",
    "linkedin_only": "Только с подтвержденным LinkedIn",
}


LINKEDIN_STATUS_LABELS = {
    "not_started": "Не отправлен",
    "pending": "На модерации",
    "verified": "Подтвержден",
    "failed": "Отклонен",
}


def admin_stats_text(stats: dict) -> str:
    lines = ["<b>MVP статистика</b>"]
    for key, value in stats.items():
        lines.append(f"{escape(key)}: <code>{value}</code>")
    return "\n".join(lines)


def admin_home_text(stats: dict, pending_linkedin: int, open_complaints: int) -> str:
    return (
        "<b>Админ-панель</b>\n"
        f"Активных профилей: <code>{stats['active_profiles']}</code>\n"
        f"Открытых жалоб/тикетов: <code>{open_complaints}</code>\n"
        f"Pending LinkedIn: <code>{pending_linkedin}</code>\n"
        f"Интро отправлено: <code>{stats['intros_sent']}</code>\n"
        f"Мэтчей создано: <code>{stats['matches_created']}</code>"
    )


def admin_management_text(admins: list[dict]) -> str:
    lines = ["<b>Управление администраторами</b>"]
    if not admins:
        lines.append("Администраторы пока не найдены.")
        return "\n".join(lines)
    for item in admins:
        username = item.get("username")
        display_name = item.get("display_name") or "—"
        tg_user_id = item.get("tg_user_id")
        status = "активен" if tg_user_id else "ждет первого входа"
        tag = f"@{escape(username)}" if username else f"<code>{tg_user_id}</code>"
        lines.append(f"{tag} • {escape(display_name)} • {status}")
    return "\n".join(lines)


def admin_complaint_text(item: dict) -> str:
    return (
        "<b>Жалоба / тикет</b>\n"
        f"ID: <code>{item['id']}</code>\n"
        f"Статус: <code>{item.get('status') or 'open'}</code>\n"
        f"Тип: <code>{escape(item['target_type'])}</code>\n"
        f"Причина: <code>{escape(item['reason'])}</code>\n"
        f"Target ID: <code>{item['target_id'] if item['target_id'] is not None else '—'}</code>\n"
        f"От: {escape(item.get('reporter_name') or '—')} "
        f"(<code>{item.get('reporter_tg_user_id') or '—'}</code>)\n"
        f"Комментарий: {escape(item.get('comment') or '—')}"
    )


PROFILE_FIELD_PROMPTS = {
    "name": ("display_name", ProfileStates.waiting_name, "Укажи своё ФИО."),
    "role": ("role", ProfileStates.waiting_role, "Введите роль или должность."),
    "industry": ("industry", ProfileStates.waiting_industry, "Введите индустрию."),
    "location": ("location", ProfileStates.waiting_location, "Укажи свой город."),
    "bio": ("bio", ProfileStates.waiting_bio, "Напишите короткое био."),
    "languages": ("languages", ProfileStates.waiting_languages, "Укажите языки общения через запятую."),
    "company": ("company", ProfileStates.waiting_company, "Введите компанию."),
    "skills": ("skills", ProfileStates.waiting_skills, "Укажите навыки или теги через запятую."),
    "links": ("external_links", ProfileStates.waiting_links, "Добавьте внешние ссылки на резюме или портфолио."),
    "avatar": ("avatar_file_id", ProfileStates.waiting_avatar, "Отправьте фотографию для аватара."),
}


PREFERENCE_FIELD_PROMPTS = {
    "contact_types": (
        PreferenceStates.waiting_contact_types,
        "Укажи типы контактов через запятую: наставник, ученик, кофаундер, рекрутер, коллега, клиент, партнёр.",
    ),
    "industries": (PreferenceStates.waiting_industries, "Какие индустрии вам интересны?"),
    "roles": (PreferenceStates.waiting_roles, "Какие роли вы ищете?"),
    "geography": (PreferenceStates.waiting_geography, "Укажите географию поиска."),
    "formats": (PreferenceStates.waiting_formats, "Форматы взаимодействия: чат, звонок, офлайн и т.д."),
    "topics": (PreferenceStates.waiting_topics, "Укажите темы интереса через запятую."),
}


REGISTRATION_STEPS = [
    {
        "kind": "profile",
        "field": "display_name",
        "prompt": "Укажи своё ФИО",
    },
    {
        "kind": "profile",
        "field": "role",
        "prompt": "Укажи свою роль или должность",
    },
    {
        "kind": "profile",
        "field": "industry",
        "prompt": "Укажи свою индустрию",
    },
    {
        "kind": "profile",
        "field": "location",
        "prompt": "Укажи свой город",
    },
    {
        "kind": "profile",
        "field": "bio",
        "prompt": "Расскажи коротко о себе",
    },
    {
        "kind": "profile",
        "field": "languages",
        "prompt": "Укажи языки общения через запятую",
    },
    {
        "kind": "profile",
        "field": "company",
        "prompt": "Укажи компанию",
    },
    {
        "kind": "profile",
        "field": "skills",
        "prompt": "Перечисли навыки или теги через запятую",
    },
    {
        "kind": "profile",
        "field": "external_links",
        "prompt": "Добавьте внешние ссылки на резюме или портфолио",
    },
    {
        "kind": "profile",
        "field": "avatar_file_id",
        "type": "avatar",
        "prompt": "Отправь фото для аватара",
    },
    {
        "kind": "preference",
        "field": "contact_types",
        "prompt": "Укажи, кого ты ищешь: наставник, ученик, кофаундер, рекрутер, коллега, клиент, партнёр",
    },
    {
        "kind": "preference",
        "field": "industries",
        "prompt": "Укажи интересующие индустрии",
    },
    {
        "kind": "preference",
        "field": "roles",
        "prompt": "Укажи интересующие роли",
    },
    {
        "kind": "preference",
        "field": "geography",
        "prompt": "Укажи географию поиска",
    },
    {
        "kind": "preference",
        "field": "interaction_formats",
        "prompt": "Укажи удобный формат общения: чат, звонок или офлайн",
    },
    {
        "kind": "preference",
        "field": "topics",
        "prompt": "Перечисли темы, которые тебе интересны",
    },
]


def profile_summary(profile: dict, linkedin: dict | None) -> str:
    linkedin_status = linkedin["status"] if linkedin else "not_started"
    status_label = PROFILE_STATUS_LABELS.get(profile.get("profile_status"), profile.get("profile_status") or "—")
    links_line = "доступны по кнопке" if has_external_links(profile.get("external_links")) else "—"
    return (
        "<b>Мой профиль</b>\n"
        f"Статус: <code>{status_label}</code>\n"
        f"Имя: {escape(profile.get('display_name') or '—')}\n"
        f"Роль: {escape(profile.get('role') or '—')}\n"
        f"Индустрия: {escape(profile.get('industry') or '—')}\n"
        f"Локация: {escape(profile.get('location') or '—')}\n"
        f"Био: {escape(profile.get('bio') or '—')}\n"
        f"Языки: {escape(profile.get('languages') or '—')}\n"
        f"Компания: {escape(profile.get('company') or '—')}\n"
        f"Навыки: {escape(profile.get('skills') or '—')}\n"
        f"Ссылки: {links_line}\n"
        f"LinkedIn: <code>{linkedin_status}</code>\n"
        f"Принимаю запросы на знакомство: {'да' if int(profile.get('open_to_intro') or 0) else 'нет'}"
    )


def profile_summary(profile: dict, linkedin: dict | None) -> str:
    status_label = PROFILE_STATUS_LABELS.get(profile.get("profile_status"), profile.get("profile_status") or "—")
    links = extract_links(profile.get("external_links"))
    links_line = "—" if not links else "\n".join(
        f'<a href="{escape(url, quote=True)}">{escape(url)}</a>' for url in links
    )
    return (
        "<b>Мой профиль</b>\n"
        f"Статус: <code>{status_label}</code>\n"
        f"Имя: {escape(profile.get('display_name') or '—')}\n"
        f"Роль: {escape(profile.get('role') or '—')}\n"
        f"Индустрия: {escape(profile.get('industry') or '—')}\n"
        f"Локация: {escape(profile.get('location') or '—')}\n"
        f"Био: {escape(profile.get('bio') or '—')}\n"
        f"Языки: {escape(profile.get('languages') or '—')}\n"
        f"Компания: {escape(profile.get('company') or '—')}\n"
        f"Навыки: {escape(profile.get('skills') or '—')}\n"
        f"Ссылки: {links_line}\n"
        f"Принимаю запросы на знакомство: {'да' if int(profile.get('open_to_intro') or 0) else 'нет'}"
    )


def preference_summary(preferences: dict | None, profile: dict | None) -> str:
    preferences = preferences or {}
    profile = profile or {}
    return (
        "<b>Кого я ищу</b>\n"
        f"Типы контактов: {escape(preferences.get('contact_types') or '—')}\n"
        f"Индустрии: {escape(preferences.get('industries') or '—')}\n"
        f"Роли: {escape(preferences.get('roles') or '—')}\n"
        f"География: {escape(preferences.get('geography') or '—')}\n"
        f"Формат: {escape(preferences.get('interaction_formats') or '—')}\n"
        f"Темы: {escape(preferences.get('topics') or '—')}\n"
        f"Принимаю запросы на знакомство: {'да' if int(profile.get('open_to_intro') or 0) else 'нет'}"
    )


def privacy_summary(privacy: dict) -> str:
    return (
        "<b>Приватность</b>\n"
        f"Видимость: <code>{privacy['visibility']}</code>\n"
        f"Кто может отправлять запросы на знакомство: <code>{privacy['who_can_intro']}</code>\n"
        f"Показывать компанию: {'да' if int(privacy['show_company']) else 'нет'}\n"
        f"Показывать LinkedIn: {'да' if int(privacy['show_linkedin']) else 'нет'}\n"
        f"Показывать город: {'да' if int(privacy['show_location']) else 'нет'}\n"
        f"Сообщения только после мэтча: {'да' if int(privacy['messages_after_match']) else 'нет'}"
    )


def privacy_summary(privacy: dict) -> str:
    visibility_label = VISIBILITY_LABELS.get(privacy["visibility"], privacy["visibility"])
    intro_policy_label = INTRO_POLICY_LABELS.get(privacy["who_can_intro"], privacy["who_can_intro"])
    return (
        "<b>Приватность</b>\n"
        f"Видимость анкеты: <code>{visibility_label}</code>\n"
        f"Кто может отправлять запросы на знакомство: <code>{intro_policy_label}</code>\n"
        f"Показывать компанию: {'да' if int(privacy['show_company']) else 'нет'}\n"
        f"Показывать LinkedIn: {'да' if int(privacy['show_linkedin']) else 'нет'}\n"
        f"Показывать город: {'да' if int(privacy['show_location']) else 'нет'}\n"
        f"Сообщения только после мэтча: {'да' if int(privacy['messages_after_match']) else 'нет'}"
    )


def candidate_card(candidate: dict) -> str:
    verified_badge = " ✅ LinkedIn verified" if candidate.get("linkedin_status") == "verified" else ""
    company_line = f"\nКомпания: {escape(candidate.get('company') or '—')}" if int(candidate.get("show_company") or 0) else ""
    location_line = f"\nЛокация: {escape(candidate.get('location') or '—')}" if int(candidate.get("show_location") or 0) else ""
    linkedin_line = f"\nLinkedIn: {escape(candidate.get('linkedin_url') or '—')}" if int(candidate.get("show_linkedin") or 0) else ""
    links_line = "\nСсылки: доступны по кнопке" if has_external_links(candidate.get("external_links")) else ""
    return (
        "<b>Рекомендация</b>\n"
        f"{escape(candidate.get('display_name') or 'Без имени')}{verified_badge}\n"
        f"Роль: {escape(candidate.get('role') or '—')}\n"
        f"Индустрия: {escape(candidate.get('industry') or '—')}"
        f"{company_line}"
        f"{location_line}\n"
        f"Био: {escape(candidate.get('bio') or '—')}\n"
        f"Языки: {escape(candidate.get('languages') or '—')}{linkedin_line}{links_line}\n"
        f"Скоринг: <code>{candidate.get('score')}</code>"
    )


def intro_summary(intro: dict) -> str:
    return (
        "<b>Входящее интро</b>\n"
        f"От: {escape(intro.get('sender_name') or '—')}\n"
        f"Роль: {escape(intro.get('sender_role') or '—')}\n"
        f"Индустрия: {escape(intro.get('sender_industry') or '—')}\n"
        f"Статус: <code>{intro.get('status')}</code>\n\n"
        f"{escape(intro.get('intro_text') or '')}"
    )


def match_summary(match: dict) -> str:
    return (
        "<b>Мэтч</b>\n"
        f"Контакт: {escape(match.get('partner_name') or '—')}\n"
        f"Роль: {escape(match.get('partner_role') or '—')}\n"
        f"Статус: <code>{match.get('status')}</code>"
    )


def build_router(settings: Settings, db: Database) -> Dispatcher:
    dp = Dispatcher()
    db.seed_admin_ids(settings.admin_ids)

    async def send_main_menu(message: Message, text: str) -> None:
        await message.answer(text, reply_markup=main_menu_keyboard())

    async def send_links_message(message: Message, title: str, raw_links: str | None) -> None:
        links = extract_links(raw_links)
        if not links:
            await message.answer("Ссылки не указаны.")
            return
        await message.answer(
            title,
            reply_markup=external_links_keyboard(links),
        )

    async def send_card(
        message: Message,
        text: str,
        avatar_file_id: str | None = None,
        reply_markup=None,
    ) -> None:
        if avatar_file_id and avatar_file_id != "-":
            await message.answer_photo(
                photo=avatar_file_id,
                caption=text,
                reply_markup=reply_markup,
            )
            return
        await message.answer(text, reply_markup=reply_markup)

    async def replace_card(
        message: Message,
        text: str,
        avatar_file_id: str | None = None,
        reply_markup=None,
    ) -> None:
        try:
            await message.delete()
        except Exception:
            logger.exception("Failed to delete old card message")
        await send_card(
            message=message,
            text=text,
            avatar_file_id=avatar_file_id,
            reply_markup=reply_markup,
        )

    def normalize_registration_text(value: str) -> str:
        cleaned = value.strip()
        return "-" if cleaned.lower() in {"-", "нет"} else cleaned

    async def prompt_registration_step(message: Message, state: FSMContext, step_index: int) -> None:
        step = REGISTRATION_STEPS[step_index]
        total = len(REGISTRATION_STEPS)
        await state.update_data(registration_step=step_index)
        if step.get("type") == "avatar":
            await state.set_state(RegistrationStates.waiting_avatar)
        else:
            await state.set_state(RegistrationStates.waiting_text)
        intro = ""
        if step_index == 0:
            intro = (
                "<b>Добро пожаловать!</b>\n\n"
                "Я помогу тебе заполнить профиль для нетворкинга\n"
                "и найти релевантные знакомства.\n\n"
            )
        await message.answer(
            (
                f"{intro}"
                f"<b>Шаг {step_index + 1} из {total}</b>\n\n"
                f"<blockquote>{step['prompt']}</blockquote>\n\n"
                "Если данных нет, отправь <code>-</code> или <code>нет</code>."
            ),
            reply_markup=ReplyKeyboardRemove(),
        )

    async def finish_registration(message: Message, state: FSMContext) -> None:
        db.set_profile_status(message.from_user.id, "active")
        db.record_event(message.from_user.id, "onboarding_completed")
        await state.clear()
        await send_main_menu(
            message,
            "Регистрация завершена. Профиль активирован, теперь доступно главное меню.",
        )

    async def start_registration(message: Message, state: FSMContext) -> None:
        await state.clear()
        await prompt_registration_step(message, state, 0)

    async def ensure_registration(message: Message, state: FSMContext) -> bool:
        if db.is_registration_complete(message.from_user.id):
            return True
        await start_registration(message, state)
        return False

    async def notify_admins(bot: Bot, text: str, reply_markup=None) -> None:
        admin_ids = db.get_admin_ids()
        if not admin_ids:
            return
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, text, reply_markup=reply_markup)
            except Exception:
                logger.exception("Failed to notify admin %s", admin_id)

    def is_admin(user_id: int, username: str | None = None) -> bool:
        return db.is_admin_user(user_id, username)

    def user_tag(tg_user_id: int | None, username: str | None, display_name: str | None) -> str:
        if username:
            return f"@{escape(username)}"
        if tg_user_id:
            label = escape(display_name or f"user_{tg_user_id}")
            return f"<a href=\"tg://user?id={tg_user_id}\">{label}</a>"
        return escape(display_name or "—")

    def complaint_detail_text(item: dict) -> str:
        reporter = user_tag(
            item.get("reporter_tg_user_id"),
            item.get("reporter_username"),
            item.get("reporter_name"),
        )
        lines = [
            "<b>Жалоба / тикет</b>",
            f"ID: <code>{item['id']}</code>",
            f"Статус: <code>{item.get('status') or 'open'}</code>",
            f"Тип: <code>{escape(item['target_type'])}</code>",
            f"Причина: <code>{escape(item['reason'])}</code>",
            f"От кого: {reporter}",
            f"Комментарий: {escape(item.get('comment') or '—')}",
        ]

        target_type = item.get("target_type")
        target_id = item.get("target_id")

        if target_type == "profile" and target_id is not None:
            target = db.get_user_by_internal_id(int(target_id))
            if target:
                lines.extend(
                    [
                        f"На кого: {user_tag(target.get('tg_user_id'), target.get('username'), target.get('display_name'))}",
                        (
                            "На что: профиль\n"
                            f"Роль: {escape(target.get('role') or '—')}\n"
                            f"Индустрия: {escape(target.get('industry') or '—')}\n"
                            f"Био: {escape(target.get('bio') or '—')}"
                        ),
                    ]
                )
            else:
                lines.append(f"На что: профиль <code>{target_id}</code>")
        elif target_type == "intro" and target_id is not None:
            intro = db.get_intro(int(target_id))
            if intro:
                lines.extend(
                    [
                        f"На кого: {user_tag(intro.get('sender_tg_user_id'), intro.get('sender_username'), intro.get('sender_name'))}",
                        (
                            "На что: интро\n"
                            f"Кому: {user_tag(intro.get('recipient_tg_user_id'), intro.get('recipient_username'), intro.get('recipient_name'))}\n"
                            f"Текст интро: {escape(intro.get('intro_text') or '—')}"
                        ),
                    ]
                )
            else:
                lines.append(f"На что: интро <code>{target_id}</code>")
        elif target_type == "message" and target_id is not None:
            target_message = db.get_message_detail(int(target_id))
            if target_message:
                lines.extend(
                    [
                        f"На кого: {user_tag(target_message.get('sender_tg_user_id'), target_message.get('sender_username'), target_message.get('sender_name'))}",
                        (
                            "На что: сообщение\n"
                            f"Кому: {user_tag(target_message.get('recipient_tg_user_id'), target_message.get('recipient_username'), target_message.get('recipient_name'))}\n"
                            f"Текст сообщения: {escape(target_message.get('content') or '—')}"
                        ),
                    ]
                )
            else:
                lines.append(f"На что: сообщение <code>{target_id}</code>")
        elif target_type == "support":
            lines.append("На что: тикет в поддержку")
        else:
            lines.append(f"Target ID: <code>{target_id if target_id is not None else '—'}</code>")

        return "\n".join(lines)

    async def render_admin_home_message(message: Message) -> None:
        stats = db.get_dashboard_stats()
        pending_linkedin = len(db.pending_linkedin_requests())
        open_complaints = len(db.list_open_complaints(limit=100))
        await message.answer(
            admin_home_text(stats, pending_linkedin, open_complaints),
            reply_markup=admin_dashboard_keyboard(),
        )

    async def render_admin_home_callback(callback: CallbackQuery) -> None:
        stats = db.get_dashboard_stats()
        pending_linkedin = len(db.pending_linkedin_requests())
        open_complaints = len(db.list_open_complaints(limit=100))
        await callback.message.edit_text(
            admin_home_text(stats, pending_linkedin, open_complaints),
            reply_markup=admin_dashboard_keyboard(),
        )

    async def render_admin_management_message(message: Message) -> None:
        await message.answer(
            admin_management_text(db.list_admins()),
            reply_markup=admin_management_keyboard(),
        )

    async def render_admin_management_callback(callback: CallbackQuery) -> None:
        await callback.message.edit_text(
            admin_management_text(db.list_admins()),
            reply_markup=admin_management_keyboard(),
        )

    async def send_pending_linkedin_queue(message: Message) -> None:
        pending = db.pending_linkedin_requests()
        if not pending:
            await message.answer("Нет pending LinkedIn-заявок.")
            return
        for item in pending[:10]:
            await message.answer(
                (
                    "<b>Pending LinkedIn</b>\n"
                    f"User ID: <code>{item['id']}</code>\n"
                    f"Telegram: <code>{item['tg_user_id']}</code>\n"
                    f"Имя: {escape(item['display_name'] or '—')}\n"
                    f"URL: {escape(item['profile_url'] or '—')}"
                ),
                reply_markup=linkedin_admin_keyboard(int(item["id"])),
            )

    async def send_open_complaints_queue(message: Message) -> None:
        complaints = db.list_open_complaints(limit=10)
        if not complaints:
            await message.answer("Открытых жалоб и тикетов нет.")
            return
        for item in complaints:
            await message.answer(
                complaint_detail_text(item),
                reply_markup=admin_complaint_keyboard(int(item["id"])),
            )

    @dp.message(CommandStart())
    async def on_start(message: Message, state: FSMContext) -> None:
        db.upsert_telegram_user(
            tg_user_id=message.from_user.id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )
        db.record_event(message.from_user.id, "bot_started")
        if not db.is_registration_complete(message.from_user.id):
            await start_registration(message, state)
            return
        await send_main_menu(
            message,
            "Бот для нетворкинга запущен. Используйте кнопки меню для работы с профилем, рекомендациями и мэтчами.",
        )

    @dp.message(Command("admin"))
    async def admin_entry(message: Message) -> None:
        if not is_admin(message.from_user.id, message.from_user.username):
            await message.answer("Доступ запрещён.")
            return
        await render_admin_home_message(message)

    @dp.message(RegistrationStates.waiting_text)
    async def registration_text_step(message: Message, state: FSMContext) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Нужен текстовый ответ. Если хотите пропустить поле, отправьте `-` или `нет`.")
            return

        data = await state.get_data()
        step_index = int(data["registration_step"])
        step = REGISTRATION_STEPS[step_index]
        value = normalize_registration_text(message.text)

        if step["kind"] == "profile":
            db.update_profile_field(message.from_user.id, step["field"], value)
        else:
            db.update_preference_field(message.from_user.id, step["field"], value)

        next_step = step_index + 1
        if next_step >= len(REGISTRATION_STEPS):
            await finish_registration(message, state)
            return
        await prompt_registration_step(message, state, next_step)

    @dp.message(RegistrationStates.waiting_avatar, F.photo)
    async def registration_avatar_step(message: Message, state: FSMContext) -> None:
        photo = message.photo[-1]
        db.update_profile_field(message.from_user.id, "avatar_file_id", photo.file_id)
        data = await state.get_data()
        next_step = int(data["registration_step"]) + 1
        if next_step >= len(REGISTRATION_STEPS):
            await finish_registration(message, state)
            return
        await prompt_registration_step(message, state, next_step)

    @dp.message(RegistrationStates.waiting_avatar)
    async def registration_avatar_skip(message: Message, state: FSMContext) -> None:
        if not message.text or normalize_registration_text(message.text) != "-":
            await message.answer("Для аватара пришлите фото или отправьте `-` / `нет`.")
            return
        db.update_profile_field(message.from_user.id, "avatar_file_id", None)
        data = await state.get_data()
        next_step = int(data["registration_step"]) + 1
        if next_step >= len(REGISTRATION_STEPS):
            await finish_registration(message, state)
            return
        await prompt_registration_step(message, state, next_step)

    @dp.message(Command("admin_stats"))
    async def admin_stats(message: Message) -> None:
        if not is_admin(message.from_user.id, message.from_user.username):
            return
        await message.answer(
            admin_stats_text(db.get_dashboard_stats()),
            reply_markup=admin_dashboard_keyboard(),
        )

    @dp.message(Command("admin_pending_linkedin"))
    async def admin_pending_linkedin(message: Message) -> None:
        if not is_admin(message.from_user.id, message.from_user.username):
            return
        await send_pending_linkedin_queue(message)

    @dp.callback_query(F.data == "admin:menu:home")
    async def admin_menu_home(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await render_admin_home_callback(callback)
        await callback.answer()

    @dp.callback_query(F.data == "admin:menu:stats")
    async def admin_menu_stats(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await callback.message.edit_text(
            admin_stats_text(db.get_dashboard_stats()),
            reply_markup=admin_dashboard_keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data == "admin:menu:linkedin")
    async def admin_menu_linkedin(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        pending = db.pending_linkedin_requests()
        await callback.message.edit_text(
            (
                "<b>Очередь LinkedIn</b>\n"
                f"Pending заявок: <code>{len(pending)}</code>\n"
                "Карточки заявок отправлены ниже отдельными сообщениями."
            ),
            reply_markup=admin_dashboard_keyboard(),
        )
        await send_pending_linkedin_queue(callback.message)
        await callback.answer()

    @dp.callback_query(F.data == "admin:menu:complaints")
    async def admin_menu_complaints(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        complaints = db.list_open_complaints(limit=10)
        await callback.message.edit_text(
            (
                "<b>Очередь жалоб и тикетов</b>\n"
                f"Открытых элементов: <code>{len(complaints)}</code>\n"
                "Карточки очереди отправлены ниже отдельными сообщениями."
            ),
            reply_markup=admin_dashboard_keyboard(),
        )
        await send_open_complaints_queue(callback.message)
        await callback.answer()

    @dp.callback_query(F.data == "admin:menu:admins")
    async def admin_menu_admins(callback: CallbackQuery) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await render_admin_management_callback(callback)
        await callback.answer()

    @dp.callback_query(F.data == "admin:admins:add_prompt")
    async def admin_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        await state.clear()
        await state.set_state(AdminStates.waiting_admin_username)
        await callback.message.answer(
            "Отправьте тег нового администратора в формате `@username`.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await callback.answer()

    @dp.message(AdminStates.waiting_admin_username)
    async def admin_add_username(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id, message.from_user.username):
            await state.clear()
            await message.answer("Доступ запрещён.")
            return
        if not message.text or not message.text.strip().startswith("@"):
            await message.answer("Нужно отправить тег в формате `@username`.")
            return
        username = message.text.strip()
        added = db.add_admin_by_username(username, message.from_user.id)
        await state.clear()
        activation_note = (
            "Права уже активны."
            if added.get("tg_user_id")
            else "Права активируются, когда пользователь впервые напишет боту с этим username."
        )
        await message.answer(
            f"Администратор {escape(username)} добавлен.\n{activation_note}",
            reply_markup=admin_management_keyboard(),
        )

    @dp.callback_query(F.data.startswith("admin:complaint:"))
    async def admin_complaint_action(callback: CallbackQuery, bot: Bot) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        _, _, action, complaint_id_raw = callback.data.split(":")
        complaint_id = int(complaint_id_raw)
        complaint = db.get_complaint(complaint_id)
        if not complaint:
            await callback.answer("Жалоба не найдена.", show_alert=True)
            return

        new_status = "resolved" if action == "resolve" else "dismissed"
        db.update_complaint_status(complaint_id, new_status)
        updated = db.get_complaint(complaint_id)
        await callback.message.edit_text(
            complaint_detail_text(updated),
            reply_markup=admin_complaint_keyboard(complaint_id),
        )
        reporter_tg_user_id = updated.get("reporter_tg_user_id")
        if reporter_tg_user_id:
            await bot.send_message(
                reporter_tg_user_id,
                f"Ваше обращение #{complaint_id} обработано администратором. Статус: {new_status}.",
            )
        await callback.answer("Статус обновлён")

    @dp.message(F.text == "Мой профиль")
    async def show_profile(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        profile = db.get_user_profile(message.from_user.id)
        linkedin = db.get_linkedin(message.from_user.id)
        await send_card(
            message=message,
            text=profile_summary(profile, linkedin),
            avatar_file_id=profile.get("avatar_file_id"),
            reply_markup=profile_keyboard(open_to_intro=bool(int(profile.get("open_to_intro") or 0))),
        )

    @dp.callback_query(F.data.startswith("profile:edit:"))
    async def profile_edit(callback: CallbackQuery, state: FSMContext) -> None:
        field_key = callback.data.split(":")[-1]
        _, state_name, prompt = PROFILE_FIELD_PROMPTS[field_key]
        await state.clear()
        await state.set_state(state_name)
        await state.update_data(profile_field=PROFILE_FIELD_PROMPTS[field_key][0])
        await callback.message.answer(prompt)
        await callback.answer()

    @dp.callback_query(F.data == "profile:status_menu")
    async def profile_status_menu(callback: CallbackQuery) -> None:
        profile = db.get_user_profile(callback.from_user.id)
        linkedin = db.get_linkedin(callback.from_user.id)
        await replace_card(
            message=callback.message,
            text=profile_summary(profile, linkedin) + "\n\nВыберите новый статус:",
            avatar_file_id=profile.get("avatar_file_id"),
            reply_markup=profile_status_keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data == "profile:status_back")
    async def profile_status_back(callback: CallbackQuery) -> None:
        profile = db.get_user_profile(callback.from_user.id)
        linkedin = db.get_linkedin(callback.from_user.id)
        await replace_card(
            message=callback.message,
            text=profile_summary(profile, linkedin),
            avatar_file_id=profile.get("avatar_file_id"),
            reply_markup=profile_keyboard(open_to_intro=bool(int(profile.get("open_to_intro") or 0))),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("profile:set_status:"))
    async def profile_set_status(callback: CallbackQuery) -> None:
        new_status = callback.data.split(":")[-1]
        db.set_profile_status(callback.from_user.id, new_status)
        profile = db.get_user_profile(callback.from_user.id)
        linkedin = db.get_linkedin(callback.from_user.id)
        await replace_card(
            message=callback.message,
            text=profile_summary(profile, linkedin),
            avatar_file_id=profile.get("avatar_file_id"),
            reply_markup=profile_keyboard(open_to_intro=bool(int(profile.get("open_to_intro") or 0))),
        )
        await callback.answer(f"Статус: {PROFILE_STATUS_LABELS.get(new_status, new_status)}")

    @dp.callback_query(F.data == "profile:toggle:open")
    async def profile_toggle_open_to_intro(callback: CallbackQuery) -> None:
        value = db.toggle_open_to_intro(callback.from_user.id)
        profile = db.get_user_profile(callback.from_user.id)
        linkedin = db.get_linkedin(callback.from_user.id)
        await replace_card(
            message=callback.message,
            text=profile_summary(profile, linkedin),
            avatar_file_id=profile.get("avatar_file_id"),
            reply_markup=profile_keyboard(open_to_intro=bool(int(profile.get("open_to_intro") or 0))),
        )
        await callback.answer("Запросы на знакомство включены" if value else "Запросы на знакомство выключены")

    @dp.message(ProfileStates.waiting_avatar, F.photo)
    async def save_avatar(message: Message, state: FSMContext) -> None:
        photo = message.photo[-1]
        db.update_profile_field(message.from_user.id, "avatar_file_id", photo.file_id)
        await state.clear()
        profile = db.get_user_profile(message.from_user.id)
        linkedin = db.get_linkedin(message.from_user.id)
        await send_card(
            message=message,
            text="Аватар сохранён.\n\n" + profile_summary(profile, linkedin),
            avatar_file_id=profile.get("avatar_file_id"),
            reply_markup=profile_keyboard(open_to_intro=bool(int(profile.get("open_to_intro") or 0))),
        )

    @dp.message(ProfileStates.waiting_avatar)
    async def save_avatar_invalid(message: Message) -> None:
        await message.answer("Отправьте фотографию для аватара.")

    @dp.message(
        ProfileStates.waiting_name,
        ProfileStates.waiting_role,
        ProfileStates.waiting_industry,
        ProfileStates.waiting_location,
        ProfileStates.waiting_bio,
        ProfileStates.waiting_languages,
        ProfileStates.waiting_company,
        ProfileStates.waiting_skills,
        ProfileStates.waiting_links,
    )
    async def save_profile_field(message: Message, state: FSMContext) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Введите текстовое значение.")
            return
        data = await state.get_data()
        field = data["profile_field"]
        db.update_profile_field(message.from_user.id, field, message.text.strip())
        await state.clear()
        profile = db.get_user_profile(message.from_user.id)
        linkedin = db.get_linkedin(message.from_user.id)
        await send_card(
            message=message,
            text="Профиль обновлён.\n\n" + profile_summary(profile, linkedin),
            avatar_file_id=profile.get("avatar_file_id"),
            reply_markup=profile_keyboard(open_to_intro=bool(int(profile.get("open_to_intro") or 0))),
        )

    @dp.callback_query(F.data == "links:open:profile")
    async def links_open_profile(callback: CallbackQuery) -> None:
        profile = db.get_user_profile(callback.from_user.id)
        raw_links = profile.get("external_links") if profile else None
        if not has_external_links(raw_links):
            await callback.answer("Ссылки не указаны.", show_alert=True)
            return
        await send_links_message(callback.message, "<b>Ссылки профиля</b>", raw_links)
        await callback.answer()
        return
        if db.has_external_links_consent(callback.from_user.id):
            await send_links_message(callback.message, "<b>Ссылки профиля</b>", raw_links)
            await callback.answer()
            return
        await callback.message.answer(
            (
                "<b>Предупреждение</b>\n"
                "Вы собираетесь перейти по внешним ссылкам. Мы не проверяем их содержимое "
                "и не несем ответственности за информацию на сторонних сайтах. "
                "Пожалуйста, открывайте только те ссылки, которым доверяете."
            ),
            reply_markup=external_links_warning_keyboard("profile"),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("links:open:rec:"))
    async def links_open_recommendation(callback: CallbackQuery) -> None:
        candidate_id = int(callback.data.split(":")[-1])
        candidate = db.get_user_by_internal_id(candidate_id)
        raw_links = candidate.get("external_links") if candidate else None
        if not has_external_links(raw_links):
            await callback.answer("Ссылки не указаны.", show_alert=True)
            return
        if db.has_external_links_consent(callback.from_user.id):
            await send_links_message(callback.message, "<b>Ссылки пользователя</b>", raw_links)
            await callback.answer()
            return
        await callback.message.answer(
            (
                "<b>Предупреждение</b>\n"
                "Вы собираетесь перейти по внешним ссылкам. Мы не проверяем их содержимое "
                "и не несем ответственности за информацию на сторонних сайтах. "
                "Пожалуйста, открывайте только те ссылки, которым доверяете."
            ),
            reply_markup=external_links_warning_keyboard("rec", candidate_id),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("links:confirm:"))
    async def links_confirm(callback: CallbackQuery) -> None:
        payload = callback.data.split(":")
        context = payload[2]
        target_id = int(payload[3]) if len(payload) > 3 else None
        db.set_external_links_consent(callback.from_user.id, True)
        try:
            await callback.message.delete()
        except Exception:
            logger.exception("Failed to delete links warning")

        if context == "profile":
            profile = db.get_user_profile(callback.from_user.id)
            await send_links_message(callback.message, "<b>Ссылки профиля</b>", profile.get("external_links") if profile else None)
        elif context == "rec" and target_id is not None:
            candidate = db.get_user_by_internal_id(target_id)
            await send_links_message(callback.message, "<b>Ссылки пользователя</b>", candidate.get("external_links") if candidate else None)
        await callback.answer("Подтверждение сохранено")

    @dp.callback_query(F.data == "links:cancel")
    async def links_cancel(callback: CallbackQuery) -> None:
        try:
            await callback.message.delete()
        except Exception:
            logger.exception("Failed to delete links warning")
        await callback.answer("Отменено")

    @dp.message(F.text == "Кого я ищу")
    async def show_preferences(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        preferences = db.get_preferences(message.from_user.id)
        profile = db.get_user_profile(message.from_user.id)
        await message.answer(
            preference_summary(preferences, profile),
            reply_markup=preferences_keyboard(),
        )

    @dp.callback_query(F.data.startswith("pref:edit:"))
    async def edit_preferences(callback: CallbackQuery, state: FSMContext) -> None:
        field_key = callback.data.split(":")[-1]
        state_name, prompt = PREFERENCE_FIELD_PROMPTS[field_key]
        await state.clear()
        await state.set_state(state_name)
        mapped_field = "interaction_formats" if field_key == "formats" else field_key
        await state.update_data(pref_field=mapped_field)
        await callback.message.answer(prompt)
        await callback.answer()

    @dp.callback_query(F.data == "pref:toggle:open")
    async def toggle_open_to_intro(callback: CallbackQuery) -> None:
        value = db.toggle_open_to_intro(callback.from_user.id)
        preferences = db.get_preferences(callback.from_user.id)
        profile = db.get_user_profile(callback.from_user.id)
        await callback.message.edit_text(
            preference_summary(preferences, profile),
            reply_markup=preferences_keyboard(),
        )
        await callback.answer("Запросы на знакомство включены" if value else "Запросы на знакомство выключены")

    @dp.message(
        PreferenceStates.waiting_contact_types,
        PreferenceStates.waiting_industries,
        PreferenceStates.waiting_roles,
        PreferenceStates.waiting_geography,
        PreferenceStates.waiting_formats,
        PreferenceStates.waiting_topics,
    )
    async def save_preferences(message: Message, state: FSMContext) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Введите текстовое значение.")
            return
        data = await state.get_data()
        db.update_preference_field(message.from_user.id, data["pref_field"], message.text.strip())
        await state.clear()
        db.record_event(message.from_user.id, "preferences_updated")
        preferences = db.get_preferences(message.from_user.id)
        profile = db.get_user_profile(message.from_user.id)
        await message.answer(
            "Предпочтения сохранены.\n\n" + preference_summary(preferences, profile),
            reply_markup=preferences_keyboard(),
        )

    @dp.message(F.text == "Рекомендации")
    async def show_recommendations(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        profile = db.get_user_profile(message.from_user.id)
        if not profile or profile["profile_status"] == "draft" or not db.minimum_profile_completed(message.from_user.id):
            await message.answer("Сначала заполните обязательные поля профиля и переведите его в статус active.")
            return
        recommendations = db.get_recommendations(message.from_user.id, limit=1)
        if not recommendations:
            await message.answer("Пока нет подходящих рекомендаций. Попробуйте обновить профиль и критерии поиска.")
            return
        candidate = recommendations[0]
        db.mark_recommendation(message.from_user.id, int(candidate["id"]), "shown")
        db.record_event(message.from_user.id, "recommendation_shown", {"candidate_id": int(candidate["id"])})
        await send_card(
            message=message,
            text=candidate_card(candidate),
            avatar_file_id=candidate.get("avatar_file_id"),
            reply_markup=recommendation_keyboard(int(candidate["id"]), has_external_links(candidate.get("external_links"))),
        )

    @dp.callback_query(F.data.startswith("rec:skip:"))
    async def recommendation_skip(callback: CallbackQuery) -> None:
        candidate_id = int(callback.data.split(":")[-1])
        db.mark_recommendation(callback.from_user.id, candidate_id, "skipped")
        await callback.answer("Пропущено")
        recommendations = db.get_recommendations(callback.from_user.id, limit=1)
        if not recommendations:
            try:
                await callback.message.delete()
            except Exception:
                logger.exception("Failed to delete old recommendation card")
            await callback.message.answer("Рекомендации закончились.")
            return
        candidate = recommendations[0]
        db.mark_recommendation(callback.from_user.id, int(candidate["id"]), "shown")
        db.record_event(callback.from_user.id, "recommendation_shown", {"candidate_id": int(candidate["id"])})
        await replace_card(
            message=callback.message,
            text=candidate_card(candidate),
            avatar_file_id=candidate.get("avatar_file_id"),
            reply_markup=recommendation_keyboard(int(candidate["id"]), has_external_links(candidate.get("external_links"))),
        )

    @dp.callback_query(F.data.startswith("rec:intro:"))
    async def recommendation_intro(callback: CallbackQuery, state: FSMContext) -> None:
        candidate_id = int(callback.data.split(":")[-1])
        allowed, reason = db.can_send_intro(callback.from_user.id, candidate_id)
        if not allowed:
            await callback.answer(reason, show_alert=True)
            return
        await state.clear()
        await state.set_state(IntroStates.waiting_intro_text)
        await state.update_data(recipient_id=candidate_id)
        await callback.message.answer("Напишите короткое интро для этого контакта.")
        await callback.answer()

    @dp.callback_query(F.data.startswith("rec:report:"))
    async def recommendation_report(callback: CallbackQuery, state: FSMContext) -> None:
        candidate_id = int(callback.data.split(":")[-1])
        db.mark_recommendation(callback.from_user.id, candidate_id, "reported")
        await state.clear()
        await state.set_state(SupportStates.waiting_complaint_comment)
        await state.update_data(target_type="profile", target_id=candidate_id, complaint_reason="profile_report")
        await callback.message.answer("Опишите жалобу на профиль.")
        await callback.answer("Жалоба создаётся")

    @dp.message(IntroStates.waiting_intro_text)
    async def save_intro(message: Message, state: FSMContext, bot: Bot) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Введите текст интро.")
            return
        data = await state.get_data()
        recipient_id = int(data["recipient_id"])
        allowed, reason = db.can_send_intro(message.from_user.id, recipient_id)
        if not allowed:
            await state.clear()
            await message.answer(reason)
            return
        intro_id = db.create_intro(message.from_user.id, recipient_id, message.text.strip())
        db.mark_recommendation(message.from_user.id, recipient_id, "intro_sent")
        db.record_event(message.from_user.id, "intro_sent", {"intro_id": intro_id, "recipient_id": recipient_id})
        recipient = db.get_user_by_internal_id(recipient_id)
        sender = db.get_user_profile(message.from_user.id)
        if recipient:
            await bot.send_message(
                recipient["tg_user_id"],
                (
                    "<b>Новое интро</b>\n"
                    f"От: {escape(sender.get('display_name') or '—')}\n\n"
                    f"{escape(message.text.strip())}"
                ),
            )
        await state.clear()
        await message.answer("Интро отправлено.", reply_markup=main_menu_keyboard())

    @dp.message(F.text == "Входящие интро")
    async def show_incoming_intros(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        intros = db.list_incoming_intros(message.from_user.id)
        if not intros:
            await message.answer("Входящих интро пока нет.")
            return
        for intro in intros[:10]:
            await message.answer(
                intro_summary(intro),
                reply_markup=intro_item_keyboard(int(intro["id"])),
            )

    @dp.callback_query(F.data.startswith("intro:accept:"))
    async def accept_intro(callback: CallbackQuery, bot: Bot) -> None:
        intro_id = int(callback.data.split(":")[-1])
        intro = db.get_intro(intro_id)
        if not intro or int(intro["recipient_tg_user_id"]) != callback.from_user.id:
            await callback.answer("Интро не найдено.", show_alert=True)
            return
        match = db.create_match_from_intro(intro_id)
        db.record_event(callback.from_user.id, "match_created", {"match_id": int(match["id"])})
        await callback.message.edit_text(intro_summary({**intro, "status": "accepted"}))
        await bot.send_message(
            intro["sender_tg_user_id"],
            "Ваше интро приняли. Контакт появился в разделе 'Мои мэтчи'.",
        )
        await callback.answer("Мэтч создан")

    @dp.callback_query(F.data.startswith("intro:decline:"))
    async def decline_intro(callback: CallbackQuery) -> None:
        intro_id = int(callback.data.split(":")[-1])
        intro = db.get_intro(intro_id)
        if not intro or int(intro["recipient_tg_user_id"]) != callback.from_user.id:
            await callback.answer("Интро не найдено.", show_alert=True)
            return
        db.update_intro_status(intro_id, "declined")
        intro["status"] = "declined"
        await callback.message.edit_text(intro_summary(intro))
        await callback.answer("Интро отклонено")

    @dp.callback_query(F.data.startswith("intro:report:"))
    async def report_intro(callback: CallbackQuery, state: FSMContext) -> None:
        intro_id = int(callback.data.split(":")[-1])
        await state.clear()
        await state.set_state(SupportStates.waiting_complaint_comment)
        await state.update_data(target_type="intro", target_id=intro_id, complaint_reason="intro_report")
        await callback.message.answer("Опишите жалобу на интро.")
        await callback.answer()

    @dp.message(F.text == "Мои мэтчи")
    async def show_matches(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        matches = db.list_matches(message.from_user.id)
        if not matches:
            await message.answer("Активных мэтчей пока нет.")
            return
        for match in matches[:10]:
            await message.answer(
                match_summary(match),
                reply_markup=match_actions_keyboard(int(match["id"]), str(match["status"])),
            )

    @dp.callback_query(F.data.startswith("match:message:"))
    async def start_match_message(callback: CallbackQuery, state: FSMContext) -> None:
        match_id = int(callback.data.split(":")[-1])
        allowed, reason = db.can_send_message(callback.from_user.id, match_id)
        if not allowed:
            await callback.answer(reason, show_alert=True)
            return
        await state.clear()
        await state.set_state(MatchMessageStates.waiting_message_text)
        await state.update_data(match_id=match_id)
        await callback.message.answer("Введите сообщение для собеседника.")
        await callback.answer()

    @dp.callback_query(F.data.startswith("match:toggle_mute:"))
    async def toggle_match_mute(callback: CallbackQuery) -> None:
        match_id = int(callback.data.split(":")[-1])
        match = db.get_match_for_user(match_id, callback.from_user.id)
        if not match:
            await callback.answer("Мэтч не найден.", show_alert=True)
            return
        new_status = "active" if match["status"] == "muted" else "muted"
        db.set_match_status(match_id, new_status)
        updated = db.get_match_for_user(match_id, callback.from_user.id)
        await callback.message.edit_text(
            match_summary(updated),
            reply_markup=match_actions_keyboard(match_id, new_status),
        )
        await callback.answer(f"Статус: {new_status}")

    @dp.callback_query(F.data.startswith("match:close:"))
    async def close_match(callback: CallbackQuery) -> None:
        match_id = int(callback.data.split(":")[-1])
        db.set_match_status(match_id, "closed")
        await callback.message.edit_text("Мэтч скрыт из активной работы.")
        await callback.answer("Закрыто")

    @dp.callback_query(F.data.startswith("match:block:"))
    async def block_match(callback: CallbackQuery) -> None:
        match_id = int(callback.data.split(":")[-1])
        blocked_id = db.block_user_from_match(match_id, callback.from_user.id)
        await callback.message.edit_text("Пользователь заблокирован, мэтч закрыт.")
        await callback.answer("Заблокировано")
        if blocked_id:
            db.record_event(callback.from_user.id, "user_blocked", {"blocked_user_id": blocked_id})

    @dp.message(MatchMessageStates.waiting_message_text)
    async def send_match_message(message: Message, state: FSMContext, bot: Bot) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Введите текст сообщения.")
            return
        data = await state.get_data()
        match_id = int(data["match_id"])
        allowed, reason = db.can_send_message(message.from_user.id, match_id)
        if not allowed:
            await state.clear()
            await message.answer(reason)
            return
        created = db.create_message(message.from_user.id, match_id, message.text.strip())
        db.record_event(message.from_user.id, "message_sent", {"message_id": created["id"], "match_id": match_id})
        await bot.send_message(
            created["recipient_tg_user_id"],
            (
                "<b>Новое сообщение в мэтче</b>\n"
                f"От: {escape(created['sender_name'])}\n\n"
                f"{escape(created['content'])}"
            ),
            reply_markup=message_report_keyboard(int(created["id"])),
        )
        await message.answer("Сообщение отправлено.")
        await state.clear()

    @dp.callback_query(F.data.startswith("msg:report:"))
    async def report_message(callback: CallbackQuery, state: FSMContext) -> None:
        message_id = int(callback.data.split(":")[-1])
        await state.clear()
        await state.set_state(SupportStates.waiting_complaint_comment)
        await state.update_data(target_type="message", target_id=message_id, complaint_reason="message_report")
        await callback.message.answer("Опишите жалобу на сообщение.")
        await callback.answer()

    @dp.message(F.text == "Приватность")
    async def show_privacy(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        privacy = db.get_privacy(message.from_user.id)
        await message.answer(
            privacy_summary(privacy),
            reply_markup=privacy_keyboard(privacy["who_can_intro"], privacy["visibility"]),
        )

    @dp.callback_query(F.data == "privacy:cycle:visibility")
    async def cycle_visibility(callback: CallbackQuery) -> None:
        db.cycle_privacy_value(callback.from_user.id, "visibility")
        privacy = db.get_privacy(callback.from_user.id)
        await callback.message.edit_text(
            privacy_summary(privacy),
            reply_markup=privacy_keyboard(privacy["who_can_intro"], privacy["visibility"]),
        )
        await callback.answer("Обновлено")

    @dp.callback_query(F.data == "privacy:cycle:intro")
    async def cycle_intro_policy(callback: CallbackQuery) -> None:
        db.cycle_privacy_value(callback.from_user.id, "who_can_intro")
        privacy = db.get_privacy(callback.from_user.id)
        await callback.message.edit_text(
            privacy_summary(privacy),
            reply_markup=privacy_keyboard(privacy["who_can_intro"], privacy["visibility"]),
        )
        await callback.answer("Обновлено")

    @dp.callback_query(F.data.startswith("privacy:toggle:"))
    async def toggle_privacy(callback: CallbackQuery) -> None:
        field_key = callback.data.split(":")[-1]
        mapping = {
            "company": "show_company",
            "linkedin": "show_linkedin",
            "location": "show_location",
            "messages": "messages_after_match",
        }
        db.toggle_privacy_flag(callback.from_user.id, mapping[field_key])
        privacy = db.get_privacy(callback.from_user.id)
        await callback.message.edit_text(
            privacy_summary(privacy),
            reply_markup=privacy_keyboard(privacy["who_can_intro"], privacy["visibility"]),
        )
        await callback.answer("Обновлено")

    @dp.message(F.text == "LinkedIn")
    async def show_linkedin(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        linkedin = db.get_linkedin(message.from_user.id)
        status_label = LINKEDIN_STATUS_LABELS.get(linkedin["status"], linkedin["status"])
        await message.answer(
            (
                "<b>LinkedIn верификация</b>\n"
                f"Статус: <code>{status_label}</code>\n"
                f"URL: {escape(linkedin.get('profile_url') or '—')}"
            ),
            reply_markup=linkedin_keyboard(linkedin["status"], bool(linkedin.get("profile_url"))),
        )

    @dp.callback_query(F.data == "linkedin:noop")
    async def linkedin_noop(callback: CallbackQuery) -> None:
        await callback.answer()

    @dp.callback_query(F.data == "linkedin:start")
    async def linkedin_start(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(LinkedinStates.waiting_linkedin_url)
        linkedin = db.get_linkedin(callback.from_user.id)
        if linkedin and linkedin.get("profile_url"):
            await callback.message.answer("Отправьте новую ссылку на LinkedIn-профиль.")
        else:
            await callback.message.answer("Отправьте ссылку на LinkedIn-профиль.")
        await callback.answer()

    @dp.message(LinkedinStates.waiting_linkedin_url)
    async def linkedin_submit(message: Message, state: FSMContext, bot: Bot) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Отправьте ссылку на LinkedIn-профиль.")
            return
        url = message.text.strip()
        db.submit_linkedin(message.from_user.id, url)
        db.record_event(message.from_user.id, "linkedin_submitted")
        user = db.get_user_profile(message.from_user.id)
        await notify_admins(
            bot,
            (
                "<b>Новая LinkedIn-заявка</b>\n"
                f"User ID: <code>{user['id']}</code>\n"
                f"Telegram: <code>{user['tg_user_id']}</code>\n"
                f"Имя: {escape(user.get('display_name') or '—')}\n"
                f"URL: {escape(url)}"
            ),
            reply_markup=linkedin_admin_keyboard(int(user["id"])),
        )
        await state.clear()
        await message.answer("Ссылка сохранена. Профиль отправлен на модерацию.")

    @dp.callback_query(F.data.startswith("admin:linkedin:"))
    async def admin_linkedin_action(callback: CallbackQuery, bot: Bot) -> None:
        if not is_admin(callback.from_user.id, callback.from_user.username):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return
        _, _, action, user_id_raw = callback.data.split(":")
        user_id = int(user_id_raw)
        status = "verified" if action == "verify" else "failed"
        db.set_linkedin_status(user_id, status)
        status_label = LINKEDIN_STATUS_LABELS.get(status, status)
        user = db.get_user_by_internal_id(user_id)
        if user:
            await bot.send_message(
                user["tg_user_id"],
                (
                    "<b>Обновление LinkedIn-верификации</b>\n"
                    f"Статус: <code>{status_label}</code>\n"
                    f"URL: {escape(user.get('linkedin_url') or '—')}"
                ),
            )
        await callback.message.edit_text(f"LinkedIn-статус обновлён: {status_label}")
        await callback.answer("Готово")

    @dp.message(F.text == "Поддержка")
    async def show_support(message: Message, state: FSMContext) -> None:
        if not await ensure_registration(message, state):
            return
        await message.answer(
            "Через поддержку можно оставить тикет или жалобу.",
            reply_markup=support_keyboard(),
        )

    @dp.callback_query(F.data == "support:create")
    async def support_create(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await state.set_state(SupportStates.waiting_support_text)
        await callback.message.answer("Опишите вопрос или проблему.")
        await callback.answer()

    @dp.message(SupportStates.waiting_support_text)
    async def save_support(message: Message, state: FSMContext, bot: Bot) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Опишите вопрос или проблему текстом.")
            return
        ticket_id = db.create_complaint(
            reporter_tg_user_id=message.from_user.id,
            target_type="support",
            target_id=None,
            reason="support_request",
            comment=message.text.strip(),
        )
        db.record_event(message.from_user.id, "support_ticket_created", {"ticket_id": ticket_id})
        ticket = db.get_complaint(ticket_id)
        await notify_admins(
            bot,
            complaint_detail_text(ticket),
            reply_markup=admin_complaint_keyboard(ticket_id),
        )
        await state.clear()
        await message.answer("Тикет отправлен в поддержку.")

    @dp.message(SupportStates.waiting_complaint_comment)
    async def save_complaint(message: Message, state: FSMContext, bot: Bot) -> None:
        if not message.text or not message.text.strip():
            await message.answer("Опишите жалобу текстом.")
            return
        data = await state.get_data()
        complaint_id = db.create_complaint(
            reporter_tg_user_id=message.from_user.id,
            target_type=data["target_type"],
            target_id=int(data["target_id"]),
            reason=data["complaint_reason"],
            comment=message.text.strip(),
        )
        db.record_event(
            message.from_user.id,
            "complaint_created",
            {"complaint_id": complaint_id, "target_type": data["target_type"]},
        )
        complaint = db.get_complaint(complaint_id)
        await notify_admins(
            bot,
            complaint_detail_text(complaint),
            reply_markup=admin_complaint_keyboard(complaint_id),
        )
        await state.clear()
        await message.answer("Жалоба отправлена модератору.")

    @dp.message()
    async def fallback(message: Message, state: FSMContext) -> None:
        if not db.is_registration_complete(message.from_user.id):
            await start_registration(message, state)
            return
        await message.answer(
            "Используйте кнопки главного меню.",
            reply_markup=main_menu_keyboard(),
        )

    return dp


async def run_bot(settings: Settings, db: Database) -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = build_router(settings, db)
    await dispatcher.start_polling(bot)


def start_bot(settings: Settings, db: Database) -> None:
    asyncio.run(run_bot(settings, db))
