import asyncio
import sys
import logging
import uuid
from datetime import datetime

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from config import BOT_TOKEN, PAYMENT_TOKEN
from db import conn

bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

ADMIN_IDS = {5359189451}          # admin tg id
FREE_PREMIUM_IDS = {577310969,7867041380}   # test premium users id

class AnonState(StatesGroup):
    waiting = State()

class ReplyState(StatesGroup):
    waiting = State()


def is_premium(cur, telegram_id: int) -> bool:
    cur.execute("SELECT is_premium FROM hosts WHERE telegram_id=?", (telegram_id,))
    row = cur.fetchone()
    return bool(row and row[0] == 1)

def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("🔗 Create anonymous link", callback_data="create_link"),
        InlineKeyboardButton("⭐ Upgrade to Premium", callback_data="upgrade")
    )
    return kb

@dp.message_handler(commands=["start"], state="*")
async def start(msg: types.Message, state: FSMContext):
    await state.finish()
    args = msg.get_args()

    if args.startswith("host_"):
        try:
            host_id = int(args.split("_")[1])
        except ValueError:
            return await msg.answer("❌ Invalid link.")

        await state.update_data(host_id=host_id)
        await AnonState.waiting.set()
        return await msg.answer("✉️ Send your anonymous message:")

    await msg.answer("Welcome 👋", reply_markup=main_menu())

#create host
@dp.callback_query_handler(lambda c: c.data == "create_link")
async def create_link(call: types.CallbackQuery):
    cur = conn.cursor()
    tid = call.from_user.id

    cur.execute("SELECT host_id FROM hosts WHERE telegram_id=?", (tid,))
    row = cur.fetchone()

    if row:
        host_id = row[0]
    else:
        cur.execute(
            "INSERT INTO hosts (telegram_id, is_premium, created_at) VALUES (?,?,?)",
            (tid, 0, datetime.utcnow().isoformat())
        )
        conn.commit()
        host_id = cur.lastrowid

    link = f"https://t.me/{(await bot.me).username}?start=host_{host_id}"
    await call.message.answer(f"🔗 Your anonymous link:\n{link}")
    await call.answer()

# upgrading premium
@dp.callback_query_handler(lambda c: c.data == "upgrade")
async def upgrade(call: types.CallbackQuery):
    cur = conn.cursor()
    tid = call.from_user.id

    # ensure host exists
    cur.execute("SELECT host_id FROM hosts WHERE telegram_id=?", (tid,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO hosts (telegram_id, is_premium, created_at) VALUES (?,?,?)",
            (tid, 0, datetime.utcnow().isoformat())
        )
        conn.commit()

    # free premium (test)
    if tid in FREE_PREMIUM_IDS:
        cur.execute("UPDATE hosts SET is_premium=1 WHERE telegram_id=?", (tid,))
        conn.commit()
        await call.message.answer("⭐ Premium enabled (test mode).")
        return await call.answer()

    prices = [LabeledPrice("Premium Host", 100)]
    try:
        await bot.send_invoice(
            tid,
            "Premium Upgrade",
            "Unlock reveal feature",
            "premium",
            PAYMENT_TOKEN,
            "XTR",
            prices
            )
    except Exception as e:
        logging.exception(e)
        await call.answer("Payment is not available right now")

@dp.pre_checkout_query_handler(lambda q: True)
async def pre_checkout(q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message_handler(content_types=types.ContentTypes.SUCCESSFUL_PAYMENT)
async def payment_done(msg: types.Message):
    cur = conn.cursor()
    cur.execute("UPDATE hosts SET is_premium=1 WHERE telegram_id=?", (msg.from_user.id,))
    conn.commit()
    await msg.answer("⭐ You are now Premium!")

#receiving anonymous messages
@dp.message_handler(state=AnonState.waiting, content_types=types.ContentTypes.TEXT)
async def receive_anon(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    host_id = data.get("host_id")
    cur = conn.cursor()

    cur.execute("SELECT telegram_id, is_premium FROM hosts WHERE host_id=?", (host_id,))
    row = cur.fetchone()
    if not row:
        await msg.answer("❌ Link expired.")
        return await state.finish()

    host_tid, is_premium_flag = row
    anon_id = uuid.uuid4().hex[:10]

    cur.execute("""
        INSERT INTO anon_users
        (anon_id, host_id, telegram_id, first_name, last_name, username)
        VALUES (?,?,?,?,?,?)
    """, (
        anon_id,
        host_id,
        msg.from_user.id,
        msg.from_user.first_name,
        msg.from_user.last_name,
        msg.from_user.username
    ))

    cur.execute("""
        INSERT INTO messages (anon_id, host_id, text, created_at)
        VALUES (?,?,?,?)
    """, (anon_id, host_id, msg.text, datetime.utcnow().isoformat()))
    conn.commit()

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔁 Reply", callback_data=f"reply:{anon_id}"))
    if is_premium_flag:
        kb.add(InlineKeyboardButton("👁 Reveal", callback_data=f"reveal:{anon_id}"))

    await bot.send_message(host_tid, msg.text, reply_markup=kb)
    await msg.answer("✅ Sent anonymously.")
    await state.finish()

#replying
@dp.callback_query_handler(lambda c: c.data.startswith("reply:"))
async def reply_btn(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(anon_id=call.data.split(":")[1])
    await ReplyState.waiting.set()
    await call.message.answer("✍️ Type your reply:")
    await call.answer()

@dp.message_handler(state=ReplyState.waiting, content_types=types.ContentTypes.TEXT)
async def send_reply(msg: types.Message, state: FSMContext):
    anon_id = (await state.get_data()).get("anon_id")
    cur = conn.cursor()

    cur.execute("SELECT telegram_id FROM anon_users WHERE anon_id=?", (anon_id,))
    row = cur.fetchone()
    if not row:
        await msg.answer("❌ Message expired.")
        return await state.finish()

    await bot.send_message(row[0], f"💬 Host replied:\n\n{msg.text}")
    await msg.answer("✅ Reply sent.")
    await state.finish()

# revealing
@dp.callback_query_handler(lambda c: c.data.startswith("reveal:"))
async def reveal(call: types.CallbackQuery):
    anon_id = call.data.split(":")[1]
    cur = conn.cursor()
    tid = call.from_user.id

    if not is_premium(cur, tid):
        return await call.answer("🔒 Premium only.", show_alert=True)

    cur.execute("""
        SELECT first_name, last_name, username
        FROM anon_users WHERE anon_id=?
    """, (anon_id,))
    row = cur.fetchone()

    if not row:
        return await call.answer("Not found", show_alert=True)

    f, l, u = row
    text = f"👤 Sender:\n{f or ''} {l or ''}"
    if u:
        text += f"\n@{u}"

    await call.message.answer(text)
    await call.answer()

# admin
@dp.message_handler(commands=["admin_users"])
async def admin_users(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, is_premium FROM hosts")
    rows = cur.fetchall()
    await msg.answer("\n".join(f"{t} | premium={p}" for t,p in rows) or "No users")

@dp.message_handler(commands=["admin_messages"])
async def admin_messages(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    cur = conn.cursor()
    cur.execute("SELECT text FROM messages ORDER BY id DESC LIMIT 20")
    await msg.answer("\n\n".join(r[0] for r in cur.fetchall()) or "No messages")

#run
async def on_startup(dp):
    logging.info("Bot started and polling")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
