import telebot
import os
import dotenv

from function.chat import chatmodel
from function.res import findlink
from function.qna import doc_qna, chatpdf_chat
# from function.qna import chatpdf_chat

# Load environment variables
dotenv.load_dotenv()
# Get bot token from environment variable
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

# Initialize user state
user_state = STATE_NONE

# Start command


@bot.message_handler(commands=['start'])
def start(message):
    global user_state, context
    bot.reply_to(message, """Hello there! I'm AcadBot, your personal academic assistant. I can help you with various tasks, including:
⁕ Answering your questions on diverse academic topics.
⁕ Searching for relevant study materials, articles, and other resources.
⁕ Answering your questions directly within uploaded PDF documents.
**Just ask me anything! ** You can chat with me like you would a friend, or use specific commands for certain functionalities. 
For more info, click here "/help".""")
    user_state = STATE_WAITING_FOR_START

# Help command


@bot.message_handler(commands=['help'])
def help(message):
    global user_state
    bot.reply_to(message, """Hey! Looking for some guidance? Here's how you can use me:
⁕ Chat & Ask Questions: Type your queries as you normally would, and I'll do my best to provide helpful answers.
⁕ Find Resources: Need articles, books, or other materials? Use the command "/resource".
⁕ Ask Questions about PDFs: Upload a PDF and ask your questions directly within the document. Just send the file and wait for the bots message to ask questions. Use the command "/pdf_qna"
⁕ I'm still under development, but I'm learning every day! Feel free to ask anything, and if I can't answer, I'll let you know""")
    user_state = STATE_WAITING_FOR_HELP

# Resource command


@bot.message_handler(commands=['resource'])
def resource(message):
    global user_state
    bot.reply_to(message, "Enter your query to find the resource link.")
    user_state = STATE_WAITING_FOR_RESOURCE

# PDF QnA command


@bot.message_handler(commands=['pdf_qna'])
def pdf_qna(message):
    global user_state
    bot.reply_to(message, "Send your file.")
    user_state = STATE_WAITING_FOR_PDF


sourceID = None


@bot.message_handler(content_types=['document'])
def docs(message):
    global user_state, sourceID
    bot.send_message(message.chat.id, "{0} file received.".format(
        message.document.file_name))
    bot.send_message(message.chat.id, "Processing, please wait....")
    if user_state == STATE_WAITING_FOR_PDF:
        fileid = message.document.file_id
        filename = message.document.file_name

        # Call doc_qna to download and return source ID
        sourceID = doc_qna(bot_token, fileid, filename, api_key)
        # print(sourceID)

        # Check if doc_qna was successful
        if sourceID:

            bot.send_message(
                message.chat.id, "Ask me your questions about the file. (Type 'stop' to finish)")
            user_state = STATE_WAITING_FOR_MORE_QUERY

        else:
            bot.reply_to(
                message, "Failed to process the file. Please try again.")
            user_state = STATE_NONE
    else:
        bot.reply_to(message, "No document received.")
        user_state = STATE_NONE
    # return sourceID


# Chat command
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    global user_state, sourceID
    if user_state == STATE_WAITING_FOR_RESOURCE:
        reply = findlink(message.text)
        if reply:
            bot.reply_to(message, reply)
        else:
            bot.reply_to(
                message, "Sorry, I couldn't find any link for your query.")
        user_state = STATE_NONE

    elif user_state == STATE_WAITING_FOR_MORE_QUERY:
        bot.send_chat_action(message.chat.id, 'typing')
        if message.text == "Stop":
            user_state = STATE_NONE
            bot.reply_to(message, "Goodbye!")
        else:
            question = message.text
            # Send question to ChatPDF
            answer = chatpdf_chat(api_key, question, sourceID)
            bot.reply_to(message, answer)
            bot.send_message(
                message.chat.id, "Do you have another question? (Type 'stop' to finish)")
    elif user_state in [STATE_WAITING_FOR_START, STATE_WAITING_FOR_HELP]:
        user_state = STATE_NONE

    else:
        try:
            reply = chatmodel(message.text)
            # print(message)
            bot.send_chat_action(message.chat.id, 'typing')
            bot.reply_to(message, reply)
            user_state = STATE_NONE
        except Exception as e:
            bot.reply_to(message, str(e))
            user_state = STATE_NONE


print("Bot is running...")
bot.polling()  # To keep the bot running
