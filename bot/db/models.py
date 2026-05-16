"""
Database models.
"""
import json
from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float,
    Integer, String, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from db.database import Base


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id   = Column(BigInteger, unique=True, nullable=False, index=True)
    username      = Column(String(64), nullable=True)
    first_name    = Column(String(64), nullable=True)
    last_name     = Column(String(64), nullable=True)
    phone         = Column(String(20), nullable=True)
    balance       = Column(Float, default=0.0, nullable=False)
    is_banned     = Column(Boolean, default=False, nullable=False)
    referral_code = Column(String(16), unique=True, nullable=True)
    referral_count= Column(Integer, default=0, nullable=False)
    referred_by   = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders       = relationship("Order",       back_populates="user", lazy="select")
    transactions = relationship("Transaction", back_populates="user", lazy="select")

    def display_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else (self.username or f"User{self.telegram_id}")


class Order(Base):
    __tablename__ = "orders"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    service_id   = Column(Integer, nullable=False)
    service_name = Column(String(255), nullable=True)
    link         = Column(Text, nullable=False)
    quantity     = Column(Integer, nullable=False)
    cost_price   = Column(Float, nullable=False)
    sell_price   = Column(Float, nullable=False)
    status       = Column(String(32), default="pending", nullable=False, index=True)
    start_count  = Column(Integer, nullable=True)
    remains      = Column(Integer, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="orders")


class Transaction(Base):
    __tablename__ = "transactions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type           = Column(String(32), nullable=False)  # deposit, order, refund, manual
    amount         = Column(Float, nullable=False)
    status         = Column(String(32), default="pending", nullable=False)
    method         = Column(String(32), nullable=True)   # usdt, ton, trx, manual
    tx_hash        = Column(String(128), nullable=True)
    wallet_address = Column(String(128), nullable=True)
    description    = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="transactions")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username    = Column(String(64), nullable=True)
    role        = Column(String(32), default="admin", nullable=False)  # admin, moderator, support
    permissions = Column(Text, default="{}", nullable=False)  # JSON
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    def all_perms(self) -> dict:
        try:
            return json.loads(self.permissions or "{}")
        except Exception:
            return {}

    def has_perm(self, perm: str) -> bool:
        return self.all_perms().get(perm, False)


class AdminSetting(Base):
    __tablename__ = "admin_settings"

    id    = Column(Integer, primary_key=True, autoincrement=True)
    key   = Column(String(64), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    code        = Column(String(8), nullable=False)
    is_used     = Column(Boolean, default=False, nullable=False)
    expires_at  = Column(DateTime, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
