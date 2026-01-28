const fs = require("fs");
const fetch = require("node-fetch").default || require("node-fetch");
const puppeteer = require("puppeteer");

const ORS_KEY = "your_openrouteservice_api_key_here";

if (!ORS_KEY) {
  console.error("Set ORS_KEY as environment variable");
  process.exit(1);
}

const trips = JSON.parse(fs.readFileSync("sample-trips.json", "utf-8"));

const HOME_COORDS_VERSIONS = [
  [41.0330, -73.7646],
  [41.0350, -73.7666],
  [41.0310, -73.7626],
  [41.0340, -73.7630],
  [41.0320, -73.7670]
];

// Generate plausible destination coords
function generateDestinationCoords(walkingDurationMinutes, homeCoords) {
  const walkingSpeedKmh = 4.8;
  const baseDistanceKm = (walkingDurationMinutes / 60) * walkingSpeedKmh;
  const bearing = Math.random() * 360;
  const bearingRad = bearing * (Math.PI / 180);
  const R = 6371;
  const lat1 = homeCoords[0] * (Math.PI / 180);
  const lng1 = homeCoords[1] * (Math.PI / 180);

  const lat2orig = Math.asin(Math.sin(lat1) * Math.cos(baseDistanceKm / R) +
                        Math.cos(lat1) * Math.sin(baseDistanceKm / R) * Math.cos(bearingRad));

  const lng2orig = lng1 + Math.atan2(Math.sin(bearingRad) * Math.sin(baseDistanceKm / R) * Math.cos(lat1),
                                Math.cos(baseDistanceKm / R) - Math.sin(lat1) * Math.sin(lat2orig));

  const lat2deg = lat2orig * (180 / Math.PI);
  const lng2deg = lng2orig * (180 / Math.PI);

  const factor = 0.6;
  const finalLat = homeCoords[0] + factor * (lat2deg - homeCoords[0]);
  const finalLng = homeCoords[1] + factor * (lng2deg - homeCoords[1]);

  return [finalLat, finalLng];
}

async function processTrip(trip, homeCoords) {
  console.log(`Processing trip: ${trip.walking_duration} min walk to ${trip.destination_point}`);
  
  const maxRetries = 5;
  let attempt = 0;
  
  while (attempt < maxRetries) {
    attempt++;
    const destinationCoords = generateDestinationCoords(trip.walking_duration, homeCoords);
    
    const walkRes = await fetch(
      `https://api.openrouteservice.org/v2/directions/foot-walking?api_key=${ORS_KEY}&start=${homeCoords[1]},${homeCoords[0]}&end=${destinationCoords[1]},${destinationCoords[0]}`
    );
    const walkData = await walkRes.json();
    
    const driveRes = await fetch(
      `https://api.openrouteservice.org/v2/directions/driving-car?api_key=${ORS_KEY}&start=${homeCoords[1]},${homeCoords[0]}&end=${destinationCoords[1]},${destinationCoords[0]}`
    );
    const driveData = await driveRes.json();
    
    const walkValid = walkData && !walkData.error && walkData.features?.length > 0;
    const driveValid = driveData && !driveData.error && driveData.features?.length > 0;
    
    if (walkValid && driveValid) {
      return {
        ...trip,
        start_coords: homeCoords,
        end_coords: destinationCoords,
        ors_walking: walkData,
        ors_driving: driveData
      };
    }
    await new Promise(r => setTimeout(r, 3000));
  }
  
  throw new Error(`Failed to find valid route after ${maxRetries} attempts`);
}

