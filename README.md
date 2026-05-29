# AcadBot — Your University Assistant on Telegram

AcadBot is a Telegram bot that acts as a personal academic assistant for university students. Point it at any university website and it will scrape, index, and answer questions about results, notices, study material, events, timetables, and more — all in a natural chat interface.

---

## Features

| Feature | Description |
|---|---|
| 💬 **AI Chat** | Groq (Llama 3.3 70B) as primary model, Google Gemini 2.0 Flash as automatic fallback |
| 🏫 **University Scraper** | Crawls any university website (login-protected or public) and indexes all content |
| 📄 **PDF Q&A** | Upload any PDF and chat with it — fully local, no external API |
| 🔍 **Resource Search** | Semantic + keyword search over scraped university pages |
| 🔒 **Secure Credentials** | University login credentials encrypted with Fernet before storage |
| 🗄️ **Shared Index** | Multiple students from the same university share one scrape — efficient |

---

## How It Works

```
Student (Telegram)
       │
       ▼
   AcadBot
   ┌──────────────────────────────────────────────┐
   │                                              │
   │  AI Chat ──────────► Groq (Llama 3.3 70B)   │
   │                  └──► Gemini 2.0 Flash       │
   │                        (auto fallback)       │
   │                                              │
   │  Uni Info ─────────► Scraper (requests +     │
   │                       BeautifulSoup)         │
   │                    └──► FAISS vector index   │
   │                         (local, on-disk)     │
   │                                              │
   │  PDF Q&A ──────────► pdfplumber extract      │
   │                    └──► FAISS session index  │
   │                         (in-memory)          │
   │                                              │
   │  Database ──────────► SQLite                 │
   │                       (users, universities,  │
   │                        credentials, pages)   │
   └──────────────────────────────────────────────┘
```

### Onboarding Flow (new user)
```
/start
  └─► "What's your university URL?"
        └─► Auto-detect if login required
              ├─► No login → start scraping in background
              └─► Login needed → ask username → ask password (encrypted)
                                  └─► scrape with credentials
                                        └─► index complete → bot is ready
```

---

## Tech Stack

| Component | Technology | Cost |
|---|---|---|
| Chat model | Groq API (Llama 3.3 70B) | Free |
| Chat fallback | Google Gemini 2.0 Flash | Free |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Free, local |
| Vector search | FAISS | Free, local |
| PDF extraction | pdfplumber | Free, local |
| Web scraping | requests + BeautifulSoup | Free, local |
| Database | SQLite | Free, local |
| Encryption | cryptography (Fernet) | Free, local |

**Total running cost: $0/month**

---

## Project Structure

```
AcadBot/
├── main.py                  # Bot entry point, all command & state handlers
├── requirements.txt
├── .env.example             # Template for environment variables
├── .env                     # Your secrets (never committed)
│
├── function/
│   ├── chat.py              # Groq + Gemini fallback chat model
│   ├── rag.py               # RAG pipeline (embed → FAISS → query)
│   ├── scraper.py           # Universal university website crawler
│   ├── database.py          # SQLite schema and queries
│   ├── res.py               # Resource finder (RAG → DB → static fallback)
│   └── pdflinks.txt         # Static fallback resource links
│
├── data/
│   ├── acadbot.db           # SQLite database (auto-created)
│   └── vector_stores/       # FAISS indexes per university (auto-created)
│       └── {uni_id}/
│           ├── index.faiss
│           └── chunks.pkl
│
└── website/                 # Companion website (hosted on Netlify)
```

---

## Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/AniketMishra23/AcadBot.git
cd AcadBot
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

Copy `.env.example` to `.env` and fill in your keys:

```env
BOT_TOKEN=your_telegram_bot_token

GROQ_API_KEY=your_groq_api_key        # https://console.groq.com  (free)
GEMINI_API_KEY=your_gemini_api_key    # https://aistudio.google.com (free)

ENCRYPTION_KEY=your_fernet_key        # generate with the command below
```

Generate your `ENCRYPTION_KEY`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Create a Telegram bot
- Open [@BotFather](https://t.me/BotFather) on Telegram
- Send `/newbot` and follow the prompts
- Copy the token into `BOT_TOKEN` in your `.env`

### 5. Run
```bash
python main.py
```

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Onboard (new user) or greet returning user |
| `/setup` | Change or re-index your university |
| `/resource` | Search for notices, results, study material, events |
| `/pdf_qna` | Upload a PDF and chat with it |
| `/clear` | Clear chat history and active PDF session |
| `/help` | Show all commands |

---

## Page Classification

The scraper automatically classifies every page it crawls:

| Type | Keywords detected |
|---|---|
| `result` | result, marksheet, grade, score, merit list, cgpa |
| `notice` | notice, circular, announcement, notification, bulletin |
| `event` | event, seminar, workshop, conference, webinar, fest |
| `material` | syllabus, notes, lecture, study material, question paper |
| `timetable` | timetable, schedule, routine, exam date, academic calendar |
| `admission` | admission, enroll, registration, application, fee |
| `general` | everything else |

---

## How the RAG Pipeline Works

```
Scrape university pages
        │
        ▼
  Extract text + PDF links
        │
        ▼
  Chunk into 500-char segments (80-char overlap)
        │
        ▼
  Embed with all-MiniLM-L6-v2  (384-dim vectors)
        │
        ▼
  Store in FAISS index  →  saved to data/vector_stores/{uni_id}/
        │
  ┌─────┘
  │  On student query
  ▼
  Embed the question
        │
        ▼
  Top-5 nearest chunks retrieved from FAISS
        │
        ▼
  Injected as context into the LLM prompt
        │
        ▼
  LLM answers citing the source pages
```

The same pipeline handles uploaded PDFs — just stored in a per-user in-memory index instead of on disk.

---

## Security

- University passwords are **never stored in plain text**
- Encrypted with [Fernet symmetric encryption](https://cryptography.io/en/latest/fernet/) before writing to SQLite
- The `ENCRYPTION_KEY` in `.env` is required to decrypt — keep it safe
- `.env` and `data/` are excluded from git via `.gitignore`

---

## Roadmap

- [ ] Freemium model (usage limits + Telegram Stars payments)
- [ ] Scheduled re-scraping (auto-refresh university content daily)
- [ ] Playwright support for JavaScript-heavy university portals
- [ ] Multi-language support
- [ ] Deployment guide (Railway / Render)

---

## Contributing

Pull requests are welcome. For major changes, open an issue first.

---

## License

MIT
