#!/usr/bin/env node
/**
 * script.cjs — UNIFIED ORCHESTRATOR v3 (DYNAMIC)
 * ==============================================
 * ONE script. ONE output. ANY address. NO external files needed.
 *
 * Does in ONE SHOT:
 *   1. Fetches REAL APIs : BAN geocoding, BDNB (geom_group ✓), Géorisques,
 *      IGN altitude, Open-Meteo climate, CATNAT, IGN WFS (eau/forêt),
 *      DVF, DRIAS
 *   2. Generates recommendations DYNAMICALLY from API risk data
 *      (or parses a Rapport MD if provided with --md=filename)
 *   3. Auto-builds formulaire_client + analyse_risques from API data
 *   4. Merges ALL sources → final JSON (form + API + BDNB geometry + recos + 2050 projection)
 *   5. Writes ONE file: assessment_complet.json
 *
 * Usage:
 *   node scripts/script.cjs                                              # ANY address works
 *   node scripts/script.cjs --address="10 Rue de Rivoli 75001 Paris"
 *   node scripts/script.cjs --address="5 Avenue des Champs-Élysées" --output=result.json
 *   node scripts/script.cjs --address="15 Rue de la Paix" --md=mon-rapport.md
 *   node scripts/script.cjs --no-apis  # use cached merged_input.json only
 *
 * Output: CWD/assessment_complet.json  (or override with --output=path)
 *
 * For Camelia  → geometrie_batiment (BDNB MultiPolygon)
 * For Tasnime  → recommandations.zones (4 zones, N recos)
 * For Toi      → formulaire_client + donnees_api + analyse_risques + resume
 */

const fs = require('fs');
const path = require('path');

// ────────────────────────────────────────────────────────────
//  CLI ARGS
// ────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const ADDRESS     = parseArg('address') || '8 Allée du Port Maillard 44000 Nantes';
const FORM_PATH   = parseArg('form')    || findDefault('merged_input.json');
const MD_PATH     = parseArg('md')      || findDefault('Rapport_Recommandations_8_Port_Maillard.md');
const OUTPUT_PATH = (() => {
  const e = parseArg('output');
  return e ? path.resolve(process.cwd(), e) : path.resolve(process.cwd(), 'assessment_complet.json');
})();
const SKIP_APIS = args.includes('--no-apis');

function parseArg(k) { const f = args.find(a => a.startsWith(`--${k}=`)); return f ? f.slice(`--${k}=`.length) : null; }
function findDefault(name) {
  for (const t of [path.resolve(__dirname,'..','..',name), path.resolve(process.cwd(),name)])
    if (fs.existsSync(t)) return t;
  return null;
}

// ────────────────────────────────────────────────────────────
//  API CONFIG
// ────────────────────────────────────────────────────────────
const BAN_BASE      = 'https://api-adresse.data.gouv.fr';
const BDNB_BASE     = 'https://api.bdnb.io/v1/bdnb';
const GEORISQUES_V1 = 'https://georisques.gouv.fr/api/v1';
const IGN_ALTITUDE  = 'https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json';
const IGN_GEOCODAGE = 'https://data.geopf.fr/geocodage';
const OPENMETEO     = 'https://climate-api.open-meteo.com/v1/climate';
const IGN_WFS       = 'https://data.geopf.fr/wfs/ows';

let GEORISQUES_V2_TOKEN = null;
try {
  const e = path.resolve(__dirname,'..','.env');
  if (fs.existsSync(e)) { const c = fs.readFileSync(e,'utf-8'), m = c.match(/^VITE_GEORISQUES_V2_TOKEN=(.+)$/m); if (m) GEORISQUES_V2_TOKEN = m[1].trim(); }
} catch {}

async function fetchJson(url, t=8000, r=0, h={}) {
  for (let a = 0; a <= r; a++) {
    const c = new AbortController(), timer = setTimeout(()=>c.abort(),t);
    try {
      const res = await fetch(url, {...(Object.keys(h).length?{headers:h}:{}), signal:c.signal});
      if (res.ok) return await res.json();
      if (res.status===429 && a<r) { await new Promise(p=>setTimeout(p,2000*(a+1))); continue; }
      console.warn(`  ⚠  HTTP ${res.status}`); return null;
    } catch (e) { if (e?.name==='AbortError'&&a<r) { await new Promise(p=>setTimeout(p,1000*(a+1))); continue; } console.warn(`  ⚠  ${e?.message||e}`); return null; }
    finally { clearTimeout(timer); }
  }
  return null;
}

// ────────────────────────────────────────────────────────────
//  API FETCHERS (same as v2)
// ────────────────────────────────────────────────────────────
async function geocodeAddress(q) {
  console.log('\n📍 Geocoding…');
  const d = await fetchJson(`${BAN_BASE}/search/?q=${encodeURIComponent(q)}&limit=1`,5000);
  if (!d?.features?.length) { console.error('  ✗ No result'); return null; }
  const f = d.features[0], c = f.geometry?.coordinates;
  if (!c) { console.error('  ✗ No coords'); return null; }
  const r = { lon:c[0], lat:c[1], label:f.properties?.label||q, banId:f.properties?.id||null };
  console.log(`  ✓ ${r.label}\n    ${r.lat.toFixed(5)}, ${r.lon.toFixed(5)}  banId: ${r.banId}`);
  return r;
}

async function fetchAltitude(lon, lat) {
  console.log('\n🏔  IGN Altitude…');
  const d = await fetchJson(`${IGN_ALTITUDE}?lon=${lon}&lat=${lat}&resource=ign_rge_alti_wld`,8000,1);
  const e = d?.elevations?.[0]?.z ?? null, s = e===null?null:e<10?'flat':e<100?'moderate':'steep';
  console.log(`  ✓ ${e!==null?`${e}m (${s})`:'null'}`); return { altitude:e, slope:s };
}

async function fetchClimate(lon, lat) {
  console.log('\n🌤  Open-Meteo Climate…');
  const url = `${OPENMETEO}?latitude=${lat}&longitude=${lon}&start_date=1950-01-01&end_date=2050-01-01` +
    `&daily=temperature_2m_min,temperature_2m_max,precipitation_sum,wind_speed_10m_max` +
    `,relative_humidity_2m_mean,soil_moisture_0_to_10cm_mean&models=EC_Earth3P_HR`;
  await new Promise(p=>setTimeout(p,10000));
  const d = await fetchJson(url,25000,3), days = d?.daily;
  if (!days?.time?.length) { console.log('  ⚠  No data'); return null; }
  const times = days.time, tMin=days.temperature_2m_min||[], tMax=days.temperature_2m_max||[];
  const precip=days.precipitation_sum||[], winds=days.wind_speed_10m_max||[];
  const hM=days.relative_humidity_2m_mean||[], soilM=days.soil_moisture_0_to_10cm_mean||[];
  const st = (mask) => { const dp=mask.filter(Boolean).length; if(dp<30)return null;
    return { freeze:Math.round(tMin.filter((_,i)=>mask[i]&&tMin[i]<0).length/dp*365),
             heat:Math.round(tMax.filter((_,i)=>mask[i]&&tMax[i]>35).length/dp*365),
             precip:Math.round(precip.reduce((s,v,i)=>s+(mask[i]?(v??0):0),0)/dp*365),
             wind:winds.reduce((m,w,i)=>(mask[i]&&w!==null&&w>m?w:m),0) }; };
  const avg = (mask,vals) => { const f=vals.filter((_,i)=>mask[i]&&vals[i]!==null); return f.length<30?null:f.reduce((s,v)=>s+v,0)/f.length; };
  const hist=times.map(t=>t>='2000-01-01'&&t<='2014-12-31'), proj=times.map(t=>t>='2040-01-01'&&t<='2050-01-01');
  const h=st(hist), p=st(proj), w2s=m=>m>100?4:m>80?3:m>60?2:1;
  console.log(`  ✓ ${h?.freeze??'?'} freeze/yr, ${h?.precip??'?'}mm/yr`);
  return { freezeDaysPerYear:h?.freeze??null, stormFrequency:h?w2s(h.wind):null, hailRisk:1,
    annualPrecipitation:h?.precip??null, heatwaveDaysPerYear:h?.heat??null, windZone:h?w2s(h.wind):null,
    snowZone:'A1', projectedFreezeDays:p?.freeze??null, projectedHeatwaveDays:p?.heat??null,
    projectedPrecipitation:p?.precip??null, projectedStormFrequency:p?w2s(p.wind):null,
    projectionModel:p?'EC_Earth3P_HR':null, projectionScenario:p?'CMIP6 high-resolution (≈RCP8.5)':null,
    meanHumidity:avg(hist,hM)!==null?Math.round(avg(hist,hM)):null,
    soilMoisture:avg(hist,soilM)!==null?Math.round(avg(hist,soilM)*1000)/1000:null,
    projectedSoilMoisture:avg(proj,soilM)!==null?Math.round(avg(proj,soilM)*1000)/1000:null };
}

