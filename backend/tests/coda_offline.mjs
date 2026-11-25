import assert from "node:assert/strict";

import { creaCoda, inviaAPezzi } from "../../frontend/sopralluogo/js/coda.js";

function memoria() {
  const mappa = new Map();
  return {
    async get(chiave) {
      return mappa.has(chiave) ? structuredClone(mappa.get(chiave)) : null;
    },
    async set(chiave, valore) {
      mappa.set(chiave, structuredClone(valore));
    },
  };
}

async function testCodaSiFermaOfflineERiprende() {
  const store = memoria();
  let rete = false;
  const visti = [];
  const coda = creaCoda(store, async (voce) => {
    visti.push(voce.id);
    if (voce.id !== "a") return;
    if (!rete) {
      const err = new Error("offline");
      err.checkpoint = { passo: 1 };
      throw err;
    }
    assert.equal(voce.checkpoint.passo, 1);
  });
  await coda.accoda({ id: "a", kind: "json", payload: { path: "/a" } });
  await coda.accoda({ id: "b", kind: "json", payload: { path: "/b" } });
  let riepilogo = await coda.sincronizza();
  assert.deepEqual(visti, ["a"]);
  assert.equal(riepilogo.in_coda, 2);
  assert.equal((await coda.elenco()).find((voce) => voce.id === "a").checkpoint.passo, 1);
  rete = true;
  visti.length = 0;
  riepilogo = await coda.sincronizza();
  assert.deepEqual(visti, ["a", "b"]);
  assert.equal(riepilogo.inviate, 2);
  assert.equal(riepilogo.in_coda, 0);
  const prima = visti.length;
  await coda.sincronizza();
  assert.equal(visti.length, prima);
}

async function testErroreDefinitivoNonBlocca() {
  const coda = creaCoda(memoria(), async (voce) => {
    if (voce.id === "bad") {
      const err = new Error("dati");
      err.definitivo = true;
      throw err;
    }
  });
  await coda.accoda({ id: "bad", kind: "json" });
  await coda.accoda({ id: "ok", kind: "json" });
  await coda.sincronizza();
  const elenco = await coda.elenco();
  assert.equal(elenco[0].stato, "scartata");
  assert.equal(elenco[1].stato, "inviata");
}

async function testPezziRiprendonoDalCheckpoint() {
  const blob = new Blob(["abcdefghij"]);
  const sent = [];
  let create = 0;
  let failOn = 1;
  let checkpoint = null;
  try {
    await inviaAPezzi({
      blob,
      checkpoint: null,
      creaSessione: async () => {
        create += 1;
        return { upload_id: "u1", chunk_size: 4 };
      },
      inviaParte: async (_id, index, slice) => {
        if (index === failOn) throw new Error("rete");
        sent.push([index, await slice.text()]);
      },
      completa: async () => {
        throw new Error("non deve");
      },
    });
    throw new Error("doveva fallire");
  } catch (err) {
    assert.equal(err.message, "rete");
    assert.equal(err.checkpoint.prossimo, 1);
    assert.equal(err.checkpoint.upload_id, "u1");
    checkpoint = err.checkpoint;
  }
  assert.equal(create, 1);
  assert.deepEqual(sent, [[0, "abcd"]]);
  failOn = -1;
  let completata = false;
  await inviaAPezzi({
    blob,
    checkpoint,
    creaSessione: async () => {
      create += 1;
      throw new Error("sessione già aperta");
    },
    inviaParte: async (_id, index, slice) => {
      sent.push([index, await slice.text()]);
    },
    completa: async (id) => {
      assert.equal(id, "u1");
      completata = true;
    },
  });
  assert.equal(create, 1);
  assert.equal(completata, true);
  assert.deepEqual(sent, [[0, "abcd"], [1, "efgh"], [2, "ij"]]);
}

await testCodaSiFermaOfflineERiprende();
await testErroreDefinitivoNonBlocca();
await testPezziRiprendonoDalCheckpoint();
console.log("coda ok");
