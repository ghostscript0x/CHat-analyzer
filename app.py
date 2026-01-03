# BetweenLines - WhatsApp Chat Analyzer
# Installation:
# 1. Install Python dependencies: pip install Flask requests python-dotenv
# 2. Create a .env file in the root directory with: GROQ_API_KEY=your_actual_key_here
# 3. Run: python app.py
#
# Notes: Ensure 'templates' and 'uploads' directories exist.

from flask import Flask, render_template, request, redirect, url_for, flash
import os
import re
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this in production
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB file size limit

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'

def parse_whatsapp_chat(file_path):
    messages = []
    participants = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        # WhatsApp format: dd/mm/yyyy, h:mm am/pm - sender: message
        match = re.match(r'^(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2}\s*[ap]m) - (.+?): (.+)', line.strip(), re.IGNORECASE)
        if match:
            date_str, time_str, sender, message = match.groups()
            timestamp_str = f"{date_str}, {time_str.strip()}"
            try:
                timestamp = datetime.strptime(timestamp_str, '%d/%m/%Y, %I:%M %p')
                messages.append({
                    'timestamp': timestamp,
                    'sender': sender,
                    'message': message
                })
                participants.add(sender)
            except ValueError:
                continue
    participants = list(participants)
    if len(participants) < 2:
        raise ValueError("Chat must contain at least two participants.")
    return messages, participants

def calculate_scores(messages, person_a, person_b):
    # Use Groq AI to classify and score messages
    prompt = f"""
Analyze the following WhatsApp chat messages between {person_a} and {person_b}.
For each role, count how many messages from each person fit the description:

Roles:
- Conversation Starter: Messages that initiate new conversations after long silences.
- Snubber: Messages that are delayed, short, or ignore questions.
- Romantic One: Messages with affectionate language or emojis.
- Trouble One: Sarcastic, teasing, or passive-aggressive messages.
- At Fault: Messages with blame or accusations.

Messages:
""" + "\n".join([f"{msg['timestamp']} - {msg['sender']}: {msg['message']}" for msg in messages[:100]])  # Limit to 100 messages

    try:
        response = requests.post(GROQ_URL, json={
            'model': 'llama3-8b-8192',
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 500
        }, headers={'Authorization': f'Bearer {GROQ_API_KEY}'})
        if response.status_code == 200:
            result = response.json()['choices'][0]['message']['content']
            # Parse the result, assuming AI returns something like "PersonA: starter=5, snubber=3, ..."
            scores = parse_ai_scores(result, person_a, person_b)
        else:
            scores = fallback_scores(messages, person_a, person_b)  # Fallback to manual
    except:
        scores = fallback_scores(messages, person_a, person_b)

    return scores

def parse_ai_scores(text, p1, p2):
    scores = {p1: {'starter': 0, 'snubber': 0, 'romantic': 0, 'trouble': 0, 'fault': 0},
              p2: {'starter': 0, 'snubber': 0, 'romantic': 0, 'trouble': 0, 'fault': 0}}
    lines = text.split('\n')
    current_person = None
    for line in lines:
        line = line.strip()
        if p1 in line and ':' in line:
            current_person = p1
        elif p2 in line and ':' in line:
            current_person = p2
        elif current_person and '=' in line:
            parts = line.split(',')
            for part in parts:
                if '=' in part:
                    role, count = part.split('=')
                    role = role.strip().lower()
                    try:
                        count = int(count.strip())
                        if role in scores[current_person]:
                            scores[current_person][role] = count
                    except ValueError:
                        pass
    return scores

def fallback_scores(messages, person_a, person_b):
    # Original manual scoring
    scores = {person_a: {'starter': 0, 'snubber': 0, 'romantic': 0, 'trouble': 0, 'fault': 0, 'listener': 0, 'joker': 0},
              person_b: {'starter': 0, 'snubber': 0, 'romantic': 0, 'trouble': 0, 'fault': 0, 'listener': 0, 'joker': 0}}
    
    last_timestamp = None
    last_sender = None
    last_msg = None
    for msg in messages:
        sender = msg['sender']
        message = msg['message']
        timestamp = msg['timestamp']
        
        if last_timestamp and (timestamp - last_timestamp) >= timedelta(hours=8):
            scores[sender]['starter'] += 1
        
        if last_sender and last_sender != sender:
            gap = timestamp - last_timestamp
            if gap > timedelta(hours=6):
                scores[sender]['snubber'] += 1
            if len(message.split()) < 4:
                scores[sender]['snubber'] += 1
            if last_msg and '?' in last_msg and not any(word in message.lower() for word in ['yes', 'no', 'maybe']):
                scores[sender]['snubber'] += 1
        
        if any(emoji in message for emoji in ['❤️', '🥰', '😘']):
            scores[sender]['romantic'] += 1
        affectionate_words = ['love', 'darling', 'sweetheart']
        if any(word in message.lower() for word in affectionate_words):
            scores[sender]['romantic'] += 1
        
        if re.search(r'\b(sure|okay|whatever)\b.*\.{3,}', message, re.IGNORECASE):
            scores[sender]['trouble'] += 1
        
        if any(phrase in message.lower() for phrase in ['you always', 'you never', "it's your fault"]):
            scores[sender]['fault'] += 1
        
        # Listener
        if '?' in message:
            scores[sender]['listener'] += 1
        
        # Joker
        if any(word in message.lower() for word in ['lol', 'haha', '😂', '🤣']):
            scores[sender]['joker'] += 1
        
        last_timestamp = timestamp
        last_sender = sender
        last_msg = message
    
    return scores

