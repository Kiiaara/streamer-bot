# 🏗️ Streamer Bot Architecture

## Overview

Multi-channel Telegram bot with integrated web admin panel for content management. Python stack: aiogram bot + Flask admin panel + SQLite/PostgreSQL database + Redis cache + Groq AI search.

---

## 🔄 System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         USERS                                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Telegram Users              Admin Panel Users                   │
│  (bot chat)                  (web dashboard)                     │
│     │                               │                            │
│     ▼                               ▼                            │
└──────────────────────────────────────────────────────────────────┘
     │                               │
     ▼                               ▼
┌──────────────────┐      ┌──────────────────────────┐
│   Aiogram Bot    │      │   Flask Admin Panel      │
│  (Python)        │      │  (Web UI)                │
├──────────────────┤      ├──────────────────────────┤
│ • Handlers       │      │ • Content CRUD           │
│ • Message parse  │      │ • Section management     │
│ • AI search      │      │ • Category editor        │
│ • Auto-comments  │      │ • Auto-comments config   │
│ • Keyboards      │      │ • Channel settings       │
│ • Telegram API   │      │ • User management        │
│                  │      │ • Statistics dashboard   │
└────────┬─────────┘      │ • Settings editor        │
         │                └──────────┬───────────────┘
         │                           │
         └───────────────┬───────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │    Shared Database            │
         │   (SQLite / PostgreSQL)       │
         ├───────────────────────────────┤
         │ • posts (content items)       │
         │ • categories                  │
         │ • sections                    │
         │ • auto_comments config        │
         │ • channels                    │
         │ • users (admin login)         │
         │ • settings                    │
         │ • stats                       │
         └────────┬─────────────────────┘
                  │
         ┌────────▼──────────┐
         │   Redis Cache     │
         ├───────────────────┤
         │ • FSM state       │
         │ • Content cache   │
         │ • Search index    │
         │ • TTL: 5 min      │
         └───────────────────┘
         
         ┌──────────────────┐
         │  Groq LLM API    │
         ├──────────────────┤
         │ • Search queries │
         │ • Embeddings     │
         │ • Semantic match │
         └──────────────────┘
```

---

## 📊 Data Flow

### Admin Edits Content
```
Admin opens https://admin.travobot.ru/sections/game/dota2/edit
        │
        ▼
Edit item: title, url, description, keywords
        │
        ▼
Submit form → Flask route: POST /items/{id}
        │
        ▼
Database update: posts table
        │
        ▼
Redis cache invalidation (delete old cache)
        │
        ▼
Next user /start → bot fetches fresh data
        │
        ▼
Redis updates with new data
```

### User Navigates Menu
```
User sends: /start
        │
        ▼
Bot checks Redis cache (content)
        │
        ├─ Cache hit → use cached data
        └─ Cache miss → fetch from DB → cache
        │
        ▼
Generate keyboard buttons from sections
        │
        ▼
User clicks [Игры]
        │
        ▼
Bot loads categories (Dota 2, Warhammer, etc)
        │
        ▼
User clicks [Dota 2]
        │
        ▼
Bot loads items for that category
        │
        ▼
Send as inline buttons with links
```

### AI Search
```
User sends: "где найти гайд по доте?"
        │
        ▼
Bot sends to Groq API with user text
        │
        ▼
Groq generates embeddings
        │
        ▼
Search in Redis cache + DB for similar descriptions/keywords
        │
        ▼
Rank by relevance
        │
        ▼
Return top 3-5 results as buttons
```

### Auto-Comments in Discussion
```
Channel posts video
        │
        ▼
Discussion group auto-created by Telegram
        │
        ▼
Bot member of group (added manually)
        │
        ▼
Admin configured auto-comment via /admin/auto_comments
        │
        ▼
DB stores: chat_id + theme + text + buttons
        │
        ▼
Bot detects new discussion in that chat_id
        │
        ▼
