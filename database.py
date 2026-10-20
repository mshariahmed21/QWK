from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, ForeignKey, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column

engine = create_engine("sqlite:///./qwk.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

class Community(Base):
    __tablename__ = "communities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    __table_args__ = (UniqueConstraint("community_id", "user_id"),)

class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10), default="text")

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    username: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)
