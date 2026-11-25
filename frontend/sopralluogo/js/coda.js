/**
 * Coda di invio, senza DOM. Funziona nel browser e nei test Node.
 * Una voce in errore ferma il giro (di solito non c'è rete).
 * Un errore definitivo si scarta e si passa alla voce successiva.
 * Il checkpoint permette di riprendere un video a pezzi.
 */

export function creaCoda(storage, invia) {
  const CHIAVE = "coda";

  async function leggi() {
    return (await storage.get(CHIAVE)) || [];
  }

  async function scrivi(voci) {
    await storage.set(CHIAVE, voci);
  }

  function riepilogo(voci) {
    const conta = (stato) => voci.filter((voce) => voce.stato === stato).length;
    const errori = conta("errore");
    return {
      in_coda: conta("in_coda") + errori,
      in_invio: conta("in_invio"),
      inviate: conta("inviata"),
      errori,
      scartate: conta("scartata"),
    };
  }

  return {
    async accoda(voce) {
      if (!voce || !voce.id) throw new Error("Voce senza id.");
      const voci = await leggi();
      const idx = voci.findIndex((riga) => riga.id === voce.id);
      const precedente = idx >= 0 ? voci[idx] : null;
      const riga = {
        id: voce.id,
        kind: voce.kind || "json",
        payload: voce.payload || {},
        checkpoint: voce.checkpoint || (precedente && precedente.checkpoint) || null,
        tentativi: precedente ? precedente.tentativi || 0 : 0,
        stato: "in_coda",
        errore: null,
        creata: (precedente && precedente.creata) || new Date().toISOString(),
      };
      if (precedente && precedente.stato !== "inviata") voci[idx] = riga;
      else if (!precedente) voci.push(riga);
      await scrivi(voci);
      return riga;
    },
    async elenco() {
      return leggi();
    },
    async riepilogo() {
      return riepilogo(await leggi());
    },
    async sincronizza() {
      const voci = await leggi();
      for (const voce of voci) {
        if (voce.stato === "inviata" || voce.stato === "scartata") continue;
        voce.stato = "in_invio";
        voce.errore = null;
        await scrivi(voci);
        try {
          await invia(voce);
          voce.stato = "inviata";
          voce.checkpoint = null;
          voce.errore = null;
          await scrivi(voci);
        } catch (err) {
          voce.tentativi = (voce.tentativi || 0) + 1;
          voce.errore = err && err.message ? err.message : String(err);
          if (err && err.checkpoint) voce.checkpoint = err.checkpoint;
          voce.stato = err && err.definitivo ? "scartata" : "errore";
          await scrivi(voci);
          if (voce.stato === "errore") break;
        }
      }
      return riepilogo(await leggi());
    },
  };
}

export async function inviaAPezzi({ blob, checkpoint, creaSessione, inviaParte, completa }) {
  if (!blob || !blob.size) throw new Error("File vuoto.");
  let cp = checkpoint ? { ...checkpoint } : null;
  try {
    if (!cp) {
      const sessione = await creaSessione();
      const chunk = sessione.chunk_size;
      cp = {
        upload_id: sessione.upload_id || sessione.id,
        chunk_size: chunk,
        parti: Math.ceil(blob.size / chunk),
        prossimo: 0,
      };
    }
    for (let indice = cp.prossimo; indice < cp.parti; indice += 1) {
      const inizio = indice * cp.chunk_size;
      const slice = blob.slice(inizio, Math.min(blob.size, inizio + cp.chunk_size));
      await inviaParte(cp.upload_id, indice, slice);
      cp = { ...cp, prossimo: indice + 1 };
    }
    await completa(cp.upload_id);
  } catch (err) {
    const errore = err instanceof Error ? err : new Error(String(err));
    if (cp) errore.checkpoint = cp;
    throw errore;
  }
}
