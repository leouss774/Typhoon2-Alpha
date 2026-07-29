const API_BASE = 'http://localhost:8000';
const BAN_URL = 'https://api-adresse.data.gouv.fr/search';

let map = null;
let mode = 'single';
let markers = [];
let currentReport = null;
let layerSources = {};
let selectedCoord = null;

const TIER_CONFIG = {
  faible: { color: '#10b981' },
  modere: { color: '#f59e0b' },
  eleve:  { color: '#fb8c00' },
  critique: { color: '#ef4444' },
};

const HAZARD_LEGEND = {
  rga_ground_movement: { label: 'Mouvement de terrain', color: '#a78bfa' },
  flood: { label: 'Inondation', color: '#60a5fa' },
  wildfire_wind: { label: 'Feu de forêt / Vent', color: '#fb923c' },
};

const addressInput = document.getElementById('address-input');
const suggestions = document.getElementById('suggestions');
const modeSingleBtn = document.getElementById('mode-single');
const modeMultiBtn = document.getElementById('mode-multi');
const modeInfoText = document.getElementById('mode-info-text');
const assessBtn = document.getElementById('assess-btn');
const statusLine = document.getElementById('status-line');
const resultsPanel = document.getElementById('results-panel');
const legend = document.getElementById('map-legend');
const layerPanel = document.getElementById('layer-panel');
const layerToggles = document.getElementById('layer-toggles');
const pointsCount = document.getElementById('points-count');
const clearPointsBtn = document.getElementById('clear-points');

function initMap() {
  const stored = localStorage.getItem('mapbox_token');
  if (stored) document.getElementById('mapbox-token').value = stored;

  const token = document.getElementById('mapbox-token').value.trim();
  if (!token) {
    document.getElementById('status-line').textContent = 'Veuillez entrer votre token Mapbox ci-dessus et cliquer sur Appliquer';
    return;
  }
  mapboxgl.accessToken = token;
  if (map) { map.remove(); map = null; }

  map = new mapboxgl.Map({
    container: 'map',
    style: 'mapbox://styles/mapbox/light-v11',
    center: [2.3333, 48.8667],
    zoom: 11,
  });
  map.addControl(new mapboxgl.NavigationControl(), 'bottom-right');
  map.on('load', () => {
    map.on('click', onMapClick);
    buildLayerToggles();
  });
}

document.getElementById('token-apply-btn').addEventListener('click', () => {
  localStorage.setItem('mapbox_token', document.getElementById('mapbox-token').value.trim());
  initMap();
});

// ========== MAP CLICK ==========
function onMapClick(e) {
  if (mode === 'single') {
    clearMarkers();
    selectedCoord = { lat: e.lngLat.lat, lon: e.lngLat.lng };
    addMarker(e.lngLat.lat, e.lngLat.lng, 'A');
    reverseGeocode(e.lngLat.lat, e.lngLat.lng);
  } else {
    const n = markers.length + 1;
    addMarker(e.lngLat.lat, e.lngLat.lng, String(n));
    updatePointsUI();
  }
}

function addMarker(lat, lon, label) {
  const el = document.createElement('div');
  el.className = 'pin-marker';
  el.textContent = label;
  const marker = new mapboxgl.Marker({ element: el, draggable: true })
    .setLngLat([lon, lat])
    .addTo(map);
  el.addEventListener('click', (ev) => {
    ev.stopPropagation();
    if (mode === 'multi') {
      marker.remove();
      markers = markers.filter(m => m !== marker);
      renumberMarkers();
      updatePointsUI();
    }
  });
  markers.push(marker);
  assessBtn.disabled = false;
}

function renumberMarkers() {
  markers.forEach((m, i) => {
    m.getElement().textContent = String(i + 1);
  });
}

function clearMarkers() {
  markers.forEach(m => m.remove());
  markers = [];
  selectedCoord = null;
  assessBtn.disabled = (mode === 'multi');
  updatePointsUI();
}

function updatePointsUI() {
  if (mode === 'multi') {
    pointsCount.textContent = `${markers.length} point(s)`;
    assessBtn.disabled = markers.length < 3;
  }
}

clearPointsBtn.addEventListener('click', clearMarkers);

// ========== REVERSE GEOCODE ==========
function reverseGeocode(lat, lon) {
  fetch(`${BAN_URL}/reverse/?lat=${lat}&lon=${lon}`)
    .then(r => r.json())
    .then(data => {
      if (data.features && data.features.length > 0)
        addressInput.value = data.features[0].properties.label;
    })
    .catch(() => {});
}

// ========== BAN AUTOCOMPLETE ==========
let banTimeout = null;
function updateAssessBtn() {
  if (mode === 'single') {
    const hasAddr = addressInput.value.trim().length > 0;
    assessBtn.disabled = !(hasAddr || selectedCoord);
  }
}

