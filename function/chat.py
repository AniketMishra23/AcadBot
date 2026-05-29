from dotenv import load_dotenv
import os
import openai
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Per-user chat history: { user_id: conversation_string }
user_chat_histories = {}

MAX_HISTORY_CHARS = 4000  # Trim history to avoid hitting token limits


def chatmodel(user_id, prompt):
    openai.api_key = os.getenv("OPENAI_KEY")

    # Get or initialise this user's history
    history = user_chat_histories.get(user_id, "")

    history += f"User: {prompt}\nAcadBot: "

    # Trim oldest history if it's getting too long
    if len(history) > MAX_HISTORY_CHARS:
        history = history[-MAX_HISTORY_CHARS:]

    try:
        completion = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are AcadBot, a helpful academic assistant. "
                        "Your role is to help students with their academic queries clearly and concisely."
                    )
                },
                {"role": "user", "content": history}
            ]
        )

        message = completion.choices[0].message.content
        history += f"{message}\n"
        user_chat_histories[user_id] = history
        return message

    except Exception as e:
        logger.error(f"OpenAI API error for user {user_id}: {e}")
        raise
