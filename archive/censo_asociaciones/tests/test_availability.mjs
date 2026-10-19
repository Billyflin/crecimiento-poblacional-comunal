// Verifica las opciones ofrecidas contra las respuestas reales de la API.
import assert from "node:assert/strict";
import {availableContextKeys, contextKey, contextsFromRules, regionAllowsContext, filterContexts} from "../app/static/availability.mjs";

const base = process.argv[2] || "http://127.0.0.1:8787";
const response = await fetch(`${base}/api/model`);
assert.equal(response.status, 200);
const model = await response.json();
const contexts = contextsFromRules(model);
assert(!contexts.has(contextKey(["agua:1"]))); // No tiene reglas.
assert(contexts.has(contextKey(["area:1", "tipologia:5"]))); // Existe solo como pareja.
assert(!regionAllowsContext(model, 11, contextKey(["agua:3"]))); // Aysén: 61 antecedentes.
assert(regionAllowsContext(model, 0, contextKey(["agua:3"])));
assert.equal(contextKey(["area:2", "tipologia:1"]), contextKey(["tipologia:1", "area:2"]));
const choices=[...contexts.values()];
assert.deepEqual(filterContexts(choices,"RÚRAL, unipersonal").map(c=>c.key),[contextKey(["area:2","tipologia:1"])]);
assert.deepEqual(filterContexts(choices,"  unipersonal rural  "),filterContexts(choices,"rural unipersonal"));
assert.equal(filterContexts(choices,"" ).length,contexts.size);
assert.equal(filterContexts(choices,"una condición que no existe").length,0);
const aysenChoices=choices.filter(c=>availableContextKeys(model,11).has(c.key));
assert.equal(filterContexts(aysenChoices,"camión aljibe").length,0);
assert.equal(filterContexts(choices,"camion aljibe").length,1);

for (const path of ["/", "/app.js", "/availability.mjs"]) {
  const asset = await fetch(`${base}${path}`);
  assert.equal(asset.status, 200, `Archivo necesario: ${path}`);
  if (path === "/") assert((await asset.text()).includes('type="module"'));
  else assert(asset.headers.get("Content-Type").includes("javascript"));
}

let checked = 0;
for (const region of [0, ...model.regions.map(r => r.code)]) {
  const available = availableContextKeys(model, region);
  assert(available.size > 0);
  // Una opción está habilitada si, y solo si, la consulta devuelve reglas.
  for (const context of contexts.values()) {
    const result = await fetch(`${base}/api/query`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({items: context.items, region}),
    });
    assert.equal(result.status, 200);
    const query = await result.json();
    assert.equal(available.has(context.key), query.rules.length > 0, `${region}: ${context.key}`);
    assert.equal(regionAllowsContext(model, region, context.key), query.rules.length > 0);
    for (const rule of query.rules) assert.equal(contextKey(rule.antecedent), context.key);
    checked++;
  }
}
console.log(`Opciones verificadas contra la API: ${checked} consultas; ${contexts.size} combinaciones; Chile y 16 regiones.`);
