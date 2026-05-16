"""
Database models for SMM Panel.
"""
from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, Boolean,
    DateTime, Numeric, ForeignKey, Index
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    telegram_id   = Column(BigInteger, unique=True, nullable=False, index=True)
    username      = Column(String(255))
    first_name    = Column(String(255))
    last_name     = Column(String(255))
    phone         = Column(String(30))          # verified phone
    balance       = Column(Numeric(10, 4), default=0)
    is_banned     = Column(Boolean, default=False, index=True)
    referral_code = Column(String(20), unique=True)
    referral_count= Column(Integer, default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions  = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    orders        = relationship("Order",       back_populates="user", cascade="all, delete-orphan")

    def display_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) or self.username or str(self.telegram_id)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id          = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username    = Column(String(255))
    # role: superadmin | admin | moderator | support
    role        = Column(String(50), default="admin")
    # JSON string: {"manage_users":true, "manage_orders":true, "manage_deposits":true, "view_stats":true}
    permissions = Column(Text, default="{}")
    created_at  = Column(DateTime, default=datetime.utcnow)

    def has_perm(self, perm: str) -> bool:
        import json
        try:
            perms = json.loads(self.permissions or "{}")
            return perms.get(perm, False)
        except Exception:
            return False

    def all_perms(self) -> dict:
        import json
        try:
            return json.loads(self.permissions or "{}")
        except Exception:
            return {}


class Transaction(Base):
    __tablename__ = "transactions"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # type: deposit | order | refund | manual_credit | manual_debit
    type           = Column(String(50), nullable=False)
    amount         = Column(Numeric(10, 4), nullable=False)
    # status: pending | approved | rejected
    status         = Column(String(20), default="pending", index=True)
    # method: usdt_trc20 | usdt_erc20 | ton | trx | manual
    method         = Column(String(50))
    tx_hash        = Column(String(255))
    wallet_address = Column(String(255))
    description    = Column(Text)
    created_at     = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class Order(Base):
    __tablename__ = "orders"

    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    service_id   = Column(Integer, nullable=False)
    service_name = Column(String(255), nullable=False)
    link         = Column(Text, nullable=False)
    quantity     = Column(Integer, nullable=False)
    # charge: price user paid (with markup)
    charge       = Column(Numeric(10, 4), nullable=False)
    # cost: actual cost from SMMPass
    cost         = Column(Numeric(10, 4))
    status       = Column(String(20), default="pending", index=True)
    start_count  = Column(Integer)
    remains      = Column(Integer)
    created_at   = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="orders")


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id          = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)
    code        = Column(String(10), nullable=False)
    expires_at  = Column(DateTime, nullable=False)
    is_used     = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.utcnow)


class AdminSetting(Base):
    __tablename__ = "admin_settings"

    key        = Column(String(100), primary_key=True)
    value      = Column(Text)
    description= Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Composite indexes
Index("ix_tx_user_status",   Transaction.user_id, Transaction.status)
Index("ix_order_user_status",Order.user_id,       Order.status)
Index("ix_vc_tg_used",       VerificationCode.telegram_id, VerificationCode.is_used)
