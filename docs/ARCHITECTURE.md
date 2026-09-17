# 🏗️ Streamer Bot Architecture

## Overview

Multi-channel Telegram bot powered by aiogram, Google Sheets content management, and Groq AI search capabilities.

---

## 🔄 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram Users                           │
│        (in private chat + channel discussion groups)        │
└────────────────────────┬──────────────────────────────────┘
                         │ /start, buttons, queries
                         ▼
┌─────────────────────────────────────────────────────────────┐
│            Aiogram 3 (Python Bot Framework)                │
│            (running in Docker container)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Message Handlers                                          │
│  ├─ /start → Main menu                                   │
│  ├─ /menu → Show navigation buttons                      │
│  ├─ /reload → Refresh Google Sheets cache                │
│  ├─ Text message → AI search                             │
│  └─ Button clicks → Route to section                     │
│                                                             │
│  Auto-Comments Handler                                     │
│  ├─ Listen to discussion group chats                     │
│  ├─ Detect channel discussion group                      │
│  ├─ Post first comment (topic-based)                    │
│  └─ Add inline buttons                                   │
│                                                             │
└─────────┬──────────────────────────┬──────────────────────┘
          │                          │
          ▼                          ▼
    ┌──────────────┐         ┌─────────────────┐
    │  Google      │         │  Groq LLM API   │
    │  Sheets API  │         │                 │
    │  (gspread)   │         │ • Embeddings    │
    │              │         │ • Semantic      │
    │ • Kontekt    │         │   search        │
    │ • AutoKom    │         │ • Hybrid search │
    │ • Channels   │         │                 │
    │ • Settings   │         │ free tier OK    │
    └──────────────┘         └─────────────────┘
          │
          ▼
    ┌──────────────┐
    │  Redis       │
    │  Cache       │
    │              │
    │ FSM state    │
    │ Sheet cache  │
    │ (5 min TTL)  │
    └──────────────┘
```

---

## 📊 Data Flow

### User → Menu → Content
```
User sends /start
        │
        ▼
Bot loads from Google Sheets (if not cached)
        │
        ▼
Generate keyboard with sections:
  [Сайт] [Соцсети] [Гайды] [Игры] [Сервисы] [Ставки]
        │
        ▼
User clicks [Игры]
        │
        ▼
If has subcategories:
  Show: [Dota 2] [Warhammer] [Warcraft] [Civ5]
        │
        ▼
User clicks [Dota 2]
        │
        ▼
Show buttons from Sheets with links/descriptions
        │
        ▼
User clicks button → Open URL or send message
```

### AI Search Flow
```
User sends: "как играть в доту?"
        │
        ▼
Groq LLM embeddings on user text
        │
        ▼
Search in Sheets descriptions + keywords (hybrid search)
        │
        ▼
Rank results by semantic similarity + keyword match
        │
        ▼
Return top 3-5 results with links
        │
        ▼
Format as inline buttons in Telegram
```

### Auto-Comments in Discussion Groups
```
1. Channel goes live (video/stream posted)
        │
        ▼
2. Discussion group link activated (auto-created by Telegram)
        │
        ▼
3. Bot is member of discussion group (added manually)
        │
        ▼
4. Bot detects new discussion group created (by chat_id)
        │
        ▼
5. Posts auto-comment from АвтоКомменты sheet
        │
        ▼
6. Adds inline buttons (topic-based)
```

---

## 🗄️ Google Sheets Schema

### Sheet: "Контент"
```
| section    | category  | title         | url       | description       | keywords        |
|------------|-----------|---------------|-----------|-------------------|-----------------|
| Игры       | Dota 2    | Guide: Carry  | http://.. | Tips for farming   | dota, carry, farm|
| Игры       | Dota 2    | Hero Stats    | http://.. | 7.35 meta update   | dota, heroes     |
| Сервисы    |           | VPN Proxy     | http://.. | Bypass blocks      | vpn, proxy       |
| Сайт       |           | Main Site     | http://.. | My website link    | site, portfolio  |
```

**Columns:**
- `section`: Сайт, Соцсети, Гайды, Игры, Сервисы, Ставки
- `category`: Optional subcategory (shows as submenu)
- `title`: Button text
- `url`: Click → open this link
- `description`: Used for AI search
- `keywords`: For keyword-based search (comma-separated)

### Sheet: "АвтоКомменты"
```
| chat_id         | название              | тематика      | текст              | кнопки           |
|-----------------|----------------------|---------------|--------------------|-----------------|
| -1001234567890  | Основной канал        | dota          | Привет! Я тут.    | Ссылка1\|url1;;Ссылка2\|url2 |
| -1002345678901  | Warhammer обсуждение  | warhammer     | W40K fans, welcome!| Rules\|url\;FAQ\|url |
```

**Columns:**
- `chat_id`: From /getMyId in the group (negative number)
- `название`: Name for you (not shown to users)
- `тематика`: dota, warhammer, warcraft, civ5, bets_dota, bets_football
- `текст`: First comment message
- `кнопки`: Format: `Text1|url1;;Text2|url2;;Text3|url3`

### Sheet: "Каналы"
```
| chat_id       | название            | привязка_к_категории |
|---------------|---------------------|----------------------|
| -1001234567   | Main Discussion     | Dota 2               |
| -1002345678   | Warhammer Chat      | Warhammer            |
```

### Sheet: "Настройки"
```
| ключ           | значение                                           |
|----------------|---------------------------------------------------|
| greeting       | Привет! Я Травобот 🤖...                        |
| support_email  | support@travobot.ru                               |
| owner_id       | 327410144                                         |
```

---

## 🔐 Authentication & Credentials

### Telegram Bot Token
```
From @BotFather: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi
├─ Never commit to git
├─ Store in .env: BOT_TOKEN=...
└─ Used in bot.run_polling()
```

### Google Sheets Access
```
1. Service Account JSON (credentials.json)
   ├─ Created in Google Cloud Console
   ├─ Contains private_key + client_email
   ├─ Never commit to git
   └─ Mount in Docker: GOOGLE_CREDENTIALS=/app/credentials.json

