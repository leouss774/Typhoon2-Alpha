var mapLoadTime = 1000;
var TYPHOON_API = window.TYPHOON_API || 'http://127.0.0.1:8765';

var currentGeoLocation = {
  lat: 41.656723,
  lon: -91.541021,
  address: "Location"
};

var currentDisasterDiagnostic = null;

document.getElementById("resizeButton").addEventListener("click", function(){
  var xrcontainer = document.getElementById("xrcontainer");
  xrcontainer.classList.toggle("fullscreen");
  xrcontainer.classList.toggle("smallscreen");
});

function updateMapLocation(lat, lon, zoom=16){
  currentGeoLocation.lat = lat;
  currentGeoLocation.lon = lon;
  var mapParams = {"lat": lat, "lon": lon, "zoom": zoom};
  var paramsJSON = JSON.stringify(mapParams);
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CitySimulatorMap", "jsSetMap", paramsJSON);
  }
  if (window.map && typeof window.map.setCenter === 'function' && window.google) {
    window.map.setCenter(new google.maps.LatLng(lat, lon));
  }
}

function extendMap(west, east, north, south){
  var mapParams = {"west": west, "east":east, "north":north, "south":south};
  var paramsJSON = JSON.stringify(mapParams);
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CitySimulatorMap", "jsSetExtent", paramsJSON);
  }
}

function addPOI(pois){
  var paramsJSON = JSON.stringify(pois);
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CitySimulatorMap", "jsSetPOIs", paramsJSON);	
  }
}

function enableTraffic(){
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CitySimulatorMap", "jsEnableTraffic", "all");	
  }
}

function generateFlood(){
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CitySimulatorMap", "jsGenerateFlood", "");	
  }
}

function generateFire(poiJSON){
  var paramsJSON = JSON.stringify(poiJSON);
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CitySimulatorMap", "jsSetFire", paramsJSON);	
  }
}

function adjustFlood(level){
  var mapParams = {"floodLevel": level};
  var paramsJSON = JSON.stringify(mapParams);
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CitySimulatorMap", "jsAdjustFlood", paramsJSON);
  }
}

function setUserName(){
  if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
    window.gameInstance.SendMessage("CameraMain", "jsSetProfile", "Yusuf Sermet");	
  }
}

// ---------------------------------------------------------------------------
// Scènes de catastrophes géolocalisées dynamiquement
// ---------------------------------------------------------------------------

function useCaseTraffic(lat, lon){
  lat = lat || currentGeoLocation.lat || 37.5317132;
  lon = lon || currentGeoLocation.lon || -77.4289454;
  updateMapLocation(lat, lon);

  var accidentPOIs = {"pois": [
    {"lat": lat + 0.0010, "lon": lon - 0.0028, "type": "Accident", "height": 70, "content": "Accident / Landslide\nInjuries: 1\nFatalities: 0"},
    {"lat": lat + 0.0038, "lon": lon + 0.0036, "type": "Accident", "height": 70, "content": "Accident / Collapse\nInjuries: 2\nFatalities: 0"},
    {"lat": lat + 0.0051, "lon": lon + 0.0036, "type": "Accident", "height": 70, "content": "Property Damage\nInjuries: 0\nFatalities: 0"}
  ]};

  var warningPOIs = {"pois": [
    {"lat": lat + 0.0006, "lon": lon + 0.0050, "type": "Warning", "height": 60, "content": "High Risk Zone\nRoad Widening / Barrier"}
  ]};

  var radioactivePOIs = {"pois": [
    {"lat": lat, "lon": lon, "type": "Radioactive", "height": 70, "content": "Sensor Alert\nEnvironmental Risk Detected"}
  ]};

  var sensorPOIs = {"pois": [
    {"lat": lat - 0.0002, "lon": lon - 0.0001, "type": "SensorGeneric", "height": 55, "content": "V Detector #3\nVoltage: 599"},
    {"lat": lat + 0.0001, "lon": lon + 0.0012, "type": "SensorGeneric", "height": 45, "content": "V Detector #5\nVoltage: 601.5"}
  ]};

  setTimeout(function(){
    addPOI(accidentPOIs);
    addPOI(radioactivePOIs);
    addPOI(sensorPOIs);
    addPOI(warningPOIs);
    enableTraffic();
  }, mapLoadTime);
}

