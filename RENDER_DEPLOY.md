# Deploy to Render (Free & Permanent Storage)

## Why Render?
- ✅ **100% Free** - No credit card required
- ✅ **Persistent Storage** - Your tips won't disappear
- ✅ **Access Anywhere** - Get a permanent URL
- ✅ **Auto-Deploy** - Push to GitHub, auto-updates

## Step-by-Step Deployment

### 1. Create GitHub Repository

```bash
cd /Users/Christine/Fencing

# Initialize git (if not already done)
git init
git add .
git commit -m "Fencing tips app"

# Create repo on GitHub
# Go to github.com → New Repository → "fencing-tips"

# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/fencing-tips.git
git branch -M main
git push -u origin main
```

### 2. Deploy to Render

1. Go to [render.com](https://render.com) and sign up (use GitHub login - it's faster)

2. Click **"New +"** → **"Web Service"**

3. Connect your GitHub account and select **"fencing-tips"** repo

4. Render will auto-detect Python. Configure:
   - **Name**: `fencing-tips` (or whatever you want)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Instance Type**: `Free`

5. Click **"Advanced"** and add environment variables:
   - Click **"Add Environment Variable"**
   - Key: `OPENAI_API_KEY`, Value: `[your OpenAI key]`
   - Key: `ANTHROPIC_API_KEY`, Value: `[your Anthropic key]`

6. Click **"Create Web Service"**

7. Wait 2-3 minutes for deployment...

8. You'll get a URL like: `https://fencing-tips.onrender.com`

### 3. Access from Your Phone

1. Open the Render URL on your phone
2. Tap Share → **"Add to Home Screen"**
3. Name it "Fencing Tips"
4. Now it works like a native app!

### 4. Upload Voice Memos

On your phone:
1. Record voice memo on your iPhone
2. Open the Fencing Tips app
3. Tap "Choose Audio File"
4. Select your voice memo
5. Wait ~30-60 seconds
6. View tips!

## Important Notes

### File Storage on Free Tier
Render's free tier has **persistent disk storage** - your `fencing_data.json` will be saved! However:
- If your app is inactive for 15+ minutes, it "spins down" to sleep
- First request after sleep takes 30-60 seconds to wake up
- This is normal and fine - all data is preserved

### Upgrading Later (Optional)
If you want instant response (no sleep):
- Upgrade to paid tier: $7/month
- Keeps app always running
- Worth it if using before every competition

## Updating Your App

When you make changes:
```bash
git add .
git commit -m "Updated tips"
git push
```

Render automatically re-deploys! 🎉

## Troubleshooting

**App won't start?**
- Check Environment Variables are set correctly
- Check deployment logs in Render dashboard

**Tips disappearing?**
- Make sure you're on a Web Service (not Static Site)
- Verify disk storage is enabled (it is by default)

**Upload failing?**
- Check file size (max 50MB)
- Verify API keys are correct in Environment Variables

Need help? The Render logs show all errors clearly.
