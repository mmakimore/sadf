"""
Админ-панель ParkingBot
"""
import logging, asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
import os
import sqlite3
import tempfile
from openpyxl import Workbook
from config import ADMIN_PASSWORD, DATABASE_PATH
from keyboards import *
from utils import *

logger = logging.getLogger(__name__)
router = Router()

class AdminStates(StatesGroup):
    waiting_password = State()
    waiting_ban_reason = State()
    waiting_broadcast_message = State()
    waiting_edit_hours = State()


# ==================== AUTH ====================
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Команда /admin"""
    await state.clear()
    user = db.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала /start"); return
    if user['role'] == 'admin':
        await message.answer("🔑 <b>Админ-панель</b>", reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")
    else:
        await message.answer("🔑 Введите пароль:")
        await state.set_state(AdminStates.waiting_password)

@router.message(F.text == "🔑 Админ-панель")
async def admin_start(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_user_by_telegram_id(message.from_user.id)
    if not user: return
    if user['role'] == 'admin':
        await message.answer("🔑 <b>Админ-панель</b>", reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")
    else:
        await message.answer("🔑 Введите пароль:")
        await state.set_state(AdminStates.waiting_password)

@router.message(AdminStates.waiting_password)
async def admin_password(message: Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        user = db.get_user_by_telegram_id(message.from_user.id)
        db.set_user_role(user['id'], 'admin')
        db.create_admin_session(user['id'], message.from_user.id)
        await state.clear()
        await message.answer("✅ Вы админ!", reply_markup=get_main_menu_keyboard(True))
        await message.answer("🔑 <b>Админ-панель</b>", reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")
    else:
        await state.clear()
        await message.answer("❌ Неверный пароль.", reply_markup=get_main_menu_keyboard())


# ==================== BOOKING MANAGEMENT ====================
@router.callback_query(F.data == "admin_pending")
async def admin_pending(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bookings = db.get_pending_bookings()
    if not bookings:
        await callback.message.edit_text("✅ Нет ожидающих заявок.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")]]))
        return
    buttons = []
    for b in bookings[:20]:
        s = datetime.fromisoformat(b['start_time'])
        text = f"⏳ #{b['id']} {b['spot_number']} {s.strftime('%d.%m %H:%M')} — {b['customer_name']}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"adm_bk_{b['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")])
    await callback.message.edit_text("📋 <b>Заявки на подтверждение:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data == "admin_all_bookings")
async def admin_all_bookings(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bookings = db.get_all_bookings(limit=20)
    if not bookings:
        await callback.message.edit_text("📋 Нет бронирований.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")]]))
        return
    buttons = []
    for b in bookings[:20]:
        s = datetime.fromisoformat(b['start_time'])
        st = {"pending":"⏳","confirmed":"✅","cancelled":"❌","completed":"✔️"}.get(b['status'],'')
        text = f"{st} #{b['id']} {b['spot_number']} {s.strftime('%d.%m')} {b['customer_name']}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"adm_bk_{b['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")])
    await callback.message.edit_text("📊 <b>Все бронирования:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_bk_"))
async def admin_booking_detail(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bid = int(callback.data.replace("adm_bk_",""))
    b = db.get_booking_by_id(bid)
    if not b: await callback.message.edit_text("❌ Не найдена."); return
    s = datetime.fromisoformat(b['start_time'])
    e = datetime.fromisoformat(b['end_time'])
    h = (e-s).total_seconds()/3600
    rate = get_price_per_hour(h)
    st = {"pending":"⏳ Ожидает","confirmed":"✅ Подтверждена","cancelled":"❌ Отменена","completed":"✔️ Завершена"}.get(b['status'],'')
    car = ""
    if b.get('customer_plate'): car = f"\n🚗 {b['customer_car']} {b['customer_car_color']} ({b['customer_plate']})"
    text = (
        f"📋 <b>Бронь #{bid}</b>\n\n"
        f"📊 {st}\n"
        f"🏠 {b['spot_number']}\n"
        f"📅 {format_datetime(s)} — {format_datetime(e)}\n"
        f"⏱ {h:.1f}ч | {rate}₽/ч = <b>{b['total_price']}₽</b>\n\n"
        f"🔵 <b>Арендатор:</b>\n👤 {b['customer_name']}\n📞 {b['customer_phone']}")
    if b.get('customer_username'): text += f"\n📱 @{b['customer_username']}"
    text += car
    text += f"\n\n🟢 <b>Поставщик:</b>\n👤 {b['supplier_name']}\n📞 {b.get('supplier_phone','')}"
    if b.get('supplier_username'): text += f"\n📱 @{b['supplier_username']}"
    if b.get('card_number'): text += f"\n💳 {b.get('bank','')}: {b['card_number']}"
    await callback.message.edit_text(text,
        reply_markup=get_admin_booking_keyboard(bid, b['status']), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_confirm_"))
async def admin_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bid = int(callback.data.replace("adm_confirm_",""))
    ok, status = db.confirm_booking_idempotent(bid)

    if status == 'already':
        try:
            await callback.message.edit_text(f"ℹ️ Бронь #{bid} уже подтверждена.")
        except:
            await callback.message.answer(f"ℹ️ Бронь #{bid} уже подтверждена.")
        return

    if status == 'not_paid':
        await callback.message.answer(f"⏳ Бронь #{bid} ещё не отмечена как оплаченная (ждём чек).")
        return

    if not ok:
        await callback.message.answer(f"❌ Не удалось подтвердить бронь #{bid}.")
        return

    b = db.get_booking_by_id(bid)
    await callback.message.edit_text(f"✅ Бронь #{bid} подтверждена!")

    # Финальное сообщение пользователю с адресом
    try:
        await callback.bot.send_message(
            b['customer_telegram_id'],
            f"🎉 <b>Всё подтверждено!</b>\n\n"
            f"🏠 {b['spot_number']}\n"
            f"📍 {b.get('address','')}\n"
            f"📅 {format_datetime(b['start_time'])} — {format_datetime(b['end_time'])}\n"
            f"💰 {b['total_price']}₽",
            parse_mode="HTML"
        )
    except:
        pass
    db.log_admin_action('booking_confirmed', booking_id=bid)
@router.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bid = int(callback.data.replace("adm_reject_",""))
    b = db.get_booking_by_id(bid)
    db.reject_booking(bid)
    await callback.message.edit_text(f"❌ Бронь #{bid} отклонена.")
    if b:
        try:
            await callback.bot.send_message(b['customer_telegram_id'],
                f"❌ <b>Бронь #{bid} отклонена.</b>\n🏠 {b['spot_number']}", parse_mode="HTML")
        except: pass
    db.log_admin_action('booking_rejected', booking_id=bid)

@router.callback_query(F.data.startswith("adm_cancel_"))
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bid = int(callback.data.replace("adm_cancel_",""))
    b = db.get_booking_by_id(bid)
    db.cancel_booking(bid)
    await callback.message.edit_text(f"❌ Бронь #{bid} отменена админом.")
    if b:
        try:
            await callback.bot.send_message(b['customer_telegram_id'],
                f"❌ <b>Бронь #{bid} отменена администратором.</b>", parse_mode="HTML")
        except: pass
    db.log_admin_action('booking_cancelled_admin', booking_id=bid)

@router.callback_query(F.data.startswith("adm_edit_"))
async def admin_edit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bid = int(callback.data.replace("adm_edit_",""))
    b = db.get_booking_by_id(bid)
    if not b: return
    s = datetime.fromisoformat(b['start_time'])
    e = datetime.fromisoformat(b['end_time'])
    h = (e-s).total_seconds()/3600
    await state.update_data(edit_booking_id=bid)
    await callback.message.edit_text(
        f"✏️ <b>Редактирование #{bid}</b>\n\n"
        f"Текущее время: {h:.1f}ч\n"
        f"📅 {format_datetime(s)} — {format_datetime(e)}\n\n"
        f"Введите количество <b>оплаченных часов</b>.\n"
        f"Остальное время вернётся свободным слотом.",
        parse_mode="HTML")
    await state.set_state(AdminStates.waiting_edit_hours)

@router.message(AdminStates.waiting_edit_hours)
async def admin_edit_hours(message: Message, state: FSMContext):
    try:
        hours = float(message.text.replace(',','.'))
        if hours <= 0: raise ValueError
    except:
        await message.answer("❌ Введите число (3 или 4.5)"); return
    data = await state.get_data()
    bid = data['edit_booking_id']
    ok = db.admin_edit_booking_hours(bid, hours)
    await state.clear()
    if ok:
        b = db.get_booking_by_id(bid)
        await message.answer(f"✅ Бронь #{bid}: {hours}ч оплачено. Остаток свободен.",
                            reply_markup=get_main_menu_keyboard(True))
        db.log_admin_action('booking_edited', booking_id=bid, details=f"paid={hours}h")
        if b:
            try:
                await message.bot.send_message(b['customer_telegram_id'],
                    f"📝 <b>Бронь #{bid} обновлена.</b>\nОплачено: {hours}ч",
                    parse_mode="HTML")
            except: pass
    else:
        await message.answer("❌ Ошибка.", reply_markup=get_main_menu_keyboard(True))


# ==================== SLOT MANAGEMENT ====================
@router.callback_query(F.data == "admin_slots")
async def admin_slots(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    spots = db.get_all_spots()
    if not spots:
        await callback.message.edit_text("🏠 Нет мест.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")]]))
        return
    buttons = []
    for sp in spots[:20]:
        buttons.append([InlineKeyboardButton(text=f"🏠 {sp['spot_number']} ({sp['supplier_name']})",
            callback_data=f"adm_spot_{sp['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")])
    await callback.message.edit_text("🏠 <b>Места:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_spot_"))
async def admin_spot_detail(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    sid = int(callback.data.replace("adm_spot_",""))
    avails = db.get_spot_availabilities(sid)
    spot = db.get_spot_by_id(sid)
    if not spot: return
    buttons = []
    for a in avails[:15]:
        s = datetime.fromisoformat(a['start_time'])
        e = datetime.fromisoformat(a['end_time'])
        icon = "🔴" if a['is_booked'] else "🟢"
        text = f"{icon} {s.strftime('%d.%m %H:%M')}-{e.strftime('%d.%m %H:%M')}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"adm_sa_{a['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_slots")])
    await callback.message.edit_text(f"🏠 <b>{spot['spot_number']}</b> — слоты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_sa_"))
async def admin_slot_action(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    aid = int(callback.data.replace("adm_sa_",""))
    slot = db.get_availability_by_id(aid)
    if not slot: return
    s = datetime.fromisoformat(slot['start_time'])
    e = datetime.fromisoformat(slot['end_time'])
    status = "🔴 Забронирован" if slot['is_booked'] else "🟢 Свободен"
    await callback.message.edit_text(
        f"📅 {format_datetime(s)} — {format_datetime(e)}\n{status}",
        reply_markup=get_admin_slot_actions_keyboard(aid, slot['is_booked']))

@router.callback_query(F.data.startswith("adm_toggle_"))
async def admin_toggle(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    aid = int(callback.data.replace("adm_toggle_",""))
    new_status = db.admin_toggle_slot(aid)
    if new_status is not None:
        st = "🔴 забронированным" if new_status else "🟢 свободным"
        await callback.message.edit_text(f"✅ Слот стал {st}.")
        db.log_admin_action('slot_toggled', details=f"slot={aid}, booked={new_status}")
    else:
        await callback.message.edit_text("❌ Слот не найден.")


# ==================== USERS ====================
@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    users = db.get_all_users(limit=30)
    buttons = []
    for u in users:
        icon = "👑" if u['role']=='admin' else "👤"
        if not u['is_active']: icon = "🚫"
        buttons.append([InlineKeyboardButton(text=f"{icon} {u['full_name']}",
            callback_data=f"adm_user_{u['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")])
    await callback.message.edit_text("👥 <b>Пользователи:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@router.callback_query(F.data.startswith("adm_user_"))
async def admin_user_detail(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid = int(callback.data.replace("adm_user_",""))
    user = db.get_user_by_id(uid)
    if not user: return
    card = f"\n💳 {user['bank']}: {user['card_number']}" if user.get('card_number') else ""
    car = ""
    if user.get('license_plate'):
        car = f"\n🚗 {user['car_brand']} {user['car_color']} ({user['license_plate']})"
    ban = ""
    if not user['is_active']:
        if user.get('banned_until'):
            ban = f"\n🚫 Бан до {format_datetime(user['banned_until'])}"
        else: ban = "\n🚫 Перманентный бан"
        if user.get('ban_reason'): ban += f" ({user['ban_reason']})"
    text = (f"👤 <b>{user['full_name']}</b>\n📞 {user['phone']}"
            f"\n📱 @{user.get('username','—')}{card}{car}{ban}")
    await callback.message.edit_text(text,
        reply_markup=get_user_admin_actions_keyboard(uid, user), parse_mode="HTML")

@router.callback_query(F.data.startswith("set_admin_"))
async def set_admin(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    db.set_user_role(int(callback.data.replace("set_admin_","")), 'admin')
    await callback.message.edit_text("✅ Теперь админ.")

@router.callback_query(F.data.startswith("set_user_"))
async def set_user(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    db.set_user_role(int(callback.data.replace("set_user_","")), 'user')
    await callback.message.edit_text("✅ Теперь обычный пользователь.")

@router.callback_query(F.data.startswith("ban_menu_"))
async def ban_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid = int(callback.data.replace("ban_menu_",""))
    await callback.message.edit_text("⏱ Длительность бана:", reply_markup=get_ban_duration_keyboard(uid))

@router.callback_query(F.data.startswith("ban_"))
async def ban_duration(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.split("_")
    if len(parts) != 3: return
    uid = int(parts[1]); hours = int(parts[2])
    await state.update_data(ban_user_id=uid, ban_hours=hours if hours > 0 else None)
    await callback.message.edit_text("📝 Причина бана (или «-» без причины):")
    await state.set_state(AdminStates.waiting_ban_reason)

@router.message(AdminStates.waiting_ban_reason)
async def ban_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    reason = "" if message.text == "-" else message.text[:200]
    db.ban_user(data['ban_user_id'], data.get('ban_hours'), reason)
    await state.clear()
    user = db.get_user_by_id(data['ban_user_id'])
    await message.answer(f"🚫 {user['full_name']} забанен.", reply_markup=get_main_menu_keyboard(True))
    try:
        t = "🚫 Вы заблокированы"
        if data.get('ban_hours'): t += f" на {data['ban_hours']}ч"
        else: t += " навсегда"
        if reason: t += f"\n📝 {reason}"
        await message.bot.send_message(user['telegram_id'], t)
    except: pass

@router.callback_query(F.data.startswith("unban_"))
async def unban(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    db.unban_user(int(callback.data.replace("unban_","")))
    await callback.message.edit_text("✅ Разбанен.")


# ==================== STATS ====================
@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    s = db.get_statistics()
    await callback.message.edit_text(
        f"📈 <b>Статистика</b>\n\n"
        f"👥 Пользователи: {s['total_users']} (активных: {s['active_users']})\n"
        f"🏠 Мест: {s['total_spots']}\n"
        f"📋 Бронирований: {s['total_bookings']}\n"
        f"⏳ Ожидает: {s['pending_bookings']}\n"
        f"✅ Подтверждено: {s['confirmed_bookings']}\n"
        f"💰 Доход: {s['total_revenue']}₽",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Панель", callback_data="admin_panel")]]),
        parse_mode="HTML")

# ==================== BROADCAST ====================
@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("📢 Кому отправить?", reply_markup=get_broadcast_target_keyboard())

@router.callback_query(F.data.startswith("broadcast_"))
async def broadcast_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(broadcast_target=callback.data.replace("broadcast_",""))
    await callback.message.edit_text("📝 Введите текст рассылки:")
    await state.set_state(AdminStates.waiting_broadcast_message)

@router.message(AdminStates.waiting_broadcast_message)
async def broadcast_send(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get('broadcast_target','all')
    users = db.get_active_users() if target == 'active' else db.get_all_users(limit=10000)
    await state.clear()
    sent = 0; fail = 0
    for u in users:
        try:
            await message.bot.send_message(u['telegram_id'], message.text)
            sent += 1
            if sent % 20 == 0: await asyncio.sleep(0.5)
        except: fail += 1
    await message.answer(f"📢 Отправлено: {sent}, ошибок: {fail}", reply_markup=get_main_menu_keyboard(True))


# ==================== NAV ====================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("🔑 <b>Админ-панель</b>",
        reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_export_db")
async def admin_export_db(callback: CallbackQuery):
    await callback.answer()
    try:
        file = FSInputFile(DATABASE_PATH)
        await callback.message.answer_document(file, caption="💾 Резервная копия базы данных")
    except Exception as e:
        await callback.message.answer(f"Не удалось выгрузить базу: {e}")


@router.callback_query(F.data.startswith("adm_pay_confirm_"))
async def admin_pay_confirm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bid = int(callback.data.replace("adm_pay_confirm_", ""))
    ok, status = db.confirm_booking_idempotent(bid)
    if status == 'already':
        await callback.message.answer(f"ℹ️ Бронь #{bid} уже подтверждена.")
        return
    if status == 'not_paid':
        await callback.message.answer(f"⏳ Бронь #{bid} ещё не отмечена как оплаченная.")
        return
    if not ok:
        await callback.message.answer(f"❌ Не удалось подтвердить бронь #{bid}.")
        return
    b = db.get_booking_full(bid)
    if b:
        # финальное сообщение клиенту с адресом
        try:
            await callback.bot.send_message(
                b["customer_telegram_id"],
                f"🎉 Всё подтверждено!\n\n"
                f"🏠 {b.get('spot_number','')}\n"
                f"📍 {b.get('address','')}\n"
                f"📅 {b.get('start_time')} — {b.get('end_time')}\n"
                f"💰 {b.get('total_price')}₽"
            )
        except:
            pass
    await callback.message.answer(f"✅ Бронь #{bid} подтверждена.")

@router.callback_query(F.data.startswith("adm_pay_decline_"))
async def admin_pay_decline(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    bid = int(callback.data.replace("adm_pay_decline_", ""))
    ok = db.decline_payment(bid)
    b = db.get_booking_full(bid)
    if b:
        try:
            await callback.bot.send_message(
                b["customer_telegram_id"],
                f"❌ Оплата по брони #{bid} отклонена администратором.\n"
                f"Проверьте чек и отправьте снова."
            )
        except:
            pass
    await callback.message.answer("Готово." if ok else "Не удалось.")

@router.callback_query(F.data == "admin_export_excel")
async def admin_export_excel(callback: CallbackQuery):
    await callback.answer()
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        wb = Workbook()
        wb.remove(wb.active)

        def add_sheet(table_name: str):
            try:
                cur.execute(f"SELECT * FROM {table_name}")
                rows = cur.fetchall()
            except Exception:
                return
            ws = wb.create_sheet(title=table_name[:31])
            if not rows:
                ws.append(["(empty)"])
                return
            headers = rows[0].keys()
            ws.append(list(headers))
            for r in rows:
                ws.append([r[h] for h in headers])

        for tname in ("users", "parking_spots", "spot_availability", "bookings", "events_log"):
            add_sheet(tname)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp_path = tmp.name
        wb.save(tmp_path)

        file = FSInputFile(tmp_path)
        await callback.message.answer_document(file, caption="📊 Выгрузка в Excel (.xlsx)")

        try:
            os.remove(tmp_path)
        except Exception:
            pass
    except Exception as e:
        await callback.message.answer(f"Не удалось выгрузить Excel: {e}")