function useCaseActiveShooter(lat, lon){
  lat = lat || currentGeoLocation.lat || 37.526889;
  lon = lon || currentGeoLocation.lon || -77.451861;
  updateMapLocation(lat, lon);

  var policePOIs = {"pois": [
    {"lat": lat + 0.0005, "lon": lon - 0.0020, "type": "Police", "height": 66, "content": "Emergency Response\nUnits On Scene\nStatus: Active"},
    {"lat": lat + 0.0006, "lon": lon - 0.0019, "type": "Police", "height": 45, "content": "Emergency Response\nSecuring Perimeter"}
  ]};

  var shootingPOIs = {"pois": [
    {"lat": lat + 0.0005, "lon": lon - 0.0020, "type": "Shooting", "height": 80, "content": "Severe Hazard Zone\nAlert Level: CRITICAL"}
  ]};

  var unknownPOIs = {"pois": [
    {"lat": lat - 0.0022, "lon": lon - 0.0038, "type": "Unknownpackage", "height": 60, "content": "Suspicious Zone\nUnder Investigation"}
  ]};

  var warningPOIs = {"pois": [
    {"lat": lat - 0.0014, "lon": lon + 0.0046, "type": "Warning", "height": 70, "content": "Dispatch Alert"}
  ]};

  setTimeout(function(){
    addPOI(policePOIs);
    addPOI(shootingPOIs);
    addPOI(unknownPOIs);
    addPOI(warningPOIs);
    enableTraffic();
  }, mapLoadTime);
}

function useCaseFlood(lat, lon, floodLevelMultiplier){
  lat = lat || currentGeoLocation.lat || 41.656723;
  lon = lon || currentGeoLocation.lon || -91.541021;
  floodLevelMultiplier = floodLevelMultiplier || 1.2;

  updateMapLocation(lat, lon);
  extendMap(1,1,1,2);

  var stageSensorPOIs = {"pois": [
    {"lat": lat, "lon": lon, "type": "Sensor", "height": 85, "content": "Stream Gauge / Flood Sensor\nStatus: HIGH RISK\nDischarge: 8,370 ft3/s\nInondation détectée"}
  ]};

  var variousSensorsPOIs = {"pois": [
    {"lat": lat + 0.0002, "lon": lon - 0.0001, "type": "RainGauge", "height": 70, "content": "Pluviomètre\nPrécipitations: 2.4 in/hr"},
    {"lat": lat - 0.0050, "lon": lon - 0.0025, "type": "Soil", "height": 70, "content": "Hydro Station\nSaturations sol: 95%"}
  ]};

  var buildingPOIs = {"pois": [
    {"lat": lat - 0.0050, "lon": lon + 0.0019, "type": "Damage", "height": 70, "content": "Estimation Dégâts Inondation\nRisque Bâtiment: ÉLEVÉ / CRITIQUE"},
    {"lat": lat - 0.0015, "lon": lon + 0.0020, "type": "Damage", "height": 80, "content": "Zone d'inondation potentielle\nRemontée de nappe"}
  ]};

  addPOI(stageSensorPOIs);
  addPOI(variousSensorsPOIs);
  addPOI(buildingPOIs);

  setTimeout(function(){
    generateFlood();
    adjustFlood(floodLevelMultiplier);
    if (window.gameInstance && typeof window.gameInstance.SendMessage === 'function') {
      window.gameInstance.SendMessage("CitySimulatorMap", "jsSetLayerInactive", "Water");
    }
    enableTraffic();
  }, mapLoadTime);
}

