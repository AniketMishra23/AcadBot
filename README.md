# AcadBot — Your University Assistant on Telegram

AcadBot is a Telegram bot that acts as a personal academic assistant for university students. Point it at any university website and it will scrape, index, and answer questions about results, notices, study material, events, timetables, and more — all in a natural chat interface.

---

## For Students (Using the Bot)

**No setup needed.** Just open Telegram and search for **@AcadBot** (or the deployed bot username).

1. Send `/start`
2. Send your university website URL when asked
3. If your portal requires login, the bot will ask for your credentials (encrypted at rest)
4. The bot crawls your university site (~1–2 min) and is ready

That's it — no account, no app, no installation.

---

## Features

| Feature | Description |
|---|---|
| 💬 **AI Chat** | Groq (Llama 3.3 70B) as primary model, Google Gemini 2.0 Flash as automatic fallback |
| 🏫 **University Scraper** | Crawls any university website (login-protected or public) and indexes all content |
| 📄 **PDF Q&A** | Upload any PDF and chat with it — fully local, no external API cost |
| 🔍 **Resource Search** | Semantic + keyword search over scraped university pages |
| 🔒 **Secure Credentials** | University login credentials encrypted with Fernet before storage |
| 🗄️ **Shared Index** | Multiple students from the same university share one scrape — efficient |

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

## How It Works

```
Student (Telegram)
       │
       ▼
   AcadBot (Railway)
   ┌──────────────────────────────────────────────────────┐
   │                                                      │
   │  AI Chat ──────────► Groq (Llama 3.3 70B)            │
   │                  └──► Gemini 2.0 Flash (fallback)    │
   │                                                      │
   │  Uni Info ─────────► Scraper (requests+BS4)          │
   │                    └──► Qdrant Cloud (vectors)       │
   │                                                      │
   │  PDF Q&A ──────────► pdfplumber → FAISS (in-memory) │
   │                                                      │
   │  Database ──────────► PostgreSQL (Railway addon)     │
   └──────────────────────────────────────────────────────┘
```

### Onboarding Flow

```
/start
  └─► New user? → "What's your university URL?"
        └─► Auto-detect login required
              ├─► No  → scrape in background thread
              └─► Yes → ask username → ask password (encrypted)
                          └─► scrape with credentials
                                └─► index in Qdrant → bot ready
```

---

## Tech Stack

| Component | Technology | Hosted At | Cost |
|---|---|---|---|
| Bot runner | Python + pyTelegramBotAPI | Railway | Free |
| Chat model | Groq API (Llama 3.3 70B) | Groq Cloud | Free |
| Chat fallback | Google Gemini 2.0 Flash | Google AI | Free |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Railway (local) | Free |
| Vector store | Qdrant | Qdrant Cloud | Free (1 GB) |
| Database | PostgreSQL | Railway addon | Free |
| PDF extraction | pdfplumber | Railway (local) | Free |
| Web scraping | requests + BeautifulSoup | Railway (local) | Free |
| Encryption | cryptography (Fernet) | Railway (local) | Free |

**Total running cost: $0/month**

---

## Project Structure

```
AcadBot/
├── main.py                  # Bot entry point — all commands, state machine, onboarding
├── Procfile                 # Railway: tells it to run main.py as a worker
├── railway.json             # Railway deploy config
├── requirements.txt
├── .env.example             # Template — copy to .env and fill in keys
│
├── function/
│   ├── chat.py              # Groq + Gemini fallback, per-user history
│   ├── rag.py               # Qdrant (university) + FAISS (PDF sessions)
│   ├── scraper.py           # Universal university crawler + login handler
│   ├── database.py          # PostgreSQL schema and queries
│   ├── res.py               # Resource finder (RAG → DB → static fallback)
│   └── pdflinks.txt         # Static fallback resource links
│
└── website/                 # Companion website (Netlify)
```

---

## For Developers — Self-Hosting

### 1. Prerequisites — create free accounts

| Service | What it's for | Link |
|---|---|---|
| Telegram | Create a bot token | [@BotFather](https://t.me/BotFather) |
| Railway | Host the bot + PostgreSQL | [railway.app](https://railway.app) |
| Groq | Free LLM API | [console.groq.com](https://console.groq.com) |
| Google AI Studio | Gemini fallback API | [aistudio.google.com](https://aistudio.google.com) |
| Qdrant Cloud | Vector database | [cloud.qdrant.io](https://cloud.qdrant.io) |

### 2. Clone the repo

```bash
git clone https://github.com/AniketMishra23/AcadBot.git
cd AcadBot
```

### 3. Deploy to Railway

**a) Connect repo**
1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Select `AniketMishra23/AcadBot`

**b) Add PostgreSQL**
1. In your Railway project → Add Service → Database → PostgreSQL
2. Railway automatically sets `DATABASE_URL` as an environment variable

**c) Set environment variables**

In Railway → your service → Variables, add:

```
BOT_TOKEN          = your telegram bot token
GROQ_API_KEY       = from console.groq.com
GEMINI_API_KEY     = from aistudio.google.com
QDRANT_URL         = from Qdrant Cloud cluster console
QDRANT_API_KEY     = from Qdrant Cloud cluster console
ENCRYPTION_KEY     = generated below
```

Generate your `ENCRYPTION_KEY` (run once locally):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**d) Deploy**

Railway auto-deploys on every push to `main`. The `Procfile` tells it to run `python main.py` as a background worker (not a web server — no port needed).

---

### Running Locally (development)

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python main.py
```

For local PostgreSQL you can use [Neon](https://neon.tech) (free serverless Postgres) and paste the connection string as `DATABASE_URL`.

---

## How the RAG Pipeline Works

```
Scrape university pages
        │
        ▼
  Extract text + PDF links per page
        │
        ▼
  Split into 500-char chunks (80-char overlap)
        │
        ▼
  Embed with all-MiniLM-L6-v2 (384-dim vectors)
        │
        ▼
  Upsert into Qdrant Cloud  ←  filtered by uni_id
        │
  ┌─────┘  on student query
  ▼
  Embed the question
        │
        ▼
  Top-5 nearest chunks from Qdrant (same uni_id)
        │
        ▼
  Injected as context into LLM prompt
        │
        ▼
  LLM answers, citing source page titles
```

PDF uploads use the same chunking and embedding, but stored in a per-user in-memory FAISS index (not Qdrant) — ephemeral, cleared when the user types `stop`.

---

## Page Classification

The scraper automatically classifies every crawled page:

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

## Security

- University passwords are **never stored in plain text**
- Encrypted with [Fernet symmetric encryption](https://cryptography.io/en/latest/fernet/) before writing to PostgreSQL
- The `ENCRYPTION_KEY` in your environment is required to decrypt — never lose it
- `.env` is excluded from git via `.gitignore`

---

## Roadmap

- [ ] Freemium model (usage limits + Telegram Stars payments)
- [ ] Scheduled re-scraping (auto-refresh university content daily)
- [ ] Playwright support for JavaScript-heavy university portals
- [ ] Multi-language support

---

## Contributing

Pull requests are welcome. Open an issue first for major changes.

---

## License

MIT
