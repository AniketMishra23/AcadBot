import telebot
import os
import dotenv
import logging

from function.chat import chatmodel
from function.res import findlink
from function.qna import doc_qna, chatpdf_chat

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
dotenv.load_dotenv()

bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))
api_key = os.getenv("CHATPDF_API")
bot_token = os.getenv("BOT_TOKEN")

# Define states
STATE_NONE = 0
STATE_WAITING_FOR_START = 1
STATE_WAITING_FOR_HELP = 2
STATE_WAITING_FOR_RESOURCE = 3
STATE_WAITING_FOR_PDF = 4
STATE_WAITING_FOR_MORE_QUERY = 5

# Per-user state and PDF source tracking
user_states = {}    # { user_id: state }
user_sources = {}   # { user_id: sourceID }


def get_state(user_id):
    return user_states.get(user_id, STATE_NONE)


def set_state(user_id, state):
    user_states[user_id] = state


def get_source(user_id):
    return user_sources.get(user_id)


def set_source(user_id, source_id):
    user_sources[user_id] = source_id


# Start command
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    set_state(user_id, STATE_WAITING_FOR_START)
    bot.reply_to(message, (
        "Hello there! I'm AcadBot, your personal academic assistant. I can help you with:\n"
        "⁕ Answering your questions on diverse academic topics.\n"
        "⁕ Searching for relevant study materials, articles, and other resources.\n"
        "⁕ Answering your questions directly within uploaded PDF documents.\n\n"
        "Just ask me anything! For more info, type /help"
    ))
    logger.info(f"User {user_id} started the bot.")


# Help command
@bot.message_handler(commands=['help'])
def help(message):
    user_id = message.from_user.id
    set_state(user_id, STATE_WAITING_FOR_HELP)
    bot.reply_to(message, (
        "Here's how you can use me:\n"
        "⁕ Chat & Ask Questions: Type your query and I'll answer.\n"
        "⁕ Find Resources: Use /resource to search for study materials.\n"
        "⁕ Ask Questions about PDFs: Use /pdf_qna then send a PDF file.\n\n"
        "I'm still learning — feel free to ask anything!"
    ))


# Resource command
@bot.message_handler(commands=['resource'])
def resource(message):
    user_id = message.from_user.id
    set_state(user_id, STATE_WAITING_FOR_RESOURCE)
    bot.reply_to(message, "Enter your query to find the resource link.")


# PDF QnA command
@bot.message_handler(commands=['pdf_qna'])
def pdf_qna(message):
    user_id = message.from_user.id
    set_state(user_id, STATE_WAITING_FOR_PDF)
    bot.reply_to(message, "Send your PDF file.")


# Document handler
@bot.message_handler(content_types=['document'])
def docs(message):
    user_id = message.from_user.id

    if get_state(user_id) != STATE_WAITING_FOR_PDF:
        bot.reply_to(message, "Please use /pdf_qna first before sending a file.")
        return

    filename = message.document.file_name
    bot.send_message(message.chat.id, f"{filename} received. Processing, please wait...")

    fileid = message.document.file_id
    downloaded_path = None

    try:
        source_id, downloaded_path = doc_qna(bot_token, fileid, filename, api_key)

        if source_id:
            set_source(user_id, source_id)
            set_state(user_id, STATE_WAITING_FOR_MORE_QUERY)
            bot.send_message(
                message.chat.id,
                "Ready! Ask me your questions about the file. (Type 'stop' to finish)"
            )
            logger.info(f"User {user_id} uploaded PDF: {filename}, sourceId: {source_id}")
        else:
            bot.reply_to(message, "Failed to process the file. Please try again.")
            set_state(user_id, STATE_NONE)

    except Exception as e:
        logger.error(f"Error processing PDF for user {user_id}: {e}")
        bot.reply_to(message, "An error occurred while processing your file. Please try again.")
        set_state(user_id, STATE_NONE)

    finally:
        # Always clean up the downloaded file
        if downloaded_path and os.path.exists(downloaded_path):
            os.remove(downloaded_path)
            logger.info(f"Cleaned up temp file: {downloaded_path}")


# General message handler
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == STATE_WAITING_FOR_RESOURCE:
        try:
            reply = findlink(message.text)
            bot.reply_to(message, reply)
        except Exception as e:
            logger.error(f"Resource lookup error for user {user_id}: {e}")
            bot.reply_to(message, "Sorry, I couldn't find any resources for your query.")
        set_state(user_id, STATE_NONE)

    elif state == STATE_WAITING_FOR_MORE_QUERY:
        if message.text.strip().lower() == "stop":
            set_state(user_id, STATE_NONE)
            set_source(user_id, None)
            bot.reply_to(message, "Session ended. Feel free to ask something else!")
        else:
            bot.send_chat_action(message.chat.id, 'typing')
            try:
                source_id = get_source(user_id)
                answer = chatpdf_chat(api_key, message.text, source_id)
                bot.reply_to(message, answer)
                bot.send_message(
                    message.chat.id,
                    "Any other questions? (Type 'stop' to finish)"
                )
            except Exception as e:
                logger.error(f"ChatPDF error for user {user_id}: {e}")
                bot.reply_to(message, "Something went wrong. Please try asking again.")

    elif state in [STATE_WAITING_FOR_START, STATE_WAITING_FOR_HELP]:
        set_state(user_id, STATE_NONE)
        # Fall through to general chat
        _handle_chat(message, user_id)

    else:
        _handle_chat(message, user_id)


def _handle_chat(message, user_id):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        reply = chatmodel(user_id, message.text)
        bot.reply_to(message, reply)
    except Exception as e:
        logger.error(f"Chat error for user {user_id}: {e}")
        bot.reply_to(message, "Sorry, I ran into an error. Please try again.")
    set_state(user_id, STATE_NONE)


# Start bot with auto-restart on transient errors
logger.info("Bot is starting...")
while True:
    try:
        bot.polling(non_stop=True, interval=0, timeout=30)
    except Exception as e:
        logger.error(f"Polling crashed: {e}. Restarting in 5 seconds...")
        import time
        time.sleep(5)