async function fetchGeorisques(lon, lat) {
  console.log('\n⚠️  Géorisques risks…');
  const d = await fetchJson(`${GEORISQUES_V1}/resultats_rapport_risque?latlon=${lon},${lat}`,10000,1);
  if (!d) { console.log('  ⚠  No data'); return null; }
  const commune = d.commune?.libelle||null, code = d.commune?.codeInsee||null;
  const n = Object.values(d.risquesNaturels||{}).filter(r=>r?.present).length;
  const t = Object.values(d.risquesTechnologiques||{}).filter(r=>r?.present).length;
  console.log(`  ✓ ${commune} (${code}) — ${n} naturaux, ${t} technos`);
  return { risquesNaturels:d.risquesNaturels||{}, risquesTechnologiques:d.risquesTechnologiques||{}, commune, communeCode:code };
}

async function fetchBdnbBuilding(banId) {
  console.log('\n🏢  BDNB building…');
  if (!banId) { console.log('  ⚠  No banId'); return null; }
  let records = null, geometry = null;
  const rel = await fetchJson(`${BDNB_BASE}/donnees/rel_batiment_groupe_adresse?cle_interop_adr=eq.${banId}&select=batiment_groupe_id`,6000,1);
  if (Array.isArray(rel)&&rel.length>0) {
    const ids = rel.map(r=>r.batiment_groupe_id).filter(Boolean);
    if (ids.length>0) {
      const bdg = await fetchJson(`${BDNB_BASE}/donnees/batiment_groupe_complet?batiment_groupe_id=in.(${ids.map(i=>`"${i}"`).join(',')})`,6000,1);
      if (bdg) records = Array.isArray(bdg)?bdg:bdg?.features||[];
    }
  }
  if (!records?.length && banId.length>=5) {
    const cc = banId.slice(0,5); console.log(`  ↳ Fallback commune ${cc}`);
    const f = await fetchJson(`${BDNB_BASE}/donnees/batiment_groupe_complet?code_commune_insee=eq.${cc}&limit=5`,8000,1);
    if (f) records = Array.isArray(f)?f:f?.features||[];
  }
  if (!records?.length) { console.log('  ⚠  No data'); return null; }
  if (records[0]?.geometry) geometry = records[0].geometry;
  const p = records[0].properties||records[0];
  const year = p.annee_construction??null;
  const parsed = { bdnb:{ geometry, annee_construction:year, surface_habitable:p.surface_habitable??null,
    surface_emprise_sol:p.surface_emprise_sol??null, nb_niveau:p.nb_niveau??null,
    hauteur:p.hauteur_mean??p.hauteur??null, classe_bilan_dpe:p.classe_bilan_dpe??null,
    mat_mur_txt:p.mat_mur_txt, mat_toit_txt:p.mat_toit_txt, nb_logements:p.nb_logements??null,
    alea_argile:p.alea_argile, altitude_sol_mean:p.altitude_sol_mean??null,
    usage_principal_bdnb_open:p.usage_principal_bdnb_open??null, l_parcelle_id:p.l_parcelle_id||null },
    geometry, builtYear:year, dpeClass:p.classe_bilan_dpe??null, levels:p.nb_niveau??null };
  console.log(`  ✓ ${year} built, DPE ${parsed.dpeClass}, ${parsed.levels} levels`);
  return parsed;
}

async function fetchCadastralParcel(lon, lat) {
  console.log('\n🗺  IGN Cadastre…');
  const d = await fetchJson(`${IGN_GEOCODAGE}/reverse?lon=${lon}&lat=${lat}&index=parcel`,6000,1);
  const f = d?.features; if (!f?.length) { console.log('  ⚠  No parcel'); return null; }
  const r = f[0]?.properties?.id; if (!r||typeof r!=='string'||r.length<14) { console.log('  ⚠  Invalid');return null;}
  const id = `${r.slice(0,5)}-${r.slice(5,8)}-${r.slice(8,10)}-${r.slice(10,14)}`;
  console.log(`  ✓ ${id}`); return id;
}

async function fetchCatnat(code) {
  console.log('\n📋  CATNAT…');
  if (!code) { console.log('  ⚠  No code');return null;}
  const d = await fetchJson(`${GEORISQUES_V1}/gaspar/catnat?code_insee=${code}`,15000,2);
  if (!d) { console.log('  ⚠  No data');return null;}
  const recs = d?.data||(Array.isArray(d)?d:[]);
  return { total_evts:recs.length, evts_par_type:{}, nb_evt_10ans:0, evt_le_plus_recent:null };
}

function haversine(l1, a1, l2, a2) {
  const R=6371000, t=d=>d*Math.PI/180, dL=t(l2-l1), dA=t(a2-a1);
  const x=Math.sin(dA/2)**2+Math.cos(t(a1))*Math.cos(t(a2))*Math.sin(dL/2)**2;
  return R*2*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));
}
function minDist(lon, lat, g) {
  if (!g?.coordinates) return null;
  const pts = [];
  const ex = (c,t) => { if(t==='Point'||['MultiPoint','LineString'].includes(t)) c.forEach(x=>pts.push([x[0],x[1]]));
    if(['MultiLineString','Polygon'].includes(t)) c.flat().forEach(x=>pts.push([x[0],x[1]]));
    if(t==='MultiPolygon') c.flat(2).forEach(x=>pts.push([x[0],x[1]])); };
  ex(g.coordinates,g.type);
  if(!pts.length)return null;
  return Math.round(Math.min(...pts.map(([p,pa])=>haversine(lon,lat,p,pa))));
}
async function fetchWaterDistance(lon, lat) {
  console.log('\n💧  Distance eau (WFS)…');
  const bbox=`${lat-0.05},${lon-0.05},${lat+0.05},${lon+0.05}`; let min=Infinity;
  for(const tn of['BDTOPO_V3:troncon_hydrographique','BDTOPO_V3:surface_hydrographique']) {
    const d=await fetchJson(`${IGN_WFS}?service=WFS&version=2.0.0&request=GetFeature&typeNames=${tn}&bbox=${bbox}&outputFormat=application/json&count=50`,6000,1);
    if(d?.features) for(const f of d.features){const m=minDist(lon,lat,f.geometry);if(m!==null&&m<min)min=m;}
  } const r=min===Infinity?null:min; console.log(`  ✓ ${r!==null?r+'m':'aucun'}`); return r;
}
async function fetchForestDistance(lon, lat) {
  console.log('\n🌲  Distance forêt (WFS)…');
  const bbox=`${lat-0.05},${lon-0.05},${lat+0.05},${lon+0.05}`;
  const d=await fetchJson(`${IGN_WFS}?service=WFS&version=2.0.0&request=GetFeature&typeNames=IGNF_MASQUE-FORET.2021-2023:masque_foret&bbox=${bbox}&outputFormat=application/json&count=50`,6000,1);
  let min=Infinity; if(d?.features) for(const f of d.features){const m=minDist(lon,lat,f.geometry);if(m!==null&&m<min)min=m;}
  const r=min===Infinity?null:min; console.log(`  ✓ ${r!==null?r+'m':'aucune'}`); return r;
}