def get_groq_explanations(messages, you, them):
    # Use Groq to generate explanations
    explanations = {}
    roles = {
        'starter': "Conversation Starter: Initiates conversations after long silences.",
        'snubber': "Snubber: Often delays responses or gives short replies.",
        'romantic': "Romantic One: Uses affectionate language or emojis.",
        'trouble': "Trouble One: Sarcastic or teasing messages.",
        'fault': "At Fault: Messages with blame or accusations.",
        'listener': "Listener: Asks questions and shows interest in others.",
        'joker': "Joker: Uses humor and makes jokes frequently."
    }
    
    for role, base_desc in roles.items():
        # Get sample messages
        samples = [msg['message'] for msg in messages if role in ['starter', 'snubber'] or (role == 'romantic' and ('love' in msg['message'].lower() or '❤️' in msg['message'])) or (role == 'trouble' and 'sure' in msg['message']) or (role == 'fault' and 'you always' in msg['message'].lower())][:3]
        
        prompt = f"Analyze these messages for the role '{base_desc}'. Provide a one-line human-readable explanation: {samples}"
        
        try:
            response = requests.post(GROQ_URL, json={
                'model': 'llama3-8b-8192',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 100
            }, headers={'Authorization': f'Bearer {GROQ_API_KEY}'})
            if response.status_code == 200:
                explanation = response.json()['choices'][0]['message']['content'].strip()
            else:
                explanation = base_desc
        except:
            explanation = base_desc
        
        explanations[role] = explanation
    
    return explanations

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/health')
def health():
    return {"status": "healthy"}, 200

@app.route('/tutorial')
def tutorial():
    return render_template('tutorial.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))
    if not file.filename.endswith('.txt'):
        flash('Only .txt files are allowed')
        return redirect(url_for('index'))
    if file.content_length and file.content_length > 10 * 1024 * 1024:  # 10MB check
        flash('File too large. Max 10MB allowed.')
        return redirect(url_for('index'))
    
    # Read first few lines to validate format
    try:
        content = file.read(1024).decode('utf-8')
        if not re.search(r'\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}', content):
            flash('Invalid file format. Must be WhatsApp export.')
            return redirect(url_for('index'))
        file.seek(0)  # Reset file pointer
    except:
        flash('Error reading file.')
        return redirect(url_for('index'))
    
    file_path = os.path.join('uploads', file.filename)
    os.makedirs('uploads', exist_ok=True)
    file.save(file_path)
    
    try:
        messages, participants = parse_whatsapp_chat(file_path)
        return render_template('select_identity.html', participants=participants, file_path=file_path)
    except ValueError as e:
        flash(str(e))
        return redirect(url_for('index'))
        return render_template('select_identity.html', participant1=p1, participant2=p2, file_path=file_path)
    except ValueError as e:
        flash(str(e))
        return redirect(url_for('index'))

@app.route('/select_identity', methods=['POST'])
def select_identity():
    you = request.form['you']
    them = request.form['them']
    file_path = request.form['file_path']
    messages, participants = parse_whatsapp_chat(file_path)
    if you not in participants or them not in participants or you == them:
        flash('Invalid selection.')
        return redirect(url_for('index'))
    
    scores = calculate_scores(messages, you, them)
    explanations = get_groq_explanations(messages, you, them)
    
    roles = []
    for role_key, role_name in [('starter', 'Conversation Starter'), ('snubber', 'Snubber'), ('romantic', 'Romantic One'), ('trouble', 'Trouble One'), ('fault', 'At Fault'), ('listener', 'Listener'), ('joker', 'Joker')]:
        total = scores[you][role_key] + scores[them][role_key]
        you_pct = (scores[you][role_key] / total * 100) if total > 0 else 0
        them_pct = (scores[them][role_key] / total * 100) if total > 0 else 0
        roles.append({
            'name': role_name,
            'you': round(you_pct, 1),
            'them': round(them_pct, 1),
            'explanation': explanations[role_key]
        })
    
    # Store data in session for export
    session = {}
    session['results'] = {'you': you, 'them': them, 'roles': roles}
    
    # Delete file after processing for security
    import os
    if os.path.exists(file_path):
        os.remove(file_path)
    return render_template('results.html', you=you, them=them, roles=roles)



if __name__ == '__main__':
    app.run(debug=True)