import { creaCoda, inviaAPezzi } from "./coda.js";

const NOMI = { F: "foto", V: "video", A: "audio", M: "misura", T: "testo", D: "documento" };
const SOGLIA_PEZZI = 1024 * 1024;

const state = {
  user: null,
  errore: "",
  route: { name: "elenco" },
  modelli: [],
  elenco: [],
  rilievo: null,
  sezioneAperta: null,
  bozzaMisure: null,
  bozzaPer: null,
  online: navigator.onLine,
  sync: { in_coda: 0, in_invio: 0, inviate: 0, errori: 0, scartate: 0 },
  token: 0,
  kv: null,
  coda: null,
  registrando: null,
  stream: null,
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function scrive() {
  return state.user && (state.user.ruolo === "tecnico" || state.user.ruolo === "admin");
}

function messaggio(data, fallback) {
  if (data && typeof data.detail === "string") return data.detail;
  return fallback || "Richiesta non riuscita.";
}

async function api(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    });
  } catch {
    const errore = new Error("Connessione assente.");
    errore.rete = true;
    throw errore;
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    state.user = null;
    if (!location.hash.startsWith("#/login")) location.hash = "#/login";
    throw new Error(messaggio(data, "Accesso richiesto."));
  }
  if (!response.ok) throw new Error(messaggio(data));
  return data;
}

function mostraErrore(err) {
  state.errore = err && err.message ? err.message : "Qualcosa non ha funzionato.";
  const box = document.getElementById("errore");
  if (box) {
    box.hidden = false;
    box.textContent = state.errore;
  } else {
    disegna().catch(() => {});
  }
}

function erroreHtml() {
  if (!state.errore) return "";
  return `<p class="errore" id="errore">${esc(state.errore)}</p>`;
}

function testoSync() {
  const r = state.sync || { in_coda: 0, in_invio: 0 };
  if (!state.online) return `Non in linea · ${r.in_coda} in coda`;
  if (r.in_invio) return "Invio in corso";
  if (r.in_coda) return `In linea · ${r.in_coda} da inviare`;
  return "In linea · sincronizzato";
}

function barra() {
  if (!state.user) {
    return `<header class="barra"><div class="barra-interna"><p class="marca">MOSAIKA</p><h1>Sopralluogo</h1></div></header>`;
  }
  return `
    <header class="barra">
      <div class="barra-interna">
        <p class="marca">MOSAIKA</p>
        <h1>Sopralluogo</h1>
        <nav>
          <a href="#/" ${state.route.name === "elenco" ? 'aria-current="page"' : ""}>Rilievi</a>
          <a href="/">Lead</a>
        </nav>
        <span class="spazio"></span>
        <span class="ruolo">${esc(state.user.nome)} · ${esc(state.user.ruolo)}</span>
        <button type="button" class="icona" data-action="tema" data-testid="tema">Tema</button>
        <button type="button" class="fantasma" data-action="esci">Esci</button>
        <p class="sync" data-testid="stato-sync">${esc(testoSync())}</p>
      </div>
    </header>`;
}

function piede() {
  return `<p class="piede">Prototipo · i file restano nel sopralluogo, nessuna chiamata a Odoo.</p>`;
}

