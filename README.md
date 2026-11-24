# Lead wallbox

Prototipo MOSAIKA per i commerciali di BABOO ESCo. Legge i lead della campagna Meta «Wallbox» (in questa versione da una fonte fittizia, oppure da Odoo 18 in sola lettura) e permette di qualificarli, preparare il sopralluogo a distanza, prendere note e tenere un registro di obiezioni con un assistente.

Non è un deploy. Non scrive su Odoo. Non va messo in produzione senza il consenso esplicito di Renato.

## Avvio con Docker Compose

Serve Docker. Dalla radice del repository:

```bash
docker compose up --build
```

Apri `http://localhost:8000`. Il compose usa PostgreSQL e la fonte **mock**: non servono credenziali Odoo.

Per sovrascrivere le variabili, copia `.env.example` in `.env` e adattalo. Il compose imposta già i default di sviluppo (segreto di sessione locale, fonte mock, produzione spenta).

## Avvio senza Docker

Serve PostgreSQL 16 con un database `mosaika` e un utente che possa crearci le tabelle.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MOSAIKA_DATABASE_URL=postgresql+psycopg://mosaika:mosaika@localhost:5432/mosaika
uvicorn mosaika.main:app --host 0.0.0.0 --port 8000
```

Le tabelle si creano al primo avvio.

## Utenti di sviluppo

Al primo avvio, se la tabella `utente` è vuota, vengono creati tre account. La password è `MOSAIKA_SEED_PASSWORD` (default `mosaika-dev`).

| Nome | Email | Ruolo |
|---|---|---|
| Riccardo | riccardo@baboo.local | commerciale |
| Marco | marco@baboo.local | tecnico |
| Renato | renato@baboo.local | admin |

Solo tecnico e admin possono scrivere o validare una risposta. Il commerciale aggiunge la domanda con le parole del cliente.

## Accesso (scelta della v1)

Il brief lascia aperta la scelta tra utenti propri e login Google aziendale. Questa versione usa **utenti propri**: email, password e un cookie di sessione firmato (`HttpOnly`). I router chiedono solo chi è collegato (`get_current_user`). Password e firma del cookie stanno in `backend/mosaika/auth.py`. Per passare a Google si sostituisce quel modulo e si continua a riempire la tabella `utente`: lead e obiezioni restano gli stessi.

La domanda resta aperta, vedi sotto.

## Variabili d'ambiente

Tutte con prefisso `MOSAIKA_`. L'elenco commentato è in `.env.example`. Non committare un `.env` con segreti veri.

| Variabile | Default | A cosa serve |
|---|---|---|
| `MOSAIKA_DATABASE_URL` | PostgreSQL locale `mosaika` | Database del prototipo |
| `MOSAIKA_SESSION_SECRET` | valore di sviluppo | Firma del cookie |
| `MOSAIKA_SEED_PASSWORD` | `mosaika-dev` | Password iniziale degli utenti seed |
| `MOSAIKA_ODOO_SOURCE` | `mock` | `mock` oppure `xmlrpc` |
| `MOSAIKA_ODOO_URL` | vuoto | Base dell'istanza, senza `/xmlrpc/2/...` |
| `MOSAIKA_ODOO_DB` | vuoto | Nome del database Odoo |
| `MOSAIKA_ODOO_USERNAME` | vuoto | Utente di lettura |
| `MOSAIKA_ODOO_PASSWORD` | vuoto | Password di lettura |
| `MOSAIKA_ODOO_ALLOW_PRODUCTION` | `false` | Consente un URL che non è l'istanza di test |
| `MOSAIKA_ODOO_TEST_MARKER` | `esconnect18-test` | Frammento obbligatorio nell'URL di sviluppo |
| `MOSAIKA_AI_PROVIDER` | `mock` | `mock` oppure `openai` |
| `MOSAIKA_AI_API_KEY` | vuoto | Chiave del provider, se non è il mock |
| `MOSAIKA_AI_BASE_URL` | API OpenAI | Endpoint compatibile |
| `MOSAIKA_AI_MODEL` | `gpt-4o-mini` | Modello, se si usa il provider OpenAI |
| `MOSAIKA_SYNC_INTERVAL_SECONDS` | `600` | Rilettura della fonte (10 minuti) |

## Collegare l'istanza di test `esconnect18-test`

La fonte di default è il mock, con lead di esempio nel formato del brief (nome `Meta · 2026-11-wallbox-casa · …`, descrizione HTML, `create_date` UTC, telefoni `+39`). Per leggere Odoo:

```bash
MOSAIKA_ODOO_SOURCE=xmlrpc
MOSAIKA_ODOO_URL=https://esconnect18-test.example
MOSAIKA_ODOO_DB=il-database
MOSAIKA_ODOO_USERNAME=utente-in-sola-lettura
MOSAIKA_ODOO_PASSWORD=...
MOSAIKA_ODOO_ALLOW_PRODUCTION=false
```

L'URL deve contenere `esconnect18-test`. Il client usa XML-RPC (`/xmlrpc/2/common` e `/xmlrpc/2/object`) solo dal backend. Il browser non parla con Odoo.

Dominio di lettura: `[["campaign_id.name", "ilike", "Wallbox"]]`, anche gli archiviati (`active_test` falso), campi indicati nel brief, ordine `create_date desc`. Aggiornamento all'avvio, ogni 10 minuti e con il pulsante «Aggiorna».

Se l'URL non contiene `esconnect18-test` e `MOSAIKA_ODOO_ALLOW_PRODUCTION` non è `true`, l'applicazione rifiuta di partire in modalità `xmlrpc`. L'interruttore di produzione nasce spento.

La versione 1 non ha metodi di scrittura verso Odoo: il client accetta solo `search_read`, `search`, `read`, `fields_get`, `search_count`, `name_get` e rifiuta qualunque altro metodo prima di aprire la rete.

## Assistente obiezioni

Il prompt è `prompts/obiezioni_v1.md`. L'assistente risponde in 2–4 frasi usando solo le risposte **validate**. Se nessuna copre la domanda, restituisce esattamente:

> Non c'è ancora una risposta validata. Di' al cliente che verifichi con il tecnico e aggiungi la domanda al registro.

Non registra nulla da solo: «Aggiungi la domanda al registro» è un'azione della persona. Il provider è sostituibile (`backend/mosaika/ai/provider.py`):

- `mock` (default): non chiama la rete, ricuce le risposte validate passate nel messaggio.
- `openai`: endpoint chat compatibile. Serve `MOSAIKA_AI_API_KEY`.

Se il modello inserisce un prezzo o una percentuale che non stanno nelle risposte validate, il testo viene scartato e si usano le frasi del registro.

## Obiezioni di partenza

Il brief dice di importare le 7 risposte del prototipo claude.ai. Quel prototipo non è in questo repository. All'avvio, se il registro è vuoto, vengono inseriti **7 segnaposto in bozza**, marcati `[PLACEHOLDER n/7]` e `[BOZZA — da sostituire…]`. Non vanno validati.

Per metterci le risposte vere: sostituire le righe (dall'interfaccia, come tecnico o admin) oppure cambiare `DOMANDE_PLACEHOLDER` in `backend/mosaika/seed.py` prima del primo avvio. Se la tabella ha già delle righe, il seed non le riscrive.

## Test

Con PostgreSQL in ascolto e il database `mosaika_test` (lo crea chi lancia i test, deve esistere):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

URL alternativo: `MOSAIKA_TEST_DATABASE_URL`.

I test coprono il formato dei lead, i giorni di attesa, il salvataggio visibile ai tre ruoli, i link WhatsApp con prefisso 39 e il mittente collegato, il vincolo di validazione, la frase di rinvio dell'assistente, i colori e il viewport, e l'assenza di chiamate di scrittura verso Odoo (scansione del codice e rifiuto a runtime, prima della rete).

Il flusso nel browser (375 px, desktop, tema chiaro e scuro) è in `tests/test_ui.py`. Parte se nel venv c'è Playwright con Chromium:

```bash
pip install playwright
playwright install chromium
pytest tests/test_ui.py
```

## Cosa fa la schermata

- Elenco: totale, quanti da chiamare, giorni del più vecchio. Filtri: Da lavorare (né vinto né perso, è il default), Da chiamare, In corso, Chiusi, Tutti. I fuori zona stanno in fondo, poi i «da chiamare», poi i più recenti. I giorni sono in rosso oltre i 2 se il lead è ancora da chiamare.
- Scheda: stato, zona (default «da verificare»), dati del modulo, contatti, qualifica (la spunta si accende quando si scrive), versione suggerita (Solare se ha il fotovoltaico, altrimenti Smart; Essenziale si sceglie a mano), videochiamata o foto, note anche dettate (Web Speech API, italiano).
- Il mittente dei messaggi WhatsApp è il nome dell'utente collegato.
- Un'ora senza fuso, se arriva così all'API, è letta come Europe/Rome. Il browser invia l'istante in UTC.

## Decisioni prese in questa versione

- Auth locale sostituibile, non il login Google.
- «Da lavorare» = non vinto e non perso.
- Giorni di attesa = giorni interi da `create_date` UTC.
- In ritardo = più di 2 giorni e stato ancora «da chiamare».
- Zona predefinita «da verificare», finché qualcuno non la imposta.
- `lead_cache` tiene la copia letta, con `letto_il`. Lo stato di lavoro sta in `lead_stato` e non viene cancellato quando si rilegge Odoo.
- Nessun deploy, da nessuna parte.

## Domande aperte

Restano quelle del brief, §12. Non sono decise.

- Hosting del prototipo: VPS di MOSAIKA o altro?
- Accesso: utenti propri o login con Google aziendale?
- Elenco dei comuni o delle province del bacino operativo.
- Quando si può passare dalla lettura di `esconnect18-test` a quella della produzione.

La lettura della produzione si accende solo con `MOSAIKA_ODOO_ALLOW_PRODUCTION=true`, e solo dopo il consenso esplicito di Renato. Questo repository non contiene un deploy.
