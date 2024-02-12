# AcadBot: Your Academic Assistant on Telegram

## Description

AcadBot is a Telegram bot designed to assist students with their academic needs. It can handle various tasks, including:

- Chat & Ask Questions
- Find Resources
- Ask Questions about PDFs

## Getting Started

1. **Create a Telegram Bot:**
   - Visit the Telegram BotFather (@BotFather) and create a new bot.
   - Note down the provided bot token.

2. **Install Dependencies:**
   - Make sure you have Python and pip installed.
   - Run `pip install -r requirements.txt` to install the necessary libraries.

3. **Set Up Environment Variables:**
   - Create a `.env` file in your project directory and add the following lines, replacing the placeholders with your actual values:
   
     ```
     BOT_TOKEN=<YOUR_BOT_TOKEN>
     OPENAI_KEY=<YOUR_OPENAI_KEY>
     CHATPDF_API=<YOUR_CHATPDF_API_KEY>
     ```

   - Replace the placeholders with your actual values later.

4. **Run the Bot:**
- Execute `python main.py` to start the bot.

## Usage

1. Open Telegram and search for your bot's username.
2. Interact with the bot using natural language commands:
- Start a conversation: Say "Hi" or "Start".
- Ask a question: Type your question directly.
- Find resources: Use commands like "/resource query".
- Ask about PDFs: Upload a PDF document and ask questions about its content.

## Additional Notes

- AcadBot is still under development.
- Feel free to provide feedback or suggestions!