(async () => {
  console.log("Analyzing trip durations and distances...");
  const durations = trips.map(t => t.walking_duration);
  const distances = trips.map(t => t.trip_length_miles);
  console.log(`Walking duration range: ${Math.min(...durations)} - ${Math.max(...durations)} minutes`);
  console.log(`Distance range: ${Math.min(...distances)} - ${Math.max(...distances)} miles`);
  console.log(`Total trips to process: ${trips.length}`);
  
  const enriched = [];
  
  for (let i = 0; i < trips.length; i++) {
    const trip = trips[i];
    console.log(`\nProcessing trip ${i + 1}/${trips.length}: ${trip.destination_point}`);
    
    for (let version = 0; version < HOME_COORDS_VERSIONS.length; version++) {
      const homeCoords = HOME_COORDS_VERSIONS[version];
      console.log(`  Version ${version} with start coords: [${homeCoords[0].toFixed(4)}, ${homeCoords[1].toFixed(4)}]`);
      
      try {
        const processedTrip = await processTrip(trip, homeCoords);
        const validWalk = processedTrip.ors_walking?.features?.length > 0;
        const validDrive = processedTrip.ors_driving?.features?.length > 0;
        if (validWalk && validDrive) {
          processedTrip.version = version;
          enriched.push(processedTrip);
          console.log(`    ✓ Version ${version} successful`);
        } else {
          console.log(`    ⚠ Version ${version} failed - invalid routes`);
        }
      } catch (e) {
        console.error(`    ✗ Version ${version} failed:`, e.message);
      }
      
      if (version < HOME_COORDS_VERSIONS.length - 1) {
        await new Promise(r => setTimeout(r, 3000));
      }
    }
    
    if (i < trips.length - 1) {
      console.log("  Waiting 10 seconds before next trip...");
      await new Promise(r => setTimeout(r, 10000));
    }
  }
  
  fs.writeFileSync("trips_with_routes.json", JSON.stringify(enriched, null, 2));
  if (enriched.length === 0) return;

  const browser = await puppeteer.launch();
  const page = await browser.newPage();

  const html = `
  <!DOCTYPE html>
  <html>
  <head>
    <meta charset="utf-8"/>
    <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
    <style>
      body,html,#map{margin:0;padding:0;height:100%;width:100%;}
      .map-label {
        background: #ffffff !important;
        padding: 12px 16px !important;   /* larger padding */
        border-radius: 8px !important;
        font-size: 18px !important;      /* larger text */
        font-weight: bold !important;    /* bold text */
        text-align: center !important;
        line-height: 1.3 !important;
        box-sizing: border-box !important;
        font-family: Arial, Helvetica, sans-serif !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25) !important; /* stronger shadow */
        border: 2px solid rgba(0,0,0,0.25) !important;    /* thicker border */
        display: inline-block !important;
        width: auto !important;
        height: auto !important;
        white-space: pre-line !important;
      }
      /* force override Leaflet’s defaults */
      .leaflet-div-icon.map-label {
        width: auto !important;
        height: auto !important;
        min-width: unset !important;
        min-height: unset !important;
      }
      .leaflet-tooltip.map-label,
      .leaflet-tooltip.map-label .leaflet-tooltip-content {
        background: #ffffff !important;
        padding: 12px 16px !important;
        border-radius: 8px !important;
        font-size: 18px !important;
        font-weight: bold !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25) !important;
        border: 2px solid rgba(0,0,0,0.25) !important;
        white-space: pre-line !important;
      }
      .leaflet-tooltip.map-label {
        pointer-events: none;
      }
    </style>
  </head>
  <body>
    <div id="map"></div>
    <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
    <script>
      window.renderRoute = (geo, start, end, mode, labelText) => {
        const validCoords = arr => Array.isArray(arr) && arr.length === 2 && arr.every(v => typeof v === 'number');
        if (!validCoords(start) || !validCoords(end)) return;

        const mapElement = document.getElementById('map');
        if (mapElement._leaflet_id) mapElement._leaflet_id = null;
        mapElement.innerHTML = '';

        const map = L.map('map').setView(start, 14);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
        const layer = L.geoJSON(geo, {color: mode==='walking'?'green':'blue', weight:7}).addTo(map);

        const startMarker = L.marker(start).addTo(map);
        startMarker.bindTooltip('YOU', {permanent: true, direction: 'top', className: 'map-label', offset: [0, -18]});

        const endMarker = L.marker(end).addTo(map);
        endMarker.bindTooltip('MEETING POINT', {permanent: true, direction: 'top', className: 'map-label', offset: [0, -18]});

        map.fitBounds(layer.getBounds().pad(0.02));

        if (Array.isArray(geo.coordinates) && geo.coordinates.length >= 2) {
          const midIndex = Math.floor(geo.coordinates.length / 2);
          const mid = geo.coordinates[midIndex];
          if (Array.isArray(mid) && mid.length === 2) {
            L.marker([mid[1], mid[0]], {
              icon: L.divIcon({
                className:'map-label leaflet-div-icon', 
                html: labelText
              })
            }).addTo(map);
          }
        }
      };
    </script>
  </body>
  </html>`;
  
  await page.setContent(html);
  fs.mkdirSync("screenshots", { recursive: true });

  let screenshotCount = 0;
  const totalScreenshots = enriched.length * 2;

  for (let i = 0; i < enriched.length; i++) {
    const trip = enriched[i];
    console.log(`\n📸 Generating screenshots for trip ${Math.floor(i/5)}v${trip.version}: ${trip.destination_point}`);
    
    for (let [mode, data] of [["walking", trip.ors_walking], ["driving", trip.ors_driving]]) {
      try {
        if (!data || !data.features?.length) continue;
        const geo = data.features[0].geometry;
        const summary = data.features[0].properties.summary;
        if (!geo || !summary) continue;

        const distanceMiles = String(trip.trip_length_miles);
        let durationMinutes = mode === 'driving' ? Math.round(summary.duration / 60) : trip.walking_duration;
        const labelText = `${durationMinutes}min<br>${distanceMiles}mi`;

        await page.evaluate((g, s, e, m, t) => {
          window.renderRoute(g, s, e, m, t);
        }, geo, trip.start_coords, trip.end_coords, mode, labelText);

        await new Promise(r => setTimeout(r, 2000));
        
        const tripIndex = Math.floor(i / 5);
        const tripName = `${trip.walking_duration}min_${trip.trip_length_miles.toString().replace('.', '_')}miles`;
        const filename = `trip_${tripIndex}_${tripName}_v${trip.version}_${mode}.png`;
        await page.screenshot({ path: `screenshots/${filename}` });
        screenshotCount++;
        console.log(`✓ Screenshot ${screenshotCount}/${totalScreenshots}: ${filename}`);
      } catch (error) {
        console.error(`Failed screenshot for ${trip.destination_point}:`, error.message);
      }
    }
  }
  
  await browser.close();
  console.log(`Screenshot generation complete! Generated ${screenshotCount} screenshots.`);
})();
