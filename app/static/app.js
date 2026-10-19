const $=id=>document.getElementById(id);
const number=new Intl.NumberFormat('es-CL'),percent=v=>new Intl.NumberFormat('es-CL',{style:'percent',maximumFractionDigits:1}).format(v),decimal=v=>v.toLocaleString('es-CL',{minimumFractionDigits:3,maximumFractionDigits:3});
const fold=v=>v.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
const algorithmNames={RandomForestClassifier:'Random Forest',DecisionTreeClassifier:'Decision Tree',LogisticRegression:'Logistic Regression',GradientBoostingClassifier:'Gradient Boosting'};
const names={arbol_d3:'Decision Tree · 6 entradas · profundidad 3',bosque_d5:'Random Forest · 6 entradas', 'logistica_c0.1':'Logistic Regression · 6 entradas · C 0,1',logistica_c1:'Logistic Regression · 6 entradas · C 1',logistica_c10:'Logistic Regression · 6 entradas · C 10',arbol_tendencia:'Decision Tree · 4 entradas',logistica_tendencia:'Logistic Regression · 4 entradas',bosque_sin_historia:'Random Forest · sin crecimiento previo',bosque_tendencia:'Random Forest · con crecimiento previo',arbol_d2:'Decision Tree · 6 entradas · profundidad 2',mayoria:'Clase mayoritaria',persistencia:'Continuidad anterior',modelo:'Random Forest v2',v1:'Random Forest v1'};
let model,selection=null,options=[],active=-1,current=null,requestId=0;
const mode=()=>document.querySelector('input[name=mode]:checked').value;
const label=v=>v?'Crecimiento de al menos 1% anual':'Crecimiento menor que 1% anual';
function closePicker(){$('popup').hidden=true;$('commune-search').setAttribute('aria-expanded','false');$('commune-search').removeAttribute('aria-activedescendant');active=-1;}
function drawPicker(){
 const tokens=fold($('commune-search').value).split(/\s+/).filter(Boolean),region=Number($('region').value);
 options=model.communes.filter(r=>(!region||r.region_code===region)&&tokens.every(t=>fold(r.name+' '+r.region).includes(t))).sort((a,b)=>a.name.localeCompare(b.name,'es'));
 $('commune-options').replaceChildren();active=-1;$('match-count').textContent=options.length?(options.length===1?'1 comuna disponible':options.length+' comunas disponibles'):'No hay coincidencias. Prueba otro nombre.';
 options.forEach(r=>{const li=document.createElement('li');li.id='option-'+r.code;li.role='option';li.setAttribute('aria-selected',String(selection?.code===r.code));li.append(document.createTextNode(r.name));const sub=document.createElement('small');sub.textContent=r.region+(r.recovered?' · Recuperada en v2':'');li.append(sub);li.addEventListener('mousedown',e=>e.preventDefault());li.addEventListener('click',()=>choose(r));$('commune-options').append(li);});
 $('popup').hidden=false;$('commune-search').setAttribute('aria-expanded','true');$('commune-search').removeAttribute('aria-activedescendant');
}
function clearResult(){requestId++;current=null;$('result').hidden=true;$('observed').hidden=true;$('message').textContent=selection?selection.name+' elegida. Genera su predicción.':'Elige una comuna para empezar.';$('output-period').textContent=mode()==='estudio'?'COMPARACIÓN HISTÓRICA · 2017 → 2024':'ESCENARIO FUTURO · 2024 → 2031';$('output-title').textContent=mode()==='estudio'?'La predicción frente a lo observado':'Un escenario futuro por verificar';}
function choose(r){selection=r;$('commune-search').value=r.name;$('chosen').textContent=r.name+' · '+r.region;$('predict').disabled=false;closePicker();clearResult();}
async function predict(){
 if(!selection)return;const id=++requestId;$('predict').disabled=true;$('message').textContent='Consultando predicción…';
 try{const response=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({commune:selection.code,mode:mode()})});const data=await response.json();if(!response.ok)throw Error(data.error);if(id!==requestId)return;current=data;renderResult();}
 catch(error){if(id===requestId)$('message').textContent=error.message;}finally{if(id===requestId)$('predict').disabled=!selection;}
}
function renderResult(){
 const r=current.result;$('message').textContent=current.name+' · '+current.region+(current.recovered?' · Comuna recuperada':'');$('result').hidden=false;$('inputs-title').textContent='Lo que el modelo conoce al inicio de '+current.period[0];
 $('inputs').replaceChildren();[[number.format(r.population),'Residentes identificados al inicio'],[percent(r.young_share),'Menores de 15 años'],[percent(r.old_share),'65 años o más'],[percent(r.previous_rate),'Crecimiento previo · '+r.previous_year+'–'+current.period[0]]].forEach(([v,text])=>{const d=document.createElement('div'),b=document.createElement('strong'),s=document.createElement('span');b.textContent=v;s.textContent=text;d.append(b,s);$('inputs').append(d);});
 $('model-title').textContent='PREDICCIÓN · '+names[current.model].toUpperCase();
 $('prediction-class').textContent=label(r.predicted_class);$('prediction-description').textContent=r.predicted_class?'El clasificador sitúa la comuna en el grupo de crecimiento alto.':'Esta clase incluye crecimiento lento, estabilidad y disminución de población.';
 $('baseline-class').textContent=label(r.baseline_class);const agree=r.baseline_class===r.predicted_class;$('comparison').classList.toggle('disagree',!agree);$('agreement-note').textContent=agree?'Los dos enfoques coinciden. Esa coincidencia no garantiza el resultado.':'Los dos enfoques difieren. Conviene revisar ambas estimaciones y el contexto antes de usar la clasificación.';
 $('reveal').hidden=current.mode!=='estudio';$('observed').hidden=true;$('future-note').hidden=current.mode!=='futuro';
 $('training-note').textContent=current.mode==='estudio'?'Modelo histórico: 314 ejemplos, respuestas conocidas hasta 2017. Reevaluación de 2024 exploratoria.':'Modelo futuro: 630 ejemplos, respuestas conocidas hasta 2024. Su rendimiento en 2031 todavía no se conoce.';
 $('score').textContent='Puntaje interno de «al menos 1% anual»: '+decimal(r.score)+'. No es una probabilidad calibrada ni mide la certeza de esta predicción.';
 $('geography-note').textContent=current.geography_note;
}
function reveal(){if(!current||current.mode!=='estudio')return;const r=current.result,box=$('observed');box.replaceChildren();box.classList.toggle('wrong',!r.correct);const h=document.createElement('h3');h.textContent=r.correct?'El modelo coincidió con lo observado':'El modelo se equivocó';const p=document.createElement('p');p.textContent='La población residente identificada pasó de '+number.format(r.population)+' a '+number.format(r.actual_population)+'. La tasa anual observada fue '+percent(r.actual_rate)+': '+label(r.actual_class).toLowerCase()+'.';const b=document.createElement('p');b.textContent='La continuidad anterior '+(r.baseline_class===r.actual_class?'también acertó.':'se equivocó.');if(!r.correct&&r.baseline_class===r.actual_class)b.textContent='La continuidad anterior acertó en esta comuna.';box.append(h,p,b);box.hidden=false;$('reveal').hidden=true;}
function table(id,data,selected){const body=$(id);body.replaceChildren();Object.entries(data).forEach(([k,v])=>{const tr=document.createElement('tr');tr.classList.toggle('selected',k===selected);const hits=v.confusion[0][0]+v.confusion[1][1];[names[k],decimal(v.f1_macro),number.format(hits)+' / '+number.format(v.n)].forEach(t=>{const td=document.createElement('td');td.textContent=t;tr.append(td);});body.append(tr);});}
function renderTuning(){
 const t=model.tuning;if(!t)return;
 $('tuning-report').hidden=false;
 const tuned=t.test.tuneado,previous=t.test.v2,hits=v=>v.confusion[0][0]+v.confusion[1][1];
 $('tuning-conclusion').textContent='El ajuste elegido con datos anteriores obtuvo '+hits(tuned)+' aciertos, frente a '+hits(previous)+' del Random Forest v2. '+(t.improved_vs_v2?'La comparación exploratoria mejora; las consultas principales conservan v2.':'Conservamos v2 para las consultas: este intento no mejoró F1 ni aciertos.');
 const tuningNames={v2:'Random Forest v2 conservado',tuneado:(algorithmNames[t.selected_algorithm]||t.selected_algorithm)+' · tuning',solo_corte_v2:'Solo corte del Random Forest v2',persistencia:'Continuidad anterior'};
 $('tuning-table').replaceChildren();['v2','tuneado','solo_corte_v2','persistencia'].forEach(k=>{const v=t.test[k],tr=document.createElement('tr');tr.classList.toggle('selected',k==='v2');[tuningNames[k],decimal(v.f1_macro),number.format(hits(v))+' / '+number.format(v.n)].forEach(text=>{const td=document.createElement('td');td.textContent=text;tr.append(td);});$('tuning-table').append(tr);});
 $('tuning-validation').textContent='F1 conjunto de las cinco partes externas: ajuste '+decimal(t.validation.tuneado.f1_macro)+', Random Forest v2 fijo '+decimal(t.validation.v2_fijo.f1_macro)+', continuidad '+decimal(t.validation.persistencia.f1_macro)+'. Esta evaluación corresponde a comunas de 2002–2017; no acredita precisión futura.';
 const p=t.selected_parameters;$('tuning-parameters').textContent='Configuración final: '+(algorithmNames[t.selected_algorithm]||t.selected_algorithm)+', '+p.n_estimators+' árboles, profundidad máxima '+p.max_depth+', mínimo '+p.min_samples_leaf+' ejemplos por hoja, '+(p.class_weight?'con pesos de clase':'sin pesos de clase')+' y corte '+decimal(t.score_threshold)+'. El corte elegido para la comparación que conserva los parámetros de v2 fue '+decimal(t.threshold_only_v2)+'.';
}
function renderStudy(){
 const s=model.summary,n=s.comparison_n,m=s.test.modelo.confusion,old=s.test.v1.confusion;
 const hits=m[0][0]+m[1][1],oldHits=old[0][0]+old[1][1],base=s.test.persistencia.confusion,baseHits=base[0][0]+base[1][1];
 $('train-note').textContent='314 comunas; población, edades y cambio de 1992–2002 conocidos al inicio.';
 $('finding-title').textContent='De '+oldHits+' a '+hits+' aciertos sobre las mismas '+n+' comunas';
 $('finding-text').textContent='F1 macro: '+decimal(s.test.v1.f1_macro)+' → '+decimal(s.test.modelo.f1_macro)+'. La continuidad anterior conserva '+baseHits+' aciertos y F1 '+decimal(s.test.persistencia.f1_macro)+'. El modelo mejora frente a v1, pero aún no supera esa referencia.';
 $('selection-fit').textContent='Ganó '+names[s.selected]+'. Se probaron diez configuraciones de Decision Tree, Random Forest y Logistic Regression.';$('cv-value').textContent=decimal(s.validation[s.selected].selection_f1_mean);
 $('coverage-note').textContent=s.n_communes+' comunas disponibles, incluidas Temuco y Padre Las Casas. '+model.excluded.length+' continúan excluidas. Recuperación territorial preliminar.';
 $('source-check').textContent='La reconstrucción de residentes de 2017 se contrastó con una publicación independiente del INE en las 346 comunas. Las 314 de comparación y las dos recuperadas conservan sus identidades individuales.';
 table('validation-table',s.validation,s.selected);table('test-table',{v1:s.test.v1,modelo:s.test.modelo,persistencia:s.test.persistencia,mayoria:s.test.mayoria},'modelo');
 const wrap=document.createElement('div');wrap.className='matrix';['Real / predicha','Menor que 1%','Al menos 1%','Menor que 1%',String(m[0][0]),String(m[0][1]),'Al menos 1%',String(m[1][0]),String(m[1][1])].forEach((t,i)=>{const d=document.createElement('div');d.textContent=t;if([4,5,7,8].includes(i))d.className='number'+([5,7].includes(i)?' error':'');wrap.append(d);});$('confusion').replaceChildren(wrap);
 $('errors-note').textContent='Acertó en '+hits+' de '+n+' comunas. Marcó crecimiento alto en '+m[0][1]+' que no llegaron al umbral y dejó fuera '+m[1][0]+' que sí lo alcanzaron.';
 $('detection-note').textContent='De '+(m[1][0]+m[1][1])+' comunas con crecimiento alto, el Random Forest detectó '+m[1][1]+' y la continuidad '+base[1][1]+'. El Random Forest produjo '+m[0][1]+' falsas alertas, frente a '+base[0][1]+' de la continuidad. Detecta más casos, pero también obliga a revisar más alertas incorrectas.';
 $('classes-table').replaceChildren();s.labels.forEach(k=>{const v=s.test.modelo.classes[k],tr=document.createElement('tr');[k,decimal(v.precision),decimal(v.recall),decimal(v['f1-score']),number.format(v.support)].forEach(t=>{const td=document.createElement('td');td.textContent=t;tr.append(td);});$('classes-table').append(tr);});
 const p=s.paired_vs_persistence;$('paired-note').textContent='Frente a continuidad, el modelo acierta '+p.new_correct_baseline_wrong+' casos que la referencia falla y falla '+p.new_wrong_baseline_correct+' que la referencia acierta. El intervalo exploratorio de diferencia de F1 por remuestreo regional es ['+decimal(p.interval_95[0])+', '+decimal(p.interval_95[1])+']; contiene cero y no acredita una ventaja clara.';
 [...new Map(model.communes.map(r=>[r.region_code,r.region])).entries()].sort((a,b)=>a[1].localeCompare(b[1],'es')).forEach(([code,name])=>{const o=document.createElement('option');o.value=code;o.textContent=name;$('region').append(o);});
 model.excluded.sort((a,b)=>a.name.localeCompare(b.name,'es')).forEach(r=>{const li=document.createElement('li');li.textContent=r.name+': '+r.reason+'.';$('excluded-list').append(li);});
 ['region','commune-search','toggle','example-temuco','example-padre'].forEach(id=>$(id).disabled=false);
}
$('commune-search').addEventListener('input',()=>{selection=null;$('predict').disabled=true;$('chosen').textContent='Elige una opción de la lista.';clearResult();drawPicker();});
$('commune-search').addEventListener('focus',()=>{if(model&&!selection)drawPicker();});
$('toggle').addEventListener('click',()=>{if($('popup').hidden){$('commune-search').value='';drawPicker();$('commune-search').focus();}else closePicker();});
$('commune-search').addEventListener('keydown',e=>{
 if(e.key==='Escape'){closePicker();return;}
 if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();if($('popup').hidden)drawPicker();if(!options.length)return;active=active<0?(e.key==='ArrowDown'?0:options.length-1):(active+(e.key==='ArrowDown'?1:-1)+options.length)%options.length;[...$('commune-options').children].forEach((el,i)=>el.classList.toggle('active',i===active));const li=$('commune-options').children[active];$('commune-search').setAttribute('aria-activedescendant',li.id);li.scrollIntoView({block:'nearest'});}
 else if(e.key==='Enter'&&!$('popup').hidden){e.preventDefault();if(active>=0)choose(options[active]);else if(options.length===1)choose(options[0]);}
});
document.addEventListener('click',e=>{if(!$('picker').contains(e.target))closePicker();});
$('region').addEventListener('change',()=>{selection=null;$('commune-search').value='';$('predict').disabled=true;$('chosen').textContent='Elige una comuna de esta región.';clearResult();closePicker();});
document.querySelectorAll('input[name=mode]').forEach(input=>input.addEventListener('change',()=>{clearResult();$('predict').disabled=!selection;}));
$('selection-form').addEventListener('submit',e=>{e.preventDefault();predict();});$('reveal').addEventListener('click',reveal);
function example(code){$('region').value='9';choose(model.communes.find(r=>r.code===code));predict();}
$('example-temuco').addEventListener('click',()=>example(9101));$('example-padre').addEventListener('click',()=>example(9112));
try{const response=await fetch('/api/model');if(!response.ok)throw Error('No se pudo cargar el experimento.');model=await response.json();renderStudy();renderTuning();}catch(error){$('message').textContent=error.message;$('finding-text').textContent='El experimento no está disponible. Inicia el servidor local.';}
