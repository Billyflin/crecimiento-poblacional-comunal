// Opciones derivadas de las mismas reglas y límites que consulta la API.
export function rulesForRegion(model, region) {
  return model.rules.filter(rule => region === 0 ||
    rule.by_region[String(region)].antecedent_count >= model.region_min_antecedents);
}

export function contextKey(items) {
  return [...items].sort().join("|");
}

export function contextsFromRules(model) {
  const lookup = new Map(model.items.map(item => [item.code, item]));
  const contexts = new Map();
  for (const rule of model.rules) {
    const key = contextKey(rule.antecedent);
    if (contexts.has(key)) continue;
    contexts.set(key, {
      key,
      items: rule.antecedent,
      label: rule.antecedent.map(code => {
        const item = lookup.get(code);
        return `${item.group_label}: ${item.label}`;
      }).join(" + "),
    });
  }
  return contexts;
}

export function availableContextKeys(model, region) {
  return new Set(rulesForRegion(model, region).map(rule => contextKey(rule.antecedent)));
}

export function regionAllowsContext(model, region, key) {
  const keys = availableContextKeys(model, region);
  return key ? keys.has(key) : keys.size > 0;
}

export function filterContexts(contexts, query) {
  const normalize = text => text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("es");
  const words = normalize(query).match(/[\p{L}\p{N}]+/gu) || [];
  return contexts.filter(context => {
    const label = normalize(context.label);
    return words.every(word => label.includes(word));
  });
}