addressInput.addEventListener('input', () => {
  clearTimeout(banTimeout);
  const q = addressInput.value.trim();
  updateAssessBtn();
  if (q.length < 3) { suggestions.innerHTML = ''; return; }
  banTimeout = setTimeout(() => {
    fetch(`${BAN_URL}?q=${encodeURIComponent(q)}&limit=5`)
      .then(r => r.json())
      .then(data => {
        suggestions.innerHTML = '';
        (data.features || []).forEach(f => {
          const div = document.createElement('div');
          div.className = 'ban-suggestion';
          div.textContent = f.properties.label;
          div.dataset.lat = f.geometry.coordinates[1];
          div.dataset.lon = f.geometry.coordinates[0];
          div.addEventListener('click', () => {
            addressInput.value = f.properties.label;
            suggestions.innerHTML = '';
            map.flyTo({ center: [f.geometry.coordinates[0], f.geometry.coordinates[1]], zoom: 16 });
            if (mode === 'single') {
              clearMarkers();
              selectedCoord = { lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] };
              addMarker(f.geometry.coordinates[1], f.geometry.coordinates[0], 'A');
            }
          });
          suggestions.appendChild(div);
        });
      })
      .catch(() => {});
  }, 300);
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('#search-bar')) suggestions.innerHTML = '';
});

// ========== MODE TOGGLE ==========
modeSingleBtn.addEventListener('click', () => setMode('single'));
modeMultiBtn.addEventListener('click', () => setMode('multi'));

function setMode(newMode) {
  mode = newMode;
  modeSingleBtn.classList.toggle('active', mode === 'single');
  modeMultiBtn.classList.toggle('active', mode === 'multi');
  clearMarkers();
  assessBtn.disabled = true;
  document.getElementById('multi-controls').classList.toggle('hidden', mode === 'single');

  if (mode === 'single') {
    modeInfoText.textContent = 'Cliquez sur la carte ou saisissez une adresse';
    legend.classList.add('hidden');
    updateAssessBtn();
  } else {
    modeInfoText.textContent = 'Cliquez sur la carte pour ajouter des points (min. 3)';
    legend.classList.remove('hidden');
    pointsCount.textContent = '0 point(s)';
  }
}

// ========== ASSESS ==========
assessBtn.addEventListener('click', async () => {
  assessBtn.disabled = true;
  assessBtn.textContent = 'Analyse en cours…';
  statusLine.textContent = 'Évaluation en cours…';
  resultsPanel.classList.add('hidden');

  let payload;

  if (mode === 'single') {
    const addr = addressInput.value.trim();
    if (!addr && !selectedCoord) {
      statusLine.textContent = 'Saisissez une adresse ou cliquez sur la carte';
      assessBtn.disabled = false;
      assessBtn.textContent = '🔍 Évaluer';
      return;
    }
    payload = { mode: 'single', address: addr, points: selectedCoord ? [selectedCoord] : [] };
  } else {
    if (markers.length < 3) {
      statusLine.textContent = 'Placez au moins 3 points sur la carte';
      assessBtn.disabled = false;
      assessBtn.textContent = '🔍 Évaluer';
      return;
    }
    const pts = markers.map(m => {
      const lngLat = m.getLngLat();
      return { lat: lngLat.lat, lon: lngLat.lng };
    });
    payload = { mode: 'multi', points: pts };
  }

  try {
    const res = await fetch(`${API_BASE}/mvp/assess`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`Erreur ${res.status}: ${await res.text()}`);
    const report = await res.json();
    currentReport = report;
    statusLine.textContent = '';
    if (mode === 'multi') clearMarkers();
    renderReport(report);
  } catch (err) {
    statusLine.textContent = `Erreur : ${err.message}`;
  } finally {
    assessBtn.disabled = false;
    assessBtn.textContent = '🔍 Évaluer';
  }
});