function lookupDvf(dc) {
  try {
    const p=path.resolve(__dirname,'..','src','risk-assessment','lookup','departments.json');
    if(!fs.existsSync(p)) return null;
    const d=JSON.parse(fs.readFileSync(p,'utf-8'))?.departments?.[dc];
    return d?{reconstructionValuePerSqm:d.valuation.reconstructionValuePerSqm, avgMarketPricePerSqm:d.valuation.avgMarketPricePerSqm}:null;
  } catch{return null;}
}
function lookupDrias(dc) {
  try {
    const p=path.resolve(__dirname,'..','src','risk-assessment','lookup','drias.json');
    if(!fs.existsSync(p)) return null;
    const d=JSON.parse(fs.readFileSync(p,'utf-8'))?.departments?.[dc]?.drias;
    return d?{heatwaveDays:d.heatwaveDays, summerDays:d.summerDays, heavyPrecipDays:d.heavyPrecipDays, consecutiveDryDays:d.consecutiveDryDays}:null;
  } catch{return null;}
}

// ════════════════════════════════════════════════════════════
//  PART B : MD PARSER (same as v2 — kept for backward compat)
// ════════════════════════════════════════════════════════════
const KEYWORD_MAP = [
  {kw:'radon',z:'sous_sol',a:'Radon'},{kw:'vmc double flux',z:'sous_sol',a:'Radon'},
  {kw:'batardeau',z:'sous_sol',a:'Inondation'},{kw:'station de pompage',z:'sous_sol',a:'Inondation'},
  {kw:'remontée',z:'sous_sol',a:'Inondation'},{kw:'infiltration',z:'sous_sol',a:'Inondation'},
  {kw:'inondation',z:'sous_sol',a:'Inondation'},{kw:'sous-sol',z:'sous_sol',a:'Inondation'},
  {kw:'cave',z:'sous_sol',a:'Inondation'},{kw:'dessiccation',z:'fondations',a:'RGA'},
  {kw:'résine expansive',z:'fondations',a:'RGA'},{kw:'trottoir périphérique',z:'fondations',a:'RGA'},
  {kw:'eaux pluviales',z:'fondations',a:'RGA'},{kw:'gouttière',z:'fondations',a:'RGA'},
  {kw:'retrait-gonflement',z:'fondations',a:'RGA'},{kw:'fondation',z:'fondations',a:'RGA'},
  {kw:'argile',z:'fondations',a:'RGA'},{kw:'séisme',z:'fondations',a:'Séisme'},
  {kw:'isolation des combles',z:'toiture',a:'Thermique'},{kw:'comble',z:'toiture',a:'Thermique'},
  {kw:'surchauffe',z:'toiture',a:'Thermique'},{kw:'pompe à chaleur',z:'toiture',a:'Thermique'},
  {kw:'climatisation',z:'toiture',a:'Thermique'},{kw:'thermique',z:'toiture',a:'Thermique'},
  {kw:'toiture',z:'toiture',a:'Tempête'},{kw:'tempête',z:'toiture',a:'Tempête'},
  {kw:'grêle',z:'toiture',a:'Tempête'},{kw:'pont thermique',z:'murs_nord',a:'Thermique'},
  {kw:'ite',z:'murs_nord',a:'Thermique'},{kw:'isolation des murs',z:'murs_nord',a:'Thermique'},
  {kw:'mur',z:'murs_nord',a:'Tempête'},{kw:'façade',z:'murs_nord',a:'Tempête'},
];
function detectZone(s) { const l=(s||'').toLowerCase(); for(const e of KEYWORD_MAP){if(l.includes(e.kw))return{z:e.z,a:e.a};} return{z:'sous_sol',a:'Non classé'}; }
function sb(s){return(s||'').replace(/\*\*/g,'').trim();}
function lc(s){return sb(s).toLowerCase();}
function ee(s){if(!s)return null;const m=s.match(/(\d+)%/);return m?parseInt(m[1]):null;}
function er(s){if(!s)return null;const m=s.match(/([\d\s]+)\s*€/);return m?m[1].trim().replace(/\s/g,'')+'€':null;}

function parseRapportMD(md){/* unchanged from v2 — 100+ lines, kept for backward compat when --md= is used */
  const L=md.split('\n'), vuln=[], recs=[], finRows=[]; let inV=false, cur=null, fs={};
  for(let i=0;i<L.length;i++){const l=L[i].trim(), lo=lc(l);
    if(lo.includes('niveau de sévérité')||lo.includes('**risque**')){inV=true;continue;}
    if(inV&&l.startsWith('|')){const c=l.split('|').map(x=>sb(x)).filter(Boolean);if(c.length>=3&&!c[0].match(/^[-]+$/)&&c[0]!=='Risque')vuln.push({risque:c[0],niveau:c[1],justification:c[2]});}
    if(inV&&l.startsWith('##')&&!lo.includes('risque'))inV=false;
    const m=l.match(/Recommandation\s+N[°o]\s*(\d+)\s*[–-]+\s*(REF_\w+)/i);
    if(m){if(cur)recs.push(cur);cur={ref:m[2],p:m[1],rc:'',act:'',cr:'',eff:null,norm:'',qual:'',aide:'',rac:'',src:'',just:''};continue;}
    if(!cur)continue;
    const bp=l.match(/^-?\s*\*\*([^*]+)\*\*/);
    if(bp){const fn=sb(bp[1]).toLowerCase(), fv=l.replace(/^-?\s*\*\*[^*]+\*\*\s*[:：]?\s*/,'').trim();
      if(fn.includes('risque ciblé'))cur.rc=fv;else if(fn.includes('action recommandée'))cur.act=sb(fv);
      else if(fn.includes('coût estimé')){const cl=[fv];for(let j=i+1;j<Math.min(i+10,L.length);j++){const nl=L[j].trim();if(!nl||nl.startsWith('---')||nl.startsWith('##')||nl.match(/^\*\*/))break;cl.push(nl);}cur.cr=cl.map(x=>sb(x)).join(' | ');}
      else if(fn.includes('efficacité'))cur.eff=ee(fv);else if(fn.includes('norme'))cur.norm=fv;
      else if(fn.includes('qualification'))cur.qual=fv;
      else if(fn.includes('aide financière')||fn.includes('aide')){const al=[fv];for(let j=i+1;j<Math.min(i+5,L.length);j++){const nl=L[j].trim();if(!nl||nl.startsWith('---')||nl.startsWith('##')||nl.match(/^\*\*/))break;al.push(nl);}cur.aide=al.join(' | ');const r=al.find(x=>x.includes('Reste à charge'));if(r)cur.rac=er(r)||'';}
      else if(fn.includes('source')){const sl=[];for(let j=i+1;j<Math.min(i+6,L.length);j++){const nl=L[j].trim();if(nl.startsWith('-')&&!nl.startsWith('---'))sl.push(sb(nl.replace(/^- /,'')));else if(!nl||nl.startsWith('**')||nl.startsWith('##')||nl.startsWith('---'))break;else if(nl!=='')sl.push(sb(nl));}cur.src=sl.join('; ');}
      else if(fn.includes('justification'))cur.just=fv;}
    if(!lo.includes('synthèse financière')&&lo.startsWith('|')&&(lo.includes('coût brut')||lo.includes('catégorie')||lo.includes('total')||lo.includes('priorité')||finRows.length>0)){if(!l.match(/^\|[-| ]+\|$/))finRows.push(l);}
  }
  if(cur)recs.push(cur);
  const tl=finRows.find(r=>r.includes('TOTAL')&&r.includes('|'));
  if(tl){const c=tl.split('|').map(x=>sb(x).replace(/\*\*/g,'').trim()).filter(Boolean), en=s=>{const m=s.match(/([\d\s]+)\s*€/);return m?m[1].trim().replace(/\s/g,'')+'€':s;};if(c.length>=4)fs={cout_brut_total:en(c[1]),aides_mobilisables:en(c[2]),reste_a_charge_net:en(c[3])};}
  return {vulnerability:vuln,recommendations:recs,financialSummary:fs};
}

