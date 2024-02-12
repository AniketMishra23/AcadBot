AcadBot: Your Academic Assistant on Telegram
AcadBot is a Telegram bot designed to assist students with their academic needs. It can handle various tasks, including:

Chat & Ask Questions: Engage in open-ended conversations and ask questions on diverse academic topics.
Find Resources: Search for relevant study materials, articles, and other resources.
Ask Questions about PDFs: Upload PDFs and have your questions answered directly within the document.
Getting Started
Create a Telegram Bot: Visit the Telegram BotFather (@BotFather) and create a new bot. Note down the provided bot token.
Install Dependencies: Make sure you have Python and pip installed. Run pip install -r requirements.txt to install the necessary libraries.
Set Up Environment Variables: Create a .env file in your project directory and add the following lines, replacing the placeholders with your actual values:
BOT_TOKEN=YOUR_BOT_TOKEN
OPENAI_KEY=YOUR_OPENAI_KEY
CHATPDF_API=YOUR_CHATPDF_API_KEY
Run the Bot: Execute python main.py to start the bot.
Using AcadBot
Open Telegram and search for your bot's username. You can then interact with the bot using natural language commands:

Start a conversation: Say "Hi" or "Start" to begin a general chat session.
Ask a question: Type your question directly, and AcadBot will do its best to answer it.
Find resources: Use commands like "/resource query" to search for relevant resources based on your query.
Ask about PDFs: Upload a PDF document and ask questions about its content.
Additional Notes
AcadBot is still under development, and its capabilities are constantly being improved.
Feel free to provide feedback or suggestions to help make AcadBot even better!