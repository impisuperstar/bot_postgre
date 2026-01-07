import random
from datetime import datetime

import sqlalchemy as sq
from sqlalchemy import func
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from telebot import TeleBot, types
from telebot.custom_filters import StateFilter
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage

temp_word_data = {}
limit = 4
state_storage = StateMemoryStorage()
token = ''
bot = TeleBot(token, state_storage=state_storage)
bot.add_custom_filter(StateFilter(bot))
WORDS = {'слон': 'elephant', 'стол': 'table',
         'стул': 'chair', 'левые': 'left', 'правый': 'right'}

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    user_id = sq.Column(sq.Integer, primary_key=True)
    telegram_id = sq.Column(sq.Integer, unique=True, nullable=False)
    username = sq.Column(sq.String(length=100), nullable=False)
    first_name = sq.Column(sq.String(length=100), nullable=False)
    last_name = sq.Column(sq.String(length=100), nullable=False)

    user_words = relationship(
        "UserWord",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Dictionary(Base):
    __tablename__ = 'dictionary'

    word_id = sq.Column(sq.Integer, primary_key=True)
    russian_word = sq.Column(sq.String(length=100), nullable=False)
    english_word = sq.Column(sq.String(length=100), nullable=False)

    user_words = relationship(
        "UserWord",
        back_populates="word"
    )


class UserWord(Base):
    __tablename__ = "user_words"

    user_word_id = sq.Column(sq.Integer, primary_key=True, autoincrement=True)
    user_id = sq.Column(sq.Integer, sq.ForeignKey(
        "users.user_id", ondelete="CASCADE"), nullable=False)
    word_id = sq.Column(sq.Integer, sq.ForeignKey(
        "dictionary.word_id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="user_words")
    word = relationship("Dictionary", back_populates="user_words")


def create_tables(engine):
    Base.metadata.create_all(engine)


DSN = 'postgresql://msizov@localhost:5432/translater'
engine = sq.create_engine(DSN)

create_tables(engine)

Session = sessionmaker(bind=engine)
session = Session()

print('Start telegram bot...')


class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'


class MyStates(StatesGroup):
    target_word = State()
    translate_word = State()
    another_words = State()
    waiting_russian = State()
    waiting_english = State()
    waiting_deleted = State()
    waiting_russian_delete = State()


@bot.message_handler(commands=['cards', 'start'])
def create_cards(message):

    user = session.query(User).filter_by(
        telegram_id=message.from_user.id).first()

    if not user:
        user = User(first_name=message.from_user.first_name, telegram_id=message.from_user.id,
                    last_name=message.from_user.last_name, username=message.from_user.username)
        session.add(user)
        session.commit()
        bot.send_message(
            message.chat.id, "Congratulations! Your user has been successfully added!")

    for key, value in WORDS.items():
        word = session.query(Dictionary).filter_by(
            russian_word=key, english_word=value).first()
        if not word:
            word = Dictionary(russian_word=key, english_word=value)
            session.add(word)
            session.commit()

            existing = session.query(UserWord).filter_by(
                user_id=user.user_id, word_id=word.word_id).first()

            if not existing:
                user_word = UserWord(user_id=user.user_id,
                                     word_id=word.word_id)
                session.add(user_word)
                session.commit()

            bot.send_message(message.chat.id, word.word_id)

    bot.send_message(
        message.chat.id, "Данный Бот используется для изучения английского языка")

    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)

    word = session.query(Dictionary).order_by(func.random()).first()

    target_word = word.english_word
    translate = word.russian_word

    target_word_btn = types.KeyboardButton(target_word)

    other_words = []
    other = session.query(Dictionary).filter(
        Dictionary.english_word != target_word).order_by(func.random()).limit(limit).all()
    for oth in other:
        other_words.append(types.KeyboardButton(oth.english_word))

    buttons = [target_word_btn] + other_words
    random.shuffle(buttons)
    next_btn = types.KeyboardButton(Command.NEXT)
    add_word_btn = types.KeyboardButton(Command.ADD_WORD)
    delete_word_btn = types.KeyboardButton(Command.DELETE_WORD)
    buttons.extend([next_btn, add_word_btn, delete_word_btn])

    markup.add(*buttons)

    greeting = f"Выбери перевод слова:\n🇷🇺 {translate}"
    bot.send_message(message.chat.id, greeting, reply_markup=markup)

    bot.set_state(message.from_user.id, MyStates.target_word, message.chat.id)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['target_word'] = target_word
        data['translate_word'] = translate
        data['other_words'] = others
        data['buttons'] = buttons


@bot.message_handler(state=MyStates.target_word, func=lambda message: message.text not in [Command.ADD_WORD, Command.NEXT, Command.DELETE_WORD])
def check_answer(message):
    text = message.text

    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        target_word = data['target_word']

    if text == target_word:
        bot.send_message(message.chat.id, "✅ Правильно!")
    else:
        bot.send_message(message.chat.id, "❌ Неправильно. Попробуйте еще раз!")


user_states = {}


@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message):
    create_cards(message)


@bot.message_handler(state="*", func=lambda message: message.text == Command.ADD_WORD)
def handle_simple_word_add(message):

    bot.set_state(message.from_user.id,
                  MyStates.waiting_russian, message.chat.id)

    remove_keyboard = types.ReplyKeyboardRemove()

    bot.send_message(message.chat.id, "🇷🇺 Введите русское слово:",
                     reply_markup=remove_keyboard)


@bot.message_handler(state=MyStates.waiting_russian)
def get_russian_word(message):

    russian_word = message.text.strip()

    if not russian_word:
        bot.send_message(message.chat.id, "Пожалуйста, введите слово")
        return

    user_id = message.from_user.id
    temp_word_data[user_id] = {'russian': russian_word}

    bot.set_state(user_id, MyStates.waiting_english, message.chat.id)

    bot.send_message(
        message.chat.id, f"Русское слово: *{russian_word}*\n\n🇬🇧 Теперь введите английский перевод:",  parse_mode='Markdown')


@bot.message_handler(state=MyStates.waiting_english)
def handle_all_messages(message):

    english_word = message.text.strip()

    user_id = message.from_user.id

    if not english_word:
        bot.send_message(message.chat.id, "Пожалуйста, введите перевод")
        return

    print(temp_word_data)
    russian_word = temp_word_data[user_id]['russian']

    user = session.query(User).filter_by(
        telegram_id=message.from_user.id).first()

    word = session.query(Dictionary).filter_by(
        russian_word=russian_word, english_word=english_word).first()
    if not word:
        word = Dictionary(russian_word=russian_word, english_word=english_word)
        session.add(word)
        session.commit()

        existing = session.query(UserWord).join(User, UserWord.user_id == User.user_id).filter(
            User.telegram_id == message.from_user.id, UserWord.word_id == word.word_id).first()

        if not existing:
            user_word = UserWord(user_id=user.user_id, word_id=word.word_id)
            session.add(user_word)
            session.commit()

    create_cards(message)


@bot.message_handler(state="*", func=lambda message: message.text == Command.DELETE_WORD)
def handle_simple_word_add(message):

    bot.set_state(message.from_user.id,
                  MyStates.waiting_russian_delete, message.chat.id)

    remove_keyboard = types.ReplyKeyboardRemove()

    bot.send_message(message.chat.id, "🇷🇺 Введите русское слово:",
                     reply_markup=remove_keyboard)


@bot.message_handler(state=MyStates.waiting_russian_delete)
def get_russian_word(message):
    russian_word_delete = message.text.strip().lower()

    if not russian_word_delete:
        bot.send_message(message.chat.id, "Пожалуйста, введите слово")
        return

    user = session.query(User).filter_by(
        telegram_id=message.from_user.id).first()

    print(user.user_id)

    if not user:
        bot.send_message(message.chat.id, "Пользователь не найден")
        bot.delete_state(message.from_user.id, message.chat.id)
        return

    word = session.query(Dictionary).filter_by(
        russian_word=russian_word_delete).first()
    print(word.word_id)

    if not word:
        bot.send_message(
            message.chat.id, f"Слово '{russian_word_delete}' не найдено в словаре")
        bot.delete_state(message.from_user.id, message.chat.id)
        create_cards(message)
        return

    user_word = session.query(UserWord).filter_by(
        user_id=user.user_id,
        word_id=word.word_id
    ).first()

    if not user_word:
        bot.send_message(
            message.chat.id, f"Слово '{russian_word_delete}' не найдено в вашем списке")
        bot.delete_state(message.from_user.id, message.chat.id)
        create_cards(message)
        return

    session.delete(user_word)
    session.commit()

    other_users = session.query(UserWord).filter_by(word_id=word.word_id).all()

    if not other_users:
        session.delete(word)
        session.commit()
        bot.send_message(
            message.chat.id, f"✅ Слово '{russian_word_delete}' полностью удалено из словаря")
    else:
        bot.send_message(
            message.chat.id, f"✅ Слово '{russian_word_delete}' удалено из вашего списка")

    bot.delete_state(message.from_user.id, message.chat.id)

    create_cards(message)


bot.infinity_polling()
