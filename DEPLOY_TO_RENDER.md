# How to Deploy Fencing Coach to Render

This guide walks you through deploying your Fencing Coach app to Render so you can access it from anywhere.

## What You Need

- GitHub account: https://github.com/christinesalim
- Repository: https://github.com/christinesalim/fencing-coach
- Render account: https://render.com
- Your API keys from `.env` file

## Step-by-Step Deployment

### 1. Push Code to GitHub (Already Done!)

Your code is at: https://github.com/christinesalim/fencing-coach

To update in the future:
```bash
cd /Users/Christine/Fencing
git add .
git commit -m "Description of changes"
git push
```

### 2. Sign Up for Render

1. Go to [render.com](https://render.com)
2. Click **"Get Started"**
3. Sign up with your GitHub account (easiest way)
4. Authorize Render to access your GitHub repositories

### 3. Create Web Service

1. Once logged in, click **"New +"** in the top right
2. Select **"Web Service"**
3. You'll see a list of your GitHub repositories
4. Find **"fencing-coach"** and click **"Connect"**

### 4. Configure the Service

Render will auto-detect most settings. Verify these are correct:

- **Name**: `fencing-coach` (or choose your own)
- **Region**: Choose closest to you (e.g., Oregon)
- **Branch**: `main`
- **Root Directory**: Leave blank
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python app.py`
- **Instance Type**: **Free**

### 5. Add Environment Variables

This is the most important step! Scroll down to **"Environment Variables"**:

1. Click **"Add Environment Variable"**
2. Add the first variable:
   - **Key**: `OPENAI_API_KEY`
   - **Value**: Copy from your `.env` file (starts with `sk-proj-`)

3. Click **"Add Environment Variable"** again
4. Add the second variable:
   - **Key**: `ANTHROPIC_API_KEY`
   - **Value**: Copy from your `.env` file (starts with `sk-ant-`)

**Important**: Make sure to copy the entire key without quotes!

#### Why Two API Keys?

The app uses two different AI services, each with their own strengths:

1. **OpenAI API (Whisper)** - For transcribing audio
   - Converts your voice memos (.m4a files) into text
   - OpenAI's Whisper model is the best at accurate speech-to-text
   - This is the first step when you upload a voice memo

2. **Anthropic API (Claude)** - For analyzing and extracting tips
   - Takes the transcript and intelligently extracts fencing advice
   - Categorizes tips into sections (Patience, When Ahead, etc.)
   - Claude Sonnet 4 is excellent at understanding context and creating actionable advice
   - Also creates the summaries you see

**Why not use just one?**
- OpenAI's Whisper is the industry standard for transcription
- Claude is better at understanding nuanced coaching feedback and extracting actionable tips
- Using both gives you the best results: perfect transcription + intelligent analysis

### 6. Create PostgreSQL Database

**Important**: This ensures your tips persist across restarts and tournaments!

1. In Render dashboard, click **"New +"** → **"PostgreSQL"**
2. Configure:
   - **Name**: `fencing-coach-db`
   - **Database**: `fencing_coach` (or leave default)
   - **User**: Leave default
   - **Region**: Same as your web service
   - **Instance Type**: **Free**

3. Click **"Create Database"**
4. Wait for it to provision (1-2 minutes)
5. Once ready, click on the database name
6. Find **"Internal Database URL"** and **copy it**

### 7. Connect Database to Web Service

1. Go back to your **"fencing-coach"** web service
2. Click the **"Environment"** tab
3. Click **"Add Environment Variable"**
4. Add:
   - **Key**: `DATABASE_URL`
   - **Value**: Paste the Internal Database URL you copied

5. Click **"Save Changes"**

Render will automatically redeploy your app with the database!

### 8. Deploy

1. If not already deployed, click **"Create Web Service"**
2. Render will start building your app (takes 2-3 minutes)
3. Watch the logs - you'll see it installing dependencies and starting
4. When it says **"Your service is live"**, you're done!

### 9. Get Your URL

Once deployed, you'll get a URL like:
```
https://fencing-coach.onrender.com
```

Copy this URL and open it on your phone!

### 8. Add to iPhone Home Screen

1. Open the URL in Safari on your iPhone
2. Tap the **Share** button (square with arrow)
3. Scroll down and tap **"Add to Home Screen"**
4. Name it "Fencing Coach"
5. Tap **"Add"**

Now you have a mobile app! 📱⚔️

## Using Your App

### Upload Voice Memos
1. Record coaching feedback on your iPhone
2. Open the Fencing Coach app
3. Tap "Choose Audio File"
4. Select your voice memo
5. Wait 30-60 seconds for processing
6. View your tips!

### View & Edit Tips
- Tap "View All Tips" to see organized advice
- Tap ✏️ to edit any tip
- Tap 🗑️ to delete tips you don't need
- Tap "Print" to save as PDF

## Important Notes

### Free Tier Limitations
- App "sleeps" after 15 minutes of inactivity
- First request after sleep takes 30-60 seconds to wake up
- This is normal! All your data is saved.
- Tips are stored in PostgreSQL database (permanent storage!)
- Database persists even when app sleeps or restarts

### Updating Your App

When you make changes to your code locally:

```bash
cd /Users/Christine/Fencing
git add .
git commit -m "Description of what you changed"
git push
```

Render automatically detects the push and redeploys! 🎉

### Monitoring Your App

1. Go to [dashboard.render.com](https://dashboard.render.com)
2. Click on "fencing-coach"
3. View logs, metrics, and settings
4. Check if it's sleeping or awake

### Troubleshooting

**App won't start?**
- Check the logs in Render dashboard
- Verify environment variables are set correctly
- Make sure API keys don't have quotes around them

**Upload failing?**
- Check file size (max 50MB)
- Verify API keys are valid
- Check the logs for specific errors

**Tips not saving?**
- This shouldn't happen - Render has persistent storage
- Check logs to see if there are write errors

**App is slow?**
- If it's been inactive, it's waking up (30-60 seconds)
- After that, it should be fast!

## Upgrading (Optional)

If you want the app to never sleep:
- Upgrade to Starter plan ($7/month)
- Your app stays always-on
- Worth it if you use it frequently before competitions

## Your Credentials

- GitHub Repo: https://github.com/christinesalim/fencing-coach
- Render Dashboard: https://dashboard.render.com
- App URL: (will be shown after deployment)

## Contact

Questions? Check the Render documentation or the logs in your dashboard.

Good luck at your competitions! 🤺
