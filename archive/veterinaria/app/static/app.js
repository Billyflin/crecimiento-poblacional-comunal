"use strict";

const $ = selector => document.querySelector(selector);
const pct = value => value === null || value === undefined ? "Sin estimación" : new Intl.NumberFormat("es-CL", {style: "percent", maximumFractionDigits: 1}).format(value);
const num = value => new Intl.NumberFormat("es-CL", {maximumFractionDigits: 2}).format(value);
let model;
let requestVersion = 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function renderModel() {
  const directions = new Set(model.rules.map(rule => rule.family_direction)).size;
  for (const [value, label] of [[model.sample_count, "muestras utilizables"], [model.laboratories, "laboratorios"], [directions, "patrón entre familias"]]) {
    const stat = element("div", undefined, "stat");
    stat.append(element("strong", num(value)), element("span", label));
    $("#stats").append(stat);
  }
  const groups = new Map();
  for (const drug of model.drugs) {
    if (!groups.has(drug.class)) groups.set(drug.class, []);
    groups.get(drug.class).push(drug);
  }
  for (const [family, drugs] of groups) {
    const fieldset = element("fieldset");
    fieldset.append(element("legend", family));
    for (const drug of drugs) {
      const label = element("label", undefined, "drug-option");
      const input = element("input");
      input.type = "checkbox";
      input.name = "items";
      input.value = drug.code;
      label.append(input, element("span", drug.spanish), element("small", `R ≥ ${drug.resistant_min} µg/mL`));
      fieldset.append(label);
    }
    $("#drug-options").append(fieldset);
  }
  for (const config of model.comparison) {
    const row = element("tr");
    if (config.configuration === model.selected_configuration) row.className = "selected";
    for (const value of [config.configuration, pct(config.min_support), pct(config.min_confidence), config.candidate_rules, config.eligible_rules]) row.append(element("td", String(value)));
    $("#comparison").append(row);
  }
  $("#selection-note").textContent = model.selected_configuration ? `Se eligió la configuración ${model.selected_configuration}. Publica ${model.rules.length} reglas que representan ${directions} dirección entre familias. Los dos consecuentes de esta versión pertenecen a la misma familia y no son hallazgos independientes.` : "Ninguna configuración aporta reglas que superen los controles definidos.";
  for (const [text, url] of [["Fuente FDA Vet-LIRN ↗", model.source.url], ["Cortes históricos USDA 2020 ↗", model.threshold_reference.url]]) {
    const a = element("a", text);
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    $("#source-links").append(a);
  }
  for (const selector of ["#consult", "#example", "#reset"]) $(selector).disabled = false;
  $("#result-message").textContent = "Selecciona resultados R para consultar el modelo.";
}

function renderRule(rule) {
  const drugs = new Map(model.drugs.map(drug => [drug.code, drug]));
  const names = rule.antecedent.map(code => drugs.get(code).spanish).join(" + ");
  const consequent = drugs.get(rule.consequent).spanish;
  const metrics = rule.confirmation;
  const card = element("article", undefined, "rule-card");
  card.append(element("p", "Asociación entre familias", "rule-tag"));
  const heading = element("h3", undefined, "rule-title");
  const first = element("span");
  first.append(element("small", "Resultado seleccionado"), document.createTextNode(names));
  const second = element("span");
  second.append(element("small", "Resultado asociado"), document.createTextNode(consequent));
  heading.append(first, element("span", "→", "rule-arrow"), second);
  card.append(heading, element("p", rule.family_direction.replace(" -> ", " → "), "family-label"));
  const count = element("p", undefined, "rule-count");
  count.append(element("strong", `${metrics.joint_count} de ${metrics.antecedent_count} muestras`), document.createTextNode(` con R en ${names} también tuvieron R en ${consequent}, en 2023–2024.`));
  card.append(count);
  const metricsRow = element("div", undefined, "rule-metrics");
  for (const [value, label] of [[pct(metrics.confidence), "Confianza observada"], [pct(metrics.support), `Soporte · ${num(metrics.n)} muestras`], [`${num(metrics.lift)}×`, "Lift sobre frecuencia basal"]]) {
    const metric = element("div", undefined, "metric");
    metric.append(element("strong", value), element("span", label));
    metricsRow.append(metric);
  }
  card.append(metricsRow, element("p", `Intervalo descriptivo 95 %: ${pct(metrics.confidence_ci95_low)}–${pct(metrics.confidence_ci95_high)}. Frecuencia basal de R en ${consequent}: ${pct(metrics.baseline)}.`, "rule-interval"));
  const detail = element("details", undefined, "rule-detail");
  detail.append(element("summary", "Ver evidencia anterior y por laboratorio"));
  detail.append(element("p", `Descubrimiento 2017–2021: ${rule.discovery.joint_count}/${rule.discovery.antecedent_count}, confianza ${pct(rule.discovery.confidence)}. Selección 2022: ${rule.selection.joint_count}/${rule.selection.antecedent_count}, confianza ${pct(rule.selection.confidence)}; intervalo ${pct(rule.selection.confidence_ci95_low)}–${pct(rule.selection.confidence_ci95_high)}.`));
  detail.append(element("p", `${rule.lab_audit.labs_with_at_least_5_antecedents} laboratorios aportan al menos 5 muestras con el antecedente en descubrimiento. Al excluir cada laboratorio, el lift mínimo es ${num(rule.lab_audit.leave_one_lab_out_min_lift)}. Esta sensibilidad no es validación clínica externa.`));
  for (const [year, m] of Object.entries(rule.confirmation_by_year)) detail.append(element("p", `${year}: ${m.joint_count}/${m.antecedent_count} coincidencias; confianza ${pct(m.confidence)}.`));
  card.append(detail);
  return card;
}

async function consult() {
  const version = ++requestVersion;
  const items = [...document.querySelectorAll('input[name="items"]:checked')].map(input => input.value);
  $("#result-message").textContent = "Consultando asociaciones…";
  try {
    const response = await fetch("/api/query", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({items})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "No se pudo consultar el modelo.");
    if (version !== requestVersion) return;
    $("#rules").replaceChildren(...result.rules.map(renderRule));
    $("#result-message").textContent = result.message;
    $("#empty").hidden = result.rules.length > 0;
    $("#empty h3").textContent = items.length ? "Sin reglas para esta selección" : "Empieza con una selección";
    $("#empty p").textContent = items.length ? "El modelo solo muestra reglas que superan los controles definidos. Que no aparezcan reglas no permite concluir que una resistencia esté ausente." : "Consulta las reglas que superaron los controles temporales y de laboratorio, o prueba el ejemplo.";
  } catch (error) {
    if (version !== requestVersion) return;
    $("#rules").replaceChildren();
    $("#empty").hidden = true;
    $("#result-message").textContent = error.message;
  }
}

$("#selection-form").addEventListener("submit", event => {event.preventDefault(); consult();});
$("#selection-form").addEventListener("change", consult);
$("#example").addEventListener("click", () => {
  for (const input of document.querySelectorAll('input[name="items"]')) input.checked = input.value === "GEN";
  consult();
});
$("#reset").addEventListener("click", () => {$("#selection-form").reset(); consult();});

(async () => {
  try {
    const response = await fetch("/api/model");
    if (!response.ok) throw new Error("No se pudo cargar el modelo. Comprueba que el estudio esté ejecutado.");
    model = await response.json();
    renderModel();
  } catch (error) {
    $("#result-message").textContent = error.message;
    $("#empty").hidden = true;
  }
})();
