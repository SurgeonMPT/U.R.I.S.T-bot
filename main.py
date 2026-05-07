import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, get_available_dates
from database import Database
from keyboards import (
    main_menu_keyboard,
    dates_keyboard,
    times_keyboard,
    gender_keyboard,
    confirm_user_data_keyboard,
    cancel_booking_keyboard,
)
from states import BookingStates

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()


async def show_main_menu(message: Message):
    await message.answer(
        "Выберите действие:",
        reply_markup=main_menu_keyboard()
    )


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте! Я бот для записи к юристу.\n\n"
        "Через меня вы можете выбрать свободную дату и время, "
        "оставить данные и получить подтверждение записи.",
        reply_markup=main_menu_keyboard()
    )


@dp.message(Command("help"))
@dp.message(F.text == "Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "/start — начать работу\n"
        "/help — помощь\n"
        "/book — записаться\n"
        "/my_booking — посмотреть свою запись\n"
        "/cancel — отменить запись\n\n"
        "Или используйте кнопки меню."
    )


@dp.message(Command("book"))
@dp.message(F.text == "Записаться")
async def cmd_book(message: Message, state: FSMContext):
    await state.clear()
    db.seed_slots()
    await message.answer(
        "Выберите дату:",
        reply_markup=dates_keyboard(get_available_dates())
    )


@dp.callback_query(F.data == "back_to_dates")
async def back_to_dates(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите дату:",
        reply_markup=dates_keyboard(get_available_dates())
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("date:"))
async def process_date_selection(callback: CallbackQuery, state: FSMContext):
    selected_date = callback.data.split(":", 1)[1]
    free_times = db.get_free_times_by_date(selected_date)

    if not free_times:
        await callback.answer("На эту дату свободного времени нет.", show_alert=True)
        return

    await state.update_data(selected_date=selected_date)

    await callback.message.edit_text(
        f"Вы выбрали дату: {selected_date}\nТеперь выберите время:",
        reply_markup=times_keyboard(free_times, selected_date)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("time:"))
async def process_time_selection(callback: CallbackQuery, state: FSMContext):
    _, selected_date, safe_time = callback.data.split(":")
    selected_time = safe_time.replace("_", ":")

    slot_id = db.get_slot_id(selected_date, selected_time)

    if not slot_id or not db.is_slot_free(slot_id):
        await callback.answer("Это время уже занято. Выберите другое.", show_alert=True)
        return

    await state.update_data(
        selected_date=selected_date,
        selected_time=selected_time,
        slot_id=slot_id
    )

    user = db.get_user_by_telegram_id(callback.from_user.id)

    if user:
        full_name = user[2]
        age = user[3]
        gender = user[4]

        await callback.message.answer(
            "Я нашёл ваши сохранённые данные:\n"
            f"ФИО: {full_name}\n"
            f"Возраст: {age}\n"
            f"Пол: {gender}\n\n"
            "Использовать их?",
            reply_markup=confirm_user_data_keyboard()
        )
    else:
        await callback.message.answer("Введите ваше ФИО:")
        await state.set_state(BookingStates.waiting_for_full_name)

    await callback.answer()


@dp.callback_query(F.data == "use_saved_data")
async def use_saved_data(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    slot_id = data.get("slot_id")

    user = db.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.message.answer("Сохранённые данные не найдены. Введите ФИО:")
        await state.set_state(BookingStates.waiting_for_full_name)
        await callback.answer()
        return

    user_id = user[0]
    success = db.create_appointment(user_id, slot_id)

    if success:
        await callback.message.answer(
            f"✅ Запись подтверждена!\n\n"
            f"Дата: {data['selected_date']}\n"
            f"Время: {data['selected_time']}\n"
            f"ФИО: {user[2]}",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.message.answer(
            "❌ Это время уже занято. Попробуйте выбрать другое.",
            reply_markup=main_menu_keyboard()
        )

    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "reenter_data")
async def reenter_data(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ваше ФИО:")
    await state.set_state(BookingStates.waiting_for_full_name)
    await callback.answer()


@dp.message(BookingStates.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    full_name = message.text.strip()

    if len(full_name) < 5:
        await message.answer("Введите корректное ФИО.")
        return

    await state.update_data(full_name=full_name)
    await message.answer("Введите ваш возраст:")
    await state.set_state(BookingStates.waiting_for_age)


@dp.message(BookingStates.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    age_text = message.text.strip()

    if not age_text.isdigit():
        await message.answer("Возраст должен быть числом.")
        return

    age = int(age_text)
    if age < 10 or age > 120:
        await message.answer("Введите реальный возраст.")
        return

    await state.update_data(age=age)
    await message.answer("Выберите пол:", reply_markup=gender_keyboard())
    await state.set_state(BookingStates.waiting_for_gender)


@dp.message(BookingStates.waiting_for_gender)
async def process_gender(message: Message, state: FSMContext):
    gender = message.text.strip()

    if gender not in ["Мужской", "Женский"]:
        await message.answer("Пожалуйста, выберите пол кнопкой.")
        return

    data = await state.get_data()
    full_name = data["full_name"]
    age = data["age"]
    slot_id = data["slot_id"]

    user_id = db.create_or_update_user(
        telegram_id=message.from_user.id,
        full_name=full_name,
        age=age,
        gender=gender
    )

    success = db.create_appointment(user_id, slot_id)

    if success:
        await message.answer(
            f"✅ Запись подтверждена!\n\n"
            f"Дата: {data['selected_date']}\n"
            f"Время: {data['selected_time']}\n"
            f"ФИО: {full_name}",
            reply_markup=main_menu_keyboard()
        )
    else:
        await message.answer(
            "❌ К сожалению, это время уже занято. Попробуйте выбрать другое.",
            reply_markup=main_menu_keyboard()
        )

    await state.clear()


@dp.message(Command("my_booking"))
@dp.message(F.text == "Моя запись")
async def cmd_my_booking(message: Message):
    appointment = db.get_user_active_appointment(message.from_user.id)

    if not appointment:
        await message.answer("У вас нет активной записи.")
        return

    appointment_id, slot_date, slot_time, full_name = appointment
    await message.answer(
        f"Ваша запись:\n\n"
        f"ФИО: {full_name}\n"
        f"Дата: {slot_date}\n"
        f"Время: {slot_time}"
    )


@dp.message(Command("cancel"))
@dp.message(F.text == "Отменить запись")
async def cmd_cancel(message: Message):
    appointment = db.get_user_active_appointment(message.from_user.id)

    if not appointment:
        await message.answer("У вас нет активной записи для отмены.")
        return

    appointment_id, slot_date, slot_time, full_name = appointment
    await message.answer(
        f"Вы действительно хотите отменить запись?\n\n"
        f"Дата: {slot_date}\n"
        f"Время: {slot_time}",
        reply_markup=cancel_booking_keyboard(appointment_id)
    )


@dp.callback_query(F.data.startswith("confirm_cancel:"))
async def process_cancel(callback: CallbackQuery):
    appointment_id = int(callback.data.split(":")[1])
    success = db.cancel_appointment(appointment_id, callback.from_user.id)

    if success:
        await callback.message.answer(
            "✅ Запись отменена.",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.message.answer(
            "❌ Не удалось отменить запись.",
            reply_markup=main_menu_keyboard()
        )

    await callback.answer()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())