Posts pre-configured message + buttons
```

---

## 🗄️ Database Schema

### Core Tables

**posts** (content items)
```sql
id | section_id | category_id | title | url | description | keywords | created_at | updated_at
```

**sections** (Сайт, Игры, Сервисы, etc)
```sql
id | name | display_order | icon | is_active
```

**categories** (Dota 2, Warhammer, etc)
```sql
id | section_id | name | display_order
```

**auto_comments**
```sql
id | chat_id | theme | text | buttons (JSON) | is_active
```

**channels**
```sql
id | chat_id | name | theme | linked_category_id
```

**settings**
```sql
key | value | description
// greeting, support_email, owner_id, etc
```

**users** (admin login)
```sql
id | username | password_hash | email | role | is_active | created_at
```

**stats**
```sql
date | user_count | message_count | search_count | clicks
```

---

## 🏗️ Project Structure

```
streamer-bot/
├── bot/
│   ├── main.py                   # Aiogram entry point
│   ├── config.py                 # Load .env
│   ├── keyboards.py              # Generate Telegram keyboards
│   ├── handlers.py               # Message handlers
│   ├── search.py                 # Hybrid search (keyword + AI)
│   ├── auto_comments.py          # Discussion group logic
│   └── utils.py                  # Helper functions
│
├── admin/
│   ├── main.py                   # Flask app entry
│   ├── config.py                 # Admin config
│   ├── auth.py                   # Login/auth
│   ├── common.py                 # Shared functions
│   ├── static/
│   │   └── editor.js             # Frontend JS
│   ├── templates/
│   │   ├── base.html             # Base layout
│   │   ├── login.html            # Login page
│   │   ├── section.html          # View section
│   │   ├── section_form.html     # Edit section
│   │   ├── category_form.html    # Edit category
│   │   ├── item_form.html        # Edit content item
│   │   ├── auto_comments.html    # Auto-comments config
│   │   ├── channels.html         # Channel management
│   │   ├── settings.html         # Global settings
│   │   ├── users.html            # User management
│   │   ├── stats.html            # Analytics
│   │   └── access_denied.html    # Error page
│   └── routes/
│       ├── content.py            # POST/PUT/DELETE items
│       ├── categories.py         # Category CRUD
│       ├── auto_comments.py      # Auto-comments routes
│       ├── settings_routes.py    # Settings management
│       └── users.py              # User management
│
├── shared/
│   ├── __init__.py
│   ├── db.py                     # SQLAlchemy models + init
│   ├── models.py                 # Pydantic models
│   ├── email_sender.py           # Email notifications
│   └── html_sanitize.py          # Security
│
├── docker-compose.yml            # Redis + Bot + Admin
├── Dockerfile                    # Python 3.12 image
├── requirements.txt              # Dependencies
├── .env.example                  # Config template
├── .gitignore
└── README.md
```

---

## 🚀 Deployment

### Docker Compose Stack
```yaml
services:
  redis:
    image: redis:7
    ports: ["6379:6379"]
  
  bot:
    build: .
    environment: .env
    depends_on: [redis]
    volumes: [./db:/app/db]  # SQLite persistence
  
  admin:
    build: .
    ports: ["8000:8000"]
    environment: .env
    depends_on: [redis]
    volumes: [./db:/app/db]
```

### Access Points
```
Bot:        Telegram @Tpabomah_bot
Admin:      https://admin.travobot.ru (or http://localhost:8000 locally)
Database:   SQLite in /app/db (or PostgreSQL for production)
Redis:      localhost:6379 (internal only in Docker)
```

---

## 🔐 Authentication

### Bot
- Telegram bot token (from @BotFather)
- No user auth needed (public Telegram bot)
- Per-chat permissions handled by Telegram

### Admin Panel
```
Login: username + password (hashed with bcrypt)
Session: Flask session cookies
Permissions: Simple role-based (admin/moderator/viewer)
HTTPS recommended for production
```

---

## 💾 Caching Strategy

### Redis Cache
```python
# Cache key structure
cache_keys = {
    "sections": "all sections",
    "category:{id}": "items in category",
    "item:{id}": "single item",
    "search:{query}": "search results",
    "user:{id}:fsmdata": "user bot state"
}

