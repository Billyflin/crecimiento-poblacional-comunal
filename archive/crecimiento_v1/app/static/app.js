const $=id=>document.getElementById(id);
const number=new Intl.NumberFormat('es-CL'),percent=v=>new Intl.NumberFormat('es-CL',{style:'percent',maximumFractionDigits:1}).format(v),decimal=v=>v.toLocaleString('es-CL',{minimumFractionDigits:3,maximumFractionDigits:3});
const fold=v=>v.normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
const names={arbol:'Árbol de decisión',bosque:'Bosque aleatorio',mayoria:'Clase mayoritaria',persistencia:'Continuar la tendencia anterior',modelo:'Modelo elegido'};
let model,selection=null,options=[],active=-1,current=null,requestId=0;
const mode=()=>document.querySelector('input[name=mode]:checked').value;
function closePicker(){$('popup').hidden=true;$('commune-search').setAttribute('aria-expanded','false');$('commune-search').removeAttribute('aria-activedescendant');active=-1;}
function drawPicker(){
 const tokens=fold($('commune-search').value).split(/\s+/).filter(Boolean),region=Number($('region').value);
 options=model.communes.filter(r=>(!region||r.region_code===region)&&tokens.every(t=>fold(r.name+' '+r.region).includes(t))).sort((a,b)=>a.name.localeCompare(b.name,'es'));
 $('commune-options').replaceChildren();active=-1;$('match-count').textContent=options.length?(options.length===1?'1 comuna disponible':options.length+' comunas disponibles'):'No hay coincidencias. Prueba otro nombre.';
 options.forEach(r=>{const li=document.createElement('li');li.id='option-'+r.code;li.role='option';li.setAttribute('aria-selected',String(selection?.code===r.code));li.append(document.createTextNode(r.name));const sub=document.createElement('small');sub.textContent=r.region;li.append(sub);li.addEventListener('mousedown',e=>e.preventDefault());li.addEventListener('click',()=>choose(r));$('commune-options').append(li);});
 $('popup').hidden=false;$('commune-search').setAttribute('aria-expanded','true');$('commune-search').removeAttribute('aria-activedescendant');
}
function clearResult(){requestId++;current=null;$('result').hidden=true;$('observed').hidden=true;$('message').textContent=selection?selection.name+' elegida. Genera su predicción.':'Elige una comuna para empezar.';$('output-period').textContent=mode()==='estudio'?'PRUEBA HISTÓRICA · 2017 → 2024':'ESCENARIO FUTURO · 2024 → 2031';$('output-title').textContent=mode()==='estudio'?'Una predicción, un resultado verificable':'Un escenario futuro todavía sin verificar';}
function choose(r){selection=r;$('commune-search').value=r.name;$('chosen').textContent=r.name+' · '+r.region;$('predict').disabled=false;closePicker();clearResult();}
async function predict(){
 if(!selection)return;const id=++requestId;$('predict').disabled=true;$('message').textContent='Consultando predicción…';
 try{const response=await fetch('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({commune:selection.code,mode:mode()})});const data=await response.json();if(!response.ok)throw Error(data.error);if(id!==requestId)return;current=data;renderResult();}
 catch(error){if(id===requestId)$('message').textContent=error.message;}finally{if(id===requestId)$('predict').disabled=!selection;}
}
function renderResult(){
 const r=current.result;$('message').textContent=current.name+' · '+current.region;$('result').hidden=false;$('inputs-title').textContent='Lo que el modelo conoce del Censo '+current.period[0];
 $('inputs').replaceChildren();[[number.format(r.population),'Habitantes al inicio'],[percent(r.young_share),'Menores de 15 años'],[percent(r.old_share),'65 años o más']].forEach(([v,label])=>{const d=document.createElement('div'),b=document.createElement('strong'),s=document.createElement('span');b.textContent=v;s.textContent=label;d.append(b,s);$('inputs').append(d);});
 $('model-title').textContent='PREDICCIÓN · '+names[current.model].toUpperCase();
 $('prediction-class').textContent=r.predicted_class?'Crecimiento de al menos 1% anual':'Crecimiento menor que 1% anual';$('prediction-description').textContent=r.predicted_class?'El modelo clasifica esta comuna en el grupo de crecimiento alto.':'Esta clase incluye crecimiento lento, estabilidad y disminución de población.';
 $('reveal').hidden=current.mode!=='estudio';$('observed').hidden=true;$('future-note').hidden=current.mode!=='futuro';
 $('score').textContent='Puntaje interno para «al menos 1% anual»: '+decimal(r.score)+'. Combina las salidas de los árboles. No es una probabilidad calibrada ni mide la certeza de esta predicción.';
}
function reveal(){if(!current||current.mode!=='estudio')return;const r=current.result,box=$('observed');box.replaceChildren();box.classList.toggle('wrong',!r.correct);const h=document.createElement('h3');h.textContent=r.correct?'La predicción coincidió con 2024':'La predicción se equivocó';const p=document.createElement('p');p.textContent='La población pasó de '+number.format(r.population)+' a '+number.format(r.actual_population)+' habitantes. La tasa anual observada fue '+percent(r.actual_rate)+': '+(r.actual_class?'al menos 1% anual':'menor que 1% anual')+'.';box.append(h,p);box.hidden=false;$('reveal').hidden=true;}
function table(id,data,selected){const body=$(id);body.replaceChildren();Object.entries(data).forEach(([k,v])=>{const tr=document.createElement('tr');tr.classList.toggle('selected',k===selected);[names[k],decimal(v.f1_macro),percent(v.accuracy)].forEach(t=>{const td=document.createElement('td');td.textContent=t;tr.append(td);});body.append(tr);});}
function renderStudy(){
 const s=model.summary,n=s.n_communes;
 $('train-note').textContent=n+' comunas para aprender del cambio posterior.';$('val-note').textContent=n+' comunas para comparar árbol y bosque.';$('test-note').textContent=n+' comunas para evaluar después de elegir.';
 $('finding-text').textContent='El '+names[s.selected].toLowerCase()+' obtuvo F1 macro '+decimal(s.test.modelo.f1_macro)+'. Continuar la tendencia anterior obtuvo '+decimal(s.test.persistencia.f1_macro)+' y clasificó mejor. Con estas tres variables, el modelo entrenado todavía no mejora esa referencia.';
 $('selection-fit').textContent='Ambos modelos se entrenaron con '+s.selection_fit_n+' ejemplos de 1992–2002. Elegimos entre ambos por F1 macro de validación.';
 $('final-fit').textContent='La configuración elegida se reentrenó con '+s.final_fit_n+' ejemplos anteriores. La prueba no modificó la elección ni los parámetros.';
 $('coverage-note').textContent='Se excluyeron '+model.excluded.length+' comunas por cambios territoriales conocidos o identidad ambigua. Falta certificar todos los límites históricos.';
 $('source-check').textContent='La reconstrucción de residentes habituales de 2017 coincidió con una tabla independiente del INE en las 346 comunas. Tras las exclusiones, usamos las mismas '+n+' comunas en cada etapa.';
 table('validation-table',s.validation,s.selected);table('test-table',s.test,'modelo');
 const m=s.test.modelo.confusion,wrap=document.createElement('div');wrap.className='matrix';
 ['Real / predicha','Menor que 1%','Al menos 1%','Menor que 1%',String(m[0][0]),String(m[0][1]),'Al menos 1%',String(m[1][0]),String(m[1][1])].forEach((t,i)=>{const d=document.createElement('div');d.textContent=t;if([4,5,7,8].includes(i))d.className='number'+([5,7].includes(i)?' error':'');wrap.append(d);});$('confusion').replaceChildren(wrap);
 $('errors-note').textContent='Acertó en '+(m[0][0]+m[1][1])+' de '+n+' comunas. Marcó crecimiento alto en '+m[0][1]+' que no alcanzaron el umbral y dejó fuera '+m[1][0]+' que sí lo alcanzaron.';
 s.labels.forEach(k=>{const v=s.test.modelo.classes[k],tr=document.createElement('tr');[k,decimal(v.precision),decimal(v.recall),decimal(v['f1-score']),number.format(v.support)].forEach(t=>{const td=document.createElement('td');td.textContent=t;tr.append(td);});$('classes-table').append(tr);});
 [...new Map(model.communes.map(r=>[r.region_code,r.region])).entries()].sort((a,b)=>a[1].localeCompare(b[1],'es')).forEach(([code,name])=>{const o=document.createElement('option');o.value=code;o.textContent=name;$('region').append(o);});
 model.excluded.sort((a,b)=>a.name.localeCompare(b.name,'es')).forEach(r=>{const li=document.createElement('li');li.textContent=r.name+': '+r.reason+'.';$('excluded-list').append(li);});
 ['region','commune-search','toggle','example'].forEach(id=>$(id).disabled=false);
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
$('example').addEventListener('click',()=>{$('region').value='0';choose(model.communes.find(r=>r.name==='Valdivia'));predict();});
try{const response=await fetch('/api/model');if(!response.ok)throw Error('No se pudo cargar el experimento.');model=await response.json();renderStudy();}catch(error){$('message').textContent=error.message;$('finding-text').textContent='El experimento no está disponible. Inicia el servidor local.';}
