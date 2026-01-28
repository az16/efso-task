from flask import Flask, request, jsonify, render_template_string, url_for, redirect
import csv
import os
import threading
import json
import random
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
app = Flask(__name__, static_folder='static', static_url_path='/static')


# Trip Reflection Questions
TRIP_REFLECTION_QUESTIONS = [
    {
        'id': 'rationale',
        'text': 'For the trip shown above you chose the option displayed on the screen right now. Please describe your thought process when you made this decision.',
        'type': 'textarea',
        'placeholder': 'Description...'
    }
]

# Trip-Specific Likert Questions (for participants who switched from walking to riding)
TRIP_LIKERT_QUESTIONS = [
    {
        'id': 'credit.lost',
        'text': 'I\'ve lost moral credit through my choices in this trip.',
        'type': 'likert_7_point'
    },
    {
        'id': 'impact.comparison', 
        'text': 'Compared to walking, the presented RidePal version causes significant environmental damage.',
        'type': 'likert_7_point'
    }
]
# Walking-Only Reflection Questions (for participants who always walked in a condition)
WALKING_REFLECTION_QUESTIONS = [
    {
        'id': 'walking.reason',
        'text': 'You chose to walk in all trips.',
        'type': 'textarea',
        'placeholder': 'Please explain your reasoning for consistently choosing to walk...'
    }
]
# Default 7-point Likert scale labels
DEFAULT_LIKERT_LABELS = ['Strongly Disagree', 'Disagree', 'Slightly Disagree', 'Neutral', 'Slightly Agree', 'Agree', 'Strongly Agree']


def generate_likert_question_html(question, question_number=None):
    """Generate HTML for a Likert scale question"""
    labels = question.get('scale_labels', DEFAULT_LIKERT_LABELS)
    question_id = question['id']
    title = f"{question_number}. {question['text']}" if question_number else question['text']
    html = f'''
    <div class="bg-gray-50 p-4 rounded-lg">
        <p class="font-medium text-gray-700 mb-3">{title}</p>
        <div class="grid grid-cols-7 gap-2 text-sm">'''
    for i, label in enumerate(labels, 1):
        html += f'''
            <label class="text-center cursor-pointer">
                <input type="radio" name="{question_id}" value="{i}" required class="block mx-auto mb-1">
                <span class="block">{label}</span>
            </label>'''
    html += '''
        </div>
    </div>'''
    return html

def generate_textarea_question_html(question):
    """Generate HTML for a textarea question"""
    question_id = question['id']
    placeholder = question.get('placeholder', '')
    html = f'''
    <div>
        <label for="{question_id}" class="block text-sm font-medium text-gray-700 mb-2">
            {question['text']}
        </label>
        <textarea 
            id="{question_id}" 
            name="{question_id}" 
            rows="4" 
            required 
            class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            placeholder="{placeholder}"
        ></textarea>
    </div>'''
    return html

def generate_question_html(question, question_number=None):
    """Generate HTML for any type of question"""
    if question['type'] in ['likert_7_point', 'likert_7_point_custom']:
        return generate_likert_question_html(question, question_number)
    elif question['type'] == 'textarea':
        return generate_textarea_question_html(question)
    else:
        return f"<p>Unknown question type: {question['type']}</p>"
    
def generate_javascript_validation(questions):
    """Generate JavaScript validation code for a set of questions"""
    js_code = ""
    for question in questions:
        question_id = question['id']
        # Use a safe JS variable name (IDs may contain dots). Keep original IDs in selectors and response keys.
        js_var_name = question_id.replace('.', '_')
        if question['type'] in ['likert_7_point', 'likert_7_point_custom']:
            js_code += f'''
                const {js_var_name}_radio = document.querySelector('input[name="{question_id}"]:checked');
                if (!{js_var_name}_radio) {{
                    alert('Please answer all questions before continuing.');
                    return;
                }}
                responses['{question_id}'] = parseInt({js_var_name}_radio.value);'''
        elif question['type'] == 'textarea':
            js_code += f'''
                const {js_var_name}_value = document.getElementById('{question_id}').value.trim();
                if (!{js_var_name}_value) {{
                    alert('Please answer all questions before continuing.');
                    return;
                }}
                responses['{question_id}'] = {js_var_name}_value;'''
    return js_code


assignment_lock = threading.Lock()
csv_write_lock = threading.Lock()


# Load trip data
with open('informedTrips.json', 'r') as f:
    TRIPS_DATA = json.load(f)
ASSIGNMENTS_FILE = 'participant_assignments.csv'
LOGS_DIR = 'participant_logs'
EVENT_LOGS_DIR = 'event_logs'
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(EVENT_LOGS_DIR, exist_ok=True)

if not app.logger.handlers:  
    file_handler = RotatingFileHandler('application.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Trip task application startup')


# Latin square sequences for condition order (5 conditions, 5 different orders)
CONDITION_ORDER_SEQUENCES = [
    [0, 1, 2, 3, 4],  
    [1, 2, 3, 4, 0],  
    [2, 3, 4, 0, 1],  
    [3, 4, 0, 1, 2],  
    [4, 0, 1, 2, 3],  
]


# Trip order sequences for randomization within each condition (10 trips, 10 different orders)
TRIP_ORDER_SEQUENCES = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],  
    [4, 7, 1, 9, 2, 0, 5, 8, 3, 6],  
    [8, 2, 5, 0, 6, 9, 1, 4, 7, 3],  
    [3, 6, 9, 1, 8, 4, 0, 2, 5, 7],  
    [7, 0, 4, 8, 1, 3, 9, 6, 2, 5],  
    [2, 9, 6, 3, 5, 7, 4, 0, 1, 8],  
    [5, 3, 0, 7, 9, 1, 8, 2, 6, 4],  
    [9, 5, 8, 2, 0, 6, 3, 1, 4, 7],  
    [1, 8, 3, 6, 7, 2, 0, 9, 5, 4],  
    [6, 4, 7, 5, 3, 8, 2, 9, 0, 1],  
]


def get_next_assignment():
    """Assign condition order and trip order sequences"""
    with assignment_lock:
        if not os.path.exists(ASSIGNMENTS_FILE):
            with open(ASSIGNMENTS_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['participant_id', 'condition_order_idx', 'trip_order_idx', 'timestamp'])
        participant_count = 0
        if os.path.exists(ASSIGNMENTS_FILE):
            with open(ASSIGNMENTS_FILE, 'r') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                participant_count = sum(1 for _ in reader)
        condition_order_idx = participant_count % 5
        trip_order_idx = participant_count % 10
        return condition_order_idx, trip_order_idx
    

