# MOSAIKA

Due prototipi nello stesso processo, con gli stessi utenti e lo stesso PostgreSQL.

- **Lead wallbox** (`/`) per i commerciali: lead della campagna Meta «Wallbox», qualifica, note, registro obiezioni.
- **Sopralluogo** (`/sopralluogo/`) per il tecnico in cantiere: checklist con foto, video, audio, misure e documenti, anche offline.

L'avvio è uno solo, descritto sotto. Nessuno dei due è un deploy. Nessuno scrive su Odoo. Non vanno messi in produzione senza il consenso esplicito di Renato.

## Lead wallbox

Legge i lead (in questa versione da una fonte fittizia, oppure da Odoo 18 in sola lettura) e permette di qualificarli, preparare il sopralluogo a distanza, prendere note e tenere un registro di obiezioni con un assistente.

## Avvio con Docker Compose

Serve Docker. Dalla radice del repository:

```bash
docker compose up --build
```

Apri `http://localhost:8000` per i lead e `http://localhost:8000/sopralluogo/` per la checklist di cantiere. Il compose usa PostgreSQL e la fonte **mock**: non servono credenziali Odoo. I file del sopralluogo finiscono nel volume `mosaika_media`.

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
| `MOSAIKA_STORAGE_BACKEND` | `local` | `local` oppure `s3` per i file del sopralluogo |
| `MOSAIKA_STORAGE_PATH` | `data/sopralluogo` | Disco locale e area dei pezzi in transito |
| `MOSAIKA_S3_ENDPOINT` | vuoto | Endpoint compatibile S3, se il backend è `s3` |
| `MOSAIKA_S3_BUCKET` | vuoto | Bucket |
| `MOSAIKA_S3_ACCESS_KEY` | vuoto | Access key. Non finisce nelle risposte API |
| `MOSAIKA_S3_SECRET_KEY` | vuoto | Secret. Non finisce nelle risposte API |
| `MOSAIKA_S3_REGION` | `eu-south-1` | Regione, se il provider la chiede |
| `MOSAIKA_S3_PREFIX` | `sopralluogo` | Prefisso delle chiavi nel bucket |
| `MOSAIKA_UPLOAD_CHUNK_BYTES` | `1048576` | Dimensione di un pezzo (i video grandi) |
| `MOSAIKA_UPLOAD_MAX_BYTES` | `536870912` | Dimensione massima di un file (512 MiB) |

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

Per il sopralluogo coprono il modello OPP 1733 (73 voci, capitoli, evidenze, consenso), l'import di un altro modello, i ruoli, il nome progressivo dei file e i metadati, l'upload a pezzi, lo ZIP, la chiusura, e la coda offline (serve `node` nel PATH).

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

## Sopralluogo

Checklist di raccolta dati in cantiere. Il primo modello è l'OPP 1733 (condominio Viale Bacchiglione 28, centrale ibrida e fotovoltaico), copiato dal PDF nel file `backend/mosaika/sopralluogo/templates/opp1733.yaml`. Si carica da solo al primo avvio. Un altro modello si aggiunge con `POST /api/sopralluogo/modelli` (YAML o JSON): se il codice esiste già l'import si rifiuta, così i rilievi già aperti non cambiano sotto i piedi.

Entra con gli stessi utenti del lead wallbox. Marco (tecnico) e Renato (admin) compilano. Riccardo (commerciale) legge ed esporta, non carica file.

Su un rilievo, voce per voce:

- foto, video e audio: scatto o file, oppure registrazione nel browser (`MediaRecorder`), con caricamento del file se il microfono non c'è;
- prima di un'intervista (le due voci che nel PDF dicono «con consenso») va spuntato il consenso, e resta salvato sul file insieme a chi parla;
- misure con valore e unità; per le temperature anche ora e temperatura esterna;
- testo breve, fatto, non applicabile;
- le evidenze ancora mancanti restano visibili sulla voce.

I file prendono il nome `prefisso-progressivo` (`CT-01`, `IDR-01`, …). Il prefisso `DOC` per «Prima di partire» non è nel PDF: il foglio numera solo le sette sezioni tecniche, e i documenti vanno comunque nominati. Il nome originale, la voce, il tipo, l'istante, l'autore e il GPS (se il telefono lo concede) stanno nel database e in un JSON accanto al file nello ZIP. Il numero si prenota all'inizio dell'upload e non si riusa: un invio abbandonato lascia un buco.