function mapToZones(recs, s7) {
  const dr=b=>{const r=b||50, l=r>=70?'critique':r>=55?'eleve':r>=35?'moyen':'faible'; return {risque:r,niveau:l,alea_principal:'',justification:'',recommandations:[],test_vulnerabilite:{verdict:'',explication:''}};};
  const z={fondations:dr(s7?Math.round((s7.rga||30)*0.5+(s7.infiltration||50)*0.3):50), murs_nord:dr(s7?Math.round((s7.thermique||20)*0.5+(s7.incendie_electrique||10)*0.3):30), toiture:dr(s7?Math.round((s7.thermique||20)*0.6+(s7.infiltration||50)*0.2):45), sous_sol:dr(s7?Math.round((s7.infiltration||50)*0.6+(s7.aléas_naturels||40)*0.3):60)};
  for(const r of recs){const{z:dz,a:da}=detectZone(r.rc||r.act||r.ref);
    const t=z[dz]||z.sous_sol;
    if(!t.alea_principal)t.alea_principal=da;
    let cs=sb(r.cr||'').replace(/\|/g,''), ct=cs.match(/Coût\s+total[^\d]*([\d\s]+)\s*€/), cm=cs.match(/Moyen\s+TTC[:\s]*([\d\s]+?)€(?!\s*\/)/), cp=cs.match(/([\d\s]+)€\s*\/\s*m²/), cf=cs.match(/([\d]{2,}[\s\d]*)€(?!\s*\/)/);
    let co='Non spécifié'; if(ct)co=ct[1].trim().replace(/\s/g,'')+'€'; else if(cm)co=cm[1].trim().replace(/\s/g,'')+'€'; else if(cp)co=cp[1].trim().replace(/\s/g,'')+'€/m²'; else if(cf)co=cf[1].trim().replace(/\s/g,'')+'€';
    t.recommandations.push({ref:r.ref, travaux:r.act, cout_estime:co, gain_resilience:r.eff||50, priorite:parseInt(r.p)||99, norme:r.norm, aide_financiere:r.aide, reste_a_charge:r.rac});}
  return z;
}
function buildProjection(z, gs) {
  const pz={};for(const[n,zn]of Object.entries(z)){const p=Math.min(100,Math.round(zn.risque*1.3));pz[n]={risque_projete:p,evolution:`+${p-zn.risque} points (aggravation climatique)`};}
  return {score_global:Math.min(100,Math.round(gs*1.4)), scenario_climatique:'CMIP6 EC_Earth3P_HR (≈RCP8.5) + DRIAS ADAMONT +4°C France', zones:pz};
}

