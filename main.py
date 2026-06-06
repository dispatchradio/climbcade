import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from auth import create_token, decode_token, hash_password, verify_password
from database import Note, SessionLocal, User

app = FastAPI()
security = HTTPBearer()

url = os.getenv("FRONTEND_URL")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[url],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        user_id = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


class UserCreate(BaseModel):
    username: str
    password: str

    @field_validator("password")
    def validate_password(cls, v):
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 characters or fewer")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class NoteCreate(BaseModel):
    title: str
    content: str

    @field_validator("title", "content")
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("cannot be empty")
        return v.strip()


@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = User(username=user.username, password=hash_password(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User created"}


@app.post("/login")
def login(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"token": create_token(db_user.id)}


@app.get("/notes")
def get_notes(
    query: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if query is None:
        return db.query(Note).filter(Note.owner == current_user).all()

    return (
        db.query(Note)
        .filter(
            Note.owner_id == current_user.id,
            Note.title.ilike(f"%{query}%") | Note.content.ilike(f"%{query}%"),
        )
        .all()
    )


@app.get("/notes/{id}")
def get_note(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = db.query(Note).filter(Note.id == id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return note


@app.post("/notes")
def create_note(
    note: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_note = Note(title=note.title, content=note.content, owner_id=current_user.id)
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note


@app.put("/notes/{id}")
def update_note(
    id: int,
    new_note: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = db.query(Note).filter(Note.id == id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    note.title = new_note.title
    note.content = new_note.content
    db.commit()
    db.refresh(note)
    return note


@app.delete("/notes/{id}")
def delete_note(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    note = db.query(Note).filter(Note.id == id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    db.delete(note)
    db.commit()
    return {"message": f"Note {id} deleted"}