function parseRoute() {
  const parti = (location.hash || "#/").replace(/^#/, "").split("/").filter(Boolean);
  if (parti[0] === "login") return { name: "login" };
  if (parti[0] === "nuovo") return { name: "nuovo" };
  if (parti[0] === "rilievo" && parti[1]) {
    const id = Number(parti[1]);
    if (parti[2] === "voce" && parti[3]) return { name: "voce", id, voceId: Number(parti[3]) };
    if (parti[2] === "chiusura") return { name: "chiusura", id };
    return { name: "rilievo", id };
  }
  return { name: "elenco" };
}

function voceAperta() {
  if (!state.rilievo) return null;
  for (const sezione of state.rilievo.sezioni) {
    for (const voce of sezione.voci) {
      if (voce.id === state.route.voceId) return { sezione, voce };
    }
  }
  return null;
}

async function caricaRilievo(id) {
  try {
    state.rilievo = await api("GET", `/api/sopralluogo/rilievi/${id}`);
    if (state.kv) await state.kv.set("rilievo:" + id, state.rilievo);
  } catch (err) {
    if (!err.rete) throw err;
    const cached = state.kv ? await state.kv.get("rilievo:" + id) : null;
    if (!cached) throw err;
    state.rilievo = cached;
    state.errore = "Non in linea: mostro l'ultima copia salvata sul telefono.";
  }
}

async function route() {
  state.route = parseRoute();
  if (!state.user && state.route.name !== "login") {
    location.hash = "#/login";
    return;
  }
  if (state.user && state.route.name === "login") {
    location.hash = "#/";
    return;
  }
  if (state.route.voceId && state.route.voceId !== state.bozzaPer) {
    state.bozzaMisure = null;
    state.bozzaPer = state.route.voceId;
  }
  await disegna();
}

async function disegna() {
  const token = ++state.token;
  state.online = navigator.onLine;
  try {
    if (state.coda) state.sync = await state.coda.riepilogo();
    if (state.route.name === "elenco" && state.user) {
      state.elenco = (await api("GET", "/api/sopralluogo/rilievi")).rilievi;
    } else if (state.route.name === "nuovo") {
      state.modelli = (await api("GET", "/api/sopralluogo/modelli")).modelli;
    } else if (state.route.id) {
      await caricaRilievo(state.route.id);
    }
  } catch (err) {
    if (err.rete) state.errore = err.message;
    else state.errore = err.message || "Qualcosa non ha funzionato.";
  }
  if (token !== state.token) return;
  const vista = {
    login: renderLogin,
    nuovo: renderNuovo,
    rilievo: renderRilievo,
    voce: renderVoce,
    chiusura: renderChiusura,
    elenco: renderElenco,
  }[state.route.name] || renderElenco;
  document.getElementById("app").innerHTML = vista();
  dopoRender();
}

function renderLogin() {
  return `
    ${barra()}
    <main class="pagina">
      <form class="login card" id="login-form" data-testid="login">
        ${erroreHtml()}
        <h2>Entra</h2>
        <p class="muto">Checklist di sopralluogo. Stessi utenti di Lead wallbox.</p>
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

function renderElenco() {
  const cards = state.elenco.length
    ? state.elenco.map((riga) => `
      <a class="card" href="#/rilievo/${riga.id}">
        <div>
          <p class="nome">${esc(riga.sito)}</p>
          <p class="comune">${esc(riga.titolo)}</p>
          <div class="badge-riga">
            <span class="badge">${esc(riga.stato)}</span>
            ${riga.odoo_opportunity_id ? `<span class="tag">OPP ${esc(riga.odoo_opportunity_id)}</span>` : ""}
            <span class="badge ${riga.voci_aperte ? "in-ritardo" : "validata"}">${esc(riga.voci_aperte)} aperte</span>
          </div>
        </div>
      </a>`).join("")
    : `<p class="muto">Nessun sopralluogo. Il modello OPP 1733 è già pronto.</p>`;
  return `
    ${barra()}
    <main class="pagina" data-testid="elenco">
      ${erroreHtml()}
      ${scrive() ? `<p><a class="bottone" href="#/nuovo" data-testid="nuovo">Nuovo sopralluogo</a></p>` : ""}
      <div class="lista">${cards}</div>
      ${piede()}
    </main>`;
}

function renderNuovo() {
  const opzioni = state.modelli.map((modello) => {
    const scelto = modello.codice === "opp-1733" || state.modelli.length === 1;
    return `<option value="${esc(modello.codice)}" ${scelto ? "selected" : ""}>${esc(modello.titolo)}</option>`;
  }).join("");
  const iniziale = state.modelli.find((modello) => modello.codice === "opp-1733") || state.modelli[0] || {};
  return `
    ${barra()}
    <main class="pagina">
      <p><a href="#/">← Rilievi</a></p>
      <form class="card campi" id="form-nuovo">
        ${erroreHtml()}
        <h2>Nuovo sopralluogo</h2>
        <label class="campo"><span class="etichetta">Modello</span>
          <select id="modello" name="modello">${opzioni}</select>
        </label>
        <label class="campo"><span class="etichetta">Sito</span>
          <input id="sito" name="sito" required value="${esc(iniziale.sito || "")}">
        </label>
        <label class="campo"><span class="etichetta">Titolo</span>
          <input id="titolo" name="titolo" value="${esc(iniziale.titolo || "")}">
        </label>
        <label class="campo"><span class="etichetta">Opportunità Odoo (facoltativa)</span>
          <input id="opportunita" name="opportunita" inputmode="numeric" value="${esc(iniziale.odoo_opportunity_id || "")}">
        </label>
        <button class="bottone" type="submit">Apri il sopralluogo</button>
      </form>
    </main>`;
}

function renderRilievo() {
  const rilievo = state.rilievo;
  if (!rilievo) return `${barra()}<main class="pagina">${erroreHtml()}<p>Sopralluogo non trovato.</p></main>`;
  const sezioni = rilievo.sezioni.filter((sezione) => sezione.tipo !== "chiusura").map((sezione) => {
    const aperta = state.sezioneAperta === sezione.codice;
    const corpo = aperta ? corpoSezione(sezione) : "";
    return `
      <section class="blocco">
        <button type="button" class="nudo" data-action="sezione" data-codice="${esc(sezione.codice)}" data-testid="sezione">
          <p class="etichetta">${esc(sezione.prefisso || sezione.tipo)}</p>
          <h2>${esc(sezione.titolo)}</h2>
          <p class="muto">${esc(sezione.sottotitolo || "")}</p>
        </button>
        ${corpo}
      </section>`;
  }).join("");
  return `
    ${barra()}
    <main class="pagina" data-testid="rilievo">
      ${erroreHtml()}
      <p><a href="#/">← Rilievi</a></p>
      <p class="etichetta">${rilievo.odoo_opportunity_id ? `OPP ${esc(rilievo.odoo_opportunity_id)} · ` : ""}${esc(rilievo.revisione ? "rev. " + rilievo.revisione : "")}</p>
      <h2>${esc(rilievo.sito)}</h2>
      <p class="muto">${esc(rilievo.perimetro || "")}</p>
      <div class="leggenda">
        <span class="tag">F foto</span><span class="tag">V video</span><span class="tag">A audio</span>
        <span class="tag">M misura</span><span class="tag">T testo</span><span class="tag">D documento</span>
      </div>
      <div class="lista" style="margin-top:12px">${sezioni}</div>
      <p class="azioni">
        <a class="bottone" href="#/rilievo/${rilievo.id}/chiusura" data-testid="vai-chiusura">Prima di andare via</a>
        <a class="secondario" href="/api/sopralluogo/rilievi/${rilievo.id}/export" data-testid="esporta">Esporta ZIP</a>
        <button type="button" class="secondario" data-action="sincronizza">Sincronizza</button>
      </p>
      ${piede()}
    </main>`;
}

function corpoSezione(sezione) {
  if (sezione.tipo === "strumenti") {
    return sezione.voci.map((voce) => `
      <label class="giro">
        <input type="checkbox" data-action="strumento" data-id="${voce.id}" ${voce.stato === "fatto" ? "checked" : ""} ${scrive() ? "" : "disabled"}>
        ${esc(voce.testo)}
      </label>`).join("");
  }
  return `<div class="lista">${sezione.voci.map((voce) => `
    <a class="card voce-link" data-testid="voce" href="#/rilievo/${state.rilievo.id}/voce/${voce.id}">
      <div>
        <p class="nome" style="font-size:1rem">${esc(voce.testo)}</p>
        <div class="badge-riga">
          <span class="tag">${esc(voce.capitolo_etichetta)}</span>
          ${voce.mancanti.map((codice) => `<span class="badge in-ritardo">manca ${esc(NOMI[codice] || codice)}</span>`).join("")}
          ${voce.stato === "fatto" ? `<span class="badge validata">fatto</span>` : ""}
          ${voce.stato === "non_applicabile" ? `<span class="badge">n/a</span>` : ""}
        </div>
      </div>
    </a>`).join("")}</div>`;
}

function renderVoce() {
  const trovata = voceAperta();
  if (!trovata) return `${barra()}<main class="pagina">${erroreHtml()}<p>Voce non trovata.</p></main>`;
  const { sezione, voce } = trovata;
  const indietro = `#/rilievo/${state.rilievo.id}`;
  const mancanti = voce.mancanti.length
    ? `Manca: ${voce.mancanti.map((codice) => NOMI[codice] || codice).join(", ")}`
    : "Niente in sospeso";
  const misure = (state.bozzaMisure || voce.misure.map((misura) => ({
    etichetta: misura.etichetta,
    valore: misura.valore,
    unita: misura.unita,
    rilevata_il: isoInLocale(misura.rilevata_il),
    temperatura_esterna: misura.temperatura_esterna || "",
  })));
  const righe = (misure.length ? misure : [misuraVuota(voce)]).map((misura, indice) => rigaMisura(voce, misura, indice)).join("");
  const consenso = voce.consenso_richiesto ? `
    <label class="giro"><input type="checkbox" data-testid="consenso"> Ho il consenso di chi parla</label>
    <label class="campo"><span class="etichetta">Chi parla</span>
      <input data-testid="consenso-nome" placeholder="Nome, se lo si conosce">
    </label>` : "";
  const bloccaAudio = voce.consenso_richiesto ? "disabled data-richiede-consenso" : "";
  const previsto = sezione.prefisso ? `<p class="muto">All'inizio di' <strong data-testid="prossimo-nome">${esc(prossimoNome(sezione))}</strong>.</p>` : "";
  return `
    ${barra()}
    <main class="pagina" data-testid="scheda-voce">
      ${erroreHtml()}
      <p><a href="${indietro}" data-testid="indietro">← ${esc(sezione.titolo)}</a></p>
      <p class="etichetta">${esc(voce.capitolo_etichetta)}</p>
      <h2>${esc(voce.testo)}</h2>
      <p class="${voce.mancanti.length ? "manca" : "muto"}" data-testid="mancanti">${esc(mancanti)}</p>
      ${previsto}
      ${scrive() ? `
        <div class="azioni">
          <button type="button" class="secondario" data-action="stato" data-stato="fatto">Fatto</button>
          <button type="button" class="secondario" data-action="stato" data-stato="non_applicabile">Non applicabile</button>
          <button type="button" class="secondario" data-action="stato" data-stato="aperto">Da fare</button>
        </div>
        ${campiTesto(voce)}
        ${voce.evidenze.includes("M") ? `<div class="campi" id="misure">${righe}</div><p><button type="button" class="secondario" data-action="aggiungi-misura">Aggiungi lettura</button></p>` : ""}
        ${voce.evidenze.includes("F") ? bloccoFile("F", "Foto", "image/*", "foto", true) : ""}
        ${voce.evidenze.includes("V") ? bloccoVideo() : ""}
        ${voce.evidenze.includes("A") ? `${consenso}${bloccoAudio(bloccaAudio)}` : ""}
        ${voce.evidenze.includes("D") ? bloccoDocumento(voce) : ""}
        <p><button type="button" class="bottone" data-action="salva-voce" data-testid="salva-voce">Salva</button></p>
      ` : ""}
      <ul class="lista">${voce.file.map((file) => `
        <li><a class="nome-file" data-testid="nome-file" href="/api/sopralluogo/rilievi/${state.rilievo.id}/file/${file.id}" target="_blank" rel="noopener">${esc(file.nome_assegnato)}</a>
        <span class="muto"> ${esc(file.nome_originale)} · ${esc(file.autore)}</span></li>`).join("")}</ul>
    </main>`;
}

function misuraVuota(voce) {
  return {
    etichetta: (voce.etichette && voce.etichette[0]) || "",
    valore: "",
    unita: voce.unita_suggerita || "",
    rilevata_il: "",
    temperatura_esterna: "",
  };
}

function rigaMisura(voce, misura, indice) {
  const etichette = voce.etichette || [];
  const scelta = etichette.length
    ? `<select data-campo="etichetta">${etichette.map((etichetta) => `<option ${etichetta === misura.etichetta ? "selected" : ""}>${esc(etichetta)}</option>`).join("")}<option ${misura.etichetta && !etichette.includes(misura.etichetta) ? "selected" : ""}>Altro</option></select>`
    : `<input data-campo="etichetta" placeholder="Etichetta" value="${esc(misura.etichetta || "")}">`;
  const ora = (voce.temperatura || voce.con_ora) ? `
    <label class="campo"><span class="etichetta">Ora</span>
      <input type="datetime-local" data-campo="ora" value="${esc(misura.rilevata_il || "")}">
    </label>` : "";
  const esterna = voce.temperatura ? `
    <label class="campo"><span class="etichetta">Temperatura esterna</span>
      <input data-campo="esterna" inputmode="decimal" value="${esc(misura.temperatura_esterna || "")}" placeholder="°C">
    </label>` : "";
  const testid = indice === 0 ? `data-testid="misura-valore"` : "";
  const testidUnita = indice === 0 ? `data-testid="misura-unita"` : "";
  return `
    <div class="riga-misura" data-misura>
      <label class="campo"><span class="etichetta">Lettura</span>${scelta}</label>
      <label class="campo"><span class="etichetta">Valore</span>
        <input ${testid} data-campo="valore" inputmode="decimal" value="${esc(misura.valore || "")}">
      </label>
      <label class="campo"><span class="etichetta">Unità</span>
        <input ${testidUnita} data-campo="unita" value="${esc(misura.unita || "")}">
      </label>
      ${ora}${esterna}
    </div>`;
}

function campiTesto(voce) {
  if (!voce.evidenze.includes("T") && !voce.evidenze.includes("D")) return "";
  return `
    <label class="campo"><span class="etichetta">Nota</span>
      <textarea id="testo-voce" data-testid="testo-voce">${esc(voce.testo_nota || "")}</textarea>
    </label>`;
}

function bloccoFile(tipo, etichetta, accept, testid, insieme) {
  return `
    <div class="campi">
      <label class="campo"><span class="etichetta">${etichetta}</span>
        <input type="file" accept="${accept}" capture="environment" data-file="${tipo}" data-testid="${testid}">
      </label>
      ${insieme ? `<label class="giro"><input type="checkbox" data-testid="vista-insieme"> Vista d'insieme</label>` : ""}
    </div>`;
}

function bloccoVideo() {
  const ferma = state.registrando && state.registrando._tipo === "video";
  return `
    <div class="campi">
      <video class="anteprima" data-testid="anteprima" autoplay muted playsinline hidden></video>
      <label class="campo"><span class="etichetta">Video</span>
        <input type="file" accept="video/*" capture="environment" data-file="V" data-testid="video">
      </label>
      <p class="azioni">
        ${ferma
          ? `<button type="button" class="bottone" data-action="stop-registra">Stop</button>`
          : `<button type="button" class="secondario" data-action="registra-video" data-testid="registra-video">Registra video</button>`}
      </p>
    </div>`;
}

function bloccoAudio(attributi) {
  const ferma = state.registrando && state.registrando._tipo === "audio";
  return `
    <div class="campi">
      <label class="campo"><span class="etichetta">Audio</span>
        <input type="file" accept="audio/*" data-file="A" data-testid="audio" ${attributi}>
      </label>
      <p class="azioni">
        ${ferma
          ? `<button type="button" class="bottone" data-action="stop-registra">Stop</button>`
          : `<button type="button" class="secondario" data-action="registra-audio" data-testid="registra-audio" ${attributi}>Registra audio</button>`}
      </p>
    </div>`;
}

function bloccoDocumento(voce) {
  return `
    ${bloccoFile("D", "Documento o foto del documento", "image/*,.pdf,application/pdf", "documento", false)}
    <label class="campo"><span class="etichetta">Chi lo manda, se manca</span>
      <input data-testid="chi-invia" value="${esc(voce.chi_invia || "")}">
    </label>
    <label class="campo"><span class="etichetta">Entro il</span>
      <input type="date" data-testid="entro-il" value="${esc(voce.entro_il || "")}">
    </label>`;
}

function renderChiusura() {
  const rilievo = state.rilievo;
  if (!rilievo) return `${barra()}<main class="pagina">${erroreHtml()}</main>`;
  const chiusura = rilievo.chiusura || {};
  const fin = rilievo.sezioni.find((sezione) => sezione.tipo === "chiusura");
  const blocchi = (fin ? fin.voci : []).map((voce) => bloccoControllo(voce, chiusura)).join("");
  return `
    ${barra()}
    <main class="pagina" data-testid="chiusura">
      ${erroreHtml()}
      <p><a href="#/rilievo/${rilievo.id}" data-testid="indietro">← Sopralluogo</a></p>
      <h2>Prima di andare via</h2>
      <p class="muto">I capitoli sono le sette sezioni del sopralluogo. Puoi chiudere anche con voci aperte: restano nel riepilogo.</p>
      ${blocchi || controlliGenerici(chiusura)}
      ${piede()}
    </main>`;
}

function bloccoControllo(voce, chiusura) {
  if (voce.chiave === "controllo_foto_misure") {
    const foto = chiusura.senza_foto_insieme || [];
    const misure = chiusura.senza_misure || [];
    const ok = foto.length === 0 && misure.length === 0;
    return `
      <article class="flag ${ok ? "ok" : "no"}">
        <p><strong>${esc(voce.testo)}</strong></p>
        <p>${foto.length ? `Senza foto d'insieme: ${esc(foto.map((s) => s.titolo).join(", "))}` : "Ogni capitolo ha una foto d'insieme."}</p>
        <p>${misure.length ? `Misure aperte: ${esc(misure.map((s) => s.titolo).join(", "))}` : "Le misure previste ci sono."}</p>
      </article>`;
  }
  if (voce.chiave === "controllo_temperature") {
    const ok = chiusura.temperature_complete;
    return `
      <article class="flag ${ok ? "ok" : "no"}" data-testid="flag-temperature">
        <p><strong>${esc(voce.testo)}</strong></p>
        <p>${ok ? "Temperature di mandata e ritorno registrate." : "Mancano le temperature di mandata e ritorno con ora e temperatura esterna."}</p>
      </article>`;
  }
  if (voce.chiave === "controllo_posizione") {
    const ok = chiusura.posizione_fotografata;
    return `
      <article class="flag ${ok ? "ok" : "no"}">
        <p><strong>${esc(voce.testo)}</strong></p>
        <p>${ok ? "C'è almeno una foto delle posizioni." : "Manca una foto delle posizioni candidate."}</p>
      </article>`;
  }
  if (voce.chiave === "controllo_documenti") {
    const documenti = chiusura.documenti_mancanti || [];
    const righe = documenti.length
      ? documenti.map((doc) => `
        <div class="riga-misura" data-documento="${doc.voce_id}">
          <p>${esc(doc.testo)} <span class="tag">${esc(doc.capitolo_etichetta)}</span></p>
          <label class="campo"><span class="etichetta">Chi lo manda</span>
            <input data-testid="chi-invia" value="${esc(doc.chi_invia || "")}" ${scrive() ? "" : "disabled"}>
          </label>
          <label class="campo"><span class="etichetta">Entro il</span>
            <input type="date" data-testid="entro-il" value="${esc(doc.entro_il || "")}" ${scrive() ? "" : "disabled"}>
          </label>
        </div>`).join("")
      : `<p>Nessun documento in sospeso.</p>`;
    return `<article class="flag ${documenti.length ? "no" : "ok"}"><p><strong>${esc(voce.testo)}</strong></p>${righe}</article>`;
  }
  if (voce.chiave === "controllo_tecnico") {
    return `
      <article class="flag">
        <p><strong>${esc(voce.testo)}</strong></p>
        <label class="campo"><span class="etichetta">Tecnico</span>
          <input data-testid="tecnico" value="${esc(state.rilievo.tecnico_nome || state.user.nome)}" ${scrive() ? "" : "disabled"}>
        </label>
        <label class="campo"><span class="etichetta">Data e ora</span>
          <input type="datetime-local" data-testid="data-ora" value="${esc(adessoLocale())}">
        </label>
      </article>`;
  }
  if (voce.chiave === "controllo_firma") {
    return `
      <article class="flag">
        <p><strong>${esc(voce.testo)}</strong></p>
        ${state.rilievo.firma ? `<p class="muto">Firma già salvata. Un nuovo tratto la sostituisce.</p>` : ""}
        <canvas class="firma" data-testid="firma"></canvas>
        <p class="azioni">
          <button type="button" class="secondario" data-action="cancella-firma">Cancella</button>
          ${scrive() ? `<button type="button" class="secondario" data-action="salva-chiusura" data-testid="salva-chiusura">Salva</button>` : ""}
          ${scrive() ? `<button type="button" class="bottone" data-action="chiudi" data-testid="chiudi-sopralluogo">Chiudi sopralluogo</button>` : ""}
        </p>
      </article>`;
  }
  return `<article class="flag"><p>${esc(voce.testo)}</p></article>`;
}

function controlliGenerici(chiusura) {
  return `<p data-testid="flag-temperature">${chiusura.temperature_complete ? "Temperature registrate." : "Mancano le temperature di mandata e ritorno con ora e temperatura esterna."}</p>`;
}

function prossimoNome(sezione) {
  const prefisso = sezione.prefisso || sezione.codice;
  let quanti = 0;
  for (const altra of state.rilievo.sezioni) {
    if ((altra.prefisso || altra.codice) !== prefisso) continue;
    for (const voce of altra.voci) quanti += voce.file.length;
  }
  return `${prefisso}-${String(quanti + 1).padStart(2, "0")}`;
}

function isoInLocale(iso) {
  if (!iso) return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${data.getFullYear()}-${p(data.getMonth() + 1)}-${p(data.getDate())}T${p(data.getHours())}:${p(data.getMinutes())}`;
}

function adessoLocale() {
  return isoInLocale(new Date().toISOString());
}

function leggiMisureDalDom() {
  return [...document.querySelectorAll("[data-misura]")].map((row) => ({
    etichetta: row.querySelector("[data-campo=etichetta]")?.value || "",
    valore: row.querySelector("[data-campo=valore]")?.value || "",
    unita: row.querySelector("[data-campo=unita]")?.value || "",
    rilevata_il: row.querySelector("[data-campo=ora]")?.value || "",
    temperatura_esterna: row.querySelector("[data-campo=esterna]")?.value || "",
  }));
}

function leggiScheda(stato) {
  const trovata = voceAperta();
  const body = {};
  if (stato) body.stato = stato;
  const testo = document.querySelector("[data-testid=testo-voce]");
  if (testo) body.testo = testo.value;
  const chi = document.querySelector("[data-testid=chi-invia]");
  if (chi && state.route.name === "voce") body.chi_invia = chi.value;
  const entro = document.querySelector("[data-testid=entro-il]");
  if (entro && state.route.name === "voce") body.entro_il = entro.value || null;
  if (trovata && trovata.voce.evidenze.includes("M")) {
    body.misure = leggiMisureDalDom().map((misura) => ({
      etichetta: misura.etichetta === "Altro" ? "" : misura.etichetta,
      valore: misura.valore,
      unita: misura.unita,
      rilevata_il: misura.rilevata_il ? new Date(misura.rilevata_il).toISOString() : null,
      temperatura_esterna: misura.temperatura_esterna || null,
    }));
  }
  return body;
}

async function salvaVoce(stato) {
  const trovata = voceAperta();
  if (!trovata) return;
  state.bozzaMisure = null;
  await inviaJson("PUT", `/api/sopralluogo/rilievi/${state.rilievo.id}/voci/${trovata.voce.id}`, leggiScheda(stato));
}

async function inviaJson(method, path, body, opzioni = {}) {
  const ridisegna = opzioni.ridisegna !== false;
  if (!navigator.onLine) {
    await state.coda.accoda({ id: crypto.randomUUID(), kind: "json", payload: { method, path, body } });
    state.errore = "Salvato sul telefono. Parte quando torna la rete.";
    state.sync = await state.coda.riepilogo();
    if (ridisegna) await disegna();
    return null;
  }
  try {
    const data = await api(method, path, body);
    if (data && data.sezioni) {
      state.rilievo = data;
      if (state.kv) await state.kv.set("rilievo:" + data.id, data);
    }
    state.errore = "";
    if (ridisegna) await disegna();
    return data;
  } catch (err) {
    if (!err.rete) throw err;
    await state.coda.accoda({ id: crypto.randomUUID(), kind: "json", payload: { method, path, body } });
    state.errore = "Connessione assente. La modifica è in coda.";
    state.sync = await state.coda.riepilogo();
    if (ridisegna) await disegna();
    return null;
  }
}

async function onFile(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const tipo = input.dataset.file;
  const trovata = voceAperta();
  if (!trovata) return;
  const consenso = document.querySelector("[data-testid=consenso]");
  if (tipo === "A" && trovata.voce.consenso_richiesto && !(consenso && consenso.checked)) {
    input.value = "";
    mostraErrore(new Error("Per questa intervista serve il consenso di chi parla."));
    return;
  }
  const meta = {
    rilievoId: state.rilievo.id,
    voceId: trovata.voce.id,
    tipo,
    vista: Boolean(document.querySelector("[data-testid=vista-insieme]")?.checked),
    consenso: Boolean(consenso && consenso.checked),
    consensoNome: document.querySelector("[data-testid=consenso-nome]")?.value || "",
  };
  input.value = "";
  try {
    await inviaFile(file, meta);
    state.errore = "";
    await disegna();
  } catch (err) {
    mostraErrore(err);
  }
}

async function inviaFile(file, meta) {
  const grande = file.size > SOGLIA_PEZZI || meta.tipo === "V";
  if (!navigator.onLine) {
    await accodaFile(file, meta, null);
    return;
  }
  try {
    if (grande) await inviaGrande(file, meta, null);
    else await inviaDiretto(file, meta);
  } catch (err) {
    if (err.rete || err.checkpoint) {
      await accodaFile(file, meta, err.checkpoint || null);
      state.errore = "File in coda. Riprende da solo appena c'è rete.";
      return;
    }
    throw err;
  }
}

async function inviaDiretto(file, meta) {
  const gps = await chiediGps();
  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("voce_id", String(meta.voceId));
  fd.append("tipo", meta.tipo);
  fd.append("vista_insieme", meta.vista ? "true" : "false");
  fd.append("consenso", meta.consenso ? "true" : "false");
  fd.append("consenso_nome", meta.consensoNome || "");
  if (gps) {
    fd.append("gps_lat", String(gps.lat));
    fd.append("gps_lon", String(gps.lon));
    fd.append("gps_accuracy", String(gps.accuracy ?? ""));
  }
  let response;
  try {
    response = await fetch(`/api/sopralluogo/rilievi/${meta.rilievoId}/file`, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
    });
  } catch {
    const errore = new Error("Connessione assente.");
    errore.rete = true;
    throw errore;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(messaggio(data, "Caricamento non riuscito."));
  state.rilievo = data;
  if (state.kv) await state.kv.set("rilievo:" + data.id, data);
}

async function inviaGrande(file, meta, checkpoint) {
  await inviaAPezzi({
    blob: file,
    checkpoint,
    creaSessione: () => creaSessione(file, meta),
    inviaParte: (id, indice, slice) => putParte(meta.rilievoId, id, indice, slice),
    completa: async (id) => {
      const data = await api("POST", `/api/sopralluogo/rilievi/${meta.rilievoId}/upload/${id}/completa`);
      state.rilievo = data;
      if (state.kv) await state.kv.set("rilievo:" + data.id, data);
    },
  });
}

async function creaSessione(file, meta) {
  const gps = await chiediGps();
  const data = await api("POST", `/api/sopralluogo/rilievi/${meta.rilievoId}/upload`, {
    voce_id: meta.voceId,
    tipo: meta.tipo,
    nome_originale: file.name || "ripresa",
    content_type: file.type || "application/octet-stream",
    total_size: file.size,
    vista_insieme: meta.vista,
    consenso: meta.consenso,
    consenso_nome: meta.consensoNome || null,
    gps_lat: gps ? gps.lat : null,
    gps_lon: gps ? gps.lon : null,
    gps_accuracy: gps ? gps.accuracy : null,
  });
  return { upload_id: data.id, chunk_size: data.chunk_size };
}

async function putParte(rilievoId, uploadId, indice, slice) {
  let response;
  try {
    response = await fetch(`/api/sopralluogo/rilievi/${rilievoId}/upload/${uploadId}/parti/${indice}`, {
      method: "PUT",
      body: slice,
      credentials: "same-origin",
    });
  } catch {
    const errore = new Error("Connessione assente.");
    errore.rete = true;
    throw errore;
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const errore = new Error(messaggio(data, "Parte non accettata."));
    if (response.status >= 400 && response.status < 500 && response.status !== 408) errore.definitivo = true;
    throw errore;
  }
}

async function accodaFile(file, meta, checkpoint) {
  const blobId = crypto.randomUUID();
  await state.kv.set("blob:" + blobId, file);
  await state.coda.accoda({
    id: blobId,
    kind: "media",
    checkpoint,
    payload: { ...meta, blobId, nome: file.name, contentType: file.type, size: file.size },
  });
  state.sync = await state.coda.riepilogo();
}

async function inviaVoceCoda(voce) {
  if (voce.kind === "json") {
    const response = await fetch(voce.payload.path, {
      method: voce.payload.method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(voce.payload.body),
      credentials: "same-origin",
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const errore = new Error(messaggio(data));
      if (response.status >= 400 && response.status < 500) errore.definitivo = true;
      throw errore;
    }
    return;
  }
  const blob = await state.kv.get("blob:" + voce.payload.blobId);
  if (!blob) {
    const errore = new Error("File locale assente.");
    errore.definitivo = true;
    throw errore;
  }
  const file = blob instanceof File ? blob : new File([blob], voce.payload.nome || "file", { type: voce.payload.contentType || blob.type });
  await inviaGrande(file, voce.payload, voce.checkpoint);
  await state.kv.delete("blob:" + voce.payload.blobId);
}

async function sincronizza() {
  state.online = navigator.onLine;
  if (!state.coda || !state.online) {
    state.sync = state.coda ? await state.coda.riepilogo() : state.sync;
    const el = document.querySelector("[data-testid=stato-sync]");
    if (el) el.textContent = testoSync();
    return;
  }
  const prima = state.sync.inviate || 0;
  state.sync = await state.coda.sincronizza();
  const el = document.querySelector("[data-testid=stato-sync]");
  if (el) el.textContent = testoSync();
  if ((state.sync.inviate || 0) > prima && state.route.id) await caricaRilievo(state.route.id);
  if ((state.sync.inviate || 0) > prima) await disegna();
}

function chiediGps() {
  return Promise.race([
    new Promise((resolve) => {
      if (!navigator.geolocation) {
        resolve(null);
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
        () => resolve(null),
        { maximumAge: 60000, timeout: 2000 }
      );
    }),
    new Promise((resolve) => setTimeout(() => resolve(null), 800)),
  ]);
}

function scegliMime(candidati) {
  if (typeof MediaRecorder === "undefined" || !MediaRecorder.isTypeSupported) return "";
  return candidati.find((tipo) => MediaRecorder.isTypeSupported(tipo)) || "";
}

async function registra(tipo) {
  const trovata = voceAperta();
  if (!trovata) return;
  const consenso = document.querySelector("[data-testid=consenso]");
  if (tipo === "audio" && trovata.voce.consenso_richiesto && !(consenso && consenso.checked)) {
    mostraErrore(new Error("Per questa intervista serve il consenso di chi parla."));
    return;
  }
  if (!navigator.mediaDevices || typeof MediaRecorder === "undefined") {
    mostraErrore(new Error("Registrazione non disponibile. Carica un file."));
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: tipo === "video" });
  } catch {
    mostraErrore(new Error("Microfono o camera non disponibili. Carica un file."));
    return;
  }
  const mime = tipo === "video"
    ? scegliMime(["video/webm;codecs=vp9,opus", "video/webm", "video/mp4"])
    : scegliMime(["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]);
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  rec._tipo = tipo;
  const pezzi = [];
  const consensoAcceso = Boolean(consenso && consenso.checked);
  const consensoNome = document.querySelector("[data-testid=consenso-nome]")?.value || "";
  const meta = {
    rilievoId: state.rilievo.id,
    voceId: trovata.voce.id,
    tipo: tipo === "video" ? "V" : "A",
    vista: false,
    consenso: consensoAcceso,
    consensoNome,
  };
  rec.ondataavailable = (evento) => {
    if (evento.data && evento.data.size) pezzi.push(evento.data);
  };
  rec.onstop = () => {
    stream.getTracks().forEach((traccia) => traccia.stop());
    state.stream = null;
    state.registrando = null;
    const tipoMime = rec.mimeType || (tipo === "video" ? "video/webm" : "audio/webm");
    const est = tipoMime.includes("mp4") ? (tipo === "video" ? "mp4" : "m4a") : "webm";
    const blob = new Blob(pezzi, { type: tipoMime });
    const file = new File([blob], `${tipo}.${est}`, { type: tipoMime });
    inviaFile(file, meta).then(() => disegna()).catch(mostraErrore);
  };
  state.stream = stream;
  state.registrando = rec;
  rec.start();
  await disegna();
}

async function salvaChiusura(chiudi) {
  const rilievoId = state.rilievo.id;
  const documenti = [...document.querySelectorAll("[data-documento]")].map((riga) => ({
    id: riga.dataset.documento,
    chi_invia: riga.querySelector("[data-testid=chi-invia]")?.value || "",
    entro_il: riga.querySelector("[data-testid=entro-il]")?.value || null,
  }));
  const canvas = document.querySelector("[data-testid=firma]");
  const firma = canvas && canvas.dataset.segnata === "1" ? canvas.toDataURL("image/png") : null;
  const body = {
    tecnico_nome: document.querySelector("[data-testid=tecnico]")?.value || "",
    firmato_il: document.querySelector("[data-testid=data-ora]")?.value
      ? new Date(document.querySelector("[data-testid=data-ora]").value).toISOString()
      : null,
    chiudi,
  };
  if (firma) body.firma_png = firma;
  for (const documento of documenti) {
    await inviaJson("PUT", `/api/sopralluogo/rilievi/${rilievoId}/voci/${documento.id}`, {
      chi_invia: documento.chi_invia,
      entro_il: documento.entro_il,
    }, { ridisegna: false });
  }
  await inviaJson("PUT", `/api/sopralluogo/rilievi/${rilievoId}/chiusura`, body);
}

function dopoRender() {
  const video = document.querySelector("[data-testid=anteprima]");
  if (video && state.stream) {
    video.hidden = false;
    video.srcObject = state.stream;
  }
  const canvas = document.querySelector("[data-testid=firma]");
  if (!canvas || canvas.dataset.pronto) return;
  canvas.dataset.pronto = "1";
  const scala = Math.min(window.devicePixelRatio || 1, 2);
  const larghezza = canvas.clientWidth || 300;
  canvas.width = Math.floor(larghezza * scala);
  canvas.height = Math.floor(160 * scala);
  const ctx = canvas.getContext("2d");
  ctx.scale(scala, scala);
  ctx.strokeStyle = "#374350";
  ctx.lineWidth = 2.2;
  ctx.lineCap = "round";
  let attivo = false;
  const punto = (evento) => {
    const rect = canvas.getBoundingClientRect();
    return { x: evento.clientX - rect.left, y: evento.clientY - rect.top };
  };
  canvas.addEventListener("pointerdown", (evento) => {
    attivo = true;
    canvas.setPointerCapture(evento.pointerId);
    const p = punto(evento);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  });
  canvas.addEventListener("pointermove", (evento) => {
    if (!attivo) return;
    const p = punto(evento);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    canvas.dataset.segnata = "1";
  });
  const fine = () => { attivo = false; };
  canvas.addEventListener("pointerup", fine);
  canvas.addEventListener("pointercancel", fine);
}

function precompilaModello() {
  const codice = document.getElementById("modello")?.value;
  const modello = state.modelli.find((riga) => riga.codice === codice);
  if (!modello) return;
  const sito = document.getElementById("sito");
  const titolo = document.getElementById("titolo");
  const opp = document.getElementById("opportunita");
  if (sito) sito.value = modello.sito || "";
  if (titolo) titolo.value = modello.titolo || "";
  if (opp) opp.value = modello.odoo_opportunity_id || "";
}

document.addEventListener("click", async (evento) => {
  const bottone = evento.target.closest("[data-action]");
  if (!bottone) return;
  if (bottone.dataset.action === "strumento") return;
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
    } else if (azione === "sezione") {
      const codice = bottone.dataset.codice;
      state.sezioneAperta = state.sezioneAperta === codice ? null : codice;
      await disegna();
    } else if (azione === "salva-voce") {
      await salvaVoce();
    } else if (azione === "stato") {
      await salvaVoce(bottone.dataset.stato);
    } else if (azione === "aggiungi-misura") {
      const trovata = voceAperta();
      const righe = leggiMisureDalDom();
      righe.push(misuraVuota(trovata.voce));
      state.bozzaMisure = righe;
      await disegna();
    } else if (azione === "registra-audio") {
      await registra("audio");
    } else if (azione === "registra-video") {
      await registra("video");
    } else if (azione === "stop-registra") {
      if (state.registrando && state.registrando.state === "recording") state.registrando.stop();
    } else if (azione === "sincronizza") {
      await sincronizza();
    } else if (azione === "salva-chiusura") {
      await salvaChiusura(false);
    } else if (azione === "chiudi") {
      await salvaChiusura(true);
    } else if (azione === "cancella-firma") {
      const canvas = document.querySelector("[data-testid=firma]");
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      delete canvas.dataset.segnata;
    }
  } catch (err) {
    mostraErrore(err);
  }
});

