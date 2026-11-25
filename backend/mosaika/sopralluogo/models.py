from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mosaika.database import Base


class ModelloChecklist(Base):
    __tablename__ = "sopralluogo_modello"

    codice: Mapped[str] = mapped_column(String(64), primary_key=True)
    titolo: Mapped[str] = mapped_column(String(200), nullable=False)
    sito: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    revisione: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    odoo_opportunity_id: Mapped[int | None] = mapped_column(Integer)
    perimetro: Mapped[str | None] = mapped_column(Text)
    istruzioni: Mapped[str | None] = mapped_column(Text)
    importato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SezioneChecklist(Base):
    __tablename__ = "sopralluogo_sezione"
    __table_args__ = (UniqueConstraint("modello_codice", "codice"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    modello_codice: Mapped[str] = mapped_column(ForeignKey("sopralluogo_modello.codice"), nullable=False)
    ordine: Mapped[int] = mapped_column(Integer, nullable=False)
    codice: Mapped[str] = mapped_column(String(8), nullable=False)
    titolo: Mapped[str] = mapped_column(String(200), nullable=False)
    sottotitolo: Mapped[str | None] = mapped_column(String(300))
    prefisso: Mapped[str | None] = mapped_column(String(8))
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)


class VoceChecklist(Base):
    __tablename__ = "sopralluogo_voce"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sezione_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_sezione.id"), nullable=False)
    ordine: Mapped[int] = mapped_column(Integer, nullable=False)
    testo: Mapped[str] = mapped_column(Text, nullable=False)
    evidenze: Mapped[list] = mapped_column(JSONB, nullable=False)
    capitolo: Mapped[str] = mapped_column(String(32), nullable=False, default="—")
    unita_suggerita: Mapped[str | None] = mapped_column(String(32))
    misure_minime: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    temperatura: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    con_ora: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consenso_richiesto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chiave: Mapped[str | None] = mapped_column(String(64))
    ripetibile: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    etichette: Mapped[list] = mapped_column(JSONB, nullable=False)


class Rilievo(Base):
    __tablename__ = "sopralluogo_rilievo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    modello_codice: Mapped[str] = mapped_column(ForeignKey("sopralluogo_modello.codice"), nullable=False)
    titolo: Mapped[str] = mapped_column(String(200), nullable=False)
    sito: Mapped[str] = mapped_column(String(200), nullable=False)
    odoo_opportunity_id: Mapped[int | None] = mapped_column(Integer)
    stato: Mapped[str] = mapped_column(String(16), nullable=False, default="aperto")
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    tecnico_nome: Mapped[str | None] = mapped_column(String(120))
    firmato_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chiuso_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    firma_key: Mapped[str | None] = mapped_column(String(300))


class RispostaVoce(Base):
    __tablename__ = "sopralluogo_risposta"
    __table_args__ = (UniqueConstraint("rilievo_id", "voce_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rilievo_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_rilievo.id"), nullable=False)
    voce_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_voce.id"), nullable=False)
    stato: Mapped[str] = mapped_column(String(24), nullable=False, default="aperto")
    testo: Mapped[str | None] = mapped_column(Text)
    chi_invia: Mapped[str | None] = mapped_column(String(160))
    entro_il: Mapped[date | None] = mapped_column(Date)
    aggiornato_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aggiornato_da: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))


class Misura(Base):
    __tablename__ = "sopralluogo_misura"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    risposta_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_risposta.id"), nullable=False)
    ordine: Mapped[int] = mapped_column(Integer, nullable=False)
    etichetta: Mapped[str | None] = mapped_column(String(80))
    valore: Mapped[str] = mapped_column(String(32), nullable=False)
    unita: Mapped[str] = mapped_column(String(16), nullable=False)
    rilevata_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    temperatura_esterna: Mapped[str | None] = mapped_column(String(32))


class FileRilievo(Base):
    __tablename__ = "sopralluogo_file"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rilievo_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_rilievo.id"), nullable=False)
    voce_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_voce.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(1), nullable=False)
    nome_assegnato: Mapped[str] = mapped_column(String(80), nullable=False)
    nome_originale: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    autore_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    autore_nome: Mapped[str] = mapped_column(String(120), nullable=False)
    gps_lat: Mapped[float | None] = mapped_column(Float)
    gps_lon: Mapped[float | None] = mapped_column(Float)
    gps_accuracy: Mapped[float | None] = mapped_column(Float)
    vista_insieme: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consenso: Mapped[bool | None] = mapped_column(Boolean)
    consenso_nome: Mapped[str | None] = mapped_column(String(160))
    consenso_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContatoreFile(Base):
    __tablename__ = "sopralluogo_contatore"

    rilievo_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_rilievo.id"), primary_key=True)
    prefisso: Mapped[str] = mapped_column(String(8), primary_key=True)
    ultimo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UploadSessione(Base):
    __tablename__ = "sopralluogo_upload"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rilievo_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_rilievo.id"), nullable=False)
    voce_id: Mapped[int] = mapped_column(ForeignKey("sopralluogo_voce.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(1), nullable=False)
    nome_originale: Mapped[str] = mapped_column(String(255), nullable=False)
    nome_assegnato: Mapped[str] = mapped_column(String(80), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    parti_ricevute: Mapped[list] = mapped_column(JSONB, nullable=False)
    gps_lat: Mapped[float | None] = mapped_column(Float)
    gps_lon: Mapped[float | None] = mapped_column(Float)
    gps_accuracy: Mapped[float | None] = mapped_column(Float)
    vista_insieme: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consenso: Mapped[bool | None] = mapped_column(Boolean)
    consenso_nome: Mapped[str | None] = mapped_column(String(160))
    autore_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    autore_nome: Mapped[str] = mapped_column(String(120), nullable=False)
    creata_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("sopralluogo_file.id"))