def get_participant_assignment(participant_id):
    """Get condition order and trip order for a specific participant"""
    if os.path.exists(ASSIGNMENTS_FILE):
        with open(ASSIGNMENTS_FILE, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 3 and row[0] == participant_id:
                    condition_order_idx = int(row[1])
                    trip_order_idx = int(row[2])
                    return condition_order_idx, trip_order_idx
    return None, None
def get_condition_for_trip(participant_id, overall_trip_number):
    """Get condition for a specific overall trip number (0-49)"""
    condition_order_idx, _ = get_participant_assignment(participant_id)
    if condition_order_idx is None:
        return None
    condition_sequence = CONDITION_ORDER_SEQUENCES[condition_order_idx]
    condition_idx = overall_trip_number // 10  # 0-4
    return condition_sequence[condition_idx]


def get_trip_id_for_trip(participant_id, overall_trip_number):
    """Get trip ID for a specific overall trip number (0-49)"""
    _, trip_order_idx = get_participant_assignment(participant_id)
    if trip_order_idx is None:
        return None
    condition_block = overall_trip_number // 10
   
    effective_trip_order_idx = (trip_order_idx + condition_block) % len(TRIP_ORDER_SEQUENCES)
    trip_sequence = TRIP_ORDER_SEQUENCES[effective_trip_order_idx]
    trip_within_condition = overall_trip_number % 10  # 0-9
    return trip_sequence[trip_within_condition]


def log_assignment(participant_id, condition_order_idx, trip_order_idx):
    """Log participant assignment"""
    with open(ASSIGNMENTS_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([participant_id, condition_order_idx, trip_order_idx, datetime.now().isoformat()])

def create_participant_log(participant_id):
    """Create individual CSV log file for participant - comprehensive data structure"""
    log_filename = f"{LOGS_DIR}/{participant_id}.csv"
    if not os.path.exists(log_filename):
        with open(log_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'ProlificID', 
                'overall_trip_number',
                'condition',
                'trip_within_condition',
                'timestamp', 
                'trip_id',
                'choice',
                'trip_reflection_rationale',
                'trip_likert_credit_lost',
                'trip_likert_impact_comparison',
                'walking_reflection_walking_reason'
            ])
    return log_filename

def log_trip_choice(participant_id, overall_trip_number, condition, trip_within_condition, trip_id, choice):
    log_filename = f"{LOGS_DIR}/{participant_id}.csv"
    try:
        if os.path.exists(log_filename):
            with csv_write_lock:
                try:
                    with open(log_filename, 'r') as rf:
                        reader = csv.reader(rf)
                        header = next(reader, None)
                        overall_idx = header.index('overall_trip_number') if header and 'overall_trip_number' in header else 1
                        for row in reader:
                            if len(row) > overall_idx and str(row[overall_idx]) == str(overall_trip_number):
                                track_first_ride_switch(participant_id, overall_trip_number, condition, trip_id, choice)
                                return True
                except Exception:
                    pass
                general_likert_data = get_general_likert_data(participant_id, condition)
                trip_reflection_data = get_trip_reflection_data(participant_id, condition)
                with open(log_filename, 'a', newline='') as f:
                    writer = csv.writer(f)
                    # Base trip data
                    row_data = [
                        participant_id,
                        overall_trip_number,
                        condition,
                        trip_within_condition,
                        datetime.now().isoformat(),
                        trip_id,
                        choice
                    ]
                    # Add trip reflection data
                    if trip_reflection_data:
                        if trip_reflection_data.get('reflection_type') == 'walking_only':
                            # Walking-only reflection
                            row_data.extend([
                                '',  # rationale (not applicable)
                                '',  # credit.lost (not applicable)
                                '',  # impact.comparison (not applicable)
                                trip_reflection_data.get('walking_reason', '')
                            ])
                        else:
                            trip_likert = trip_reflection_data.get('trip_likert_responses', {})
                            row_data.extend([
                                trip_reflection_data.get('rationale', ''),
                                trip_likert.get('credit.lost', ''),
                                trip_likert.get('impact.comparison', ''),
                                ''   # walking_reason (not applicable)
                            ])
                    else:
                        # No reflection data yet
                        row_data.extend(['', '', '', ''])
                    writer.writerow(row_data)

        # Track first switch from walking to riding
        track_first_ride_switch(participant_id, overall_trip_number, condition, trip_id, choice)
        return True
    except Exception as e:
        app.logger.error(f"Failed to log trip choice for {participant_id} trip {overall_trip_number}: {e}")
        return False
    

def get_general_likert_data(participant_id, condition):
    """Get general Likert data for a specific condition"""
    general_likert_filename = f"{LOGS_DIR}/{participant_id}_general_likert_{condition}.json"
    if os.path.exists(general_likert_filename):
        with open(general_likert_filename, 'r') as f:
            return json.load(f)
    return None


def get_trip_reflection_data(participant_id, condition):
    """Get trip reflection data for a specific condition"""
    reflection_filename = f"{LOGS_DIR}/{participant_id}_reflection_{condition}.json"
    if os.path.exists(reflection_filename):
        with open(reflection_filename, 'r') as f:
            return json.load(f)
    return None


def update_csv_with_reflection_data(participant_id, condition):
    """Update CSV file with reflection data for a specific condition"""
    log_filename = f"{LOGS_DIR}/{participant_id}.csv"
    if not os.path.exists(log_filename):
        return
    # Get reflection data
    general_likert_data = get_general_likert_data(participant_id, condition)
    trip_reflection_data = get_trip_reflection_data(participant_id, condition)
    with csv_write_lock:
        rows = []
        try:
            with open(log_filename, 'r', newline='') as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            app.logger.error(f"Failed to read CSV for {participant_id}: {e}")
            return
        if len(rows) <= 1:  # Only header or empty file
            return
        header = rows[0]
        try:
            condition_col = header.index('condition')
            trip_reflection_start = header.index('trip_reflection_rationale')
            walking_reflection_start = header.index('walking_reflection_walking_reason')
        except Exception as e:
            app.logger.warning(f"Header mismatch when updating reflections for {participant_id}: {e}")
            return
        for i in range(1, len(rows)):
            row = rows[i]
            try:
                if len(row) > condition_col and int(row[condition_col]) == condition:
                    if trip_reflection_data:
                        if trip_reflection_data.get('reflection_type') == 'walking_only':
                            row[trip_reflection_start] = ''  # rationale
                            row[trip_reflection_start + 1] = ''  # credit.lost
                            row[trip_reflection_start + 2] = ''  # impact.comparison
                            row[walking_reflection_start] = trip_reflection_data.get('walking_reason', '')
                        else:
                            trip_likert = trip_reflection_data.get('trip_likert_responses', {})
                            row[trip_reflection_start] = trip_reflection_data.get('rationale', '')
                            row[trip_reflection_start + 1] = trip_likert.get('credit.lost', '')
                            row[trip_reflection_start + 2] = trip_likert.get('impact.comparison', '')
                            # Clear walking columns
                            row[walking_reflection_start] = ''
            except Exception:
                continue
        # Write CSV
        try:
            with open(log_filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows)
        except Exception as e:
            app.logger.error(f"Failed to write CSV for {participant_id}: {e}")


def track_first_ride_switch(participant_id, overall_trip_number, condition, trip_id, choice):
    """Track the first ride switch within each condition"""
    switch_filename = f"{LOGS_DIR}/{participant_id}_first_ride_switches.json"
    # Only track if participants chose a ride option (not walking)
    if choice != 'walking':
        # Load existing switches or create empty dict
        switches = {}
        if os.path.exists(switch_filename):
            with open(switch_filename, 'r') as f:
                switches = json.load(f)
        # Check if this is the first ride choice for this condition
        condition_key = f"condition_{condition}"
        if condition_key not in switches:
            # First ride choice in this condition
            switches[condition_key] = {
                'participant_id': participant_id,
                'overall_trip_number': overall_trip_number,
                'condition': condition,
                'trip_within_condition': overall_trip_number % 10,
                'trip_id': trip_id,
                'choice': choice,
                'timestamp': datetime.now().isoformat()
            }
            # Save updated switches
            with open(switch_filename, 'w') as f:
                json.dump(switches, f)


def get_condition_switches(participant_id):
    """Get all condition switches for a participant"""
    switch_filename = f"{LOGS_DIR}/{participant_id}_first_ride_switches.json"
    if os.path.exists(switch_filename):
        with open(switch_filename, 'r') as f:
            return json.load(f)
    return {}


def get_next_unreflected_condition(participant_id):
    """Get the next condition that needs reflection, or None if all done"""
    switches = get_condition_switches(participant_id)
    # Check conditions 0-4 in order
    for condition in range(5):
        condition_key = f"condition_{condition}"
        if condition_key in switches:
            # Check if reflection has been completed for this condition
            reflection_filename = f"{LOGS_DIR}/{participant_id}_reflection_{condition}.json"
            if not os.path.exists(reflection_filename):
                return condition, switches[condition_key]
    return None, None


def create_event_log(participant_id):
    """Create individual event log file for participant - for diagnostics"""
    log_filename = f"{EVENT_LOGS_DIR}/{participant_id}_events.csv"
    if not os.path.exists(log_filename):
        with open(log_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'ProlificID', 
                'overall_trip_number',
                'condition',
                'timestamp', 
                'event_type', 
                'trip_id',
                'data'
            ])
            # Log initial assignment
            writer.writerow([
                participant_id, 
                '',
                '',
                datetime.now().isoformat(), 
                'assignment', 
                '',
                'participant_assigned'
            ])
    return log_filename


