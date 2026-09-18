from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import secrets
import string

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "photo-sharing-secret-key-12345")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///photo_sharing.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# --------------------------------------------------
# DATABASE MODELS
# --------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="Team Member")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Event(db.Model):
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_by = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class EventMember(db.Model):
    __tablename__ = "event_members"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

class Photo(db.Model):
    __tablename__ = "photos"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    uploaded_by = db.Column(db.Integer, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    is_selected = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Gallery(db.Model):
    __tablename__ = "galleries"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    share_token = db.Column(db.String(50), unique=True, nullable=False)
    pin = db.Column(db.String(10), nullable=False)
    is_published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
def current_user():
    user_id = session.get("user_id")
    if not user_id: return None
    return db.session.get(User, user_id)

def user_to_dict(user):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}

def event_to_dict(event):
    members = EventMember.query.filter_by(event_id=event.id).all()
    member_data = []
    for assignment in members:
        user = db.session.get(User, assignment.user_id)
        if user: member_data.append({"id": user.id, "name": user.name, "email": user.email})
    photo_count = Photo.query.filter_by(event_id=event.id).count()
    selected_count = Photo.query.filter_by(event_id=event.id, is_selected=True).count()
    gallery = Gallery.query.filter_by(event_id=event.id).first()
    return {
        "id": event.id, "name": event.name, "created_by": event.created_by,
        "created_at": event.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "members": member_data, "member_count": len(member_data),
        "photo_count": photo_count, "selected_count": selected_count,
        "gallery": {"is_published": gallery.is_published, "share_token": gallery.share_token, "pin": gallery.pin} if gallery else None
    }

def photo_to_dict(photo):
    uploader = db.session.get(User, photo.uploaded_by)
    return {
        "id": photo.id, "event_id": photo.event_id, "filename": photo.filename,
        "url": f"/static/uploads/{photo.filename}", "uploaded_by": uploader.name if uploader else "Unknown",
        "file_size": photo.file_size, "is_selected": photo.is_selected,
        "created_at": photo.created_at.strftime("%Y-%m-%d %H:%M:%S")
    }

with app.app_context():
    db.create_all()

# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.route("/")
def index(): return render_template("index.html")

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name, email, password = data.get("name", "").strip(), data.get("email", "").strip().lower(), data.get("password", "")
    role = data.get("role", "Team Member").strip()
    if not name or not email or not password: return jsonify({"success": False, "message": "All fields required."}), 400
    if role not in ["Admin", "Team Member"]: role = "Team Member"
    if User.query.filter_by(email=email).first(): return jsonify({"success": False, "message": "Email already exists."}), 400
    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    db.session.add(User(name=name, email=email, password=hashed, role=role))
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    user = User.query.filter_by(email=data.get("email", "").strip().lower()).first()
    if not user or not bcrypt.check_password_hash(user.password, data.get("password", "")):
        return jsonify({"success": False, "message": "Invalid credentials."}), 401
    session["user_id"] = user.id
    return jsonify({"success": True, "user": user_to_dict(user)})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me", methods=["GET"])
def me():
    user = current_user()
    return jsonify({"logged_in": True, "user": user_to_dict(user)}) if user else jsonify({"logged_in": False})

@app.route("/api/events", methods=["POST"])
def create_event():
    user = current_user()
    if not user or user.role != "Admin": return jsonify({"success": False, "message": "Unauthorized."}), 403
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name: return jsonify({"success": False, "message": "Event name required."}), 400
    event = Event(name=name, created_by=user.id)
    db.session.add(event)
    db.session.commit()
    return jsonify({"success": True, "event": event_to_dict(event)}), 201

@app.route("/api/events", methods=["GET"])
def get_events():
    user = current_user()
    if not user: return jsonify({"success": False, "message": "Login required."}), 401
    if user.role == "Admin":
        events = Event.query.order_by(Event.id.desc()).all()
    else:
        assignments = EventMember.query.filter_by(user_id=user.id).all()
        ids = [a.event_id for a in assignments]
        events = Event.query.filter(Event.id.in_(ids)).order_by(Event.id.desc()).all() if ids else []
    return jsonify({"success": True, "events": [event_to_dict(e) for e in events]})

