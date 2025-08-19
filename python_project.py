import logging
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

TOKEN = "8080770352:AAHfjk_S9BrdKb6PnEd9pu1R4u54gin_dUQ"

logging.basicConfig(level=logging.INFO)

user_balances = {}
group_data = {}       # chat_id: {"nickname": str, "members": set(), "creator": user_id}
user_ranks = {}       # chat_id: {user_id: rank}
banned_users = {}     # chat_id: set(user_id)
admin_sessions = {}   # user_id: {"state": str, "current_group": chat_id}
muted_users = {}      # chat_id: {user_id: mute_end_datetime}


# ---------- Проверка доступа ----------
def check_access(chat_id, user_id):
    return user_id not in banned_users.get(chat_id, set())

def check_mute(chat_id, user_id):
    end_time = muted_users.get(chat_id, {}).get(user_id)
    if not end_time:
        return False
    return datetime.now() < end_time


# ---------- /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_id = chat.id
    user_id = update.effective_user.id

    if chat.type == "private":
        await update.message.reply_text(
            "Привет! Этот бот работает только в группах. "
            "Добавь меня в группу, чтобы использовать команды."
        )
        return

    if chat_id not in group_data or "nickname" not in group_data[chat_id]:
        await update.message.reply_text(
            "⚠ У группы пока нет ника.\n"
            "Задайте его с помощью команды:\n"
            "/setchatnick <ник>"
        )
        return

    group_data[chat_id]["members"].add(user_id)

    if not check_access(chat_id, user_id):
        await update.message.reply_text("❌ У тебя нет доступа к боту!")
        return

    if check_mute(chat_id, user_id):
        await update.message.reply_text("🔇 Ты сейчас в муте и не можешь использовать команды!")
        return

    await update.message.reply_text(
        f"✅ Группа «{group_data[chat_id]['nickname']}» готова к использованию!\n\n"
        "Доступные команды:\n"
        "🎰 /depnut — депнуть (казино)\n"
        "💰 /balans — проверить баланс\n"
        "🎁 /bonus — получить бонус (раз в 10ч)\n"
        "🏷 /setchatnick — изменить ник группы\n"
        "⚙ /action — (только по reply)\n"
        "🏅 /rangs — посмотреть ранги участников"
    )


# ---------- /setchatnick ----------
async def setchatnick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    chat_id = chat.id
    user_id = update.effective_user.id

    if len(context.args) < 1:
        await update.message.reply_text("Используй: /setchatnick <ник>")
        return

    nickname = context.args[0]

    if nickname in [g.get("nickname") for g in group_data.values()]:
        await update.message.reply_text("Такой ник уже занят, выбери другой!")
        return

    # Если группа новая, сохраняем создателя
    if chat_id not in group_data:
        group_data[chat_id] = {"nickname": nickname, "members": set(), "creator": user_id}
        user_ranks[chat_id] = {user_id: 3}  # создатель автоматически 3-й ранг
    else:
        # Если уже был ник, не меняем создателя
        group_data[chat_id]["nickname"] = nickname

    banned_users.setdefault(chat_id, set())
    await update.message.reply_text(f"✅ Ник группы установлен: {nickname}\nТеперь можно использовать бота!")


# ---------- /depnut ----------
async def depnut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in group_data or "nickname" not in group_data[chat_id]:
        await update.message.reply_text("⚠ Сначала установите ник группы")
        return

    if not check_access(chat_id, user_id):
        await update.message.reply_text("❌ У тебя нет доступа к боту!")
        return

    if check_mute(chat_id, user_id):
        await update.message.reply_text("🔇 Ты сейчас в муте и не можешь использовать команды!")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Используй: /depnut <сумма> или ответ на сообщение для депнута другого")
        return

    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        user_rank = user_ranks.get(chat_id, {}).get(user_id, 0)
        target_rank = user_ranks.get(chat_id, {}).get(target_id, 0)
        if user_rank < target_rank:
            await update.message.reply_text("❌ Ты не можешь депнуть пользователя с более высоким рангом!")
            return

    bet = context.args[0]
    try:
        bet = int(bet)
    except ValueError:
        await update.message.reply_text("Нужно число: /depnut 1000")
        return

    balance = user_balances.get(user_id, 10000)
    if bet > balance:
        await update.message.reply_text("Недостаточно средств!")
        return

    won = random.choice([True, False])
    if target_id and not won:
        # проигрыш при депнуте
        muted_users.setdefault(chat_id, {})[target_id] = datetime.now() + timedelta(hours=1)
        await update.message.reply_text(f"💀 Ты депнул и проёбал {update.message.reply_to_message.from_user.full_name}! Мут 1 час.")
    elif target_id and won:
        balance += bet
        await update.message.reply_text(f"🎉 Победа! Ты депнул {update.message.reply_to_message.from_user.full_name} и выиграл {bet} USK! Баланс: {balance}")
    else:
        if won:
            balance += bet
            await update.message.reply_text(f"🎉 Победа! Теперь у тебя {balance} USK")
        else:
            balance -= bet
            await update.message.reply_text(f"❌ Проигрыш... Осталось {balance} USK")
    user_balances[user_id] = balance


