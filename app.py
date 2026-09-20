from flask import Flask, render_template, request, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from dotenv import load_dotenv
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from functools import wraps
import os
import secrets
import string

load_dotenv()

app = Flask(__name__)

# ---------------- CONFIG ----------------
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY or len(SECRET_KEY) < 32:
    if os.getenv("FLASK_ENV") == "production":
        raise RuntimeError("SECRET_KEY must be 32+ chars in production!")
    SECRET_KEY = "dev-only-insecure-secret-key-change-me-please-12345"
app.config["SECRET_KEY"] = SECRET_KEY

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///photo_sharing.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_size": 5,
    "max_overflow": 10,
}

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_HTTPONLY"] = True

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(app.root_path, "static", "uploads"))
UPLOAD_FOLDER = os.path.abspath(UPLOAD_FOLDER)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "heic", "heif", "bmp", "tiff"}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
migrate = Migrate(app, db)

# ---------------- MODELS ----------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="Team Member")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email, "role": self.role}


class Event(db.Model):
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    gallery = db.relationship("Gallery", backref="event", uselist=False, cascade="all, delete-orphan")
    photos = db.relationship("Photo", backref="event", cascade="all, delete-orphan")
    members = db.relationship("EventMember", backref="event", cascade="all, delete-orphan")


class EventMember(db.Model):
    __tablename__ = "event_members"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("event_id", "user_id", name="uq_event_user"),)


class Photo(db.Model):
    __tablename__ = "photos"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    filename = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(500), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    is_selected = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Gallery(db.Model):
    __tablename__ = "galleries"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), unique=True, nullable=False)
    share_token = db.Column(db.String(50), unique=True, nullable=False, index=True)
    pin = db.Column(db.String(10), nullable=False)
    is_published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------- HELPERS ----------------
def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not current_user():
            return jsonify({"success": False, "message": "Login required."}), 401
        return f(*a, **k)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        u = current_user()
        if not u:
            return jsonify({"success": False, "message": "Login required."}), 401
        if u.role != "Admin":
            return jsonify({"success": False, "message": "Admin only."}), 403
        return f(*a, **k)
    return wrapper


def allowed_file(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def photo_to_dict(p):
    u = db.session.get(User, p.uploaded_by)
    return {
        "id": p.id, "event_id": p.event_id, "filename": p.filename,
        "url": p.url or f"/uploads/{p.filename}",
        "uploaded_by": u.name if u else "Unknown",
        "file_size": p.file_size, "is_selected": p.is_selected,
        "created_at": p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def event_to_dict(e):
    members = EventMember.query.filter_by(event_id=e.id).all()
    member_data = []
    for m in members:
        u = db.session.get(User, m.user_id)
        if u:
            member_data.append({"id": u.id, "name": u.name, "email": u.email})
    return {
        "id": e.id, "name": e.name, "created_by": e.created_by,
        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "members": member_data, "member_count": len(member_data),
        "photo_count": Photo.query.filter_by(event_id=e.id).count(),
        "selected_count": Photo.query.filter_by(event_id=e.id, is_selected=True).count(),
        "gallery": {
            "is_published": e.gallery.is_published,
            "share_token": e.gallery.share_token,
            "pin": e.gallery.pin,
        } if e.gallery else None,
    }


# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/register", methods=["POST"])
def register():
    d = request.get_json(silent=True) or {}
    name = d.get("name", "").strip()
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    role = d.get("role", "Team Member").strip()
    if not name or not email or not password:
        return jsonify({"success": False, "message": "All fields required."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be 6+ chars."}), 400
    if role not in ["Admin", "Team Member"]:
        role = "Team Member"
    if User.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "Email already exists."}), 400
    db.session.add(User(
        name=name, email=email,
        password=bcrypt.generate_password_hash(password).decode("utf-8"),
        role=role
    ))
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(silent=True) or {}
    u = User.query.filter_by(email=d.get("email", "").strip().lower()).first()
    if not u or not bcrypt.check_password_hash(u.password, d.get("password", "")):
        return jsonify({"success": False, "message": "Invalid credentials."}), 401
    session.permanent = True
    session["user_id"] = u.id
    return jsonify({"success": True, "user": u.to_dict()})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/me", methods=["GET"])
def me():
    u = current_user()
    return jsonify({"logged_in": True, "user": u.to_dict()}) if u else jsonify({"logged_in": False})


@app.route("/api/events", methods=["POST"])
@admin_required
def create_event():
    u = current_user()
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name:
        return jsonify({"success": False, "message": "Event name required."}), 400
    e = Event(name=name, created_by=u.id)
    db.session.add(e)
    db.session.commit()
    return jsonify({"success": True, "event": event_to_dict(e)}), 201


@app.route("/api/events", methods=["GET"])
@login_required
def get_events():
    u = current_user()
    if u.role == "Admin":
        events = Event.query.order_by(Event.id.desc()).all()
    else:
        ids = [a.event_id for a in EventMember.query.filter_by(user_id=u.id).all()]
        events = Event.query.filter(Event.id.in_(ids)).order_by(Event.id.desc()).all() if ids else []
    return jsonify({"success": True, "events": [event_to_dict(e) for e in events]})


@app.route("/api/events/<int:eid>", methods=["DELETE"])
@admin_required
def delete_event(eid):
    e = db.session.get(Event, eid)
    if not e:
        return jsonify({"success": False, "message": "Not found."}), 404
    for p in Photo.query.filter_by(event_id=eid).all():
        fp = os.path.join(app.config["UPLOAD_FOLDER"], p.filename)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
    db.session.delete(e)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/team-members", methods=["GET"])
@admin_required
def get_team_members():
    ms = User.query.filter_by(role="Team Member").order_by(User.name.asc()).all()
    return jsonify({"success": True, "members": [m.to_dict() for m in ms]})


@app.route("/api/events/<int:eid>/members", methods=["POST"])
@admin_required
def assign_member(eid):
    uid = (request.get_json(silent=True) or {}).get("user_id")
    m = db.session.get(User, uid)
    if not m or m.role != "Team Member":
        return jsonify({"success": False, "message": "Member not found."}), 404
    if EventMember.query.filter_by(event_id=eid, user_id=uid).first():
        return jsonify({"success": False, "message": "Already assigned."}), 400
    db.session.add(EventMember(event_id=eid, user_id=uid))
    db.session.commit()
    return jsonify({"success": True, "message": f"{m.name} assigned."})


@app.route("/api/events/<int:eid>/photos", methods=["POST"])
@login_required
def upload_photo(eid):
    u = current_user()
    if u.role != "Admin" and not EventMember.query.filter_by(event_id=eid, user_id=u.id).first():
        return jsonify({"success": False, "message": "Not assigned to this event."}), 403

    files = request.files.getlist("file") + request.files.getlist("files")
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"success": False, "message": "No files received."}), 400

    uploaded = 0
    errors = []
    for file in files:
        if not allowed_file(file.filename):
            errors.append(f"{file.filename}: unsupported")
            continue
        safe = secure_filename(file.filename) or "photo"
        unique = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{secrets.token_hex(4)}_{safe}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique)
        try:
            file.save(filepath)
            size = os.path.getsize(filepath)
            db.session.add(Photo(event_id=eid, filename=unique, uploaded_by=u.id, file_size=size))
            uploaded += 1
        except Exception as ex:
            errors.append(f"{file.filename}: {ex}")

    db.session.commit()
    return jsonify({
        "success": uploaded > 0,
        "uploaded": uploaded,
        "failed": len(errors),
        "errors": errors
    })