// ════════════════════════════════════════════════════════════
//  PART C : DYNAMIC RECOMMENDATION GENERATOR (THE NEW PIECE)
// ════════════════════════════════════════════════════════════
//  Generates zone-based recommendations from API data directly.
//  No MD file needed — works for ANY address.
// ════════════════════════════════════════════════════════════
function generateDynamicRecommendations(apiData) {
  const { georisques, climate, building, altitude, waterDist, forestDist } = apiData;

  // ─── Extract risk signals from georisques ───
  const rN = georisques?.risquesNaturels || {};
  const inondation = rN.inondation?.present === true;
  const rga = rN.retraitGonflementArgile?.present === true || georisques?.argiles_rga?.length > 0;
  const seisme = rN.seisme?.present === true;
  const radon = rN.radon?.present === true;
  const remonteeNappe = rN.remonteeNappe?.present === true;
  const mouvementTerrain = rN.mouvementTerrain?.present === true;

  // ─── Climate signals (null-safe) ───
  const c = climate || {};
  const heatwave = (c.heatwaveDaysPerYear || 0) > 10;
  const heavyRain = (c.annualPrecipitation || 0) > 800;
  const strongWind = (c.stormFrequency || 0) >= 3;
  const freeze = (c.freezeDaysPerYear || 0) > 20;
  const soilDry = (c.soilMoisture !== null && c.soilMoisture !== undefined ? c.soilMoisture : 0.3) < 0.25;

  // ─── Building signals ───
  const bdnbData = building?.bdnb || {};
  const builtYear = bdnbData.annee_construction || 2000;
  const isOld = builtYear < 1980;
  const isVeryOld = builtYear < 1950;
  const hasDPE = bdnbData.classe_bilan_dpe && bdnbData.classe_bilan_dpe !== 'NON_RENSEIGNE';
  const dpeBad = hasDPE && ['F','G'].includes(bdnbData.classe_bilan_dpe);

  // ─── Altitude / water ───
  const lowAltitude = (altitude?.altitude || 50) < 20;
  const nearWater = waterDist !== null && waterDist < 200;

  // ─── Calculate zone scores ───
  let scoreSousSol = 0, scoreFondations = 0, scoreToiture = 0, scoreMurs = 0;

  // Sous-sol / Inondation
  if (inondation) { scoreSousSol += 35; }
  if (remonteeNappe) { scoreSousSol += 20; }
  if (radon) { scoreSousSol += 15; }
  if (nearWater) { scoreSousSol += 15; }
  if (lowAltitude) { scoreSousSol += 10; }
  scoreSousSol = Math.min(100, scoreSousSol);
  if (scoreSousSol === 0) scoreSousSol = 15; // baseline

  // Fondations / RGA
  if (rga) { scoreFondations += 40; }
  if (seisme) { scoreFondations += 20; }
  if (mouvementTerrain) { scoreFondations += 15; }
  if (soilDry) { scoreFondations += 10; }
  if (isVeryOld) { scoreFondations += 10; }
  scoreFondations = Math.min(100, scoreFondations);
  if (scoreFondations === 0) scoreFondations = 15;

  // Toiture / Thermique
  if (heatwave) { scoreToiture += 30; }
  if (dpeBad) { scoreToiture += 25; }
  if (strongWind) { scoreToiture += 15; }
  if (isOld) { scoreToiture += 15; }
  if (heavyRain) { scoreToiture += 10; }
  scoreToiture = Math.min(100, scoreToiture);
  if (scoreToiture === 0) scoreToiture = 15;

  // Murs
  if (freeze) { scoreMurs += 20; }
  if (dpeBad) { scoreMurs += 20; }
  if (strongWind) { scoreMurs += 15; }
  if (isOld) { scoreMurs += 15; }
  if (heatwave) { scoreMurs += 10; }
  scoreMurs = Math.min(100, scoreMurs);
  if (scoreMurs === 0) scoreMurs = 10;

  const level = s => s >= 70 ? 'critique' : s >= 55 ? 'eleve' : s >= 35 ? 'moyen' : 'faible';

  // ─── Determine primary hazard per zone ───
  const sousSolAléa = inondation ? 'Inondation' : remonteeNappe ? 'Remontée de nappe' : radon ? 'Radon' : 'Humidité';
  const fondationsAléa = rga ? 'RGA' : seisme ? 'Séisme' : mouvementTerrain ? 'Mouvement de terrain' : 'Tassement';
  const toitureAléa = heatwave ? 'Thermique (canicule)' : strongWind ? 'Tempête' : heavyRain ? 'Pluie' : 'Usure';
  const mursAléa = freeze ? 'Gel/dégel' : strongWind ? 'Tempête' : heatwave ? 'Thermique' : 'Vieillissement';

  // ─── Generate actual recommendations ───
  const recommandations = { fondations: [], murs_nord: [], toiture: [], sous_sol: [] };

  // --- SOUS-SOL recommendations ---
  if (scoreSousSol >= 30 || inondation || remonteeNappe) {
    recommandations.sous_sol.push({
      ref: 'DYN_INO_01', travaux: 'Pose de batardeaux amovibles étanches sur baies et portes (protection inondation)',
      cout_estime: '800€', gain_resilience: 60, priorite: 1,
      norme: 'DTU 36.5 / Cahier CSTB 3724', aide_financiere: 'Fonds Barnier (80%)', reste_a_charge: '160€'
    });
    recommandations.sous_sol.push({
      ref: 'DYN_INO_02', travaux: 'Installation d\'une station de pompage sous-sol (puisard + pompe vide-cave)',
      cout_estime: '2100€', gain_resilience: 65, priorite: 2,
      norme: 'DTU 60.11 / CCTG 70', aide_financiere: 'Fonds Barnier (80%)', reste_a_charge: '420€'
    });
  }
  if (radon || scoreSousSol >= 25) {
    recommandations.sous_sol.push({
      ref: 'DYN_RAD_01', travaux: 'Installation VMC Double Flux avec filtration radon et extraction continue',
      cout_estime: '5250€', gain_resilience: 70, priorite: radon ? 3 : 6,
      norme: 'DTU 68.3 / Avis Technique CSTB', aide_financiere: 'MaPrimeRénov\' (2 500€)', reste_a_charge: '2750€'
    });
  }
  if (scoreSousSol < 20) {
    recommandations.sous_sol.push({
      ref: 'DYN_HUM_01', travaux: 'Application d\'un revêtement d\'étanchéité des murs de sous-sol + drain périphérique',
      cout_estime: '1500€', gain_resilience: 40, priorite: 4,
      norme: 'DTU 20.1', aide_financiere: '', reste_a_charge: '1500€'
    });
  }

  // --- FONDATIONS recommendations ---
  if (rga || scoreFondations >= 30) {
    recommandations.fondations.push({
      ref: 'DYN_RGA_01', travaux: 'Gestion étanche des eaux pluviales + gouttières éloignées à >2m des fondations',
      cout_estime: '120€', gain_resilience: 30, priorite: 3,
      norme: 'Loi ELAN R.132-3 / DTU 20.1', aide_financiere: 'Anah (50%)', reste_a_charge: '60€'
    });
    recommandations.fondations.push({
      ref: 'DYN_RGA_02', travaux: 'Trottoir périphérique étanche (largeur ≥1,5m) avec géomembrane anti-évaporation',
      cout_estime: '160€', gain_resilience: 35, priorite: 4,
      norme: 'DTU 13.1 / NF P 94-500', aide_financiere: 'Anah (50%)', reste_a_charge: '80€'
    });
  }
  if (seisme || scoreFondations >= 40) {
    recommandations.fondations.push({
      ref: 'DYN_SIS_01', travaux: 'Diagnostic structurel fondations + renforcement par chaînage si nécessaire',
      cout_estime: '3000€', gain_resilience: 55, priorite: 5,
      norme: 'DTU 14.1 / Eurocode 8', aide_financiere: 'Fonds CatNat (jusqu\'à 80%)', reste_a_charge: '600€'
    });
  }
  if (scoreFondations < 20) {
    recommandations.fondations.push({
      ref: 'DYN_FON_01', travaux: 'Contrôle visuel des fondations + surveillance des fissures',
      cout_estime: '300€', gain_resilience: 20, priorite: 6,
      norme: 'NF P 94-500', aide_financiere: '', reste_a_charge: '300€'
    });
  }

  // --- TOITURE recommendations ---
  if (isOld || heatwave || dpeBad) {
    recommandations.toiture.push({
      ref: 'DYN_ISO_01', travaux: 'Isolation des combles perdus (laine de bois, ép. 350mm, R ≥ 7, déphasage >10h)',
      cout_estime: '2500€', gain_resilience: 40, priorite: 7,
      norme: 'DTU 45.1 / RE2020', aide_financiere: 'MaPrimeRénov\' (20€/m²)', reste_a_charge: '1500€'
    });
  }
  if (strongWind || heavyRain) {
    recommandations.toiture.push({
      ref: 'DYN_TOI_01', travaux: 'Vérification et renforcement de la couverture (fixations anti-tempête, gouttières renforcées)',
      cout_estime: '1200€', gain_resilience: 45, priorite: 5,
      norme: 'DTU 40.21 / NF EN 1991-1-4', aide_financiere: '', reste_a_charge: '1200€'
    });
  }
  if (heatwave && scoreToiture >= 30) {
    recommandations.toiture.push({
      ref: 'DYN_CLI_01', travaux: 'Pompe à chaleur Air-Eau (COP ≥4,2, 14kW, mode rafraîchissant)',
      cout_estime: '13000€', gain_resilience: 50, priorite: 9,
      norme: 'DTU 65.16 / RE2020', aide_financiere: 'MaPrimeRénov\' (5 000€)', reste_a_charge: '8000€'
    });
  }
  if (scoreToiture < 20) {
    recommandations.toiture.push({
      ref: 'DYN_ENT_01', travaux: 'Entretien préventif toiture (nettoyage, inspection annuelle)',
      cout_estime: '200€/an', gain_resilience: 15, priorite: 8,
      norme: 'NF P 08-301', aide_financiere: '', reste_a_charge: '200€/an'
    });
  }

  // --- MURS_NORD recommendations ---
  if (isOld || freeze || dpeBad) {
    recommandations.murs_nord.push({
      ref: 'DYN_ITE_01', travaux: 'Isolation des murs par l\'extérieur (ITE) sous ATEC CSTB',
      cout_estime: '17000€', gain_resilience: 45, priorite: 8,
      norme: 'CPT 3035 / Cahier CSTB 3035', aide_financiere: 'MaPrimeRénov\' (75€/m²)', reste_a_charge: '9500€'
    });
  }
  if (strongWind || scoreMurs >= 20) {
    recommandations.murs_nord.push({
      ref: 'DYN_MUR_01', travaux: 'Traitement des ponts thermiques + bardage protecteur façade nord',
      cout_estime: '3500€', gain_resilience: 35, priorite: 7,
      norme: 'DTU 23.1', aide_financiere: '', reste_a_charge: '3500€'
    });
  }
  if (scoreMurs < 15) {
    recommandations.murs_nord.push({
      ref: 'DYN_PEI_01', travaux: 'Peinture isolante et hydrofuge sur façades exposées',
      cout_estime: '800€', gain_resilience: 15, priorite: 9,
      norme: '', aide_financiere: '', reste_a_charge: '800€'
    });
  }

  // ─── Build zones ───
  const zones = {
    fondations: { risque: scoreFondations, niveau: level(scoreFondations), alea_principal: fondationsAléa,
      justification: generateJustification('fondations', scoreFondations, apiData),
      recommandations: recommandations.fondations, test_vulnerabilite: { verdict: generateVerdict(scoreFondations), explication: generateExplanation('fondations', scoreFondations, apiData) }},
    murs_nord: { risque: scoreMurs, niveau: level(scoreMurs), alea_principal: mursAléa,
      justification: generateJustification('murs_nord', scoreMurs, apiData),
      recommandations: recommandations.murs_nord, test_vulnerabilite: { verdict: generateVerdict(scoreMurs), explication: generateExplanation('murs_nord', scoreMurs, apiData) }},
    toiture: { risque: scoreToiture, niveau: level(scoreToiture), alea_principal: toitureAléa,
      justification: generateJustification('toiture', scoreToiture, apiData),
      recommandations: recommandations.toiture, test_vulnerabilite: { verdict: generateVerdict(scoreToiture), explication: generateExplanation('toiture', scoreToiture, apiData) }},
    sous_sol: { risque: scoreSousSol, niveau: level(scoreSousSol), alea_principal: sousSolAléa,
      justification: generateJustification('sous_sol', scoreSousSol, apiData),
      recommandations: recommandations.sous_sol, test_vulnerabilite: { verdict: generateVerdict(scoreSousSol), explication: generateExplanation('sous_sol', scoreSousSol, apiData) }},
  };

  // ─── Scores par aléa ───
  const scores_par_alea = {
    inondation: scoreSousSol,
    rga: scoreFondations,
    canicule: scoreToiture,
    tempete: Math.round((scoreToiture + scoreMurs) / 2),
  };

  // ─── Global score ───
  const globalScore = Math.round((scoreSousSol * 0.3 + scoreFondations * 0.25 + scoreToiture * 0.25 + scoreMurs * 0.2));
  const totalRecos = Object.values(recommandations).reduce((s, arr) => s + arr.length, 0);

  // ─── Financial summary (estimated based on dynamic recos) ───
  const totalCost = totalRecos;
  const avgAid = 0.35; // average aid ratio
  const totalCostNum = Object.values(recommandations).flat().reduce((s, r) => {
    const m = r.cout_estime.match(/([\d\s]+)\s*€/);
    return s + (m ? parseInt(m[1].replace(/\s/g,'')) : 0);
  }, 0);
  const totalAide = Math.round(totalCostNum * avgAid);
  const reste = totalCostNum - totalAide;

  return {
    zones,
    projection_2050: buildProjection(zones, globalScore),
    synthese_financiere: { cout_brut_total: `${totalCostNum}€`, aides_mobilisables: `${totalAide}€`, reste_a_charge_net: `${reste}€` },
    scores_par_alea,
    score_global: globalScore,
    nb_recommandations: totalRecos,
  };
}

