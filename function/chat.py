from dotenv import load_dotenv
import os
import openai

load_dotenv()  # take environment variables from .env.

# To store the chat history
chatstr = ''


def chatmodel(prompt):
    global chatstr  # To access the chatstr variable outside the function

    openai.api_key = os.getenv("OPENAI_KEY")

    # Add user prompt to chatstr
    chatstr += f"User: {prompt}\nAcadBot: "

    # Create a chatbot using ChatCompletion.create() function
    completion = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant.Your role is to help students with their academic queries."},
            {"role": "user", "content": chatstr}
        ]
    )

    # Add bot response to chatstr
    message = completion.choices[0].message.content
    chatstr += f"{message}\n"
    return message