function useCaseFire(lat, lon){
  lat = lat || currentGeoLocation.lat || 32.380616;
  lon = lon || currentGeoLocation.lon || -110.953647;

  updateMapLocation(lat, lon);

  var firePOIs = {"pois": [
    {"lat": lat - 0.0024, "lon": lon + 0.0050, "type": "N/A", "height": 0, "content": ""}
  ]};

  var fireDataPOIs = {"pois": [
    {"lat": lat - 0.0024, "lon": lon + 0.0050, "type": "FireData", "height": 205, "content": "Feu de Forêt / Wildfire Alert\nCause: Sécheresse / Canicule\nRisque: CRITIQUE"}
  ]};

  var smokePOIs = {"pois": [
    {"lat": lat - 0.0022, "lon": lon + 0.0002, "type": "SensorGeneric", "height": 205, "content": "Capteur Qualité Air\nParticules / Fumée élevées"}
  ]};

  var spottedPeoplePOIs = {"pois": [
    {"lat": lat - 0.0007, "lon": lon + 0.0062, "type": "SensorGeneric", "height": 215, "content": "Vigilance Habitations"}
  ]};

  var firemanPOIs = {"pois": [
    {"lat": lat - 0.0016, "lon": lon + 0.0032, "type": "Fireman", "height": 200, "content": "Intervention Pompiers\nEquipe 1"},
    {"lat": lat - 0.0013, "lon": lon + 0.0028, "type": "Fireman", "height": 220, "content": "Intervention Pompiers\nChef de Secteur"}
  ]};

  setTimeout(function(){
    generateFire(firePOIs);
    addPOI(fireDataPOIs);
    addPOI(smokePOIs);
    addPOI(firemanPOIs);
    addPOI(spottedPeoplePOIs);
    enableTraffic();
  }, mapLoadTime);
}

// ---------------------------------------------------------------------------
// Analyse Backend & Détection de la Catastrophe au Score le Plus Élevé
// ---------------------------------------------------------------------------

function getNiveauScore(niveauStr) {
  if (!niveauStr) return 0;
  var s = String(niveauStr).toLowerCase();
  if (s === 'critique') return 100;
  if (s === 'eleve' || s === 'élevé') return 80;
  if (s === 'modere' || s === 'modéré') return 60;
  if (s === 'faible') return 40;
  if (s === 'tres_faible' || s === 'très faible') return 20;
  return 0;
}