// ========== RENDER REPORT ==========
function renderReport(report) {
  resultsPanel.classList.remove('hidden');

  document.getElementById('rp-address').textContent = report.address;
  const c = report.all_buildings.length > 0
    ? `${report.all_buildings[0].lat.toFixed(5)}, ${report.all_buildings[0].lon.toFixed(5)}`
    : '—';
  document.getElementById('rp-coords').textContent = c;

  const fill = document.getElementById('rp-score-ring-fill');
  const score = report.score_global;
  const tier = report.tier;
  const deg = Math.min(score / 100 * 360, 360);
  const tc = TIER_CONFIG[tier]?.color || '#888';
  fill.style.background = `conic-gradient(${tc} ${deg}deg, var(--surface-alt) ${deg}deg)`;
  document.getElementById('rp-score-val').textContent = score;
  document.getElementById('rp-score-tier').textContent = tier;

  document.getElementById('rp-stat-buildings').textContent = report.nb_buildings;
  document.getElementById('rp-stat-flagged').textContent = report.flagged_buildings.length;
  document.getElementById('rp-stat-duration').textContent = `${report.duration_seconds}s`;

  const chartContainer = document.getElementById('hazard-chart');
  chartContainer.innerHTML = '';
  for (const h of report.hazard_breakdown) {
    const color = h.mean_score >= 75 ? '#ef4444' : h.mean_score >= 50 ? '#fb8c00' : h.mean_score >= 25 ? '#f59e0b' : '#10b981';
    const item = document.createElement('div');
    item.className = 'hazard-bar-item';
    item.innerHTML = `<div class="hazard-name">${h.hazard.replace(/_/g, ' ')}</div>
      <div class="hazard-track"><div class="hazard-fill" style="width:${h.mean_score}%;background:${color}"></div></div>
      <div class="hazard-mean">${h.mean_score}</div>`;
    chartContainer.appendChild(item);
  }
  document.getElementById('rp-hazard-count').textContent = `${report.hazard_breakdown.length} aléas`;

  const hazardBody = document.querySelector('#hazard-table tbody');
  hazardBody.innerHTML = '';
  for (const h of report.hazard_breakdown) {
    hazardBody.innerHTML += `<tr><td>${h.hazard.replace(/_/g, ' ')}</td><td>${h.min_score}</td><td>${h.max_score}</td><td>${h.mean_score}</td><td>${h.pct_high_or_critical}%</td>`;
  }

  const flaggedBody = document.querySelector('#flagged-table tbody');
  flaggedBody.innerHTML = '';
  for (const b of report.flagged_buildings) {
    const cfg = TIER_CONFIG[b.tier] || { color: '#888' };
    flaggedBody.innerHTML += `<tr>
      <td>${b.address_label || `${b.lat.toFixed(4)}, ${b.lon.toFixed(4)}`}</td>
      <td><strong style="color:${cfg.color}">${b.score_global}</strong></td>
      <td style="color:${cfg.color}">${b.tier}</td>
      <td>${b.worst_peril || '—'}</td>`;
  }
  document.getElementById('rp-flagged-count').textContent = `${report.flagged_buildings.length} bâtiment(s)`;

  const recList = document.getElementById('recommendations');
  recList.innerHTML = '';
  for (const rec of report.recommendations) {
    recList.innerHTML += `<li>${rec}</li>`;
  }

  const now = new Date().toISOString().split('T')[0];
  document.getElementById('rp-meta-body').innerHTML = [
    ['Adresse', report.address],
    ['Méthode', report.enumeration_method],
    ['OK / Erreurs', `${report.nb_ok} / ${report.nb_errors}`],
    ['Durée', `${report.duration_seconds}s`],
    ['Évaluation', now],
  ].map(([l, v]) => `<div class="rp-meta-row"><span class="rp-meta-label">${l}</span><span class="rp-meta-value">${v}</span></div>`).join('');

  document.getElementById('rp-footer').textContent = `Évaluation du ${now}`;

  document.getElementById('rpExportBtn').onclick = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `typhoon-${report.address.slice(0, 20).replace(/[^a-zA-Z0-9]/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  renderMapLayers(report);
}

// ========== MAP LAYERS ==========
function renderMapLayers(report) {
  removeMapLayers();

  if (!report.all_buildings || report.all_buildings.length === 0) return;
  const buildings = report.all_buildings;

  const features = buildings.map(b => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [b.lon, b.lat] },
    properties: {
      score: b.score_global, tier: b.tier,
      label: b.address_label || '',
      color: TIER_CONFIG[b.tier]?.color || '#888',
      worst_peril: b.worst_peril || '—',
    },
  }));

  map.addSource('buildings', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features },
  });

  map.addLayer({
    id: 'buildings-circle',
    type: 'circle',
    source: 'buildings',
    paint: {
      'circle-radius': ['case', ['==', ['get', 'tier'], 'critique'], 12, 8],
      'circle-color': ['get', 'color'],
      'circle-opacity': 0.85,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#fff',
    },
  });

  map.on('click', 'buildings-circle', (e) => {
    const p = e.features[0].properties;
    const recos = report.recommendations && report.recommendations.length > 0
      ? `<strong>Recommandations</strong><br><ul style="margin:4px 0 0;padding-left:16px;font-size:0.72rem">${report.recommendations.slice(0, 3).map(r => `<li>${r}</li>`).join('')}</ul>`
      : '';
    new mapboxgl.Popup({ maxWidth: '300px' })
      .setLngLat(e.features[0].geometry.coordinates)
      .setHTML(`
        <div style="font-family:Inter,sans-serif;font-size:0.8rem">
          <strong style="color:${p.color}">${p.label || 'Bâtiment'}</strong>
          <div style="margin-top:4px;display:flex;gap:8px;font-size:0.7rem">
            <span>Score <strong>${p.score}</strong></span>
            <span>Tier <strong style="color:${p.color}">${p.tier}</strong></span>
          </div>
          <div style="margin-top:2px;font-size:0.65rem;color:#888">Pire aléa : ${p.worst_peril}</div>
          ${recos}
          <div style="margin-top:4px;font-size:0.6rem;color:#aaa">Sources : BDNB · Géorisques · IGN · Open-Meteo</div>
        </div>
      `)
      .addTo(map);
  });

  map.on('mouseenter', 'buildings-circle', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'buildings-circle', () => { map.getCanvas().style.cursor = ''; });

  // Hazard zone fill
  if (report.hazard_breakdown && report.hazard_breakdown.length > 0) {
    const avgHazard = report.hazard_breakdown.reduce((s, h) => s + h.mean_score, 0) / report.hazard_breakdown.length;
    const hazardColor = avgHazard >= 75 ? '#ef4444' : avgHazard >= 50 ? '#fb8c00' : avgHazard >= 25 ? '#f59e0b' : '#10b981';

    const lats = buildings.map(b => b.lat);
    const lons = buildings.map(b => b.lon);
    const cLat = (Math.min(...lats) + Math.max(...lats)) / 2;
    const cLon = (Math.min(...lons) + Math.max(...lons)) / 2;
    const dLat = Math.max(Math.max(...lats) - Math.min(...lats), 0.002);
    const dLon = Math.max(Math.max(...lons) - Math.min(...lons), 0.002);

    map.addSource('hazard-zone', {
      type: 'geojson',
      data: {
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [cLon - dLon, cLat - dLat],
            [cLon + dLon, cLat - dLat],
            [cLon + dLon, cLat + dLat],
            [cLon - dLon, cLat + dLat],
            [cLon - dLon, cLat - dLat],
          ]],
        },
        properties: { color: hazardColor },
      },
    });

    map.addLayer({
      id: 'hazard-fill',
      type: 'fill',
      source: 'hazard-zone',
      paint: {
        'fill-color': ['get', 'color'],
        'fill-opacity': 0.12,
      },
    });

    map.addLayer({
      id: 'hazard-outline',
      type: 'line',
      source: 'hazard-zone',
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 1.5,
        'line-opacity': 0.4,
        'line-dasharray': [3, 2],
      },
    });
  }

  if (buildings.length === 1) {
    map.flyTo({ center: [buildings[0].lon, buildings[0].lat], zoom: 16 });
  } else {
    const bounds = new mapboxgl.LngLatBounds();
    buildings.forEach(b => bounds.extend([b.lon, b.lat]));
    map.fitBounds(bounds, { padding: 60, maxZoom: 16 });
  }

  layerPanel.classList.remove('hidden');
}

function removeMapLayers() {
  ['buildings-circle', 'hazard-fill', 'hazard-outline'].forEach(id => {
    if (map.getLayer(id)) map.removeLayer(id);
  });
  ['buildings', 'hazard-zone'].forEach(id => {
    if (map.getSource(id)) map.removeSource(id);
  });
}

function toggleLayer(layerId, checked) {
  if (layerId === 'buildings' && map.getLayer('buildings-circle')) {
    map.setLayoutProperty('buildings-circle', 'visibility', checked ? 'visible' : 'none');
  }
  if (layerId === 'hazards' && map.getLayer('hazard-fill')) {
    map.setLayoutProperty('hazard-fill', 'visibility', checked ? 'visible' : 'none');
    map.setLayoutProperty('hazard-outline', 'visibility', checked ? 'visible' : 'none');
  }
}

function buildLayerToggles() {
  layerToggles.innerHTML = `
    <label class="layer-toggle"><input type="checkbox" checked data-layer="buildings"> Bâtiments</label>
    <label class="layer-toggle"><input type="checkbox" data-layer="hazards"> Zones à risque</label>
  `;
  layerToggles.querySelectorAll('input[data-layer]').forEach(cb => {
    cb.addEventListener('change', () => toggleLayer(cb.dataset.layer, cb.checked));
  });
}

// ========== NEW SEARCH ==========
document.getElementById('rpNewBtn').addEventListener('click', () => {
  resultsPanel.classList.add('hidden');
  clearMarkers();
  removeMapLayers();
  layerPanel.classList.add('hidden');
  assessBtn.disabled = true;
});

// ========== INIT ==========
initMap();
setMode('single');
