# Route Screenshot Generator

Generate map screenshots of walking and driving routes. Renders routes with durations and distances for each trip variant you specify.

## Setup

```bash
npm install
```

## Usage

1. Prepare a `trips.json` file with trip data
2. Run:
   ```bash
   node index.js
   ```
3. Screenshots are saved to `screenshots/` directory

## Input Format

`trips.json` should contain an array of trip objects with:
- `destination_point` - Name of destination
- `walking_duration` - Duration in minutes
- `trip_length_miles` - Distance in miles

## Output

- `screenshots/` - PNG images named `trip_{index}_{duration}min_{distance}miles_v{version}_{mode}.png`
- `trips_with_routes.json` - Enriched data with routing information

## API Key

Uses OpenRouteService for route calculations. The API key is embedded in the script.

## Requirements

- Node.js 16+
- Enough disk space for dependencies (Puppeteer)