@app.route("/api/events/<int:event_id>", methods=["DELETE"])
def delete_event(event_id):
    user = current_user()
    if not user or user.role != "Admin": return jsonify({"success": False}), 403
    EventMember.query.filter_by(event_id=event_id).delete()
    Photo.query.filter_by(event_id=event_id).delete()
    Gallery.query.filter_by(event_id=event_id).delete()
    db.session.delete(db.session.get(Event, event_id))
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/team-members", methods=["GET"])
def get_team_members():
    user = current_user()
    if not user or user.role != "Admin": return jsonify({"success": False}), 403
    members = User.query.filter_by(role="Team Member").order_by(User.name.asc()).all()
    return jsonify({"success": True, "members": [user_to_dict(m) for m in members]})

@app.route("/api/events/<int:event_id>/members", methods=["POST"])
def assign_member(event_id):
    user = current_user()
    if not user or user.role != "Admin": return jsonify({"success": False}), 403
    user_id = (request.get_json(silent=True) or {}).get("user_id")
    member = db.session.get(User, user_id)
    if not member or member.role != "Team Member": return jsonify({"success": False, "message": "Member not found."}), 404
    if EventMember.query.filter_by(event_id=event_id, user_id=user_id).first(): return jsonify({"success": False, "message": "Already assigned."}), 400
    db.session.add(EventMember(event_id=event_id, user_id=user_id))
    db.session.commit()
    return jsonify({"success": True, "message": f"{member.name} assigned."})

@app.route("/api/events/<int:event_id>/photos", methods=["POST"])
def upload_photo(event_id):
    user = current_user()
    if not user: return jsonify({"success": False}), 401
    if user.role != "Admin" and not EventMember.query.filter_by(event_id=event_id, user_id=user.id).first():
        return jsonify({"success": False, "message": "Not assigned."}), 403
    if 'file' not in request.files: return jsonify({"success": False, "message": "No file."}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"success": False, "message": "No selected file."}), 400
    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    db.session.add(Photo(event_id=event_id, filename=filename, uploaded_by=user.id, file_size=os.path.getsize(filepath)))
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/events/<int:event_id>/photos", methods=["GET"])
def get_photos(event_id):
    user = current_user()
    if not user: return jsonify({"success": False}), 401
    if user.role == "Admin":
        photos = Photo.query.filter_by(event_id=event_id).order_by(Photo.id.desc()).all()
    else:
        photos = Photo.query.filter_by(event_id=event_id, uploaded_by=user.id).order_by(Photo.id.desc()).all()
    return jsonify({"success": True, "photos": [photo_to_dict(p) for p in photos]})

@app.route("/api/photos/<int:photo_id>/select", methods=["POST"])
def select_photo(photo_id):
    user = current_user()
    if not user or user.role != "Admin": return jsonify({"success": False}), 403
    photo = db.session.get(Photo, photo_id)
    if not photo: return jsonify({"success": False}), 404
    photo.is_selected = (request.get_json(silent=True) or {}).get("is_selected", False)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/events/<int:event_id>/publish", methods=["POST"])
def publish_gallery(event_id):
    user = current_user()
    if not user or user.role != "Admin": return jsonify({"success": False}), 403
    if Photo.query.filter_by(event_id=event_id, is_selected=True).count() == 0:
        return jsonify({"success": False, "message": "Select at least one photo."}), 400
    gallery = Gallery.query.filter_by(event_id=event_id).first()
    if not gallery:
        gallery = Gallery(event_id=event_id, share_token=secrets.token_urlsafe(8), pin=''.join(secrets.choice(string.digits) for _ in range(6)))
        db.session.add(gallery)
    gallery.is_published = True
    db.session.commit()
    return jsonify({"success": True, "share_token": gallery.share_token, "pin": gallery.pin})

@app.route("/gallery/<share_token>")
def customer_gallery(share_token): return render_template("gallery.html", share_token=share_token)

@app.route("/api/gallery/<share_token>/verify", methods=["POST"])
def verify_gallery_pin(share_token):
    gallery = Gallery.query.filter_by(share_token=share_token, is_published=True).first()
    if not gallery: return jsonify({"success": False, "message": "Gallery not found."}), 404
    if gallery.pin != (request.get_json(silent=True) or {}).get("pin", ""):
        return jsonify({"success": False, "message": "Incorrect PIN."}), 401
    photos = Photo.query.filter_by(event_id=gallery.event_id, is_selected=True).all()
    return jsonify({"success": True, "event_name": gallery.event.name if hasattr(gallery, 'event') else "Event Gallery", "photos": [photo_to_dict(p) for p in photos]})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)