const state = {
  user: null,
  filtro: "da_lavorare",
  errore: "",
  ricerca: "",
  leadsTutti: null,
  assistente: null,
  aperta: null,
  schedaId: null,
};

const FILTRI = [
  ["da_lavorare", "Da lavorare"],
  ["da_chiamare", "Da chiamare"],
  ["in_corso", "In corso"],
  ["chiusi", "Chiusi"],
  ["tutti", "Tutti"],
];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function messaggioErrore(data) {
  if (data && typeof data.detail === "string") return data.detail;
  return "Richiesta non riuscita.";
}

async function api(method, path, body, opzioni = {}) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && !opzioni.login) {
    state.user = null;
    if (!location.hash.startsWith("#/login")) location.hash = "#/login";
    throw new Error(messaggioErrore(data));
  }
  if (!response.ok) throw new Error(messaggioErrore(data));
  return data;
}

function mostraErrore(err) {
  state.errore = err && err.message ? err.message : "Qualcosa non ha funzionato.";
  const box = document.getElementById("errore");
  if (box) {
    box.hidden = false;
    box.textContent = state.errore;
  }
}

function erroreHtml() {
  if (!state.errore) return "";
  return `<p class="errore" id="errore">${esc(state.errore)}</p>`;
}

function etichettaGiorni(n) {
  return n === 1 ? "giorno" : "giorni";
}

function formattaArrivo(createDate) {
  if (!createDate) return "";
  const data = new Date(createDate.replace(" ", "T") + "Z");
  return new Intl.DateTimeFormat("it-IT", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Europe/Rome",
  }).format(data);
}