function analyzeAndVisualizeLocation(addressQuery) {
  if (!addressQuery || typeof addressQuery !== 'string') return;
  console.log("[GeospatialVR] Analyse de la localisation :", addressQuery);
  
  updateSearchUIStatus("Analyse du risque en cours pour : " + addressQuery + "...");

  var url = TYPHOON_API + '/diagnostic/adresse?q=' + encodeURIComponent(addressQuery);
  
  fetch(url)
    .then(function(res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .then(function(data) {
      currentDisasterDiagnostic = data;
      var lat = data.lat;
      var lon = data.lon;
      var addressName = data.adresse_normalisee || addressQuery;
      
      currentGeoLocation.lat = lat;
      currentGeoLocation.lon = lon;
      currentGeoLocation.address = addressName;

      var topDisaster = findHighestScoreDisaster(data);
      console.log("[GeospatialVR] Catastrophe au plus haut score :", topDisaster);

      updateSearchUIStatus("📍 " + addressName + " | Top Risque : " + topDisaster.title + " (Score: " + topDisaster.score + "/100)");

      // Exécuter automatiquement la scène correspondante aux coordonnées fournies
      triggerSceneForDisaster(topDisaster.type, lat, lon, topDisaster.score);
    })
    .catch(function(err) {
      console.warn("[GeospatialVR] Impossible de contacter backend /diagnostic/adresse, tentative via BAN...", err);
      // Repli géocodage direct BAN
      fetch('https://api-adresse.data.gouv.fr/search/?q=' + encodeURIComponent(addressQuery) + '&limit=1')
        .then(function(r) { return r.json(); })
        .then(function(banData) {
          if (banData && banData.features && banData.features.length > 0) {
            var coords = banData.features[0].geometry.coordinates;
            var lon = coords[0];
            var lat = coords[1];
            var label = banData.features[0].properties.label;
            
            currentGeoLocation.lat = lat;
            currentGeoLocation.lon = lon;
            currentGeoLocation.address = label;

            updateSearchUIStatus("📍 " + label + " | (Géolocalisé, scène par défaut)");
            useCaseFlood(lat, lon, 1.2);
          } else {
            updateSearchUIStatus("❌ Adresse non trouvée");
          }
        })
        .catch(function(e) {
          updateSearchUIStatus("❌ Erreur de géolocalisation");
        });
    });
}

function findHighestScoreDisaster(reportData) {
  var hazards = [];

  if (reportData.aleas && Array.isArray(reportData.aleas)) {
    reportData.aleas.forEach(function(a) {
      if (a.present !== false) {
        var score = getNiveauScore(a.niveau);
        hazards.push({
          code: a.code || '',
          name: a.libelle || a.code,
          score: score,
          niveau: a.niveau || 'faible'
        });
      }
    });
  }

  // Si aucun aléa explicite, valeurs par défaut
  if (hazards.length === 0) {
    return { type: 'flood', title: 'Inondation', score: 50 };
  }

  // Trier par score décroissant
  hazards.sort(function(a, b) { return b.score - a.score; });
  var top = hazards[0];
  var codeLower = (top.code + ' ' + top.name).toLowerCase();

  var disasterType = 'flood';
  if (codeLower.includes('feu') || codeLower.includes('foret') || codeLower.includes('wildfire') || codeLower.includes('incendie') || codeLower.includes('canicule')) {
    disasterType = 'fire';
  } else inondationCheck: if (codeLower.includes('inondation') || codeLower.includes('nappe') || codeLower.includes('crue') || codeLower.includes('flood')) {
    disasterType = 'flood';
  } else if (codeLower.includes('rga') || codeLower.includes('argile') || codeLower.includes('mouvement') || codeLower.includes('glissement') || codeLower.includes('cavite')) {
    disasterType = 'traffic';
  } else if (codeLower.includes('seisme') || codeLower.includes('sismi') || codeLower.includes('radon')) {
    disasterType = 'shooter';
  }

  return {
    type: disasterType,
    title: top.name,
    score: top.score,
    niveau: top.niveau
  };
}

function triggerSceneForDisaster(disasterType, lat, lon, score) {
  if (disasterType === 'fire') {
    useCaseFire(lat, lon);
  } else if (disasterType === 'traffic') {
    useCaseTraffic(lat, lon);
  } else if (disasterType === 'shooter') {
    useCaseActiveShooter(lat, lon);
  } else {
    var floodMult = 1.0 + (score / 100.0) * 1.5;
    useCaseFlood(lat, lon, floodMult);
  }
}

function updateSearchUIStatus(msg) {
  var statusEl = document.getElementById("disaster-status-msg");
  if (statusEl) {
    statusEl.innerText = msg;
  }
}

// ---------------------------------------------------------------------------
// Lecture Automatique des Paramètres d'URL & Messages (Iframe)
// ---------------------------------------------------------------------------

window.addEventListener("DOMContentLoaded", function() {
  var params = new URLSearchParams(window.location.search);
  var address = params.get("address") || params.get("q") || params.get("adresse");
  var lat = parseFloat(params.get("lat"));
  var lon = parseFloat(params.get("lon") || params.get("lng"));

  if (address) {
    analyzeAndVisualizeLocation(address);
  } else if (!isNaN(lat) && !isNaN(lon)) {
    currentGeoLocation.lat = lat;
    currentGeoLocation.lon = lon;
    updateMapLocation(lat, lon);
    useCaseFlood(lat, lon, 1.2);
  }
});

window.addEventListener("message", function(event) {
  if (event.data) {
    if (typeof event.data === 'string') {
      try {
        var parsed = JSON.parse(event.data);
        if (parsed.address || parsed.q) analyzeAndVisualizeLocation(parsed.address || parsed.q);
        else if (parsed.lat && parsed.lon) triggerSceneForDisaster('flood', parsed.lat, parsed.lon, 70);
      } catch(e){}
    } else if (typeof event.data === 'object') {
      if (event.data.address || event.data.q) {
        analyzeAndVisualizeLocation(event.data.address || event.data.q);
      } else if (event.data.lat && event.data.lon) {
        triggerSceneForDisaster('flood', event.data.lat, event.data.lon, 70);
      }
    }
  }
});