document.addEventListener("change", async (evento) => {
  const el = evento.target;
  if (el.matches && el.matches("[data-testid=consenso]")) {
    const accesa = el.checked;
    document.querySelectorAll("[data-richiede-consenso]").forEach((nodo) => {
      nodo.disabled = !accesa;
    });
  }
  if (el.id === "modello") precompilaModello();
  if (el.dataset.file) {
    try {
      await onFile(el);
    } catch (err) {
      mostraErrore(err);
    }
  }
  if (el.dataset.action === "strumento") {
    try {
      await inviaJson("PUT", `/api/sopralluogo/rilievi/${state.rilievo.id}/voci/${el.dataset.id}`, {
        stato: el.checked ? "fatto" : "aperto",
      });
    } catch (err) {
      mostraErrore(err);
    }
  }
});

document.addEventListener("submit", async (evento) => {
  if (evento.target.id === "login-form") {
    evento.preventDefault();
    const dati = new FormData(evento.target);
    try {
      state.user = await api("POST", "/api/auth/login", {
        email: dati.get("email"),
        password: dati.get("password"),
      });
      state.errore = "";
      location.hash = "#/";
    } catch (err) {
      state.errore = err.message;
      renderErroreLogin();
    }
  }
  if (evento.target.id === "form-nuovo") {
    evento.preventDefault();
    const dati = new FormData(evento.target);
    const opp = String(dati.get("opportunita") || "").trim();
    try {
      const rilievo = await api("POST", "/api/sopralluogo/rilievi", {
        modello: dati.get("modello"),
        sito: dati.get("sito"),
        titolo: dati.get("titolo") || null,
        odoo_opportunity_id: opp ? Number(opp) : null,
      });
      state.errore = "";
      location.hash = `#/rilievo/${rilievo.id}`;
    } catch (err) {
      mostraErrore(err);
    }
  }
});