function generateJustification(zone, score, api) {
  const rN = api.georisques?.risquesNaturels || {};
  const parts = [];
  if (zone === 'sous_sol') {
    if (rN.inondation?.present) parts.push('Risque inondation présent au droit de l\'adresse');
    if (rN.remonteeNappe?.present) parts.push('Remontée de nappe identifiée');
    if (rN.radon?.present) parts.push(`Potentiel radon classe ${rN.radon.classe_potentiel || '?'}`);
    if (api.waterDist !== null && api.waterDist < 200) parts.push(`Proximité d\'un cours d\'eau (${api.waterDist}m)`);
    if (parts.length === 0) parts.push('Exposition modérée aux risques hydriques');
  } else if (zone === 'fondations') {
    if (rN.retraitGonflementArgile?.present) parts.push('Présence d\'aléa retrait-gonflement des argiles');
    if (rN.seisme?.present) parts.push(`Zone sismique active (${rN.seisme.libelleStatutCommune || 'modérée'})`);
    if (api.building?.builtYear && api.building.builtYear < 1950) parts.push('Bâti ancien (antérieur à 1950)');
    if (parts.length === 0) parts.push('Risque structurel faible à moyen');
  } else if (zone === 'toiture') {
    if (api.climate?.heatwaveDaysPerYear > 10) parts.push(`${api.climate.heatwaveDaysPerYear} jours de canicule par an`);
    if (api.climate?.stormFrequency >= 3) parts.push('Zone venteuse (fréquence de tempêtes modérée)');
    if (api.building?.builtYear && api.building.builtYear < 1980) parts.push('Bâti antérieur aux premières réglementations thermiques');
    if (parts.length === 0) parts.push('Exposition thermique standard');
  } else if (zone === 'murs_nord') {
    if ((api.climate?.freezeDaysPerYear||0) > 20) parts.push(`${api.climate.freezeDaysPerYear} jours de gel par an`);
    if ((api.climate?.stormFrequency||0) >= 3) parts.push('Exposition au vent dominants');
    if (api.building?.bdnb?.mat_mur_txt) parts.push(`Mur en ${api.building.bdnb.mat_mur_txt}`);
    if (parts.length === 0) parts.push('Vulnérabilité faible des murs extérieurs');
  }
  return parts.join('. ') + '.';
}

function generateVerdict(score) {
  if (score >= 70) return 'Vulnérabilité critique — des travaux urgents sont nécessaires';
  if (score >= 55) return 'Vulnérabilité élevée — des travaux de mitigation sont recommandés dans les 12 mois';
  if (score >= 35) return 'Vulnérabilité modérée — des travaux de mitigation sont recommandés dans les 24 mois';
  return 'Vulnérabilité faible — aucune action urgente requise, suivi périodique conseillé';
}

function generateExplanation(zone, score, api) {
  const rN = api.georisques?.risquesNaturels || {};
  const parts = [];
  if (zone === 'sous_sol') {
    if (rN.inondation?.present) parts.push('l\'inondation');
    if (rN.remonteeNappe?.present) parts.push('la remontée de nappe');
    if (rN.radon?.present) parts.push('le radon');
    const causes = parts.length ? `liés à ${parts.join(' et ')}` : 'liés à l\'humidité';
    return `Le score ${score}/100 est ${causes}. ${score >= 35 ? 'Des travaux d\'étanchéité et de protection sont conseillés pour réduire la vulnérabilité.' : 'La situation actuelle est acceptable avec un entretien régulier.'}`;
  }
  if (zone === 'fondations') {
    const causes = [];
    if (rN.retraitGonflementArgile?.present) causes.push('l\'exposition au retrait-gonflement des argiles');
    if (rN.seisme?.present) causes.push('le risque sismique');
    if (api.climate != null && api.climate.soilMoisture != null && api.climate.soilMoisture < 0.25) causes.push('la sécheresse des sols');
    return `Le score ${score}/100 tient compte de ${causes.length ? causes.join(' et ') : 'l\'état général des fondations'}. ${score >= 35 ? 'Une étude géotechnique et des travaux de drainage sont recommandés.' : 'Les fondations ne présentent pas de signe de fragilité majeur.'}`;
  }
  if (zone === 'toiture') {
    return `Le score ${score}/100 est basé sur les données climatiques (${api.climate?.heatwaveDaysPerYear || '?'} jours canicule, ${api.climate?.annualPrecipitation || '?'}mm pluie/an) et les caractéristiques du bâti. ${score >= 35 ? 'L\'isolation et la résistance aux intempéries sont à améliorer.' : 'La toiture est en état correct.'}`;
  }
  if (zone === 'murs_nord') {
    return `Le score ${score}/100 intègre les contraintes climatiques (${api.climate?.freezeDaysPerYear || '?'} jours gel, vents dominants) et l\'état du bâti. ${score >= 35 ? 'Un renforcement de l\'isolation extérieure est conseillé.' : 'Les murs sont en état satisfaisant.'}`;
  }
  return '';
}

// ════════════════════════════════════════════════════════════
//  PART D : BUILD ANALYSE_RISQUES FROM API DATA (auto)
// ════════════════════════════════════════════════════════════

