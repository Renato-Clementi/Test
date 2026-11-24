"""Dati iniziali.

Le sette obiezioni del brief stanno nel prototipo claude.ai, che non è
in questo repository. Qui ci sono solo segnaposto, tutti in bozza:
vanno sostituiti con le risposte vere e non vanno validati così come sono.
"""

from datetime import timedelta

from sqlalchemy import func, select

from mosaika.auth import hash_password
from mosaika.models import Obiezione, Utente
from mosaika.timeutil import adesso

UTENTI = (
    ("Riccardo", "riccardo@baboo.local", "commerciale"),
    ("Marco", "marco@baboo.local", "tecnico"),
    ("Renato", "renato@baboo.local", "admin"),
)

# PLACEHOLDER: non sono le 7 risposte del prototipo claude.ai.
RISPOSTA_PLACEHOLDER = (
    "[BOZZA — da sostituire con la risposta del prototipo claude.ai] "
    "Segnaposto: importare la risposta reale prima di qualsiasi validazione."
)

DOMANDE_PLACEHOLDER = (
    "[PLACEHOLDER 1/7] Quanto costa installare la wallbox?",
    "[PLACEHOLDER 2/7] Ci sono incentivi o detrazioni?",
    "[PLACEHOLDER 3/7] Quanto tempo ci vuole per l'installazione?",
    "[PLACEHOLDER 4/7] Serve per forza il fotovoltaico?",
    "[PLACEHOLDER 5/7] Si può installare in un condominio?",
    "[PLACEHOLDER 6/7] La wallbox è sicura se piove o è all'aperto?",
    "[PLACEHOLDER 7/7] Devo aumentare la potenza del contatore?",
)


def seed(db, settings) -> None:
    presenti = {
        row.email: row
        for row in db.scalars(select(Utente)).all()
    }
    for nome, email, ruolo in UTENTI:
        if email in presenti:
            continue
        db.add(
            Utente(
                nome=nome,
                email=email,
                ruolo=ruolo,
                password_hash=hash_password(
                    settings.seed_password, settings.password_iterations
                ),
            )
        )
    db.flush()

    quante = db.scalar(select(func.count()).select_from(Obiezione)) or 0
    if quante == 0:
        base = adesso()
        for indice, domanda in enumerate(DOMANDE_PLACEHOLDER):
            db.add(
                Obiezione(
                    domanda=domanda,
                    risposta=RISPOSTA_PLACEHOLDER,
                    validata=False,
                    comune=None,
                    creata_il=base + timedelta(seconds=indice),
                    creata_da=None,
                )
            )
    db.commit()