# ---------- /balans ----------
async def balans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not check_access(chat_id, user_id):
        await update.message.reply_text("❌ У тебя нет доступа к боту!")
        return
    balance = user_balances.get(user_id, 10000)
    await update.message.reply_text(f"💰 Твой баланс: {balance} USK")


# ---------- /bonus ----------
async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not check_access(chat_id, user_id):
        await update.message.reply_text("❌ У тебя нет доступа к боту!")
        return

    balance = user_balances.get(user_id, 10000) + 10000
    user_balances[user_id] = balance
    await update.message.reply_text(f"🎁 Бонус +10000 USK! Баланс: {balance}")


# ---------- /rangs ----------
async def rangs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    members = group_data.get(chat_id, {}).get("members", set())
    if not members:
        await update.message.reply_text("❌ В группе нет участников")
        return
    text = "🏅 Ранги участников:\n"
    for m in members:
        rank = user_ranks.get(chat_id, {}).get(m, 0)
        text += f"{m}: {rank}\n"
    await update.message.reply_text(text)


# ---------- /action ----------
async def action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in group_data or "nickname" not in group_data[chat_id]:
        await update.message.reply_text("⚠ Сначала установите ник группы")
        return
    if not check_access(chat_id, user_id):
        await update.message.reply_text("❌ У тебя нет доступа к боту!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠ Нужно ответить на сообщение")
        return

    keyboard = [
        [InlineKeyboardButton("🔇 Мут", callback_data="mute_"+str(update.message.reply_to_message.from_user.id)),
         InlineKeyboardButton("🔊 Размут", callback_data="unmute_"+str(update.message.reply_to_message.from_user.id))],
        [InlineKeyboardButton("⛔ Кик", callback_data="kick_"+str(update.message.reply_to_message.from_user.id)),
         InlineKeyboardButton("🚫 Бан", callback_data="ban_"+str(update.message.reply_to_message.from_user.id))]
    ]
    await update.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))


# ---------- Callback кнопок ----------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action = data[0]
    target_id = int(data[1])
    chat_id = query.message.chat.id

    if action == "ban":
        banned_users.setdefault(chat_id, set()).add(target_id)
        await query.edit_message_text("Пользователь забанен ✅")
    elif action == "unmute":
        if chat_id in muted_users and target_id in muted_users[chat_id]:
            del muted_users[chat_id][target_id]
        await query.edit_message_text("Размут ✅")
    elif action == "mute":
        muted_users.setdefault(chat_id, {})[target_id] = datetime.now() + timedelta(hours=1)
        await query.edit_message_text("Мут ✅")
    elif action == "kick":
        await query.edit_message_text("Кик ✅")
    elif action == "logout":
        user_id = query.from_user.id
        if user_id in admin_sessions:
            del admin_sessions[user_id]
        await query.edit_message_text("✅ Вышли из админ-панели")


# ---------- Подсказки команд ----------
async def set_commands(application):
    await application.bot.set_my_commands([
        ("start", "🚀 Начало"),
        ("depnut", "🎰 Депнуть"),
        ("balans", "💰 Баланс"),
        ("bonus", "🎁 Бонус"),
        ("setchatnick", "🏷 Ник группы"),
        ("login", "🔑 Вход"),
        ("action", "⚙ Действия (по reply)"),
        ("rangs", "🏅 Посмотреть ранги")
    ])


# ---------- Main ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("depnut", depnut))
    app.add_handler(CommandHandler("balans", balans))
    app.add_handler(CommandHandler("bonus", bonus))
    app.add_handler(CommandHandler("setchatnick", setchatnick))
    app.add_handler(CommandHandler("action", action))
    app.add_handler(CommandHandler("rangs", rangs))
    app.add_handler(CallbackQueryHandler(button))
    app.post_init = lambda _: set_commands(app)
    app.run_polling()


if __name__ == "__main__":
    main()
