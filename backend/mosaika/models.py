from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mosaika.database import Base


class Utente(Base):
    __tablename__ = "utente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ruolo: Mapped[str] = mapped_column(String(32), nullable=False)
    # Non è nel modello del brief: serve all'auth locale, sostituibile.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)


class LeadStato(Base):
    __tablename__ = "lead_stato"

    odoo_lead_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stato: Mapped[str | None] = mapped_column(String(64))
    zona: Mapped[str | None] = mapped_column(String(32))
    qualifica: Mapped[dict | None] = mapped_column(JSONB)
    versione: Mapped[str | None] = mapped_column(String(32))
    sopralluogo: Mapped[str | None] = mapped_column(String(16))
    video_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    giro: Mapped[dict | None] = mapped_column(JSONB)
    foto_ricevute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    aggiornato_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aggiornato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))


class Obiezione(Base):
    __tablename__ = "obiezione"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domanda: Mapped[str] = mapped_column(Text, nullable=False)
    risposta: Mapped[str | None] = mapped_column(Text)
    validata: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comune: Mapped[str | None] = mapped_column(String(120))
    creata_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creata_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    validata_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    validata_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadCache(Base):
    """Copia dei campi letti da Odoo. I dati personali restano della fonte."""

    __tablename__ = "lead_cache"

    odoo_lead_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(64))
    email_from: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(120))
    stage_id: Mapped[list | None] = mapped_column(JSONB)
    lead_type: Mapped[str | None] = mapped_column("type", String(32))
    user_id: Mapped[list | None] = mapped_column(JSONB)
    create_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    letto_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
