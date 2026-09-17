# 🤖 Streamer Bot

Multi-channel Telegram bot with integrated web admin panel for content management. Serves menu items (Site/Social/Guides/Games/Services/Betting), AI-powered search via Groq, and auto-comments in discussion groups.

**Key Features:**
- 📚 Multi-channel support with shared content database
- 🎮 Content organized by sections and categories
- 🔍 Hybrid AI search (keyword + semantic)
- 💬 Auto-comments in channel discussion groups
- 🎛️ Web admin panel for content management
- ⚡ Redis caching (5-minute TTL)
- 🐳 Docker compose deployment

---

## 🏗️ Tech Stack

- **Bot:** Python 3.12 + aiogram 3
- **Admin Panel:** Flask (Python)
- **Database:** SQLite / PostgreSQL
- **Cache:** Redis
- **AI Search:** Groq LLM (free tier)
- **Deployment:** Docker Compose

---

## 📦 Project Structure

```
streamer-bot/
├── bot/
│   ├── main.py              # aiogram entry point
│   ├── config.py            # .env configuration
│   ├── handlers.py          # Telegram handlers
│   ├── keyboards.py         # Menu generation
│   ├── search.py            # Hybrid search (keyword + AI)
│   ├── auto_comments.py     # Discussion group logic
│   └── utils.py             # helpers
├── admin/
│   ├── main.py              # Flask app entry
│   ├── auth.py              # Login/auth
│   ├── routes/              # API routes
│   ├── templates/           # HTML templates
│   └── static/              # CSS/JS
├── shared/
│   ├── db.py                # SQLAlchemy models
│   ├── models.py            # Pydantic schemas
│   └── email_sender.py      # Notifications
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── LICENSE
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Telegram bot token (from @BotFather)
- Groq API key (free at https://console.groq.com)

### 2. Local Setup

```bash
# Clone and install
git clone https://github.com/kiiaara/streamer-bot.git
cd streamer-bot

# Copy config template
cp .env.example .env

# Edit .env with your values
nano .env
# Required:
# - BOT_TOKEN (from @BotFather)
# - GROQ_API_KEY (from console.groq.com)
# - DATABASE_URL (sqlite:///./db/bot.db for local)
# - REDIS_URL (redis://localhost:6379/0)

# Python env
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Database
flask db upgrade

# Run bot (terminal 1)
python bot/main.py

# Run admin panel (terminal 2)
flask run --port 8000
```

Admin panel: http://localhost:8000  
Bot logs: check console output

### 3. Docker Deployment

```bash
# Build and run
docker compose up -d --build

# View logs
docker compose logs -f bot
docker compose logs -f admin

# Stop
docker compose down
```

---

## 🎛️ Admin Panel

Access at `http://localhost:8000` (or `https://admin.yourdomain.com` in production)

**Features:**
- 📝 Content CRUD (posts, categories, sections)
- 🏷️ Section management (Сайт, Игры, Сервисы, etc.)
- 🎮 Category organization (Dota 2, Warhammer, etc.)
- ⚙️ Auto-comment configuration per discussion group
- 📊 Statistics dashboard
- 👤 User management (role-based access)
- 🔧 Settings editor

**Database Schema:**
- `posts` - content items (title, url, description, keywords)
- `sections` - main categories
- `categories` - subcategories
- `auto_comments` - discussion group configs
- `channels` - channel metadata
- `users` - admin accounts
- `settings` - global configuration

---

## 🤖 Bot Commands

- `/start` - Show main menu
- `/menu` - Display menu (in any chat)
- `/reload` - Refresh cache (after admin edits)

---

## 🔍 Content Management Workflow

### Admin Creates Content

1. Open admin panel → Login
2. Sections → Add/Edit section (e.g., "Игры")
3. Categories → Add category under section (e.g., "Dota 2")
4. Items → Add content item (title, URL, description, keywords)
5. Save → Redis cache invalidates automatically
6. Next user `/start` → sees fresh content

### User Navigates Menu

1. Send `/start` to bot
2. Bot loads sections from cache/database
3. User clicks section button (e.g., "Игры")
4. Bot shows categories (Dota 2, Warhammer, etc.)
5. User clicks category → sees items with inline buttons
6. User can search with text → bot uses AI search

### AI Search

User sends: "где найти гайд по доте?"
- Bot sends query to Groq LLM
- Searches database for similar descriptions/keywords
- Returns top 3-5 results as buttons

---

## 📋 Configuration

### Environment Variables

```bash
# Telegram Bot
BOT_TOKEN=123456789:ABCdef...
TELEGRAM_BOT_USERNAME=YourBotName

# Admin Panel
ADMIN_SECRET=random_64_char_string

# Database
DATABASE_URL=sqlite:///./db/bot.db
# OR: postgresql://user:pass@host/dbname

# Cache
REDIS_URL=redis://redis:6379/0

# AI Search
GROQ_API_KEY=gsk_...

# Logging
LOG_LEVEL=INFO
```

---

## 🚀 Production Deployment

### Docker Stack

```yaml
services:
  redis:
    image: redis:7
  
  bot:
    build: .
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://redis:6379/0
    depends_on: [redis]
  
  admin:
    build: .
    ports: ["8000:8000"]
    depends_on: [redis]
```

### VPS Setup (Ubuntu)

```bash
# SSH into VPS, clone repo
git clone https://github.com/kiiaara/streamer-bot.git
cd streamer-bot

# Setup
cp .env.example .env
nano .env  # fill in production values

# Deploy with systemd or Docker
docker compose -f docker-compose.yml up -d

# Enable auto-restart
docker compose up -d --restart unless-stopped
```

### HTTPS (Admin Panel)

Use Nginx reverse proxy + Let's Encrypt:

```nginx
server {
    listen 443 ssl;
    server_name admin.yourdomain.com;
    
    location / {
        proxy_pass http://localhost:8000;
    }
}
```

---

## 🔐 Security

✅ Admin password: bcrypt hashed  
✅ HTTPS recommended for admin  
✅ Input sanitization (HTML + SQL)  
✅ CSRF protection (Flask-WTF)  
✅ Rate limiting on login attempts  
⚠️ Backup database regularly  
⚠️ Rotate bot token if compromised  

---

## 📊 Monitoring

```bash
# Bot logs
docker compose logs -f bot

# Admin logs
docker compose logs -f admin

# Database queries
sqlite3 db/bot.db "SELECT COUNT(*) FROM posts;"

# Redis health
docker compose exec redis redis-cli DBSIZE
```

---

## 📖 Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design, data flows, schemas
- [LICENSE](LICENSE) - MIT License

---

## 🔮 Future Enhancements

- [ ] Content versioning (rollback)
- [ ] Bulk import from CSV
- [ ] Content approval workflow
- [ ] Advanced analytics (charts, retention)
- [ ] Mobile admin app
- [ ] Webhook notifications (Slack alerts)
- [ ] Export to Google Sheets (backup)

---

## 📝 License

MIT - see [LICENSE](LICENSE) file

---

**Author:** Kiiaara  
**Status:** Active Development