def log_participant_event(participant_id, overall_trip_number, condition, event_type, data='', trip_id=''):
    """Log events to separate event log for diagnostics"""
    log_filename = f"{EVENT_LOGS_DIR}/{participant_id}_events.csv"
    # Create event log if it doesn't exist
    if not os.path.exists(log_filename):
        create_event_log(participant_id)
    with open(log_filename, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            participant_id,
            overall_trip_number,
            condition,
            datetime.now().isoformat(),
            event_type,
            trip_id,
            data
        ])
    # application log for debugging
    app.logger.info(f'Event: {participant_id} - {event_type} - Trip {overall_trip_number} - {data}')


@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests"""
    return "Not found", 404

@app.route('/robots.txt')
def robots():
    """Handle robots.txt requests"""
    return "User-agent: *\nDisallow: /", 200, {'Content-Type': 'text/plain'}

@app.route('/<participant_id>')
def assign_participant(participant_id):
    """Main endpoint: assign participant to condition and create log file"""
    # Filter out obvious bot requests (but allow long Prolific IDs)
    if (participant_id.endswith('.php') or 
        participant_id.endswith('.ico') or 
        participant_id.endswith('.txt') or 
        participant_id.endswith('.xml') or
        participant_id.endswith('.js') or
        participant_id.endswith('.css') or
        participant_id.endswith('.html') or
        participant_id.endswith('.jsp') or
        participant_id.endswith('.asp') or
        '/' in participant_id or     # No path separators
        participant_id.lower() in ['favicon.ico', 'robots.txt', 'sitemap.xml', 'wp-config.php']):
        app.logger.warning(f'Blocked suspicious request: {participant_id}')
        return "Not found", 404
    # Check if participant already exists
    participant_log_files = [f for f in os.listdir(LOGS_DIR) if f.startswith(f"{participant_id}.csv")]
    if participant_log_files:
        log_participant_event(participant_id, '', '', 'return_visit')
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome Back</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-50 min-h-screen">
            <div class="container mx-auto max-w-2xl px-4 py-16">
                <div class="bg-white rounded-lg shadow-md p-8 text-center">
                    <h1 class="text-3xl font-bold text-gray-800 mb-4">Welcome Back!</h1>
                    <div class="bg-blue-50 rounded-lg p-4 mb-6">
                        <p class="text-gray-600 mb-2">Participant ID: <span class="font-medium">{{ participant_id }}</span></p>
                        <p class="text-gray-600">You have already been assigned to this study.</p>
                    </div>
                    <a href="/study/{{ participant_id }}" class="inline-block bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-6 rounded-lg transition-colors">
                        Continue to Study
                    </a>
                </div>
            </div>
        </body>
        </html>
        """, participant_id=participant_id)
    # Assign new condition order and trip order
    condition_order_idx, trip_order_idx = get_next_assignment()
    # Log assignment
    log_assignment(participant_id, condition_order_idx, trip_order_idx)
    # Create participant log file (for trip choices only)
    log_file = create_participant_log(participant_id)
    # Create event log file (for diagnostics)
    event_log_file = create_event_log(participant_id)
    # Log assignment in application log
    app.logger.info(f'New participant assigned: {participant_id}, condition_order: {condition_order_idx}, trip_order: {trip_order_idx}')
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Study Assignment</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50 min-h-screen">
        <div class="container mx-auto max-w-2xl px-4 py-16">
            <div class="bg-white rounded-lg shadow-md p-8 text-center">
                <h1 class="text-3xl font-bold text-gray-800 mb-4">Study Assignment</h1>
                <div class="bg-green-50 rounded-lg p-4 mb-6">
                    <p class="text-gray-600 mb-2">Participant ID: <span class="font-medium">{{ participant_id }}</span></p>
                    <p class="text-green-700 font-medium">Thank you for participating in our study!</p>
                </div>
                <a href="/study/{{ participant_id }}" class="inline-block bg-green-600 hover:bg-green-700 text-white font-medium py-3 px-6 rounded-lg transition-colors">
                    Continue to Study
                </a>
            </div>
        </div>
    </body>
    </html>
    """, participant_id=participant_id)


@app.route('/study/<participant_id>')
def study_interface(participant_id):
    """Study interface - show trip overview"""
    # Find participant's log file
    participant_log_files = [f for f in os.listdir(LOGS_DIR) if f.startswith(f"{participant_id}.csv")]
    if not participant_log_files:
        return "Participant not found. Please start from the beginning.", 404
    # Log study access
    log_participant_event(participant_id, '', '', 'study_access')
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Transportation Study</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50 min-h-screen">
        <div class="container mx-auto max-w-4xl px-4 py-8">
            <div class="bg-white rounded-lg shadow-md p-8">
                <h1 class="text-3xl font-bold text-gray-800 mb-4">Transportation Study</h1>
                <div class="text-sm text-gray-600 mb-6">
                    <p>Participant: {{ participant_id }}</p>
                </div>
                <div class="space-y-6">
                    <div>
                        <h2 class="text-xl font-semibold text-gray-700 mb-3">Welcome to the Main Experimental Task</h2>
                        <div class="text-gray-600 mb-6 space-y-3">
                            <p class="font-semibold">What will happen in the following:</p>
                            <ul class="list-disc list-inside space-y-2">
                                <li>You will be shown a series of city trip scenarios. The purpose of your trip is to meet a friend in the city. This will remain the same throughout this study, but the traveling distance and duration will vary.</li>
                                <li>Your meeting is scheduled to be 60 minutes from now.
                                <li>Please imagine yourself in the following scenarios and make the decisions according to your personal preferences.</li>
                                <li>For each trip, you will decide whether to walk or use the ride-hailing service called RidePal as your mode of transportation. Think of RidePal as a typical ride-hailing service comparable to Uber or Lyft.</li>
                                <li>There will always be ride-hailing options via RidePal and the option to skip ride-hailing and walk instead</li>
                                <li>For each walking route shown, expect that infrastructure such as sidewalks and crosswalks is available, and there is no heavy traffic.</li> 
                            </ul>
                            <p class="font-semibold text-red-600 mt-4">Important: Please pay close attention during the task. Periodic attention checks will be included. If you fail more than two checks, your participation will be discontinued. Please also complete this part of the study without switching to other browser tabs. Once you click the button below the task will begin.</p>
                        </div>
                        <p class="text-lg font-medium text-blue-600 mb-6">Study Progress: 0%</p>
                        <a href="/block_intro/{{ participant_id }}/1/0" class="inline-block bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-6 rounded-lg transition-colors">
                            Start First Trip
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, participant_id=participant_id)

@app.route('/trip/<participant_id>/<int:overall_trip_number>')
def show_trip(participant_id, overall_trip_number):
    """Show individual trip scenario"""
    # Find participant's log file
    participant_log_files = [f for f in os.listdir(LOGS_DIR) if f.startswith(f"{participant_id}.csv")]
    if not participant_log_files:
        return "Participant not found. Please start from the beginning.", 404
    #prevent skipping ahead beyond the next allowed trip index
    try:
        csv_path = f"{LOGS_DIR}/{participant_id}.csv"
        if os.path.exists(csv_path):
            with open(csv_path, 'r') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                max_overall = -1
                overall_idx = header.index('overall_trip_number') if header and 'overall_trip_number' in header else 1
                for row in reader:
                    if len(row) > overall_idx:
                        try:
                            max_overall = max(max_overall, int(row[overall_idx]))
                        except Exception:
                            continue
                next_allowed = max_overall + 1
                if overall_trip_number > next_allowed:
                    return redirect(f'/trip/{participant_id}/{next_allowed}')
    except Exception:
        pass
    # Validate overall trip number (0-49)
    if overall_trip_number < 0 or overall_trip_number >= 50:
        return "Invalid trip number.", 404
    # Get condition and trip ID for this overall trip
    condition = get_condition_for_trip(participant_id, overall_trip_number)
    trip_id = get_trip_id_for_trip(participant_id, overall_trip_number)
    if condition is None or trip_id is None:
        return "Error determining trip details.", 404
    trip_data = TRIPS_DATA[trip_id]
    trip_within_condition = overall_trip_number % 10
    regular_price = trip_data['ride_price_usd'] 
    eco_price = trip_data['eco_price_usd'] 
    # Generate consistent random order for this participant and trip
    random.seed(f"{participant_id}_{overall_trip_number}_order")
    # Randomize map display order
    map_order_random = random.choice([True, False])
    driving_first = map_order_random
    # Create options based on condition
    if condition == 0:
        options = [
            {
                'type': 'walking',
                'value': 'walking',
                'image': 'walk_option.jpg',
                'price_text': ''
            },
            {
                'type': 'regular_1',
                'value': 'regular_ride',  # Both ride options log as regular_ride
                'image': 'controlA.png',
                'price_text': f'(${regular_price:.2f})'
            },
            {
                'type': 'regular_2', 
                'value': 'regular_ride',  # Both ride options log as regular_ride
                'image': 'controlB.png',
                'price_text': f'(${eco_price:.2f})'
            }
        ]
    else:
        if condition == 3:
            regular_image = 'condition3_regular_1.png'
        else:
            regular_image = f'condition{condition}_regular.png'
        options = [
            {
                'type': 'walking',
                'value': 'walking',
                'image': 'walk_option.jpg',
                'price_text': ''
            },
            {
                'type': 'regular',
                'value': 'regular_ride', 
                'image': regular_image,
                'price_text': f'(${regular_price:.2f})'
            },
            {
                'type': 'eco',
                'value': 'eco_ride',
                'image': f'condition{condition}_eco_1.png',
                'price_text': f'(${eco_price:.2f})'
            }
        ]
    random.shuffle(options)
    # Log trip view
    log_participant_event(participant_id, overall_trip_number, condition, 'trip_view', trip_id=trip_id)
   
    ridepal_suffix = "" if condition == 0 else " and has gas-powered as well as electric vehicles"
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Trip {{ overall_trip_number + 1 }} of 50</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50 min-h-screen">
        <div class="container mx-auto max-w-7xl py-1">
            <div class="bg-white rounded-lg shadow-md p-5">
                <!-- Header -->
                <div class="mb-2">
                    <h3 class="text-1xl font-bold text-gray-800 mb-2">Progress</h1>
                    <div class="flex items-center space-x-4 text-sm text-gray-600">
                        <span>{{ ((overall_trip_number + 1) / 50 * 100)|round }}%</span>
                        <div class="flex-1 bg-gray-200 rounded-full h-2">
                            <div class="bg-blue-600 h-2 rounded-full" style="width: {{ ((overall_trip_number + 1) / 50 * 100)|round }}%"></div>
                        </div>
                    </div>
                </div>
                <!-- Scenario Description -->
                <div class="bg-gray-50 rounded-lg p-6 mb-6">
                    <p class="font-bold text-gray-800 mb-2">Please imagine yourself in the following scenario:</p>
                    <ul class="space-y-2 text-gray-700">
                        <li class="flex items-start">
                            <span class="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                            You need to attend a meeting with a friend at a public location in a big city.
                        </li>
                        <li class="flex items-start">
                            <span class="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                            The meeting is 60 minutes from now.
                        </li>
                        <li class="flex items-start">
                            <span class="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                            Transportation options: walking or using a ride-hailing service (pick up at your location)
                        </li>
                        <li class="flex items-start">
                            <span class="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                            RidePal is the ride-hailing service in your area{{ ridepal_suffix }}.
                        </li>
                        <li class="flex items-start">
                            <span class="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                            For each walking route shown, expect that infrastructure such as sidewalks and crosswalks is available, and there is no heavy traffic
                        </li>          
                        <li class="flex items-start">
                            <span class="w-2 h-2 bg-blue-500 rounded-full mt-2 mr-3 flex-shrink-0"></span>
                            Route, distance, and travel duration are provided below
                        </li>
                    </ul>
                </div>
                <!-- Maps Side by Side -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-1 mb-6">
                    {% if driving_first %}
                    <div class="text-center">
                        <h3 class="font-medium text-gray-700 mb-3">Driving Route</h3>
                        <img alt="Driving route" 
                             src="/static/{{ trip_data.driving_image }}" 
                             class="w-full max-w-md mx-auto border border-gray-300 rounded-lg shadow-sm" />
                    </div>
                    <div class="text-center">
                        <h3 class="font-medium text-gray-700 mb-3">Walking Route</h3>
                        <img alt="Walking route" 
                             src="/static/{{ trip_data.walking_image }}" 
                             class="w-full max-w-md mx-auto border border-gray-300 rounded-lg shadow-sm" />
                    </div>
                    {% else %}
                    <div class="text-center">
                        <h3 class="font-medium text-gray-700 mb-3">Walking Route</h3>
                        <img alt="Walking route for trip {{ overall_trip_number + 1 }}" 
                             src="/static/{{ trip_data.walking_image }}" 
                             class="w-full max-w-md mx-auto border border-gray-300 rounded-lg shadow-sm" />
                    </div>
                    <div class="text-center">
                        <h3 class="font-medium text-gray-700 mb-3">Driving Route</h3>
                        <img alt="Driving route for trip {{ overall_trip_number + 1 }}" 
                             src="/static/{{ trip_data.driving_image }}" 
                             class="w-full max-w-md mx-auto border border-gray-300 rounded-lg shadow-sm" />
                    </div>
                    {% endif %}
                </div>
                <!-- Choice Form -->
                <div class="bg-gray-50 rounded-lg p-6">
                    <h3 class="text-l font-semibold text-gray-800 mb-3 text-center">Which transportation option would you choose?</h3>
                    <form id="tripForm" class="space-y-4">
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                            {% for option in options %}
                            <label class="flex flex-col items-center cursor-pointer transition-transform hover:scale-105">
                                <input type="radio" name="choice" value="{{ option.value }}" required class="mb-3">
                                <img src="/static/options/{{ option.image }}" alt="{{ option.type }} option" class="w-full object-contain rounded-lg mb-3">
                                {% if option.price_text %}
                                <div class="text-center">
                                    <span class="text-gray-600 text-sm">{{ option.price_text }}</span>
                                </div>
                                {% endif %}
                            </label>
                            {% endfor %}
                        </div>
                        <div class="text-center pt-4">
                            <button type="submit" class="bg-green-600 hover:bg-green-700 text-white font-medium py-3 px-8 rounded-lg transition-colors">
                                Record Choice
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        <script>
            document.getElementById('tripForm').addEventListener('submit', function(e) {
                e.preventDefault();
                // Client-side double-submit guard
                const submitBtn = this.querySelector('button[type="submit"]');
                if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Recording...'; }
                const choice = document.querySelector('input[name="choice"]:checked').value;
                // Log the choice
                fetch('/log/{{ participant_id }}/trip_choice', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        data: choice,
                        overall_trip_number: {{ overall_trip_number }},
                        condition: {{ condition }},
                        trip_within_condition: {{ trip_within_condition }},
                        trip_id: {{ trip_id }}
                    })
                }).then(async (response) => {
                    if (!response.ok) {
                        const text = await response.text().catch(() => '');
                        throw new Error(text || 'Failed to record choice');
                    }
                    return response.json().catch(() => ({}));
                }).then(() => {
                    // Navigate to next trip, condition reflection, or completion page
                    {% if overall_trip_number < 49 %}
                        {% if (overall_trip_number + 1) % 10 == 0 %}
                            // End of condition block - go to reflection
                            window.location.href = '/check_switch/{{ participant_id }}';
                        {% else %}
                            // Continue with next trip in same condition
                            window.location.href = '/trip/{{ participant_id }}/{{ overall_trip_number + 1 }}';
                        {% endif %}
                    {% else %}
                        // Last trip completed - go to final reflection for last condition
                        window.location.href = '/check_switch/{{ participant_id }}';
                    {% endif %}
                }).catch(err => {
                    console.error(err);
                    alert('Recording failed. Please try again.');
                    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Record Choice'; }
                });
            });
        </script>
    </body>
    </html>
    """, 
    participant_id=participant_id, 
    condition=condition, 
    overall_trip_number=overall_trip_number,
    trip_within_condition=trip_within_condition,
    trip_id=trip_id,
    trip_data=trip_data,
    ridepal_suffix=ridepal_suffix,
    options=options,
    driving_first=driving_first)


