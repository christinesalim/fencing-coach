# Fencing Tips Mobile App

A mobile-friendly web application for uploading voice memos and getting actionable fencing tips.

## Features

- 📱 Upload voice memos directly from your phone
- 🎯 AI-powered extraction of actionable fencing tips
- 📖 Clean, mobile-optimized viewing of all tips
- 💾 Automatic building of tips over time (no duplicates)
- 🖨️ Print-friendly format

## Setup

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Start the Server

```bash
python3 app.py
```

The app will start on `http://0.0.0.0:5000`

### 3. Access from Your Phone

#### Option A: Same WiFi Network (Easiest for home use)

1. Find your computer's local IP address:
   - Mac: System Settings → Network → Your IP will be shown
   - Or run: `ifconfig | grep "inet " | grep -v 127.0.0.1`

2. On your phone, open your browser and go to:
   ```
   http://YOUR_IP_ADDRESS:5000
   ```
   For example: `http://192.168.1.100:5000`

3. Save to your home screen:
   - **iPhone**: Tap Share → Add to Home Screen
   - **Android**: Tap Menu → Add to Home Screen

#### Option B: Deploy to Cloud (Access anywhere)

For access from anywhere, deploy to a service like:
- **Railway** (easiest, free tier available)
- **Heroku**
- **PythonAnywhere**
- **Google Cloud Run**

## Usage

### Upload Voice Memos

1. Open the app on your phone
2. Tap "Choose Audio File"
3. Select your voice memo (.m4a or other audio formats)
4. Wait for processing (usually 30-60 seconds)
5. Your tips will be automatically extracted and added!

### View Tips

1. Tap "View All Tips"
2. Review tips organized by category:
   - 🎯 Patience and Control
   - 📊 When You're Ahead
   - 📏 Distance Management
   - 🛡️ Defense and Retreat
   - 👁️ Reading Your Opponent
   - ⚔️ Attack Execution

3. Tap "Print" to save as PDF or print

### Before a Competition

1. Open the app
2. Go to "View All Tips"
3. Quickly review the key points
4. You can also print and add to your physical notebook

## Data Storage

All tips are stored in `fencing_data.json` in the app directory. This file contains:
- All uploaded sessions with transcripts
- Combined tips (deduplicated)

To backup your tips, simply copy this file.

## Deployment Options

### Railway (Recommended)

1. Install Railway CLI: `npm install -g @railway/cli`
2. Create a `Procfile`:
   ```
   web: python app.py
   ```
3. Deploy:
   ```bash
   railway login
   railway init
   railway up
   ```

### Using ngrok (Quick Testing)

For temporary access from anywhere:

1. Install ngrok: `brew install ngrok`
2. Start the app: `python3 app.py`
3. In another terminal: `ngrok http 5000`
4. Use the ngrok URL on your phone

## Troubleshooting

- **Can't connect from phone**: Make sure both devices are on the same WiFi network
- **Upload fails**: Check that your `.env` file has valid API keys
- **Processing takes too long**: Large audio files may take 1-2 minutes to process

## Security Note

This is designed for personal use. For production deployment:
- Add authentication
- Use HTTPS
- Set up proper file validation
- Add rate limiting