function aLocaleInput(iso) {
  if (!iso) return "";
  const data = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${data.getFullYear()}-${pad(data.getMonth() + 1)}-${pad(data.getDate())}T${pad(data.getHours())}:${pad(data.getMinutes())}`;
}

function barra(attivo) {
  if (!state.user) {
    return `<header class="barra"><div class="barra-interna"><p class="marca">MOSAIKA</p><h1>Lead wallbox</h1></div></header>`;
  }
  return `
    <header class="barra">
      <div class="barra-interna">
        <p class="marca">MOSAIKA</p>
        <h1>Lead wallbox</h1>
        <nav>
          <a href="#/lead" ${attivo === "lead" ? 'aria-current="page"' : ""}>Lead</a>
          <a href="#/obiezioni" ${attivo === "obiezioni" ? 'aria-current="page"' : ""}>Obiezioni</a>
        </nav>
        <span class="spazio"></span>
        <span class="ruolo">${esc(state.user.nome)} · ${esc(state.user.ruolo)}</span>
        <button type="button" class="icona" data-action="tema" data-testid="tema">Tema</button>
        <button type="button" class="fantasma" data-action="esci">Esci</button>
      </div>
    </header>`;
}

function piede() {
  return `<p class="piede">Prototipo v1 · Odoo in sola lettura · nessun deploy in produzione.</p>`;
}

function renderLogin() {
  document.getElementById("app").innerHTML = `
    ${barra()}
    <main class="pagina">
      <form class="login card" id="login-form" data-testid="login">
        ${erroreHtml()}
        <h2>Entra</h2>
        <p class="muto">Strumento dei commerciali BABOO. L'accesso di questa versione è con utenti propri.</p>
        <label class="campo"><span class="etichetta">Email</span>
          <input name="email" type="email" autocomplete="username" required>
        </label>
        <label class="campo"><span class="etichetta">Password</span>
          <input name="password" type="password" autocomplete="current-password" required>
        </label>
        <button class="bottone" type="submit">Entra</button>
      </form>
    </main>`;
}

function cardLead(lead) {
  const tags = (lead.etichette || []).map((tag) => `<span class="tag">${esc(tag)}</span>`).join("");
  return `
    <a class="card" data-testid="lead-card" href="#/lead/${lead.odoo_lead_id}">
      <div class="giorni ${lead.in_ritardo ? "in-ritardo" : ""}" data-testid="giorni">
        ${esc(lead.giorni_attesa)}
        <small>${etichettaGiorni(lead.giorni_attesa)}</small>
      </div>
      <div>
        <p class="nome">${esc(lead.nome)}</p>
        <p class="comune">${esc(lead.comune)}</p>
        <div class="badge-riga">
          <span class="badge">${esc(lead.stato)}</span>
          ${tags}
        </div>
      </div>
    </a>`;
}

async function renderElenco() {
  const dati = await api("GET", `/api/leads?filtro=${encodeURIComponent(state.filtro)}`);
  const chips = FILTRI.map(([id, nome]) => `
    <button type="button" class="chip" data-action="filtro" data-filtro="${id}" aria-pressed="${state.filtro === id}">${nome}</button>
  `).join("");
  const cards = dati.leads.length
    ? dati.leads.map(cardLead).join("")
    : `<p class="muto">Nessun lead in questo filtro.</p>`;
  document.getElementById("app").innerHTML = `
    ${barra("lead")}
    <main class="pagina" data-testid="elenco">
      ${erroreHtml()}
      <section class="riepilogo" data-testid="riepilogo">
        <div class="cifra"><p class="etichetta">Lead</p><strong>${dati.riepilogo.totale}</strong></div>
        <div class="cifra"><p class="etichetta">Da chiamare</p><strong>${dati.riepilogo.da_chiamare}</strong></div>
        <div class="cifra"><p class="etichetta">Più vecchio</p><strong>${dati.riepilogo.giorni_piu_vecchio}<small style="font-size:0.8rem"> ${etichettaGiorni(dati.riepilogo.giorni_piu_vecchio)}</small></strong></div>
      </section>
      <div class="filtri">${chips}</div>
      <p class="muto">Lettura Odoo ${dati.letto_il ? esc(new Date(dati.letto_il).toLocaleString("it-IT")) : "mai"} ·
        <button type="button" class="secondario" data-action="aggiorna">Aggiorna</button>
      </p>
      <div class="lista">${cards}</div>
      ${piede()}
    </main>`;
}

function opzioni(valori, selezionato) {
  return valori.map((valore) => `<option value="${esc(valore)}" ${valore === selezionato ? "selected" : ""}>${esc(valore)}</option>`).join("");
}

function renderScheda(lead) {
  state.schedaId = lead.odoo_lead_id;
  const modulo = ["fotovoltaico", "auto", "parcheggio"].map((campo) => {
    const riga = lead.modulo[campo];
    return `<p><span class="etichetta">${esc(riga.chiave)}</span><br>${esc(riga.valore || "—")}</p>`;
  }).join("");
  const qualifica = lead.qualifica_voci.map((voce) => {
    const dati = lead.qualifica[voce.id] || { nota: "", fatto: false };
    return `
      <div class="voce">
        <input type="checkbox" data-fatto="${esc(voce.id)}" ${dati.fatto ? "checked" : ""} aria-label="${esc(voce.etichetta)}">
        <label class="campo"><span class="etichetta">${esc(voce.etichetta)}</span>
          <input data-qualifica="${esc(voce.id)}" value="${esc(dati.nota)}">
        </label>
      </div>`;
  }).join("");
  const versioni = lead.versioni.map((versione) => `
    <label class="scelta">
      <input type="radio" name="versione" value="${esc(versione)}" ${lead.versione === versione ? "checked" : ""}>
      <span>${esc(versione)}</span>
    </label>`).join("");
  const giro = lead.giro_voci.map((voce) => `
    <label class="giro"><input type="checkbox" data-giro="${esc(voce.id)}" ${lead.giro[voce.id] ? "checked" : ""}> ${esc(voce.etichetta)}</label>
  `).join("");
  const videoUrl = lead.messaggi.video.url;
  document.getElementById("app").innerHTML = `
    ${barra("lead")}
    <main class="pagina" data-testid="scheda">
      ${erroreHtml()}
      <p><a href="#/lead">← Elenco</a></p>
      <section class="blocco intero scheda-testa">
        <div>
          <p class="etichetta">${esc(lead.comune)}</p>
          <h2>${esc(lead.nome)}</h2>
          <p class="giorni ${lead.in_ritardo ? "in-ritardo" : ""}" id="giorni-scheda" data-testid="giorni">
            ${esc(lead.giorni_attesa)} <small>${etichettaGiorni(lead.giorni_attesa)}</small>
          </p>
        </div>
        <div class="campi" style="min-width:min(100%, 220px)">
          <label class="campo"><span class="etichetta">Stato</span>
            <select id="stato">${opzioni(lead.stati, lead.stato)}</select>
          </label>
          <label class="campo"><span class="etichetta">Zona</span>
            <select id="zona">${opzioni(lead.zone, lead.zona)}</select>
          </label>
          <p class="salvato" id="salvato"></p>
        </div>
      </section>
      <div class="griglia" style="margin-top:12px">
        <section class="blocco">
          <h3>Dati</h3>
          <p><span class="etichetta">Arrivo (ora di Roma)</span><br>${esc(formattaArrivo(lead.create_date))}</p>
          <p><span class="etichetta">Create date UTC</span><br>${esc(lead.create_date)}</p>
          ${modulo}
          <p><span class="etichetta">Id Odoo</span><br>${esc(lead.odoo_lead_id)}</p>
          <p><span class="etichetta">Fase Odoo</span><br>${esc(lead.stage || "—")}${lead.archiviato ? " · archiviato" : ""}</p>
          <p><span class="etichetta">Assegnatario</span><br>${esc(lead.assegnatario || "—")}</p>
        </section>
        <section class="blocco">
          <h3>Contatti</h3>
          <div class="azioni">
            ${lead.contatti.tel ? `<a class="bottone" href="${esc(lead.contatti.tel)}">Chiama</a>` : ""}
            ${lead.contatti.whatsapp ? `<a class="secondario" data-testid="wa-contatto" href="${esc(lead.contatti.whatsapp)}" target="_blank" rel="noopener">WhatsApp</a>` : ""}
            ${lead.contatti.email ? `<a class="secondario" href="${esc(lead.contatti.email)}">Email</a>` : ""}
          </div>
        </section>
        <section class="blocco">
          <h3>Qualifica</h3>
          <div class="campi">${qualifica}</div>
        </section>
        <section class="blocco">
          <h3>Versione consigliata</h3>
          <p class="muto">Suggerita: <strong>${esc(lead.versione_suggerita)}</strong>. Solare se ha il fotovoltaico, altrimenti Smart. Essenziale se vuole solo ricaricare spendendo poco.</p>
          <div class="scelte">${versioni}</div>
        </section>
        <section class="blocco intero">
          <h3>Sopralluogo a distanza</h3>
          <div class="scelte">
            <label class="scelta"><input type="radio" name="sopralluogo" value="video" ${lead.sopralluogo !== "foto" ? "checked" : ""}><span>Videochiamata</span></label>
            <label class="scelta"><input type="radio" name="sopralluogo" value="foto" ${lead.sopralluogo === "foto" ? "checked" : ""}><span>Foto</span></label>
          </div>
          <div data-pannello="video" ${lead.sopralluogo === "foto" ? "hidden" : ""}>
            <label class="campo"><span class="etichetta">Giorno e ora</span>
              <input id="video-il" type="datetime-local" value="${esc(aLocaleInput(lead.video_il))}">
            </label>
            <p class="promemoria">${esc(lead.promemoria_sopralluogo)}</p>
            <div class="campi">${giro}</div>
            <p><button type="button" class="bottone" data-action="conferma-video" data-testid="conferma-video">Messaggio di conferma</button></p>
          </div>
          <div data-pannello="foto" ${lead.sopralluogo === "foto" ? "" : "hidden"}>
            <p class="muto">Cinque foto: contatore, quadro, punto della wallbox, percorso del cavo, inverter.</p>
            <p><button type="button" class="bottone" data-action="chiedi-foto" data-testid="chiedi-foto">Chiedi le foto su WhatsApp</button></p>
            <label class="giro"><input id="foto-ricevute" type="checkbox" ${lead.foto_ricevute ? "checked" : ""}> Foto ricevute</label>
          </div>
        </section>
        <section class="blocco intero">
          <h3>Note</h3>
          <textarea id="note" data-save="note">${esc(lead.note || "")}</textarea>
          <p><button type="button" class="secondario" data-action="detta" data-target="#note">Detta</button></p>
        </section>
        <section class="blocco intero">
          <p class="promemoria">${esc(lead.promemoria_odoo)}</p>
          ${lead.aggiornato_da ? `<p class="muto">Aggiornato da ${esc(lead.aggiornato_da)}</p>` : ""}
        </section>
      </div>
      ${piede()}
    </main>`;
}

async function apriScheda(id) {
  const lead = await api("GET", `/api/leads/${id}`);
  renderScheda(lead);
}

let timerNota = null;
let timerQualifica = null;

async function patchScheda(body) {
  const id = state.schedaId;
  const data = await api("PATCH", `/api/leads/${id}`, body);
  if (state.schedaId !== id) return data;
  const stato = document.getElementById("stato");
  if (stato) stato.value = data.stato;
  const giorni = document.getElementById("giorni-scheda");
  if (giorni) giorni.classList.toggle("in-ritardo", data.in_ritardo);
  const salvato = document.getElementById("salvato");
  if (salvato) salvato.textContent = "Salvato";
  state.scheda = data;
  const video = document.querySelector("[data-pannello=video]");
  const foto = document.querySelector("[data-pannello=foto]");
  if (video && foto) {
    const modalita = data.sopralluogo === "foto" ? "foto" : "video";
    video.hidden = modalita !== "video";
    foto.hidden = modalita !== "foto";
  }
  return data;
}

function leggiQualifica() {
  const qualifica = {};
  document.querySelectorAll("[data-qualifica]").forEach((input) => {
    const id = input.dataset.qualifica;
    const spunta = document.querySelector(`[data-fatto="${id}"]`);
    if (input.value.trim() && spunta) spunta.checked = true;
    qualifica[id] = { nota: input.value, fatto: Boolean(spunta && spunta.checked) };
  });
  return qualifica;
}

function leggiGiro() {
  const giro = {};
  document.querySelectorAll("[data-giro]").forEach((input) => {
    giro[input.dataset.giro] = input.checked;
  });
  return giro;
}

function detta(selector) {
  const Riconoscimento = window.SpeechRecognition || window.webkitSpeechRecognition;
  const target = document.querySelector(selector);
  if (!Riconoscimento || !target) {
    mostraErrore(new Error("Dettatura non disponibile su questo browser."));
    return;
  }
  const riconoscimento = new Riconoscimento();
  riconoscimento.lang = "it-IT";
  riconoscimento.onresult = (event) => {
    const detto = event.results[0][0].transcript;
    target.value = `${target.value ? `${target.value.trim()} ` : ""}${detto}`;
    target.dispatchEvent(new Event("input", { bubbles: true }));
  };
  riconoscimento.onerror = () => mostraErrore(new Error("Dettatura interrotta."));
  riconoscimento.start();
}

function apriFinestra(url) {
  const finestra = window.open("about:blank", "_blank");
  return (destinazione) => {
    if (!destinazione) {
      if (finestra) finestra.close();
      return;
    }
    if (finestra) finestra.location = destinazione;
    else location.href = destinazione;
  };
}

async function renderObiezioni() {
  if (!state.leadsTutti) {
    const leads = await api("GET", "/api/leads?filtro=tutti");
    state.leadsTutti = leads.leads;
  }
  const dati = await api("GET", `/api/obiezioni?q=${encodeURIComponent(state.ricerca || "")}`);
  const puoValidare = state.user.ruolo === "tecnico" || state.user.ruolo === "admin";
  const comuni = state.leadsTutti.map((lead) => `
    <option value="${esc(lead.comune)}">${esc(lead.nome)} — ${esc(lead.comune)}</option>
  `).join("");
  const lista = dati.obiezioni.map((item) => {
    const aperta = state.aperta === item.id;
    const editor = !aperta ? "" : puoValidare ? `
      <div class="campi" style="margin-top:12px">
        <label class="campo"><span class="etichetta">Domanda</span>
          <textarea data-campo="domanda">${esc(item.domanda)}</textarea></label>
        <label class="campo"><span class="etichetta">Risposta</span>
          <textarea data-campo="risposta">${esc(item.risposta)}</textarea></label>
        <label class="campo"><span class="etichetta">Comune</span>
          <input data-campo="comune" value="${esc(item.comune || "")}"></label>
        <label class="giro"><input data-campo="validata" type="checkbox" ${item.validata ? "checked" : ""}> Validata</label>
        <button type="button" class="bottone" data-action="salva-obiezione" data-id="${item.id}">Salva</button>
      </div>` : `
      <div class="campi" style="margin-top:12px">
        <label class="campo"><span class="etichetta">Domanda</span>
          <textarea data-campo="domanda">${esc(item.domanda)}</textarea></label>
        <p>${esc(item.risposta || "Ancora senza risposta.")}</p>
        <label class="campo"><span class="etichetta">Comune</span>
          <input data-campo="comune" value="${esc(item.comune || "")}"></label>
        <button type="button" class="bottone" data-action="salva-obiezione" data-id="${item.id}">Salva la domanda</button>
      </div>`;
    return `
      <article class="card" data-testid="obiezione" style="display:block">
        <button type="button" class="nudo" data-action="apri-obiezione" data-id="${item.id}">
          <p class="badge ${esc(item.badge).replace(" ", "-")}">${esc(item.badge)}</p>
          <p class="nome">${esc(item.domanda)}</p>
          <p class="comune">${esc(item.comune || "Comune non indicato")}</p>
        </button>
        ${editor}
      </article>`;
  }).join("");
  const risposta = state.assistente ? `
    <div class="blocco ${state.assistente.fallback ? "rinvio" : ""} risposta-box" data-testid="risposta-assistente">
      <p class="etichetta">${state.assistente.fallback ? "Rinvio" : "Dal registro"}</p>
      <p>${esc(state.assistente.risposta)}</p>
    </div>` : "";
  const eraRicerca = document.activeElement && document.activeElement.id === "ricerca";
  const pos = eraRicerca ? document.activeElement.selectionStart : null;
  document.getElementById("app").innerHTML = `
    ${barra("obiezioni")}
    <main class="pagina" data-testid="obiezioni">
      ${erroreHtml()}
      <label class="campo"><span class="etichetta">Cerca</span>
        <input id="ricerca" value="${esc(state.ricerca)}" placeholder="Domanda, risposta, comune">
      </label>
      <section class="blocco" style="margin-top:12px" data-testid="assistente">
        <h2>Assistente</h2>
        <p class="muto">Risponde solo con le risposte validate. Se non ne ha, lo dice e si ferma.</p>
        <label class="campo"><span class="etichetta">Domanda del cliente</span>
          <textarea id="domanda-assistente">${esc(state.domandaAssistente || "")}</textarea>
        </label>
        <label class="campo"><span class="etichetta">Comune del lead</span>
          <input id="comune-assistente" list="comuni-lead" value="${esc(state.comuneAssistente || "")}">
          <datalist id="comuni-lead">${comuni}</datalist>
        </label>
        <div class="azioni">
          <button type="button" class="secondario" data-action="detta" data-target="#domanda-assistente">Detta</button>
          <button type="button" class="bottone" data-action="chiedi" data-testid="chiedi">Chiedi</button>
          <button type="button" class="secondario" data-action="aggiungi-domanda">Aggiungi la domanda al registro</button>
        </div>
        ${risposta}
      </section>
      <section class="blocco" style="margin-top:12px">
        <h2>Domanda nuova</h2>
        <label class="campo"><span class="etichetta">Con le parole del cliente</span>
          <textarea id="domanda-nuova"></textarea></label>
        <label class="campo"><span class="etichetta">Comune</span>
          <input id="comune-nuovo"></label>
        <button type="button" class="bottone" data-action="crea-obiezione">Aggiungi</button>
      </section>
      <h2 style="margin-top:20px">Registro</h2>
      <div class="lista">${lista || `<p class="muto">Nessuna obiezione.</p>`}</div>
      ${piede()}
    </main>`;
  if (eraRicerca) {
    const input = document.getElementById("ricerca");
    input.focus();
    if (pos != null) input.setSelectionRange(pos, pos);
  }
}

async function route() {
  try {
    const hash = location.hash || (state.user ? "#/lead" : "#/login");
    if (!state.user && !hash.startsWith("#/login")) {
      location.hash = "#/login";
      return;
    }
    state.errore = "";
    if (hash.startsWith("#/login")) return renderLogin();
    if (hash.startsWith("#/obiezioni")) return await renderObiezioni();
    const match = hash.match(/^#\/lead\/(\d+)$/);
    if (match) return await apriScheda(Number(match[1]));
    state.schedaId = null;
    return await renderElenco();
  } catch (err) {
    mostraErrore(err);
    if (!document.getElementById("errore")) {
      document.getElementById("app").innerHTML = `${barra()}<main class="pagina">${erroreHtml()}</main>`;
    }
  }
}

document.addEventListener("click", async (event) => {
  const bottone = event.target.closest("[data-action]");
  if (!bottone) return;
  const azione = bottone.dataset.action;
  try {
    if (azione === "tema") {
      const prossimo = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = prossimo;
      localStorage.setItem("mosaika-tema", prossimo);
    } else if (azione === "esci") {
      await api("POST", "/api/auth/logout");
      state.user = null;
      location.hash = "#/login";
    } else if (azione === "filtro") {
      state.filtro = bottone.dataset.filtro;
      await renderElenco();
    } else if (azione === "aggiorna") {
      await api("POST", "/api/leads/aggiorna");
      await renderElenco();
    } else if (azione === "detta") {
      detta(bottone.dataset.target);
    } else if (azione === "conferma-video") {
      const input = document.getElementById("video-il");
      if (!input || !input.value) {
        mostraErrore(new Error("Indica giorno e ora della videochiamata."));
        return;
      }
      const vai = apriFinestra();
      try {
        const data = await patchScheda({ video_il: new Date(input.value).toISOString() });
        vai(data.messaggi.video.url);
      } catch (err) {
        vai(null);
        throw err;
      }
    } else if (azione === "chiedi-foto") {
      const vai = apriFinestra();
      try {
        const data = await patchScheda({ sopralluogo: "foto" });
        vai(data.messaggi.foto.url);
      } catch (err) {
        vai(null);
        throw err;
      }
    } else if (azione === "chiedi") {
      state.domandaAssistente = document.getElementById("domanda-assistente").value;
      state.comuneAssistente = document.getElementById("comune-assistente").value;
      state.assistente = await api("POST", "/api/assistente", { domanda: state.domandaAssistente });
      await renderObiezioni();
    } else if (azione === "aggiungi-domanda") {
      const domanda = (document.getElementById("domanda-assistente").value || state.domandaAssistente || "").trim();
      const comune = (document.getElementById("comune-assistente").value || state.comuneAssistente || "").trim();
      if (!domanda) {
        mostraErrore(new Error("Scrivi prima la domanda del cliente."));
        return;
      }
      await api("POST", "/api/obiezioni", { domanda, comune: comune || null });
      state.assistente = null;
      state.domandaAssistente = "";
      state.comuneAssistente = "";
      await renderObiezioni();
    } else if (azione === "crea-obiezione") {
      const domanda = document.getElementById("domanda-nuova").value.trim();
      const comune = document.getElementById("comune-nuovo").value.trim();
      await api("POST", "/api/obiezioni", { domanda, comune: comune || null });
      await renderObiezioni();
    } else if (azione === "apri-obiezione") {
      const id = Number(bottone.dataset.id);
      state.aperta = state.aperta === id ? null : id;
      await renderObiezioni();
    } else if (azione === "salva-obiezione") {
      const card = bottone.closest("article");
      const id = Number(bottone.dataset.id);
      const payload = {
        domanda: card.querySelector("[data-campo=domanda]").value,
        comune: card.querySelector("[data-campo=comune]").value,
      };
      const risposta = card.querySelector("[data-campo=risposta]");
      const validata = card.querySelector("[data-campo=validata]");
      if (risposta) payload.risposta = risposta.value;
      if (validata) payload.validata = validata.checked;
      await api("PATCH", `/api/obiezioni/${id}`, payload);
      await renderObiezioni();
    }
  } catch (err) {
    mostraErrore(err);
  }
});

document.addEventListener("input", (event) => {
  const el = event.target;
  if (el.id === "ricerca") {
    state.ricerca = el.value;
    clearTimeout(state.timerRicerca);
    state.timerRicerca = setTimeout(() => renderObiezioni().catch(mostraErrore), 250);
  }
  if (el.id === "domanda-assistente") state.domandaAssistente = el.value;
  if (el.id === "comune-assistente") state.comuneAssistente = el.value;
  if (el.dataset.qualifica) {
    const spunta = document.querySelector(`[data-fatto="${el.dataset.qualifica}"]`);
    if (el.value.trim() && spunta) spunta.checked = true;
    clearTimeout(timerQualifica);
    timerQualifica = setTimeout(() => {
      patchScheda({ qualifica: leggiQualifica() }).catch(mostraErrore);
    }, 400);
  }
  if (el.dataset.save === "note") {
    clearTimeout(timerNota);
    timerNota = setTimeout(() => patchScheda({ note: el.value }).catch(mostraErrore), 500);
  }
});

document.addEventListener("change", (event) => {
  const el = event.target;
  const salva = (body) => patchScheda(body).catch(mostraErrore);
  if (el.id === "stato") salva({ stato: el.value });
  if (el.id === "zona") salva({ zona: el.value });
  if (el.name === "versione") salva({ versione: el.value });
  if (el.name === "sopralluogo") salva({ sopralluogo: el.value });
  if (el.id === "foto-ricevute") salva({ foto_ricevute: el.checked });
  if (el.id === "video-il" && el.value) salva({ video_il: new Date(el.value).toISOString() });
  if (el.dataset.giro) salva({ giro: leggiGiro() });
  if (el.dataset.fatto) salva({ qualifica: leggiQualifica() });
});

document.addEventListener("submit", async (event) => {
  if (event.target.id !== "login-form") return;
  event.preventDefault();
  const dati = new FormData(event.target);
  try {
    state.user = await api("POST", "/api/auth/login", {
      email: dati.get("email"),
      password: dati.get("password"),
    }, { login: true });
    state.errore = "";
    if (location.hash !== "#/lead") location.hash = "#/lead";
    else await route();
  } catch (err) {
    state.errore = err.message;
    renderLogin();
  }
});

window.addEventListener("hashchange", () => route());

async function boot() {
  try {
    state.user = await api("GET", "/api/auth/me");
  } catch {
    state.user = null;
  }
  if (!location.hash) location.hash = state.user ? "#/lead" : "#/login";
  await route();
  if ("serviceWorker" in navigator && !navigator.webdriver) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
}

boot();
