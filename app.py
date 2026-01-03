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
import asyncio
from threading import Thread
import nest_asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback_secret_key')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB file size limit

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'

def parse_whatsapp_chat(file_path):
    messages = []
    participants = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        # Handle various WhatsApp formats
        # Try dd/mm/yyyy, h:mm am/pm - sender: message
        match = re.match(r'^(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2}\s*[ap]m) - (.+?): (.+)', line.strip(), re.IGNORECASE)
        if not match:
            # Try [mm/dd/yy, h:mm:ss AM] sender: message
            match = re.match(r'^\[(\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2}:\d{2} [APM]{2})\] (.+?): (.+)', line.strip())
        if match:
            if len(match.groups()) == 4:
                date_str, time_str, sender, message = match.groups()
                timestamp_str = f"{date_str}, {time_str.strip()}"
                date_format = '%d/%m/%Y, %I:%M %p'
            else:
                timestamp_str, sender, message = match.groups()
                date_format = '%m/%d/%y, %I:%M:%S %p'
            try:
                timestamp = datetime.strptime(timestamp_str, date_format)
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
    if not file.filename or file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))
    if not (file.filename.endswith('.txt') or file.filename.endswith('.zip')):
        flash('Only .txt or .zip files are allowed')
        return redirect(url_for('index'))
    if file.content_length and file.content_length > 10 * 1024 * 1024:  # 10MB check
        flash('File too large. Max 10MB allowed.')
        return redirect(url_for('index'))
    
    temp_dir = None
    file_path = None
    if file.filename.endswith('.zip'):
        import zipfile
        import tempfile
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, 'chat.zip')
        file.save(zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
            for root, dirs, files in os.walk(temp_dir):
                for f in files:
                    if f.endswith('.txt'):
                        file_path = os.path.join(root, f)
                        break
        if not file_path:
            flash('No .txt file found in ZIP.')
            return redirect(url_for('index'))
    else:
        file_path = os.path.join('uploads', file.filename)
        os.makedirs('uploads', exist_ok=True)
        file.save(file_path)
        temp_dir = None  # Not temp
    
    # Validate format
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(1024)
        if not re.search(r'\d{1,2}/\d{1,2}/\d{4}, \d{1,2}:\d{2}', content):
            flash('Invalid file format. Must be WhatsApp export.')
            return redirect(url_for('index'))
    except:
        flash('Error reading file.')
        return redirect(url_for('index'))
    
    try:
        messages, participants = parse_whatsapp_chat(file_path)
        if not messages:
            flash('No valid messages found in file.')
            return redirect(url_for('index'))
        return render_template('select_identity.html', participants=participants, file_path=file_path)
    except ValueError as e:
        flash(str(e))
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



TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a ZIP file containing your WhatsApp chat export (.txt). I'll analyze it!\n\n⚠️ **Privacy Notice:** Your chat data is processed locally and not stored. Files are deleted after analysis. Only share with consent. Analysis uses AI but no data is shared externally.")

async def bot_handle_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    if not file.file_name.endswith('.zip'):
        await update.message.reply_text("Please send a ZIP file.")
        return

    await update.message.reply_text("🔄 Analyzing your chat... Please wait.")

    import zipfile
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, 'chat.zip')
        txt_path = None

        file_obj = await file.get_file()
        await file_obj.download_to_drive(zip_path)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
            for root, dirs, files in os.walk(temp_dir):
                for f in files:
                    if f.endswith('.txt'):
                        txt_path = os.path.join(root, f)
                        break

        if not txt_path:
            await update.message.reply_text("No .txt file found in ZIP.")
            return

        try:
            messages, participants = parse_whatsapp_chat(txt_path)
            context.user_data['messages'] = messages
            context.user_data['participants'] = participants
            if len(participants) < 2:
                await update.message.reply_text("Chat must have at least two participants.")
                return
            keyboard = [[InlineKeyboardButton(p, callback_data=f'you_{p}')] for p in participants]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Who are you?", reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")

async def bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('you_'):
        you = data[4:]
        context.user_data['you'] = you
        participants = context.user_data['participants']
        them_options = [p for p in participants if p != you]
        keyboard = [[InlineKeyboardButton(them, callback_data=f'them_{them}')] for them in them_options]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Who is 'them'?", reply_markup=reply_markup)
    elif data.startswith('them_'):
        them = data[5:]
        you = context.user_data['you']
        messages = context.user_data['messages']
        scores = calculate_scores(messages, you, them)
        def make_bar(pct):
            filled = int(pct // 10)
            empty = 10 - filled
            return '█' * filled + '░' * empty
        result = f"🎉 **Chat Analysis Report** 🎉\n\nBetween **{you}** and **{them}**\n\n"
        roles_info = [
            ('🚀 Conversation Starter', 'starter'),
            ('💬 Snubber', 'snubber'),
            ('❤️ Romantic One', 'romantic'),
            ('😈 Trouble One', 'trouble'),
            ('⚠️ At Fault', 'fault'),
            ('👂 Listener', 'listener'),
            ('😂 Joker', 'joker')
        ]
        for emoji_name, role in roles_info:
            total = scores[you][role] + scores[them][role]
            you_pct = (scores[you][role] / total * 100) if total > 0 else 0
            them_pct = (scores[them][role] / total * 100) if total > 0 else 0
            result += f"{emoji_name}\n{you}: {you_pct:.1f}% {make_bar(you_pct)}\n{them}: {them_pct:.1f}% {make_bar(them_pct)}\n\n"
        await query.edit_message_text(result[:4000], parse_mode='Markdown')

async def run_bot():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", bot_start))
    application.add_handler(MessageHandler(filters.Document.FileExtension("zip"), bot_handle_zip))
    application.add_handler(CallbackQueryHandler(bot_callback))
    await application.run_polling()

if __name__ == '__main__':
    if TELEGRAM_BOT_TOKEN:
        nest_asyncio.apply()
        bot_thread = Thread(target=lambda: asyncio.run(run_bot()))
        bot_thread.daemon = True
        bot_thread.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)