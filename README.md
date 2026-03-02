# OptiWays 🗺️
**Multimodal Crowdsourced Transit Navigation for the Philippines**

> CS Thesis Project — Android app using Jetpack Compose, Firebase, and a custom Connection Scan Algorithm (CSA) backend deployed on Railway.app

---

## 🏗️ Architecture

```
Android App (Kotlin/Compose)
    ↓ Retrofit HTTP
Railway.app (FastAPI + CSA)     ← philippines-260301.osm.pbf
    
Firebase Auth       → Login / Register
Cloud Firestore     → Reports, Profiles, Leaderboard
Cloud Functions     → Report moderation, point awards
Google Maps SDK     → Map rendering, polylines
FusedLocationAPI    → Live GPS navigation
```

---

## 📁 Project Structure

```
OptiWays/
├── app/                    ← Android app
│   └── src/main/java/com/optiways/
│       ├── data/
│       │   ├── model/      ← Data classes
│       │   ├── remote/     ← Retrofit + Hilt module
│       │   ├── repository/ ← Auth, Route, Incident, Gamification
│       │   └── local/      ← DataStore preferences
│       └── ui/
│           ├── auth/       ← Login + Register
│           ├── routing/    ← Main screen: map + search
│           ├── navigation/ ← Live GPS navigation
│           ├── reporting/  ← Incident report bottom sheet
│           ├── gamification/← Dashboard + leaderboard
│           ├── components/ ← Shared composables
│           └── theme/      ← Material 3 colors + typography
├── backend/                ← Railway.app FastAPI backend
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── functions/              ← Firebase Cloud Functions
│   └── index.js
├── firestore.rules
└── firestore.indexes.json
```

---

## 🚀 Setup Guide

### Step 1 — Firebase Setup
1. Create project at [console.firebase.google.com](https://console.firebase.google.com)
2. Add Android app → package: `com.optiways`
3. Download `google-services.json` → place in `app/`
4. Enable **Authentication** → Email/Password
5. Enable **Cloud Firestore** → Start in Production mode
6. Enable **Cloud Functions**
7. Deploy Firestore rules: `firebase deploy --only firestore`
8. Deploy indexes: `firebase deploy --only firestore:indexes`
9. Deploy functions: `cd functions && npm install && firebase deploy --only functions`

### Step 2 — Google Maps API
1. [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create API key → restrict to `com.optiways`
3. Enable: **Maps SDK for Android**, **Places API**
4. Add to `local.properties`: `MAPS_API_KEY=your_key_here`

### Step 3 — Railway.app Backend
1. Create account at [railway.app](https://railway.app)
2. New Project → Deploy from GitHub → select `backend/` folder
3. Add your `philippines-260301.osm.pbf` to Railway volume at `/app/data/`
4. Copy the Railway URL (e.g. `https://optiways-backend.railway.app/`)
5. Add to `local.properties`: `CSA_BASE_URL=https://optiways-backend.railway.app/`

### Step 4 — Build Android App
```bash
# Open project in Android Studio Hedgehog or later
# Sync Gradle → Run on device or emulator
./gradlew assembleDebug
```

---

## 🧑‍💻 Commuter Profiles

| Profile | API Key | Optimization |
|---------|---------|-------------|
| Standard | `default` | Fastest route |
| Night-Shift | `night_shift` | 24hr, lit paths, 2AM cutoff |
| Student | `student` | Lowest fare, 20% discount |
| Accessible | `accessible` | No stairs, elevator-only |

---

## 🎮 Gamification

| Action | Points |
|--------|--------|
| Submit report | +10 |
| Report verified | +50 |
| Give upvote | +5 |
| Complete navigation | +10 |

| Rank | Min Points |
|------|-----------|
| 🚶 Commuter | 0 |
| 🧭 Navigator | 500 |
| 🗺️ PathFinder | 2,000 |
| ⭐ OptiMaster | 5,000 |

---

## 🛡️ Report Moderation Logic

```
New Report → status: PENDING
    ↓
Reporter trustScore >= 0.7?  → YES → status: VERIFIED immediately
    ↓ NO
Accumulate upvotes from nearby users
    ↓
upvotes >= 2?  → YES → status: VERIFIED (Cloud Function)
    ↓ NO
Report expires after 2 hours → status: EXPIRED
```

---

## 📚 Tech Stack

- **Android**: Kotlin, Jetpack Compose, Material 3, Hilt DI
- **Maps**: Google Maps Compose SDK
- **Backend**: FastAPI (Python), Railway.app
- **Routing**: Connection Scan Algorithm (CSA) with `philippines-260301.osm.pbf`
- **Auth**: Firebase Authentication
- **Database**: Cloud Firestore
- **Serverless**: Firebase Cloud Functions (asia-east1)
