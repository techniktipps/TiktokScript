# 🤖 TikTok Cross-Poster Automation (instagrapi Edition)

Ein vollautomatisches, produktionsbereites und modulares Python-Skript, das Kurzvideos (TikToks) wasserzeichenfrei herunterlädt und auf **YouTube Shorts** sowie **Instagram Reels** cross-postet. Das Tool läuft komplett kostenlos und serverlos über **GitHub Actions** (per Cronjob gesteuert) und nutzt **Supabase** als zustandsloses Backend für Duplikatschutz (PostgreSQL).

Für Instagram nutzen wir die inoffizielle API-Bibliothek `instagrapi` mit dem **Session-Trick**. Dadurch umgehen wir jegliche Facebook-Bürokratie und lösen das Problem der Zwei-Faktor-Authentifizierung (2FA) elegant.

---

## 📋 Features

- **Automatischer Cronjob:** Läuft alle 30 Minuten vollautomatisch via GitHub Actions.
- **Duplikatschutz:** PostgreSQL-Datenbank (Supabase) stellt sicher, dass kein Video doppelt gepostet wird.
- **Wasserzeichen-Entfernung:** Lädt TikToks ohne Wasserzeichen über die kostenlose TikWM-API herunter.
- **Instagram Reels via instagrapi:** Direkter lokaler Upload der Videodatei unter Verwendung eines zuvor generierten Session-Strings (keine Registrierung als Facebook-Entwickler nötig!).
- **Frühwarn-System:** Läuft die Instagram-Sitzung ab, beendet sich das Skript absichtlich mit `sys.exit(1)`. Der GitHub Actions Workflow schlägt fehl, und du erhältst sofort eine E-Mail-Benachrichtigung von GitHub, um die Session zu erneuern.
- **YouTube Shorts Integration:** Direkt-Upload via YouTube Data API v3 und OAuth2 Refresh Token (läuft dauerhaft ohne manuelle Re-Authentifizierung).
- **Zustandsloses Design (Stateless):** Komplett kompatibel mit GitHub Actions, da keine lokalen Dateizustände auf GitHub persistiert werden müssen.

---

## 📐 Architektur & Workflow

```
                  ┌──────────────────────┐
                  │   TikTok (Quelle)    │
                  └──────────┬───────────┘
                             │
                             ▼
                    [ TikWM Scraper ]
                             │ (Wasserzeichenfreies Video)
                             ▼
                 ┌──────────────────────┐
                 │       main.py        │
                 └───────┬──────┬───────┘
                         │      │
        ┌────────────────┘      └────────────────┐
        │ DB-Duplikats-                          │
        │ Check & Insert                         │
        ▼                                        ▼
┌──────────────┐                         ┌──────────────┐
│   Supabase   │                         │ YouTube API  │
│  PostgreSQL  │                         │  (v3 Shorts) │
└──────────────┘                         └──────┬───────┘
                                                │
                             ┌──────────────────┴──────────┐
                             ▼                             ▼
                      ┌──────────────┐             ┌──────────────┐
                      │  Instagram   │             │   YouTube    │
                      │    Reels     │             │    Shorts    │
                      └──────────────┘             └──────────────┘
```

---

## 🛠️ Setup-Anleitung

### 1. Supabase einrichten (Kostenlos)

1. Erstelle ein Konto bei [Supabase](https://supabase.com/).
2. Erstelle ein neues Projekt.
3. Öffne den **SQL Editor** im Supabase Dashboard und führe folgenden Befehl aus, um die Tabelle für bereits gepostete Videos zu erstellen:

```sql
CREATE TABLE processed_videos (
    video_id TEXT PRIMARY KEY,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

### 2. Instagram Session generieren (Einmalig lokal)

Um das Risiko von Sperrungen zu minimieren und 2FA zu unterstützen, loggst du dich einmalig lokal auf deinem Mac ein und exportierst die Session:

1. Installiere die Abhängigkeiten lokal:
   ```bash
   pip install -r requirements.txt
   ```
2. Starte das Session-Generator-Skript:
   ```bash
   python generate_ig_session.py
   ```
3. Gib deinen Instagram-Benutzernamen und dein Passwort ein.
4. Falls 2FA aktiv ist, fordert dich das Skript zur Eingabe des 2FA-Codes auf.
5. Kopiere den gesamten ausgegebenen JSON-String. Dieser String enthält die verschlüsselten Cookies und Geräte-IDs und wird als GitHub Secret hinterlegt.

---

### 3. YouTube Shorts API einrichten (Google Cloud)

1. Erstelle ein Projekt in der [Google Cloud Console](https://console.cloud.google.com/).
2. Aktiviere die **YouTube Data API v3** für dieses Projekt.
3. Konfiguriere den **OAuth-Zustimmungsbildschirm** (Typ: Extern, füge deine E-Mail hinzu und setze den Status auf "Testen").
4. Erstelle unter **Vorab-Zugangsdaten (Credentials)** eine **OAuth-Client-ID** (Anwendungstyp: *Webanwendung* oder *Desktop-App*).
5. Nutze ein OAuth2-Tauschskript (wie die Datei `py.py` in deinem Workspace), um den Autorisierungscode gegen einen permanenten **Refresh Token** einzutauschen.
   - *Benötigter Scope:* `https://www.googleapis.com/auth/youtube.upload`

---

## 🚀 Lokale Entwicklung

1. Kopiere die Datei `.env.example` zu `.env`:
   ```bash
   cp .env.example .env
   ```
2. Befülle die `.env` mit deinen API-Zugangsdaten und dem generierten `INSTAGRAM_SESSION`-String.
3. Starte das Skript manuell zum Testen:
   ```bash
   python main.py
   ```

---

## ⚙️ GitHub Actions CI/CD einrichten

Pushe den Code in dein GitHub-Repository und hinterlege die Umgebungsvariablen als **Repository Secrets** unter **Settings > Secrets and variables > Actions**:

| Secret Name | Beschreibung | Beispiel |
| :--- | :--- | :--- |
| `TIKTOK_USERNAME` | TikTok-Benutzername (ohne `@`) | `muster_creator` |
| `SUPABASE_URL` | Die URL deines Supabase-Projekts | `https://xxxx.supabase.co` |
| `SUPABASE_KEY` | Supabase API-Key (Service Role Key empfohlen) | `eyJhbGciOi...` |
| `YOUTUBE_CLIENT_ID` | Google OAuth2 Client ID | `12345-abcde.apps.googleusercontent.com` |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth2 Client Secret | `GOCSPX-xxxxxx` |
| `YOUTUBE_REFRESH_TOKEN`| YouTube API OAuth2 Refresh Token | `1//0xxxxxx` |
| `INSTAGRAM_SESSION` | JSON-Session-String aus dem Generator-Skript | `{"cookie": "...", ...}` |

Das GitHub Actions Skript (`.github/workflows/cross_poster.yml`) führt den Workflow ab sofort **alle 30 Minuten** aus.

### 🔔 Frühwarn-System / Session-Ablauf
Wenn deine Instagram-Sitzung abläuft, schlägt der GitHub Action Job fehl. GitHub sendet dir daraufhin automatisch eine E-Mail ("Run failed: TikTok Cross-Poster Automation"). 
Sobald dies geschieht, musst du lediglich:
1. `python generate_ig_session.py` lokal ausführen, um eine neue Session zu generieren.
2. Das Secret `INSTAGRAM_SESSION` in deinen GitHub Repository-Einstellungen mit dem neuen String aktualisieren.
3. Der Cronjob läuft danach wieder reibungslos weiter.
