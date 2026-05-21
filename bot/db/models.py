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
    language      = Column(String(8),  default="en",   nullable=False)

    orders       = relationship("Order",       back_populates="user", lazy="select")
    transactions = relationship("Transaction", back_populates="user", lazy="select")

    def display_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else (self.username or f"User{self.telegram_id}")


class Panel(Base):
    """پنل‌های سفارشی (دستی) — هر پنل یه دکمه در منوی کاربر"""
    __tablename__ = "panels"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(64), nullable=False)          # اسم داخلی
    button_label  = Column(String(64), nullable=False)          # متن دکمه کاربر
    description   = Column(Text, nullable=True)
    group_chat_id = Column(BigInteger, nullable=True)           # گروه تلگرام سفارش‌ها
    is_active     = Column(Boolean, default=True, nullable=False)
    order_index   = Column(Integer, default=0, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)

    categories = relationship("PanelCategory", back_populates="panel",
                              cascade="all, delete-orphan", lazy="select",
                              order_by="PanelCategory.order_index")


class PanelCategory(Base):
    """دسته‌بندی داخل هر پنل"""
    __tablename__ = "panel_categories"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    panel_id    = Column(Integer, ForeignKey("panels.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String(64), nullable=False)
    icon        = Column(String(8), default="📂", nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)

    panel    = relationship("Panel",        back_populates="categories")
    services = relationship("PanelService", back_populates="category",
                            cascade="all, delete-orphan", lazy="select",
                            order_by="PanelService.order_index")


class PanelService(Base):
    """خدمات دستی داخل هر دسته‌بندی"""
    __tablename__ = "panel_services"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("panel_categories.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    price       = Column(Float, nullable=False)                 # قیمت به دلار
    min_qty     = Column(Integer, default=1, nullable=False)
    max_qty     = Column(Integer, default=10000, nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)

    category = relationship("PanelCategory", back_populates="services")
    orders   = relationship("PanelOrder",    back_populates="service", lazy="select")


class PanelOrder(Base):
    """سفارش‌های پنل دستی"""
    __tablename__ = "panel_orders"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    panel_id         = Column(Integer, ForeignKey("panels.id"), nullable=False, index=True)
    service_id       = Column(Integer, ForeignKey("panel_services.id"), nullable=False)
    service_name     = Column(String(128), nullable=True)
    panel_name       = Column(String(64), nullable=True)
    quantity         = Column(Integer, nullable=False)
    unit_price       = Column(Float, nullable=False)            # قیمت واحد هنگام سفارش
    total_price      = Column(Float, nullable=False)            # کل مبلغ پرداختی
    link             = Column(Text, nullable=True)              # لینک/یوزرنیم
    note             = Column(Text, nullable=True)              # توضیح اضافه
    # pending / processing / completed / partial / rejected
    status           = Column(String(32), default="pending", nullable=False, index=True)
    completed_qty    = Column(Integer, nullable=True)           # برای partial
    refund_amount    = Column(Float, default=0.0, nullable=False)
    group_message_id = Column(BigInteger, nullable=True)        # ID پیام توی گروه
    admin_note       = Column(Text, nullable=True)              # یادداشت ادمین
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user    = relationship("User",         foreign_keys=[user_id])
    panel   = relationship("Panel",        foreign_keys=[panel_id])
    service = relationship("PanelService", back_populates="orders")


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
    status        = Column(String(32), default="pending", nullable=False, index=True)
    api_order_id  = Column(String(64), nullable=True, index=True)
    start_count   = Column(Integer, nullable=True)
    remains       = Column(Integer, nullable=True)
    panel_name    = Column(String(64),  nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="orders")


class Transaction(Base):
    __tablename__ = "transactions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type           = Column(String(32), nullable=False)
    amount         = Column(Float, nullable=False)
    status         = Column(String(32), default="pending", nullable=False)
    method         = Column(String(32), nullable=True)
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
    role        = Column(String(32), default="admin", nullable=False)
    permissions = Column(Text, default="{}", nullable=False)
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