@app.route("/api/events/<int:eid>/photos", methods=["GET"])
@login_required
def get_photos(eid):
    u = current_user()
    if u.role == "Admin":
        ps = Photo.query.filter_by(event_id=eid).order_by(Photo.id.desc()).all()
    else:
        ps = Photo.query.filter_by(event_id=eid, uploaded_by=u.id).order_by(Photo.id.desc()).all()
    return jsonify({"success": True, "photos": [photo_to_dict(p) for p in ps]})


@app.route("/api/photos/<int:pid>/select", methods=["POST"])
@admin_required
def select_photo(pid):
    p = db.session.get(Photo, pid)
    if not p:
        return jsonify({"success": False}), 404
    p.is_selected = bool((request.get_json(silent=True) or {}).get("is_selected", False))
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/events/<int:eid>/publish", methods=["POST"])
@admin_required
def publish_gallery(eid):
    if Photo.query.filter_by(event_id=eid, is_selected=True).count() == 0:
        return jsonify({"success": False, "message": "Select at least one photo."}), 400
    g = Gallery.query.filter_by(event_id=eid).first()
    if not g:
        g = Gallery(
            event_id=eid,
            share_token=secrets.token_urlsafe(12),
            pin="".join(secrets.choice(string.digits) for _ in range(6))
        )
        db.session.add(g)
    g.is_published = True
    db.session.commit()
    return jsonify({"success": True, "share_token": g.share_token, "pin": g.pin})


@app.route("/gallery/<share_token>")
def customer_gallery(share_token):
    return render_template("gallery.html", share_token=share_token)


@app.route("/api/gallery/<share_token>/verify", methods=["POST"])
def verify_gallery_pin(share_token):
    g = Gallery.query.filter_by(share_token=share_token, is_published=True).first()
    if not g:
        return jsonify({"success": False, "message": "Gallery not found."}), 404
    if g.pin != (request.get_json(silent=True) or {}).get("pin", ""):
        return jsonify({"success": False, "message": "Incorrect PIN."}), 401
    ps = Photo.query.filter_by(event_id=g.event_id, is_selected=True).all()
    return jsonify({
        "success": True,
        "event_name": g.event.name if g.event else "Event Gallery",
        "photos": [photo_to_dict(p) for p in ps]
    })


@app.errorhandler(413)
def too_large(e):
    return jsonify({"success": False, "message": "File too large (max 64MB)."}), 413


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)