# Deploying Your Fencing Tips App

## ⚡ Quick Deploy with Railway (Free & Recommended)

Railway offers free hosting that's perfect for this app. Your tips will be saved permanently.

### Step 1: Create a Git Repository

```bash
cd /Users/Christine/Fencing
git init
git add .
git commit -m "Initial commit - Fencing tips app"
```

### Step 2: Deploy to Railway

1. Go to [railway.app](https://railway.app) and sign up (use GitHub login)

2. Click "New Project" → "Deploy from GitHub repo"

3. Connect your GitHub account and create a new repo:
   - Go to GitHub and create a new repository called "fencing-tips"
   - Push your code:
     ```bash
     git remote add origin https://github.com/YOUR_USERNAME/fencing-tips.git
     git branch -M main
     git push -u origin main
     ```

4. Back in Railway, select the "fencing-tips" repo

5. Railway will auto-detect it's a Python app

6. Add your environment variables in Railway:
   - Click on your deployment
   - Go to "Variables" tab
   - Add:
     - `OPENAI_API_KEY`: your OpenAI API key
     - `ANTHROPIC_API_KEY`: your Anthropic API key

7. Railway will automatically deploy! You'll get a URL like:
   `https://fencing-tips.up.railway.app`

### Step 3: Access from Your Phone

1. Open the Railway URL on your phone
2. Tap Share → "Add to Home Screen"
3. Now you have a mobile app!

---

## 💾 Data Persistence

**Important**: Railway's free tier has ephemeral storage, meaning `fencing_data.json` will reset when the app restarts.

### Solution: Use PostgreSQL (Free on Railway)

Let me update the app to use a database instead of JSON files for permanent storage.

---

## 🏠 Alternative: Keep Running Locally

### Option A: Use ngrok (Temporary URL)

1. Install ngrok:
   ```bash
   brew install ngrok
   ```

2. Start your app:
   ```bash
   python3 app.py
   ```

3. In another terminal:
   ```bash
   ngrok http 5001
   ```

4. Use the ngrok URL (e.g., `https://abc123.ngrok.io`) on your phone
   - **Note**: Free ngrok URLs change each time you restart

### Option B: Local Network (Home WiFi Only)

1. Find your Mac's IP address:
   ```bash
   ifconfig | grep "inet " | grep -v 127.0.0.1
   ```
   Look for something like `192.168.1.100`

2. Start the app:
   ```bash
   python3 app.py
   ```

3. On your phone (must be on same WiFi):
   - Open: `http://YOUR_IP:5001`
   - Example: `http://192.168.1.100:5001`

4. Add to home screen for quick access

---

## 🔄 Keeping Your Mac Running

If using local network option, your Mac needs to stay on:

1. System Settings → Battery → Options
2. Disable "Put hard disks to sleep when possible"
3. Enable "Wake for network access"

Or use a tool like [Amphetamine](https://apps.apple.com/us/app/amphetamine/id937984704) (free Mac app) to keep your Mac awake when running the server.

---

## Which Option Should You Choose?

- **Railway**: Best for accessing anywhere, but needs database setup for permanent storage
- **ngrok**: Good for testing, but URL changes frequently
- **Local Network**: Perfect if you only need it at home and want to keep data local

Want me to help you set up Railway with a database for permanent storage?
