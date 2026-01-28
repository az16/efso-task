# Ride-Hailing Study Flask App

A Flask-based web application for conducting experimental research on transportation mode choices and decision-making.

## Prerequisites

- Python 3.7+
- pip (Python package manager)

## Installation

1. **Clone or download the project** to your local machine.

2. **Navigate to the project directory**:
   ```bash
   cd efso-task
   ```

3. **Install Flask** (the only external dependency):
   ```bash
   pip install flask
   ```

## Running the Application

Start the Flask development server:

```bash
python app.py
```

The application will be available at `http://127.0.0.1:5002`

## Data Directories

- **`participant_logs/`** - Individual participant response logs
- **`event_logs/`** - Detailed event tracking for analysis
- **`static/`** - Static files (images, screenshots, etc.) -- these need to be pre-generated for the application to work

## Notes

- The application runs on localhost only by default
- Participant data is stored as CSV files in the logs directories
- An `informedTrips.json` file contains trip information for the study conditions (duration, distance, etc.)