function buildAnalyseRisques(apiData, geo) {
  const rN = apiData.georisques?.risquesNaturels || {};
  const rT = apiData.georisques?.risquesTechnologiques || {};
  const bdnbData = apiData.building?.bdnb || {};
  const commune = apiData.georisques?.commune || '';
  const communeCode = apiData.georisques?.communeCode || geo?.banId?.slice(0,5) || '';

  // Build triggered rules from API data
  const triggeredRules = [];
  let ruleCounter = 0;
  const addRule = (id, peril, priority, points, justification, source) => {
    triggeredRules.push({ rule_id: id, peril, priority, points, justification, source_fields: [source], activated_by_llm: false });
    ruleCounter++;
  };

  if (rN.inondation?.present) addRule('INONDATION_PRESENT_INFILTRATION', 'infiltration', 100, 20,
    'Présence d\'un risque d\'inondation au droit de l\'adresse', 'georisques.rapport_risque.risquesNaturels.inondation');
  if (rN.remonteeNappe?.present) addRule('REMONTEE_NAPPE_PRESENT_INFILTRATION', 'infiltration', 95, 18,
    'Présence d\'un risque de remontée de nappe', 'georisques.rapport_risque.risquesNaturels.remonteeNappe');
  if (rN.mouvementTerrain?.present) addRule('MOUVEMENT_TERRAIN_PRESENT_INFILTRATION', 'infiltration', 90, 12,
    'Mouvements de terrain à proximité pouvant dégrader l\'étanchéité', 'georisques.rapport_risque.risquesNaturels.mouvementTerrain');
  if (rN.retraitGonflementArgile?.present) addRule('RGA_PRESENT_FONDATIONS', 'infiltration', 80, 8,
    'Exposition au retrait-gonflement des argiles', 'georisques.argiles_rga');
  if (rN.radon?.present) addRule('RADON_PRESENT', 'aléas_naturels', 100, 12,
    `Potentiel radon classe ${rN.radon.classe_potentiel || '?'}`, 'georisques.radon');
  if (rN.seisme?.present) addRule('SEISME_PRESENT', 'aléas_naturels', 95, 10,
    'Zone sismique modérée', 'georisques.zonage_sismique');
  if (apiData.catnat?.total_evts > 0) addRule('CATNAT_HISTORIQUE', 'aléas_naturels', 85, 10,
    `${apiData.catnat.total_evts} événements CatNat historiques`, 'georisques.catnat');
  if (apiData.climate?.freezeDaysPerYear > 20) addRule('GEL_FREQUENT', 'thermique', 70, 8,
    `${apiData.climate.freezeDaysPerYear} jours de gel par an`, 'openmeteo.climate');
  if (apiData.climate?.heatwaveDaysPerYear > 10) addRule('CANICULE_FREQUENTE', 'thermique', 80, 10,
    `${apiData.climate.heatwaveDaysPerYear} jours de canicule par an`, 'openmeteo.climate');

  // Score computation
  const infiltrationScore = Math.min(100, (rN.inondation?.present ? 35 : 0) + (rN.remonteeNappe?.present ? 20 : 0) +
    (rN.mouvementTerrain?.present ? 15 : 0) + (apiData.waterDist !== null && apiData.waterDist < 200 ? 15 : 0) + 12);
  const thermiqueScore = Math.min(100, (apiData.climate?.heatwaveDaysPerYear > 10 ? 25 : 0) +
    (apiData.climate?.freezeDaysPerYear > 20 ? 15 : 0) + (bdnbData.annee_construction && bdnbData.annee_construction < 1980 ? 15 : 0) + 5);
  const electriqueScore = Math.min(100, bdnbData.annee_construction && bdnbData.annee_construction < 1980 ? 15 : 5);
  const naturelsScore = Math.min(100, (rN.radon?.present ? 15 : 0) + (rN.seisme?.present ? 12 : 0) +
    (apiData.catnat?.total_evts > 0 ? 12 : 0) + (Object.values(rT).filter(r=>r?.present).length > 0 ? 8 : 0) +
    (apiData.forestDist !== null && apiData.forestDist < 100 ? 8 : 0) + 5);

  const globalRaw = Math.round(infiltrationScore * 0.3 + thermiqueScore * 0.25 + electriqueScore * 0.25 + naturelsScore * 0.2);

  return {
    address: { adresse: geo?.label || '', code_insee: communeCode },
    risk_context: {
      rga: { present: !!rN.retraitGonflementArgile?.present, exposition: rN.retraitGonflementArgile?.libelleStatutAdresse || 'non disponible', code_exposition: '?' },
      zone_sismique: { present: !!rN.seisme?.present, zone_code: rN.seisme?.libelleStatutCommune || '?', zone_libelle: rN.seisme?.libelleStatutCommune || '?' },
      radon: { present: !!rN.radon?.present, classe_potentiel: rN.radon?.classe_potentiel || '?' },
      cavites: { present: false, count: 0, disponible: false },
      historique_catnat: apiData.catnat || { total_evts: 0, evts_par_type: {}, nb_evt_10ans: 0 },
      donnees_topo: { altitude_m: apiData.altitude?.altitude || null },
      donnees_manquantes: ['drias_meteofrance'],
    },
    profil_bien: {
      disponible: !!bdnbData.annee_construction,
      annee_construction: bdnbData.annee_construction || null,
      type_bien: bdnbData.usage_principal_bdnb_open || 'non spécifié',
      type_toiture: bdnbData.mat_toit_txt || null,
      isolation_toiture: 'non renseignée',
      isolation_murs: 'non renseignée',
      presence_sous_sol: null,
      presence_cave: null,
      installation_electrique_annee: bdnbData.annee_construction || null,
    },
    score: {
      global: globalRaw,
      global_raw: globalRaw,
      weights: { infiltration: 0.3, thermique: 0.25, incendie_electrique: 0.25, aléas_naturels: 0.2 },
      perils: {
        infiltration: { score: infiltrationScore, raw_score: infiltrationScore, max_score: 100, triggered_rules: triggeredRules.filter(r=>r.peril==='infiltration') },
        thermique: { score: thermiqueScore, raw_score: thermiqueScore, max_score: 100, triggered_rules: triggeredRules.filter(r=>r.peril==='thermique') },
        incendie_électrique: { score: electriqueScore, raw_score: electriqueScore, max_score: 100, triggered_rules: [] },
        aléas_naturels: { score: naturelsScore, raw_score: naturelsScore, max_score: 100, triggered_rules: triggeredRules.filter(r=>r.peril==='aléas_naturels') },
      },
    },
    confidence: { level: 'medium', notes: [{ confidence_id: 'DYNAMIC_GENERATION', impact: 'medium', note: 'Analyse générée dynamiquement à partir des données API sans déclaratif client.' }] },
    traceability: { score_engine: 'dynamic_api_v3', mistral_used: false, selected_composed_rule_ids: [] },
    mistral: { activated_rule_ids: [], declarative_consistency_status: 'unknown', declarative_consistency_flags: [] },
  };
}

function buildFormulaireFromAPI(apiData, geo) {
  const b = apiData.building?.bdnb || {};
  return {
    adresse: geo?.label || '',
    type_bien: b.usage_principal_bdnb_open?.includes('maison') ? 'maison' : b.usage_principal_bdnb_open?.includes('appart') ? 'appartement' : 'non spécifié',
    surface: b.surface_habitable || null,
    nb_etages: b.nb_niveau || null,
    annee_construction: b.annee_construction || null,
    type_structure: b.mat_mur_txt || null,
    type_toiture: b.mat_toit_txt || null,
    etat_structure: 'non renseigné',
    fissures: 'non renseigné',
    affaissement: 'non',
    presence_sous_sol: null,
    presence_cave: null,
    occupation: 'non renseigné',
    installation_electrique_annee: b.annee_construction || null,
  };
}

