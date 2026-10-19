"use strict";
import {contextKey, contextsFromRules, availableContextKeys, regionAllowsContext, filterContexts} from "/availability.mjs";
const $ = selector => document.querySelector(selector);
const pct = value => value === null || value === undefined ? "Sin estimación" : new Intl.NumberFormat("es-CL", {style:"percent",maximumFractionDigits:1}).format(value);
const num = value => value === null || value === undefined ? "Sin estimación" : new Intl.NumberFormat("es-CL", {maximumFractionDigits:2}).format(value);
let model, lookup, contexts;
let requestVersion = 0;
let matchingContexts = [], activeIndex = -1;
function element(tag,text,className) {
  const node=document.createElement(tag);
  if(text!==undefined) node.textContent=text;
  if(className) node.className=className;
  return node;
}
function selectedItems() { return contexts.get($("#context-choice").value)?.items || []; }
function conditionRows(context) {
  return context.items.map(code => {
    const item=lookup.get(code), row=element("div",undefined,"condition-row");
    row.append(element("span",item.group_label,"condition-group"),element("span",item.label,"condition-value"));
    return row;
  });
}
function renderSelection() {
  const context=contexts.get($("#context-choice").value);
  $("#context-selection").hidden=!context;
  $("#context-selection").replaceChildren(...(context ? [element("p","Contexto elegido","selection-caption"),...conditionRows(context)] : []));
  $("#context-search").placeholder=context ? "Buscar otra combinación…" : "Ej.: rural, unipersonal…";
}
function highlightOption(index) {
  activeIndex=index;
  const options=[...$("#context-options").children];
  options.forEach((option,i)=>option.classList.toggle("active",i===index));
  const active=options[index];
  if(active) {
    $("#context-search").setAttribute("aria-activedescendant",active.id);
    active.scrollIntoView({block:"nearest"});
  } else $("#context-search").removeAttribute("aria-activedescendant");
}
function refreshSuggestions() {
  const available=availableContextKeys(model,Number($("#region").value));
  const choices=[...contexts.values()].filter(context=>available.has(context.key))
    .sort((a,b)=>a.items.length-b.items.length || a.label.localeCompare(b.label,"es"));
  matchingContexts=filterContexts(choices,$("#context-search").value);
  $("#context-options").replaceChildren(...matchingContexts.map((context,index)=>{
    const option=element("li",undefined,"context-option");
    option.id=`context-option-${index}`;
    option.setAttribute("role","option");
    option.setAttribute("aria-selected",String(context.key===$("#context-choice").value));
    option.setAttribute("aria-label",context.label);
    option.append(element("span",context.items.length===1 ? "Una condición" : "Dos condiciones","option-caption"),...conditionRows(context));
    option.addEventListener("pointerdown",event=>event.preventDefault());
    option.addEventListener("click",()=>chooseContext(context.key));
    return option;
  }));
  $("#context-count").textContent=matchingContexts.length ? `${matchingContexts.length} ${matchingContexts.length===1 ? "combinación disponible" : "combinaciones disponibles"}` : "No hay coincidencias";
  $("#context-no-matches").hidden=matchingContexts.length>0;
  highlightOption(-1);
}
function openPicker() {
  if(!model) return;
  refreshSuggestions();
  $("#context-popup").hidden=false;
  $("#context-search").setAttribute("aria-expanded","true");
  $("#context-toggle").setAttribute("aria-expanded","true");
  $("#context-toggle").setAttribute("aria-label","Ocultar combinaciones");
}
function closePicker() {
  $("#context-popup").hidden=true;
  $("#context-search").setAttribute("aria-expanded","false");
  $("#context-toggle").setAttribute("aria-expanded","false");
  $("#context-toggle").setAttribute("aria-label","Mostrar combinaciones");
  highlightOption(-1);
}
function chooseContext(key) {
  if(!availableContextKeys(model,Number($("#region").value)).has(key)) return;
  $("#context-choice").value=key;
  $("#context-search").value="";
  renderSelection(); closePicker(); consult();
}
function updateAvailability() {
  const region=Number($("#region").value);
  const available=availableContextKeys(model,region);
  let key=$("#context-choice").value;
  if(key && !available.has(key)) {
    $("#context-choice").value=key="";
    renderSelection();
  }
  for(const option of $("#region").options) {
    option.disabled=!regionAllowsContext(model,Number(option.value),key);
  }
  $("#consult").disabled=!key || !available.has(key);
  refreshSuggestions();
}
function renderModel() {
  lookup=new Map(model.items.map(i=>[i.code,i]));
  for(const [value,label] of [[model.sample_count,"hogares analizados"],[model.regions.length,"regiones"],[model.rules.length,"reglas seleccionadas"]]) {
    const stat=element("div",undefined,"stat");
    stat.append(element("strong",num(value)),element("span",label)); $("#stats").append(stat);
  }
  $("#context").textContent=`De ${num(model.private_households)} hogares particulares, ${num(model.excluded_incomplete)} se excluyeron por información faltante o no válida en las siete variables del estudio. Una fila corresponde a un hogar.`;
  for(const r of model.regions) { const option=element("option",r.label); option.value=r.code; $("#region").append(option); }
  contexts=contextsFromRules(model);
  for(const config of model.comparison) {
    const row=element("tr"); if(config.name===model.selected_configuration) row.className="selected";
    for(const value of [config.name,pct(config.min_support),pct(config.min_confidence),config.candidate_rules,config.eligible_rules]) row.append(element("td",String(value)));
    $("#comparison").append(row);
  }
  $("#split-note").textContent=`Se usaron ${num(model.split_counts.discovery)} hogares para descubrir reglas, ${num(model.split_counts.selection)} para elegir la configuración y ${num(model.split_counts.test)} para la prueba interna. La división se hace por vivienda para mantener juntos a los hogares que comparten una.`;
  $("#selection-note").textContent=`Configuración elegida: ${model.selected_configuration}. Primero se comparó la cobertura de categorías de acceso digital; luego, la proporción de reglas estables y su simplicidad. La prueba no intervino en esta elección.`;
  for(const [text,url] of [["Datos oficiales INE ↗",model.source.landing_url],["Manual y diccionario ↗",model.source.files.find(f=>f.url.endsWith(".pdf")).url],["Licencia y condiciones ↗",model.source.license_url]]) {
    const a=element("a",text); a.href=url; a.target="_blank"; a.rel="noopener noreferrer"; $("#source-links").append(a);
  }
  for(const selector of ["#region","#context-search","#context-toggle","#example","#reset"]) $(selector).disabled=false;
  updateAvailability();
  $("#result-message").textContent="Elige una combinación para consultar sus asociaciones.";
}
function renderRule(rule) {
  const names=rule.antecedent.map(c=>`${lookup.get(c).group_label}: ${lookup.get(c).label}`).join(" + ");
  const consequent=lookup.get(rule.consequent).label;
  const m=rule.observed;
  const card=element("article",undefined,"rule-card"); card.append(element("p","Contexto habitacional → acceso digital","rule-tag"));
  const title=element("h3",undefined,"rule-title");
  const a=element("span"); a.append(element("small","Condiciones elegidas"),document.createTextNode(names));
  const b=element("span"); b.append(element("small","Característica asociada"),document.createTextNode(consequent));
  title.append(a,element("span","→","rule-arrow"),b); card.append(title);
  const count=element("p",undefined,"rule-count"); count.append(element("strong",`${num(m.joint_count)} de ${num(m.antecedent_count)} hogares`),document.createTextNode(` que cumplen las condiciones tienen la característica «${consequent.toLowerCase()}».`)); card.append(count);
  const metrics=element("div",undefined,"rule-metrics");
  for(const [value,label] of [[pct(m.confidence),"Confianza observada"],[pct(m.support),`Soporte · ${num(m.n)} hogares`],[m.lift===null ? "Sin estimación" : `${num(m.lift)}×`,"Lift en el territorio"]]) {
    const metric=element("div",undefined,"metric"); metric.append(element("strong",value),element("span",label)); metrics.append(metric);
  }
  card.append(metrics,element("p",`Frecuencia del resultado en el territorio: ${pct(m.baseline)}. Lift nacional: ${num(rule.national_lift)}×. Son proporciones descriptivas de casos completos del censo.`,"rule-interval"));
  if(m.lift!==null && m.lift<1) card.append(element("p","En este territorio, la característica es menos frecuente entre estos hogares que en el conjunto de hogares completos. El patrón nacional cambia al observar esta región.","rule-interval"));
  const detail=element("details",undefined,"rule-detail"); detail.append(element("summary","Ver evaluación interna nacional"));
  for(const [label,stage] of [["Descubrimiento",rule.discovery],["Selección",rule.selection],["Prueba reservada",rule.test]]) detail.append(element("p",`${label}: ${num(stage.joint_count)} de ${num(stage.antecedent_count)} hogares; confianza ${pct(stage.confidence)}, lift ${num(stage.lift)}×.`));
  detail.append(element("p","Las tres particiones pertenecen al Censo 2024. Esta evaluación no demuestra generalización a otros años.")); card.append(detail);
  return card;
}
async function consult() {
  const version=++requestVersion; updateAvailability(); const items=selectedItems(); const region=Number($("#region").value);
  if(!items.length) {
    $("#rules").replaceChildren();
    $("#result-message").textContent="Elige una combinación para consultar sus asociaciones.";
    $("#territory").textContent=`${$("#region").selectedOptions[0].textContent.replace(" · todas las regiones","")} · 2024`;
    $("#empty").hidden=false;
    return;
  }
  $("#result-message").textContent="Consultando asociaciones…";
  try {
    const response=await fetch("/api/query",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items,region})});
    const result=await response.json(); if(!response.ok) throw new Error(result.error||"No se pudo consultar el modelo."); if(version!==requestVersion) return;
    $("#rules").replaceChildren(...result.rules.map(renderRule)); $("#result-message").textContent=result.message;
    $("#territory").textContent=`${result.territory} · 2024`; $("#empty").hidden=result.rules.length>0;
    if(!result.rules.length) throw new Error("Las opciones del modelo cambiaron. Recarga la página para actualizar las combinaciones disponibles.");
  } catch(error) { if(version!==requestVersion) return; $("#rules").replaceChildren(); $("#empty").hidden=true; $("#result-message").textContent=error.message; }
}
$("#selection-form").addEventListener("submit",event=>{event.preventDefault();consult();});
$("#region").addEventListener("change",()=>{closePicker();consult();});
$("#context-search").addEventListener("focus",openPicker);
$("#context-search").addEventListener("click",()=>{if($("#context-popup").hidden) openPicker();});
$("#context-search").addEventListener("input",openPicker);
$("#context-search").addEventListener("keydown",event=>{
  if(event.key==="ArrowDown" || event.key==="ArrowUp") {
    event.preventDefault();
    if($("#context-popup").hidden) openPicker();
    if(matchingContexts.length) highlightOption((activeIndex+(event.key==="ArrowDown" ? 1 : activeIndex<0 ? 0 : -1)+matchingContexts.length)%matchingContexts.length);
  } else if(event.key==="Enter" && !$("#context-popup").hidden) {
    event.preventDefault();
    if(activeIndex>=0) chooseContext(matchingContexts[activeIndex].key);
    else if(matchingContexts.length===1) chooseContext(matchingContexts[0].key);
  } else if(event.key==="Escape") {
    event.preventDefault(); closePicker(); $("#context-search").value="";
  } else if(event.key==="Tab") closePicker();
  else if(["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) highlightOption(-1);
});
$("#context-toggle").addEventListener("pointerdown",event=>event.preventDefault());
$("#context-toggle").addEventListener("click",()=>{
  const wasOpen=!$("#context-popup").hidden;
  $("#context-search").focus();
  if(wasOpen) closePicker(); else openPicker();
});
document.addEventListener("pointerdown",event=>{if(!$("#context-picker").contains(event.target)) closePicker();});
$("#context-picker").addEventListener("focusout",event=>{if(!$("#context-picker").contains(event.relatedTarget)) closePicker();});
$("#example").addEventListener("click",()=>{
  const available=availableContextKeys(model,Number($("#region").value));
  const preferred=contextKey(model.example_items);
  chooseContext(available.has(preferred) ? preferred : [...available][0] || "");
});
$("#reset").addEventListener("click",()=>{
  $("#selection-form").reset();
  $("#context-choice").value="";
  renderSelection(); closePicker(); consult();
});
(async()=>{try{const response=await fetch("/api/model");if(!response.ok) throw new Error("No se pudo cargar el modelo censal.");model=await response.json();renderModel();}catch(error){$("#result-message").textContent=error.message;$("#empty").hidden=true;}})();
