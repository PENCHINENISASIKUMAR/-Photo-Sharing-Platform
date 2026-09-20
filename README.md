# 📸 PhotoShare — Full-Stack Photo Sharing Platform

A web app for event photography teams to upload, curate, and deliver photos to clients through PIN-protected galleries.

---

## 1. Project Overview & Tech Stack

### What it does
- **Admins** create events, assign team members, upload photos, select the best ones, and publish a gallery.
- **Team Members** upload photos to events they're assigned to.
- **Clients** open a share link and enter a 6-digit PIN to view their gallery.

### Tech Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask 3.0, Flask-SQLAlchemy, Flask-Migrate, Flask-Bcrypt |
| Database | PostgreSQL (production) / SQLite (local dev) |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Server | Gunicorn |
| Hosting | Render |
| Tools | Git, GitHub, python-dotenv, psycopg2 |

---

## 2. Architecture & Database

### Architecture Diagram
```
┌──────────────┐     HTTPS      ┌────────────────────┐
│   Browser    │ ─────────────▶ │   Flask (Gunicorn) │
│  index.html  │                │   routes + models  │
│  gallery.html│ ◀───────────── │                    │
└──────────────┘                └─────────┬──────────┘
                                          │
                          ┌───────────────┴───────────────┐
                          ▼                               ▼
                 ┌─────────────────┐           ┌──────────────────┐
                 │   PostgreSQL    │           │ static/uploads/  │
                 │  users, events  │           │  (photos on disk │
                 │  photos, etc.   │           │   or Cloudinary) │
                 └─────────────────┘           └──────────────────┘
```

### Database Tables

**users** — `id`, `name`, `email`, `password` (bcrypt), `role`, `created_at`

**events** — `id`, `name`, `created_by` (FK users), `created_at`

**event_members** — `id`, `event_id` (FK), `user_id` (FK), unique pair

**photos** — `id`, `event_id` (FK), `filename`, `url`, `uploaded_by` (FK), `file_size`, `is_selected`, `created_at`

**galleries** — `id`, `event_id` (FK unique), `share_token`, `pin`, `is_published`, `created_at`

### Relationships
- One **user** creates many **events**
- One **event** has many **photos** and many **members**
- One **event** has one **gallery**
- Each **photo** belongs to one user (uploader) and one event

---

## 3. Local Setup & Environment Variables

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Git

### Steps

**1. Clone**
```bash
git clone https://github.com/PENCHINENISASIKUMAR/-Photo-Sharing-Platform.git
cd -Photo-Sharing-Platform
```

**2. Create virtual environment**
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Create the database**
```bash
psql -U postgres
```
```sql
CREATE USER photoshare WITH PASSWORD 'Sasikumar@999';
CREATE DATABASE photo_sharing OWNER photoshare;
GRANT ALL PRIVILEGES ON DATABASE photo_sharing TO photoshare;
\q
```

**5. Create `.env`** (copy from `.env.example`)
```env
SECRET_KEY=your-64-char-random-string
DATABASE_URL=postgresql://photoshare:Sasikumar%40999@localhost:5432/photo_sharing
FLASK_ENV=development
UPLOAD_FOLDER=./static/uploads
```
> Note: `@` in the password must be written as `%40`.

**6. Run migrations**
```bash
set FLASK_APP=app.py         # Windows
# export FLASK_APP=app.py    # Mac/Linux
flask db init
flask db migrate -m "initial schema"
flask db upgrade
```

**7. Start the app**
```bash
python app.py
```
Open http://127.0.0.1:5000 → Register as **Admin** → Create event → Upload photos → Publish.

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | 32+ char random string for session signing |
| `DATABASE_URL` | Yes | PostgreSQL or SQLite connection URL |
| `FLASK_ENV` | Yes | `development` or `production` |
| `UPLOAD_FOLDER` | No | Where to store photos (default `./static/uploads`) |
| `USE_CLOUDINARY` | No | `true` to store photos on Cloudinary |
| `CLOUDINARY_CLOUD_NAME` | No | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | No | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | No | Cloudinary API secret |

---

## 4. Deployment & Known Limitations

### Deploy to Render (Free)

**1. Create a PostgreSQL database**
- Go to https://dashboard.render.com/new/database
- Name: `photoshare-db`, User: `photoshare`, Region: Oregon, Plan: Free
- Copy the **Internal Database URL**

**2. Create a Web Service**
- Go to https://dashboard.render.com/web/new
- Connect your GitHub repo
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- **Instance Type:** Free

**3. Add environment variables**

| Key | Value |
|---|---|
| `SECRET_KEY` | click **Generate** |
| `FLASK_ENV` | `production` |
| `PYTHON_VERSION` | `3.11.9` |
| `DATABASE_URL` | the Internal Database URL from step 1 |

**4. Deploy** — click **Deploy web service** (takes 3–5 min).

Your app will be live at `https://photoshare-hgqq.onrender.com/`.

### Known Limitations

**Free-tier hosting**
- Photos are lost on every redeploy (use Cloudinary to fix)
- App sleeps after 15 min idle — first request after is slow
- Free Render Postgres is deleted after 90 days

**App by design**
- No email verification or password reset
- No image thumbnails (full-size images loaded)
- No pagination (fine under ~1000 photos per event)
- No rate limiting on login

**Not yet implemented**
- Watermarking, ZIP download, email notifications, analytics, multi-language

---

## 5. Project Structure

```
-Photo-Sharing-Platform/
├── app.py                  # Flask app: models, routes, auth
├── requirements.txt        # Python dependencies
├── Procfile                # Deployment process definition
├── render.yaml             # Render infrastructure config
├── .env                    # Secrets (not committed)
├── .env.example            # Template
├── migrations/             # Database migration files
├── static/uploads/         # Uploaded photos
└── templates/
    ├── index.html          # Admin/Team dashboard
    └── gallery.html        # Client PIN gallery
```

---

## 6. License

MIT License — free for personal and commercial use.

## Author

**Penchineni Sasikumar** — [@PENCHINENISASIKUMAR](https://github.com/PENCHINENISASIKUMAR)