2. Sheets ID (from URL)
   └─ docs.google.com/spreadsheets/d/[THIS_ID]/edit

3. Permissions
   └─ Share sheets with service account email (reader access)
```

### Groq API Key
```
From console.groq.com: gsk_...
├─ Free tier: good for testing
├─ Store in .env: GROQ_API_KEY=...
└─ Used for embeddings + search
```

---

## 📁 Code Structure

```
streamer-bot/
├── bot/
│   ├── main.py                  # Bot entry point, polling setup
│   ├── config.py                # Load .env, constants
│   ├── keyboards.py             # Generate Telegram keyboards
│   ├── handlers.py              # Message/button handlers
│   ├── sheets.py                # Google Sheets API + caching
│   ├── search.py                # Hybrid search (keyword + AI)
│   ├── auto_comments.py         # Discussion group logic
│   └── utils.py                 # Helper functions
│
├── Dockerfile                   # Docker image (Python 3.12)
├── docker-compose.yml           # Redis + Bot services
├── requirements.txt             # aiogram, gspread, groq, redis
├── .env.example                 # Config template
├── .gitignore                   # Exclude .env, credentials.json
└── README.md
```

---

## 🔄 Caching Strategy

### Redis Cache
```python
# TTL: 5 minutes (300 seconds)

Cache Key Structure:
├─ sheets:kontekt              → Full content (Контент sheet)
├─ sheets:avtokommen           → Auto-comments config
├─ sheets:kanaly               → Channel mappings
├─ sheets:settings             → Global settings
└─ user:{user_id}:fsmdata      → FSM state per user
```

### When Cache Refreshes
```
1. Automatic: Every 5 minutes
2. Manual: User sends /reload
3. On error: If Sheets unreachable, use stale cache
```

### Cache Miss Handling
```
1. User triggers action
2. Check Redis cache
3. If miss: Fetch from Google Sheets
4. Update Redis
5. Return result
```

---

## 🚀 Deployment

### Docker (Recommended)
```bash
docker-compose up -d

# Services:
# - Bot container (aiogram + gspread)
# - Redis container (cache)
```

### Local Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot/main.py
```

### Environment Variables
```
BOT_TOKEN=123456789:ABCdef...
SHEETS_ID=1sHC2YK...
GOOGLE_CREDENTIALS=/app/credentials.json
GROQ_API_KEY=gsk_...
REDIS_URL=redis://redis:6379/0
CACHE_TTL=300
LOG_LEVEL=INFO
ADMIN_DOMAIN=admin.travobot-workflow.ru
ADMIN_SECRET=change_me_64_chars
TG_BOT_USERNAME=Tpabomah_bot
INITIAL_ADMINS=Ki1aragg,other_user
```

---

## 📊 Message Flow Examples

### Example 1: User Clicks "Dota 2"
```
User in private chat sends /start
        │
        ▼
Bot loads "Контент" sheet from Google
        │
        ▼
Cache in Redis (5 min)
        │
        ▼
Generate keyboard:
  [Сайт] [Соцсети] [Гайды] [Игры] [Сервисы] [Ставки]
        │
        ▼
User clicks [Игры]
        │
        ▼
Subkeyboard:
  [Dota 2] [Warhammer] [Warcraft] [Civ5]
        │
        ▼
User clicks [Dota 2]
        │
        ▼
Query: SELECT all rows WHERE section='Игры' AND category='Dota 2'
        │
        ▼
Result: [Guide: Carry] [Hero Stats] [Meta Updates]
        │
        ▼
Send as inline buttons
```

### Example 2: Auto-Comment in Discussion
```
Streamer posts video in channel
        │
        ▼
Telegram auto-creates discussion group
        │
        ▼
Bot gets message in group (detects new discussion)
        │
        ▼
Check АвтоКомменты sheet for this chat_id
        │
        ▼
Find row: chat_id=-1001234567890, тематика=dota
        │
        ▼
Post текст + кнопки
        │
        ▼
Users see comment with links on first refresh
```

---

## 🔐 Security

- ✅ Credentials in .env (not in code)
- ✅ Google SA key not in git
- ✅ Redis local (no auth needed in Docker network)
- ✅ Bot token rotatable (recreate in @BotFather)
- ⚠️ Admin commands need user ID check
- ⚠️ Input validation on search queries

---

## ⚡ Performance

| Metric | Value |
|--------|-------|
| Sheets API call | 1-2s |
| Cache hit | <50ms |
| Groq search | 2-5s |
| Telegram response | <500ms |
| Memory usage | ~100MB |

---

## 📈 Monitoring

### Health Checks
```bash
# Is bot running?
docker-compose ps

# Bot logs
docker-compose logs -f bot

# Redis status
docker-compose exec redis redis-cli ping
# PONG

# Check cache
docker-compose exec redis redis-cli KEYS "sheets:*"
```

---

## 🔮 Future Enhancements

- [ ] Web dashboard (admin panel)
- [ ] Multiple language support
- [ ] Inline mode (search from any chat)
- [ ] Webhook updates (faster than polling)
- [ ] Analytics (track popular content)
- [ ] Integration with streaming platform APIs
- [ ] Admin approval workflow for content