# TTL
default_ttl = 300  # 5 minutes
```

### Cache Invalidation
```
When admin edits:
1. Delete specific cache (item:{id})
2. Delete parent cache (category:{id})
3. Delete search cache (too aggressive?)
4. Trigger bot reload if user online

Option: Add manual /reload command for bot
```

---

## 🔧 Configuration

### Environment Variables
```
# Bot
BOT_TOKEN=123456789:ABCdef...
TELEGRAM_BOT_USERNAME=Tpabomah_bot

# Admin
ADMIN_DOMAIN=admin.travobot-workflow.ru
ADMIN_SECRET=random_64_char_string

# Database
DATABASE_URL=sqlite:///./db/bot.db
# OR: postgresql://user:pass@host/dbname

# Cache
REDIS_URL=redis://redis:6379/0

# AI
GROQ_API_KEY=gsk_...

# Admin login
INITIAL_ADMINS=Ki1aragg,other_user

# Logging
LOG_LEVEL=INFO
```

---

## 📊 Features Enabled by Admin Panel

✅ **Content Management**
- Sections (Сайт, Соцсети, Гайды, Игры, Сервисы, Ставки)
- Categories (Dota 2, Warhammer, etc - organize by section)
- Items (actual links/content)
- Drag-n-drop reordering

✅ **Auto-Comments**
- Configure per chat_id (discussion groups)
- Set theme/topic
- Custom message text
- Inline buttons with links

✅ **Channel Management**
- Map channels to categories
- Theme-specific content

✅ **Settings**
- Global greeting message
- Support email
- Bot owner ID
- Feature flags

✅ **User Management**
- Create admin users
- Role-based access
- Activity logs

✅ **Statistics**
- Daily active users
- Popular sections/items
- Search analytics

---

## 🔄 Workflow Examples

### Admin Creates New Game Section
```
1. Open admin panel → Sections → Add New
2. Name: "Стратегии", Icon: 🎮
3. Save
4. Sections → Стратегии → Add Category
5. Name: "StarCraft 2"
6. Save
7. Items → Add Item (under StarCraft 2)
8. Title: "SC2 Campaign Guide"
9. URL: https://...
10. Description: "Tips for single player"
11. Keywords: "starcraft, strategy, guide"
12. Save
13. Redis cache invalidates
14. Next user /start → sees new section
```

### Admin Configures Auto-Comment
```
1. Admin Panel → Auto-Comments → Add
2. Chat ID: -1001234567890 (copied from Telegram)
3. Theme: "starcraft"
4. Message: "Welcome to SC2 discussion!"
5. Buttons: "Guide|url1;;Discord|url2"
6. Save
7. Next video in that channel → bot posts auto-comment
```

---

## ⚡ Performance

| Operation | Time |
|-----------|------|
| Admin login | <500ms |
| Load section list | <100ms (cached) |
| Edit item | <1s |
| Bot /start | <500ms |
| AI search | 2-5s |
| Cache refresh | ~1s |

---

## 🔐 Security

✅ Admin password: bcrypt hashed  
✅ HTTPS recommended for admin  
✅ Input sanitization (HTML + SQL)  
✅ CSRF protection (Flask-WTF)  
✅ Rate limiting on admin login  
⚠️ Telegram bot token in .env (not in code)  
⚠️ Database backups essential  

---

## 📈 Monitoring

```bash
# Bot logs
docker-compose logs -f bot

# Admin logs
docker-compose logs -f admin

# Database queries
sqlite3 db/bot.db "SELECT COUNT(*) FROM posts;"

# Redis cache health
docker-compose exec redis redis-cli DBSIZE
```

---

## 🔮 Future Enhancements

- [ ] Content versioning (rollback to previous)
- [ ] Bulk import from CSV
- [ ] Content approval workflow
- [ ] A/B testing (multiple versions)
- [ ] Export to Google Sheets (backup)
- [ ] Mobile admin app
- [ ] Webhook notifications (Slack alerts)
- [ ] Advanced analytics (charts, retention)

