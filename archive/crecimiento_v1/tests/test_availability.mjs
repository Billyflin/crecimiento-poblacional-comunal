import assert from 'node:assert/strict';

const url=process.env.CENSO_TEST_URL || 'http://127.0.0.1:8787';
const response=await fetch(url+'/api/model');
assert.equal(response.status,200);
const model=await response.json();
assert.equal(model.study,'crecimiento_censal');
assert.equal(model.communes.length,314);
assert.equal(new Set(model.communes.map(r=>r.code)).size,314);

let supported=0,rejected=0;
async function query(commune,mode,expected){
 const response=await fetch(url+'/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({commune,mode})});
 assert.equal(response.status,expected,'Comuna '+commune+' · '+mode);
 const data=await response.json();
 if(expected===400){assert.ok(data.error);rejected++;return;}
 assert.equal(data.code,commune);
 assert.ok([0,1].includes(data.result.predicted_class));
 assert.ok(data.result.score>=0 && data.result.score<=1);
 assert.ok(data.result.population>0);
 assert.deepEqual(data.period,mode==='estudio'?[2017,2024]:[2024,2031]);
 if(mode==='futuro'){
   assert.equal(data.result.verified,false);
   assert.equal('actual_class' in data.result,false);
 }else{
   assert.ok([0,1].includes(data.result.actual_class));
   assert.equal(data.result.correct,data.result.predicted_class===data.result.actual_class);
 }
 supported++;
}
for(let i=0;i<model.communes.length;i+=8){
 await Promise.all(model.communes.slice(i,i+8).flatMap(r=>['estudio','futuro'].map(mode=>query(r.code,mode,200))));
}
for(const r of model.excluded){
 for(const mode of ['estudio','futuro'])await query(r.code,mode,400);
}
console.log(JSON.stringify({communes:314,supported_queries:supported,excluded_queries_rejected:rejected}));