function renderErroreLogin() {
  document.getElementById("app").innerHTML = renderLogin();
}

window.addEventListener("hashchange", () => {
  route().catch(mostraErrore);
});

window.addEventListener("online", () => {
  state.online = true;
  sincronizza().catch(mostraErrore);
});

window.addEventListener("offline", () => {
  state.online = false;
  const el = document.querySelector("[data-testid=stato-sync]");
  if (el) el.textContent = testoSync();
});

async function creaStore() {
  try {
    const db = await new Promise((resolve, reject) => {
      const richiesta = indexedDB.open("mosaika-sopralluogo", 1);
      richiesta.onupgradeneeded = () => {
        if (!richiesta.result.objectStoreNames.contains("kv")) {
          richiesta.result.createObjectStore("kv");
        }
      };
      richiesta.onsuccess = () => resolve(richiesta.result);
      richiesta.onerror = () => reject(richiesta.error);
    });
    return negozio(db);
  } catch {
    const mappa = new Map();
    return {
      async get(k) { return mappa.has(k) ? mappa.get(k) : null; },
      async set(k, v) { mappa.set(k, v); },
      async delete(k) { mappa.delete(k); },
    };
  }
}

function negozio(db) {
  return {
    get(key) {
      return new Promise((resolve, reject) => {
        const tx = db.transaction("kv", "readonly");
        const richiesta = tx.objectStore("kv").get(key);
        richiesta.onsuccess = () => resolve(richiesta.result === undefined ? null : richiesta.result);
        richiesta.onerror = () => reject(richiesta.error);
      });
    },
    set(key, value) {
      return new Promise((resolve, reject) => {
        const tx = db.transaction("kv", "readwrite");
        tx.objectStore("kv").put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    },
    delete(key) {
      return new Promise((resolve, reject) => {
        const tx = db.transaction("kv", "readwrite");
        tx.objectStore("kv").delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    },
  };
}

async function boot() {
  state.kv = await creaStore();
  state.coda = creaCoda(state.kv, (voce) => inviaVoceCoda(voce));
  try {
    state.user = await api("GET", "/api/auth/me");
  } catch {
    state.user = null;
  }
  if (!location.hash) location.hash = state.user ? "#/" : "#/login";
  await route();
  if ("serviceWorker" in navigator && !navigator.webdriver) {
    navigator.serviceWorker.register("/sopralluogo/sw.js", { scope: "/sopralluogo/" }).catch(() => {});
  }
}

boot().catch(mostraErrore);
