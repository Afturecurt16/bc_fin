from aiogram.fsm.state import State, StatesGroup


class ProfileStates(StatesGroup):
    waiting_name = State()
    waiting_role = State()
    waiting_industry = State()
    waiting_location = State()
    waiting_bio = State()
    waiting_languages = State()
    waiting_company = State()
    waiting_skills = State()
    waiting_links = State()
    waiting_avatar = State()


class PreferenceStates(StatesGroup):
    waiting_contact_types = State()
    waiting_industries = State()
    waiting_roles = State()
    waiting_geography = State()
    waiting_formats = State()
    waiting_topics = State()


class IntroStates(StatesGroup):
    waiting_intro_text = State()


class MatchMessageStates(StatesGroup):
    waiting_message_text = State()


class SupportStates(StatesGroup):
    waiting_support_text = State()
    waiting_complaint_comment = State()


class LinkedinStates(StatesGroup):
    waiting_linkedin_url = State()


class RegistrationStates(StatesGroup):
    waiting_text = State()
    waiting_avatar = State()


class AdminStates(StatesGroup):
    waiting_admin_username = State()