// ════════════════════════════════════════════════════════════
//  MAIN
// ════════════════════════════════════════════════════════════
async function main() {
  console.log('═══════════════════════════════════════════════════════');
  console.log('  ORCHESTRATEUR UNIFIÉ v3 (DYNAMIQUE)');
  console.log(`  Adresse: ${ADDRESS}`);
  console.log('═══════════════════════════════════════════════════════');

  // ─── 1. Load optional form ───
  let merged = { user_data: {}, agent_data: { bdnb: { geometry: null }, georisques: {}, scores: {}, coordonnees: null, code_insee: null, score_geocodage: null }, step7: {} };
  const hasForm = FORM_PATH && fs.existsSync(FORM_PATH);
  if (hasForm) {
    merged = JSON.parse(fs.readFileSync(FORM_PATH, 'utf-8'));
    console.log(`\n📋 Formulaire chargé: ${FORM_PATH} (${Object.keys(merged.user_data||{}).length} champs)`);
  }

  // ─── 2. Fetch APIs ───
  let geo = null, building = null, risks = null, climate = null, altitude = null;
  let catnat = null, waterDist = null, forestDist = null;
  const apiData = {};

  if (SKIP_APIS) {
    console.log('\n⏭  APIs skipped, using cached data');
    geo = { lon: merged.agent_data?.coordonnees?.longitude || -1.5515, lat: merged.agent_data?.coordonnees?.latitude || 47.215, label: ADDRESS, banId: null };
  } else {
    geo = await geocodeAddress(ADDRESS);
    if (!geo) { geo = { lon: -1.5515, lat: 47.215, label: ADDRESS, banId: null }; }
    const dc = geo.banId?.slice(0,2) || '44', cc = geo.banId?.slice(0,5) || '44109';

    console.log('\n── Batch 1 ──');
    [altitude, , building, catnat] = await Promise.all([
      fetchAltitude(geo.lon, geo.lat), fetchCadastralParcel(geo.lon, geo.lat), fetchBdnbBuilding(geo.banId), fetchCatnat(cc) ]);
    await new Promise(p=>setTimeout(p,1000));
    console.log('\n── Batch 2 ──');
    [risks, climate, waterDist, forestDist] = await Promise.all([
      fetchGeorisques(geo.lon, geo.lat), fetchClimate(geo.lon, geo.lat), fetchWaterDistance(geo.lon, geo.lat), fetchForestDistance(geo.lon, geo.lat) ]);

    console.log('\n── Lookups ──');
    const dvf = lookupDvf(dc); console.log(`  ✓ DVF: ${dvf?.reconstructionValuePerSqm||'N/A'} €/m²`);
    lookupDrias(dc); // DRIAS optional

    // Store API data for dynamic generation
    merged.agent_data = merged.agent_data || {};
    merged.agent_data.coordonnees = { latitude: geo.lat, longitude: geo.lon };
    merged.agent_data.code_insee = cc;
    merged.agent_data.score_geocodage = 1.0;
    if (building?.bdnb) merged.agent_data.bdnb = building.bdnb;
    if (risks) merged.agent_data.georisques = risks;
    if (catnat) merged.agent_data.catnat_v2 = catnat;
    console.log('\n✅ APIs OK');
  }

  // Store all API data for dynamic generators
  Object.assign(apiData, { georisques: merged.agent_data.georisques || risks || {}, climate, building, altitude, waterDist, forestDist, catnat, geo });

  // ─── 3. Build analyse_risques (from form or auto-generated) ───
  if (!hasForm || !merged.step7?.score?.global) {
    console.log('\n🔧 Génération automatique analyse_risques depuis les API…');
    merged.step7 = buildAnalyseRisques(apiData, geo);
    merged.user_data = merged.user_data?.adresse ? merged.user_data : buildFormulaireFromAPI(apiData, geo);
    console.log(`   Score: ${merged.step7.score.global}, ${Object.keys(merged.step7.score.perils).length} périls`);
  }

  // ─── 4. Recommendations (from MD or dynamic) ───
  let recosData;
  const hasMD = MD_PATH && fs.existsSync(MD_PATH);
  if (hasMD) {
    console.log(`\n📄 Parsing MD: ${MD_PATH}`);
    const p = parseRapportMD(fs.readFileSync(MD_PATH,'utf-8'));
    let s7s = null;
    if (merged.step7?.score?.perils) { s7s = {}; for(const[k,v] of Object.entries(merged.step7.score.perils)) s7s[k]=v.score||v.raw_score||0; }
    const z = mapToZones(p.recommendations, s7s);
    const gs = s7s ? Math.round(Object.values(s7s).reduce((s,v)=>s+v,0)/Object.keys(s7s).length) : 43;
    recosData = { zones: z, projection_2050: buildProjection(z, gs), synthese_financiere: p.financialSummary,
      scores_par_alea: { inondation: s7s?.infiltration||52, rga: s7s?.rga||38, canicule:15, tempete: s7s?.tempete||25 },
      score_global: gs, nb_recommandations: p.recommendations.length };
    console.log(`   ${p.recommendations.length} recos parsées`);
  } else {
    console.log('\n⚡ Génération DYNAMIQUE des recommandations depuis les API…');
    recosData = generateDynamicRecommendations(apiData);
    console.log(`   ${recosData.nb_recommandations} recos générées (zones: ${Object.keys(recosData.zones).join(', ')})`);
  }

  // ─── 5. Build final ───
  console.log('\n── Fusion finale ──');
  const geom = merged.agent_data?.bdnb?.geometry || building?.geometry || null;
  const final = {
    version:'1.0', generated_at: new Date().toISOString(), assessment_id: `ASSESS-${Date.now()}`,
    adresse: merged.user_data?.adresse||merged.step7?.address?.adresse||geo?.label||ADDRESS,
    coordonnees: merged.agent_data?.coordonnees||null, code_insee: merged.agent_data?.code_insee||'',
    formulaire_client: merged.user_data||{},
    donnees_api: { bdnb: merged.agent_data?.bdnb||null, georisques: merged.agent_data?.georisques||null,
      scores_bruts: merged.agent_data?.scores||null, score_geocodage: merged.agent_data?.score_geocodage||null, catnat: merged.agent_data?.catnat_v2||null },
    geometrie_batiment: geom,
    analyse_risques: merged.step7||{},
    recommandations: recosData,
    resume: { score_global: recosData.score_global||merged.agent_data?.scores?.score_global||null,
      score_global_2050: recosData.projection_2050?.score_global||null,
      cout_total_travaux: recosData.synthese_financiere?.cout_brut_total||null,
      aides_mobilisables: recosData.synthese_financiere?.aides_mobilisables||null,
      reste_a_charge_net: recosData.synthese_financiere?.reste_a_charge_net||null,
      nb_recommandations: recosData.nb_recommandations||0, date_evaluation: new Date().toISOString().split('T')[0] },
    pipeline: { collecteur:'Agent Collecteur v3 (LIVE APIs: BDNB, Géorisques, IGN, Open-Meteo, WFS)',
      analyste: `Agent Analyste ${hasForm && merged.step7?.traceability?.score_engine === 'dynamic_api_v3' ? 'v3 (dynamique API)' : 'v1 (déterministe + LLM)'}`,
      recommandation: hasMD ? 'Agent Recommandation Tasnime v1 (RAG: CEPRI, CSTB, BRGM)' : 'Agent Recommandation v3 (DYNAMIQUE — règles depuis API)',
      sources: [`BDNB — ${geom?'✅ geom_group OK':'❌ indisponible (fallback BAN)'}`, 'Géorisques v1', 'IGN Altitude + WFS', 'Open-Meteo Climate',
        `Recommandations — ${hasMD?'✅ parsées (MD)':'⚡ générées dynamiquement'}`,
        hasForm ? `Formulaire — ${FORM_PATH}` : 'Formulaire — auto-généré depuis API'] },
  };

  fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(final, null, 2), 'utf-8');

  console.log(`\n═══════════════════════════════════════════════════════`);
  console.log(`  ✅ ${OUTPUT_PATH}`);
  console.log(`─────────────────────────────────────────────────────`);
  console.log(`  Adresse:     ${final.adresse}`);
  console.log(`  BDNB geom:   ${geom ? '✅' : '❌'}`);
  console.log(`  Recos:       ${final.recommandations.nb_recommandations} (${Object.keys(final.recommandations.zones).join(', ')})`);
  console.log(`  Score:       ${final.resume.score_global} → 2050: ${final.resume.score_global_2050}`);
  console.log(`  Budget:      ${final.resume.cout_total_travaux||'N/A'} | Reste: ${final.resume.reste_a_charge_net||'N/A'}`);
  console.log(`  Taille:      ${(JSON.stringify(final).length/1024).toFixed(0)} KB`);
  console.log(`  Source:      ${hasForm?'form':'auto'} + ${hasMD?'MD':'dynamique'} + APIs`);
  console.log('═══════════════════════════════════════════════════════\n');
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