In cantina o sul tetto la pagina resta apribile (service worker) e gli invii finiscono in una coda IndexedDB. Lo stato è in testata: in linea, non in linea, quanti file sono in coda. I video sopra 1 MiB, e comunque tutti i video, viaggiano a pezzi e possono riprendere dal pezzo successivo. La coda si prova da Node con `node backend/tests/coda_offline.mjs` (lo lancia anche pytest).

«Prima di andare via» segnala le sezioni senza foto d'insieme o con misure aperte, le temperature di mandata e ritorno, la posizione dell'unità esterna, e l'elenco dei documenti che mancano con chi li manda e per quando. Poi nome del tecnico, data e ora, firma. Si può chiudere anche con voci aperte: il riepilogo le tiene.

L'esportazione è `GET /api/sopralluogo/rilievi/{id}/export`: uno ZIP con una cartella per sezione, i file rinominati, il JSON di ciascun file, `riepilogo.csv` (separatore `;`), `riepilogo.json` e `relazione.html`. La relazione è raggruppata per capitolo di offerta (CAP. 3, CAP. 3 · 5, CAP. esclusa, …) e si stampa in PDF dal browser. Non c'è un generatore PDF nel prototipo.

L'id opportunità (1733) è un numero facoltativo sul rilievo. Non parte nessuna chiamata a Odoo.

### Storage

`MOSAIKA_STORAGE_BACKEND=local` scrive in `MOSAIKA_STORAGE_PATH` (nel compose, il volume `mosaika_media`). Con `s3` il file intero va sul bucket (`MOSAIKA_S3_ENDPOINT`, `BUCKET`, `ACCESS_KEY`, `SECRET_KEY`, `REGION`, `PREFIX`); i pezzi in arrivo restano sul disco locale finché l'upload non è completo, così un video grosso non tiene tutto in memoria e può riprendere. Le chiavi e il secret non compaiono in `/api/health`.

## Decisioni prese in questa versione

- Auth locale sostituibile, non il login Google.
- «Da lavorare» = non vinto e non perso.
- Giorni di attesa = giorni interi da `create_date` UTC.
- In ritardo = più di 2 giorni e stato ancora «da chiamare».
- Zona predefinita «da verificare», finché qualcuno non la imposta.
- `lead_cache` tiene la copia letta, con `letto_il`. Lo stato di lavoro sta in `lead_stato` e non viene cancellato quando si rilegge Odoo.
- Nessun deploy, da nessuna parte.

Sul sopralluogo, in più:

- Stesso processo e stessi utenti, modulo a `/sopralluogo/`, così resta riusabile dentro MOSAIKA senza un secondo deploy.
- Il commerciale legge ed esporta; tecnico e admin scrivono.
- I «capitoli» del controllo finale sono le sette sezioni numerate del modulo (centrale, idraulica, …), non un secondo raggruppamento per CAP. L'export, quello sì, è raggruppato per capitolo di offerta.
- Un video con commento a voce copre sia V sia A, tranne le interviste, che vogliono un audio con consenso.
- Il numero progressivo è di sezione, non di voce, come sul PDF (`CT-01`, `CT-02`, …).
- La relazione leggibile è HTML stampabile. Niente libreria PDF.

## Domande aperte

Restano quelle del brief dei lead, §12. Non sono decise.

- Hosting del prototipo: VPS di MOSAIKA o altro?
- Accesso: utenti propri o login con Google aziendale?
- Elenco dei comuni o delle province del bacino operativo.
- Quando si può passare dalla lettura di `esconnect18-test` a quella della produzione.

La lettura della produzione si accende solo con `MOSAIKA_ODOO_ALLOW_PRODUCTION=true`, e solo dopo il consenso esplicito di Renato. Questo repository non contiene un deploy.

Sul sopralluogo restano aperti:

- Per quanto si conservano foto, audio e GPS, e chi può scaricare lo ZIP (dentro ci sono interviste e dati di condominio).
- Il testo del consenso va visto da chi segue la privacy: qui è una spunta, non un'informativa.
- Il prefisso `DOC` per i documenti di «Prima di partire» è una scelta di questo prototipo.
- Più tecnici sullo stesso rilievo, in contemporanea, non sono gestiti: il numero del file lo assegna il server all'invio.
- Il collegamento vero all'opportunità Odoo (oggi è solo l'id, per esempio 1733).
- Se il commerciale debba poter compilare anche lui, o restare in sola lettura.