@app.route('/check_switch/<participant_id>')
def check_switch(participant_id):
    """Check if participant has condition switches that need reflection"""
    # Find participant's log file
    participant_log_files = [f for f in os.listdir(LOGS_DIR) if f.startswith(f"{participant_id}.csv")]
    if not participant_log_files:
        return "Participant not found.", 404
    # Determine what trip number we're at to know which condition just completed
    # This is called after every 10th trip (trips 9, 19, 29, 39, 49)
    trip_count = 0
    if os.path.exists(f"{LOGS_DIR}/{participant_id}.csv"):
        with open(f"{LOGS_DIR}/{participant_id}.csv", 'r') as f:
            reader = csv.reader(f)
            header = next(reader, None)  # header row
            max_overall = -1
            overall_idx = header.index('overall_trip_number') if header and 'overall_trip_number' in header else 1
            for row in reader:
                try:
                    if len(row) > overall_idx:
                        max_overall = max(max_overall, int(row[overall_idx]))
                except Exception:
                    continue
            trip_count = max_overall + 1 if max_overall >= 0 else 0
    # Determine which condition just completed based on trip count
    if trip_count == 0:
        return "No trips found.", 404
    # Calculate which condition block was just completed
    completed_condition_block = (trip_count - 1) // 10  # 0-based condition index
    # Get the actual condition number that corresponds to this block for this participant
    condition_order_idx, _ = get_participant_assignment(participant_id)
    if condition_order_idx is None:
        return "Participant assignment not found.", 404
    condition_order = CONDITION_ORDER_SEQUENCES[condition_order_idx]
    completed_condition = condition_order[completed_condition_block]
    # Reflection routing priority: check earlier blocks for missing reflections first
    for block_idx in range(0, completed_condition_block + 1):
        cond = condition_order[block_idx]
        refl_file = f"{LOGS_DIR}/{participant_id}_reflection_{cond}.json"
        if not os.path.exists(refl_file):
            return redirect(f'/trip_reflection/{participant_id}/{cond}')
    # Check what stage of reflection we're in for this condition
    trip_reflection_file = f"{LOGS_DIR}/{participant_id}_reflection_{completed_condition}.json"
    # If trip reflection not completed, go there
    if not os.path.exists(trip_reflection_file):
        return redirect(f'/trip_reflection/{participant_id}/{completed_condition}')
    # Both reflections completed for this condition
    if trip_count >= 50:
        # All 50 trips completed, go to study completion
        return redirect(f'/complete/{participant_id}')
    else:
        # Check if we're starting a new block (trip_count is 10, 20, 30, or 40)
        if trip_count > 0 and trip_count % 10 == 0:
            # Starting a new block, show intermediate screen
            block_number = (trip_count // 10) + 1  # Convert to 1-based block number (1-5)
            return redirect(f'/block_intro/{participant_id}/{block_number}/{trip_count}')
        else:
            # More trips to go, continue to next trip (based on max overall index + 1)
            return redirect(f'/trip/{participant_id}/{trip_count}')
        
def get_condition_switch_data(participant_id, condition):
    """Get switch data for a specific condition"""
    switches = get_condition_switches(participant_id)
    if switches:
        condition_key = f"condition_{condition}"
        return switches.get(condition_key)
    return None


@app.route('/block_intro/<participant_id>/<int:block_number>/<int:next_trip_number>')
def block_intro(participant_id, block_number, next_trip_number):
    """Show animated intermediate screen before starting a new block"""
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RidePal Prototype {{ block_number }}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .fade-in {
                animation: fadeIn 2s ease-in-out;
            }
            .pulse-text {
                animation: pulse 1.5s ease-in-out infinite;
            }
            @keyframes fadeIn {
                0% { opacity: 0; transform: translateY(20px); }
                100% { opacity: 1; transform: translateY(0); }
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.8; transform: scale(1.05); }
            }
        </style>
    </head>
    <body class="bg-gradient-to-br from-blue-50 to-indigo-100 min-h-screen flex items-center justify-center">
        <div class="text-center fade-in">
            <div class="mb-8">
                <h1 class="text-6xl font-bold text-blue-600 pulse-text mb-4">
                    Loading
                </h1>
                <div class="w-32 h-1 bg-blue-600 mx-auto rounded-full"></div>
            </div>
            <div class="mt-12">
                <div class="inline-block">
                    <div class="flex space-x-1">
                        <div class="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style="animation-delay: 0s;"></div>
                        <div class="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style="animation-delay: 0.1s;"></div>
                        <div class="w-3 h-3 bg-blue-600 rounded-full animate-bounce" style="animation-delay: 0.2s;"></div>
                    </div>
                </div>
            </div>
        </div>
        <script>
            // Auto-redirect after 3 seconds
            setTimeout(function() {
                window.location.href = '/trip/{{ participant_id }}/{{ next_trip_number }}';
            }, 3000);
        </script>
    </body>
    </html>
    """, 
    participant_id=participant_id,
    block_number=block_number,
    next_trip_number=next_trip_number)


@app.route('/general_likert/<participant_id>/<int:condition>')
def general_likert(participant_id, condition):
    """Skip general attitude questions and go directly to trip reflection"""
    return redirect(f'/trip_reflection/{participant_id}/{condition}')


@app.route('/trip_reflection/<participant_id>/<int:condition>')
def trip_reflection(participant_id, condition):
    """Show trip-specific reflection with trip details and specific questions"""
    # Get the switch data for this specific condition
    switch_data = get_condition_switch_data(participant_id, condition)
    # If no switch data, show walking-only reflection
    if switch_data is None:
        # Calculate next trip number
        trip_count = 0
        if os.path.exists(f"{LOGS_DIR}/{participant_id}.csv"):
            with open(f"{LOGS_DIR}/{participant_id}.csv", 'r') as f:
                reader = csv.reader(f)
                header = next(reader, None)  # header row
                max_overall = -1
                overall_idx = header.index('overall_trip_number') if header and 'overall_trip_number' in header else 1
                for row in reader:
                    try:
                        if len(row) > overall_idx:
                            max_overall = max(max_overall, int(row[overall_idx]))
                    except Exception:
                        continue
                trip_count = max_overall + 1 if max_overall >= 0 else 0
        # Determine next destination after reflection
        if trip_count >= 50:
            next_destination = f'/complete/{participant_id}'
        else:
            next_destination = f'/trip/{participant_id}/{trip_count}'
        # Generate walking-only questions dynamically
        walking_question_html = ""
        for question in WALKING_REFLECTION_QUESTIONS:
            walking_question_html += generate_question_html(question)
        # Generate JavaScript validation for walking questions
        walking_js_validation = generate_javascript_validation(WALKING_REFLECTION_QUESTIONS)
        return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Trip Reflection - Walking Only</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-50 min-h-screen">
            <div class="container mx-auto max-w-4xl px-4 py-8">
                <div class="bg-white rounded-lg shadow-md p-8">
                    <h1 class="text-3xl font-bold text-gray-800 mb-6 text-center">Trip Reflection - Condition {{ condition }}</h1>
                    <div class="mb-6">
                        <p class="text-lg text-gray-700 mb-4">
                            In this condition, you chose to walk for all 10 trips instead of using RidePal. 
                            Please reflect on your decision-making process.
                        </p>
                    </div>
                    <!-- Walking choice reflection form -->
                    <form id="walkingReflectionForm" class="space-y-6">
                        {{ walking_question_html | safe }}
                        <div class="flex justify-center">
                            <button 
                                type="submit" 
                                class="bg-blue-600 text-white px-8 py-3 text-lg rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 font-medium"
                            >
                                Continue
                            </button>
                        </div>
                    </form>
                </div>
            </div>
            <script>
                document.getElementById('walkingReflectionForm').addEventListener('submit', function(e) {
                    e.preventDefault();
                    // Collect responses using dynamic validation
                    const responses = {};
                    {{ walking_js_validation | safe }}
                    // Submit the walking reflection
                    fetch('/complete_reflection/{{ participant_id }}/{{ condition }}', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            reflection_type: 'walking_only',
                            walking_reason: responses['walking.reason']
                        })
                    }).then(async response => {
                        if (!response.ok) {
                            const text = await response.text().catch(() => '');
                            throw new Error(text || 'Failed to complete reflection');
                        }
                        return response.json();
                    }).then(data => {
                        if (data.status === 'reflection_completed') {
                            window.location.href = '{{ next_destination }}';
                        }
                    }).catch(error => {
                        console.error('Error:', error);
                        alert('There was an error submitting your reflection. Please try again.');
                    });
                });
            </script>
        </body>
        </html>
        """, 
        participant_id=participant_id,
        condition=condition,
        next_destination=next_destination,
        walking_question_html=walking_question_html,
        walking_js_validation=walking_js_validation)
    # Adjust to the lowest trip_id where a ride was chosen in this condition (minimal inline scan)
    try:
        csv_path = f"{LOGS_DIR}/{participant_id}.csv"
        if os.path.exists(csv_path):
            with open(csv_path, 'r') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header and all(h in header for h in ['condition', 'choice', 'trip_id', 'overall_trip_number']):
                    cond_idx = header.index('condition')
                    choice_idx = header.index('choice')
                    trip_id_idx = header.index('trip_id')
                    overall_idx = header.index('overall_trip_number')
                    best = None  # (trip_id_int, row)
                    for row in reader:
                        try:
                            if int(row[cond_idx]) == condition and row[choice_idx] != 'walking':
                                tid = int(row[trip_id_idx])
                                if best is None or tid < best[0]:
                                    best = (tid, row)
                        except Exception:
                            continue
                    if best is not None:
                        # Override switch_data to use the lowest trip_id ride row
                        switch_data['trip_id'] = best[0]
                        switch_data['overall_trip_number'] = int(best[1][overall_idx])
                        switch_data['choice'] = best[1][choice_idx]
    except Exception:
        pass
    # Get trip data for the selected switch trip
    trip_id = switch_data['trip_id']
    trip_data = TRIPS_DATA[trip_id]
    # Determine the option details for the choice made
    choice = switch_data['choice']
    if choice == 'walking':
        choice_option = {
            'image': 'walk_option.jpg',
            'display_name': 'Walking',
            'price_text': ''
        }
    elif choice == 'regular_ride':
        # Handle different naming patterns for regular images
        if condition == 0:
            image_name = 'controlA.png'
        elif condition == 3:
            image_name = 'condition3_regular_1.png'
        else:
            image_name = f'condition{condition}_regular.png'
        choice_option = {
            'image': image_name,
            'display_name': 'RidePal (Regular)',
            'price_text': f"(${trip_data['ride_price_usd']:.2f})"
        }
    elif choice == 'eco_ride':
        choice_option = {
            'image': f'condition{condition}_eco_1.png',
            'display_name': 'RidePal (Eco-friendly)',
            'price_text': f"(${trip_data['eco_price_usd']:.2f})"
        }
    else:
        # Fallback
        choice_option = {
            'image': 'walk_option.jpg',
            'display_name': choice.replace('_', ' ').title(),
            'price_text': ''
        }
    # Generate trip reflection questions dynamically
    trip_reflection_html = ""
    for question in TRIP_REFLECTION_QUESTIONS:
        trip_reflection_html += generate_question_html(question)
    # Generate trip Likert questions dynamically
    trip_likert_html = ""
    for i, question in enumerate(TRIP_LIKERT_QUESTIONS, 1):
        trip_likert_html += generate_question_html(question, i)
    # Generate JavaScript validation for all trip questions
    all_trip_questions = TRIP_REFLECTION_QUESTIONS + TRIP_LIKERT_QUESTIONS
    trip_js_validation = generate_javascript_validation(all_trip_questions)
    # Get trip data for the switch trip
    trip_id = switch_data['trip_id']
    trip_data = TRIPS_DATA[trip_id]
    # Determine the option details for the choice made
    choice = switch_data['choice']
    if choice == 'walking':
        choice_option = {
            'image': 'walk_option.jpg',
            'display_name': 'Walking',
            'price_text': ''
        }
    elif choice == 'regular_ride':
        # Handle different naming patterns for regular images
        if condition == 0:
            image_name = 'controlA.png'
        elif condition == 3:
            image_name = 'condition3_regular_1.png'
        else:
            image_name = f'condition{condition}_regular.png'
        choice_option = {
            'image': image_name,
            'display_name': 'RidePal (Regular)',
            'price_text': f"(${trip_data['ride_price_usd']:.2f})"
        }
    elif choice == 'eco_ride':
        choice_option = {
            'image': f'condition{condition}_eco_1.png',
            'display_name': 'RidePal (Eco-friendly)',
            'price_text': f"(${trip_data['eco_price_usd']:.2f})"
        }
    else:
        # Fallback
        choice_option = {
            'image': 'walk_option.jpg',
            'display_name': choice.replace('_', ' ').title(),
            'price_text': ''
        }
    # Generate trip reflection questions dynamically
    trip_reflection_html = ""
    for question in TRIP_REFLECTION_QUESTIONS:
        trip_reflection_html += generate_question_html(question)
    # Generate trip Likert questions dynamically
    trip_likert_html = ""
    for i, question in enumerate(TRIP_LIKERT_QUESTIONS, 1):
        trip_likert_html += generate_question_html(question, i)
    # Generate JavaScript validation for all trip questions
    all_trip_questions = TRIP_REFLECTION_QUESTIONS + TRIP_LIKERT_QUESTIONS
    trip_js_validation = generate_javascript_validation(all_trip_questions)
    # Randomize map display order
    random.seed(f"{participant_id}_{switch_data['overall_trip_number']}_order")
    map_order_random = random.choice([True, False])
    driving_first = map_order_random
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Trip Reflection</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50 min-h-screen">
        <div class="container mx-auto max-w-4xl px-4 py-8">
            <div class="bg-white rounded-lg shadow-md p-8">
                <h1 class="text-2xl font-bold text-gray-800 mb-6"></h1>
                <!-- Trip Information -->
                <div class="mb-8 bg-blue-50 p-6 rounded-lg">
                    <h2 class="text-xl font-semibold text-gray-800 mb-4">Trip Details</h2>
                    <!-- Maps Side by Side -->
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                        {% if driving_first %}
                        <div class="text-center">
                            <h3 class="font-medium text-gray-700 mb-2">Driving Option</h3>
                            <img src="{{ url_for('static', filename=trip_data.driving_image) }}" 
                                 alt="Driving map" 
                                 class="w-full h-auto rounded-lg border shadow-sm">
                        </div>
                        <div class="text-center">
                            <h3 class="font-medium text-gray-700 mb-2">Walking Option</h3>
                            <img src="{{ url_for('static', filename=trip_data.walking_image) }}" 
                                 alt="Walking map" 
                                 class="w-full h-auto rounded-lg border shadow-sm">
                        </div>
                        {% else %}
                        <div class="text-center">
                            <h3 class="font-medium text-gray-700 mb-2">Walking Option</h3>
                            <img src="{{ url_for('static', filename=trip_data.walking_image) }}" 
                                 alt="Walking map" 
                                 class="w-full h-auto rounded-lg border shadow-sm">
                        </div>
                        <div class="text-center">
                            <h3 class="font-medium text-gray-700 mb-2">Driving Option</h3>
                            <img src="{{ url_for('static', filename=trip_data.driving_image) }}" 
                                 alt="Driving map" 
                                 class="w-full h-auto rounded-lg border shadow-sm">
                        </div>
                        {% endif %}
                    </div>
                    <!-- Your Choice -->
                    <div class="text-center bg-white p-4 rounded-lg border">
                        <h3 class="font-medium text-gray-700 mb-3">Your Choice:</h3>
                        <div class="flex-1 items-center justify-center space-x-3">
                            <img src="{{ url_for('static', filename='options/' + choice_option.image) }}" 
                                 alt="{{ choice_option.display_name }}" 
                                 width="300" class="mx-auto mb-3 shadow-sm" />
                            <div class="text-center">
                                <p class="text-gray-600">{{ choice_option.price_text }}</p>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- Reflection Form -->
                <form id="tripReflectionForm" class="space-y-8">
                    <!-- Free Text Questions -->
                    <div class="space-y-6">
                        <h2 class="text-xl font-semibold text-gray-800">Reflection</h2>
                        {{ trip_reflection_html | safe }}
                    </div>
                    <!-- Trip-Specific Likert Questions -->
                    <div class="space-y-6">
                        <h2 class="text-xl font-semibold text-gray-800">Subjective Ratings</h2>
                        <p class="text-gray-600">Please rate your agreement with the following statements about this specific trip:</p>
                        {{ trip_likert_html | safe }}
                    </div>
                    <div class="flex justify-end">
                        <button 
                            type="submit" 
                            class="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 font-medium"
                        >
                            Complete Reflection
                        </button>
                    </div>
                </form>
            </div>
        </div>
        <script>
            document.getElementById('tripReflectionForm').addEventListener('submit', function(e) {
                e.preventDefault();
                console.log('Trip reflection form submitted');
                // Collect responses using dynamic validation
                const responses = {};
                {{ trip_js_validation | safe }}
                console.log('Trip reflection responses:', responses);
                // Separate text and Likert responses
                const textResponses = {
                    rationale: responses.rationale
                };
                const tripLikertResponses = {
                    'credit.lost': responses['credit.lost'],
                    'impact.comparison': responses['impact.comparison']
                };
                // Log the trip reflection responses
                fetch('/log/{{ participant_id }}/trip_reflection', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        rationale: textResponses.rationale,
                        trip_likert_responses: tripLikertResponses,
                        overall_trip_number: {{ switch_data.overall_trip_number }},
                        condition: {{ condition }},
                        trip_id: '{{ switch_data.trip_id }}'
                    })
                }).then(async response => {
                    console.log('Logging response:', response);
                    if (!response.ok) {
                        const text = await response.text().catch(() => '');
                        throw new Error(text || 'Failed to log reflection');
                    }
                    return response.json();
                }).then(() => {
                    console.log('Marking trip reflection complete');
                    // Mark this condition reflection as complete
                    return fetch('/complete_reflection/{{ participant_id }}/{{ condition }}', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            reflection_type: 'switch_based',
                            rationale: textResponses.rationale,
                            trip_likert_responses: tripLikertResponses
                        })
                    });
                }).then(async response => {
                    console.log('Complete reflection response:', response);
                    if (!response.ok) {
                        const text = await response.text().catch(() => '');
                        throw new Error(text || 'Failed to complete reflection');
                    }
                    return response.json();
                }).then(() => {
                    console.log('Redirecting to check_switch');
                    window.location.href = '/check_switch/{{ participant_id }}';
                }).catch(error => {
                    console.error('Error:', error);
                    alert('An error occurred. Please try again.');
                });
            });
        </script>
    </body>
    </html>
    """, 
    participant_id=participant_id, 
    condition=condition,
    switch_data=switch_data,
    trip_data=trip_data,
    choice_option=choice_option,
    trip_reflection_html=trip_reflection_html,
    trip_likert_html=trip_likert_html,
    trip_js_validation=trip_js_validation,
    driving_first=driving_first)

@app.route('/log/<participant_id>/trip_reflection', methods=['POST'])
def log_trip_reflection(participant_id):
    """Log trip-specific reflection responses"""
    data = request.get_json()
    timestamp = datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'participant_id': participant_id,
        'event_type': 'trip_reflection_response',
        'condition': data.get('condition'),
        'overall_trip_number': data.get('overall_trip_number'),
        'trip_id': data.get('trip_id'),
        'trip_likert_responses': data.get('trip_likert_responses')
    }
    # Write to event log
    event_log_filename = f"{EVENT_LOGS_DIR}/{participant_id}_events.jsonl"
    with open(event_log_filename, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
    return jsonify({'status': 'logged'})

@app.route('/complete_reflection/<participant_id>/<int:condition>', methods=['POST'])
def complete_reflection(participant_id, condition):
    """Mark reflection as completed for a specific condition"""
    try:
        data = request.get_json()
    except:
        data = None
    reflection_filename = f"{LOGS_DIR}/{participant_id}_reflection_{condition}.json"
    # Base reflection data
    reflection_data = {
        'participant_id': participant_id,
        'condition': condition,
        'completed_timestamp': datetime.now().isoformat()
    }
    # Check if this is a walking-only reflection or switch-based reflection
    if data and data.get('reflection_type') == 'walking_only':
        # Walking-only reflection
        reflection_data.update({
            'reflection_type': 'walking_only',
            'walking_reason': data.get('walking_reason')
        })
        # Log walking-only reflection event
        log_participant_event(participant_id, '', condition, 'walking_only_reflection', {
            'walking_reason': data.get('walking_reason')
        })
    else:
        # Regular switch-based reflection (existing data structure)
        reflection_data.update({
            'reflection_type': 'switch_based',
            'rationale': data.get('rationale') if data else None,
            'trip_likert_responses': data.get('trip_likert_responses') if data else None
        })
    with open(reflection_filename, 'w') as f:
        json.dump(reflection_data, f)
    # Update CSV with the new reflection data
    update_csv_with_reflection_data(participant_id, condition)
    return jsonify({'status': 'reflection_completed'})


@app.route('/complete/<participant_id>')
def study_complete(participant_id):
    """Study completion page"""
    # Find participant's log file
    participant_log_files = [f for f in os.listdir(LOGS_DIR) if f.startswith(f"{participant_id}.csv")]
    if not participant_log_files:
        return "Participant not found.", 404
    # Log study completion
    log_participant_event(participant_id, '', '', 'study_complete')
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Study Complete</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50 min-h-screen">
        <div class="container mx-auto max-w-2xl px-4 py-16">
            <div class="bg-white rounded-lg shadow-md p-8 text-center">
                <div class="mb-6">
                    <div class="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <svg class="w-8 h-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                    </div>
                    <h1 class="text-3xl font-bold text-gray-800 mb-4">You've completed the main task!</h1>
                    <p class="text-lg text-gray-600 mb-4">Please return to LimeSurvey and copy and paste this code <br/>
                                  <b>XFS20250905</b><br/> 
                                  to continue with the rest of the study.<br/><br/> <b>THIS IS NOT THE PROLIFIC COMPLETION CODE!</b></p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, participant_id=participant_id)

@app.route('/log/<participant_id>/<event_type>', methods=['POST'])
def log_event(participant_id, event_type):
    """Endpoint to log participant events"""
    # Find participant's log file
    participant_log_files = [f for f in os.listdir(LOGS_DIR) if f.startswith(f"{participant_id}.csv")]
    if not participant_log_files:
        app.logger.error(f'Participant not found: {participant_id}')
        return jsonify({'error': 'Participant not found'}), 404
    # Get event data
    data = request.get_json()
    event_data = data.get('data', '') if data else ''
    likert_responses = data.get('likert_responses', {}) if data else {}
    overall_trip_number = data.get('overall_trip_number', '') if data else ''
    condition = data.get('condition', '') if data else ''
    trip_within_condition = data.get('trip_within_condition', '') if data else ''
    trip_id = data.get('trip_id', '') if data else ''
    # Handle trip choices separately - log to both participant log and event log
    if event_type == 'trip_choice':
        success = log_trip_choice(participant_id, overall_trip_number, condition, trip_within_condition, trip_id, event_data)
        log_participant_event(participant_id, overall_trip_number, condition, event_type, event_data, trip_id)
        if not success:
            return jsonify({'status': 'error', 'message': 'Failed to persist trip choice'}), 500
    elif event_type == 'condition_likert':
        # Log each Likert response as separate events for easier analysis
        for question, response in likert_responses.items():
            log_participant_event(participant_id, overall_trip_number, condition, f'likert_{question}', str(response), trip_id)
    else:
        # Log all other events only to event log
        log_participant_event(participant_id, overall_trip_number, condition, event_type, event_data, trip_id)
    return jsonify({'status': 'logged'})


@app.route('/admin/stats')
def admin_stats():
    """Admin endpoint to check assignment statistics"""
    condition_order_counts = {i: 0 for i in range(5)}
    trip_order_counts = {i: 0 for i in range(10)}
    total_participants = 0
    if os.path.exists(ASSIGNMENTS_FILE):
        with open(ASSIGNMENTS_FILE, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 3:
                    condition_order_idx = int(row[1])
                    trip_order_idx = int(row[2])
                    condition_order_counts[condition_order_idx] += 1
                    trip_order_counts[trip_order_idx] += 1
                    total_participants += 1
    return jsonify({
        'total_participants': total_participants,
        'condition_order_counts': condition_order_counts,
        'trip_order_sequence_counts': trip_order_counts
    })
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5002, debug=True)
