# 🤖 TikTok Cross-Poster Automation

Ein vollautomatisches, produktionsbereites und modulares Python-Skript, das Kurzvideos (TikToks) wasserzeichenfrei herunterlädt und auf **YouTube Shorts** sowie **Instagram Reels** cross-postet. Das Tool läuft komplett kostenlos und serverlos über **GitHub Actions** (per Cronjob gesteuert) und nutzt **Supabase** als zustandsloses Backend für Duplikatschutz (PostgreSQL) und temporäre Videohosting-Zwecke (Storage).

---

## 📋 Features

- **Automatischer Cronjob:** Läuft alle 30 Minuten vollautomatisch via GitHub Actions.
- **Duplikatschutz:** PostgreSQL-Datenbank (Supabase) stellt sicher, dass kein Video doppelt gepostet wird.
- **Wasserzeichen-Entfernung:** Lädt TikToks ohne Wasserzeichen über die TikWM-API herunter.
- **Instagram Reels Integration:** Lädt Videos temporär in Supabase Storage hoch, um eine öffentliche URL für das Instagram-Reels-Container-System bereitzustellen, und löscht die Videos nach erfolgreicher Veröffentlichung wieder.
- **YouTube Shorts Integration:** Direkt-Upload via YouTube Data API v3 und OAuth2 Refresh Token (läuft dauerhaft ohne manuelle Re-Authentifizierung).
- **Zustandsloses Design (Stateless):** Komplett kompatibel mit GitHub Actions, da keine lokalen Dateizustände benötigt werden.
- **Robustes Error-Handling:** Fehler auf einer Plattform (z. B. Instagram) blockieren nicht den Upload auf anderen Plattformen (z. B. YouTube).

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
                 └───────┬───┬───┬──────┘
                         │   │   │
        ┌────────────────┘   │   └────────────────┐
        │ DB-Duplikats-      │   │ Temporärer     │
        │ Check & Insert     │   │ Video-Upload   │
        ▼                    │   ▼                ▼
┌──────────────┐             │ ┌──────────────┐ ┌──────────────┐
│   Supabase   │             │ │   Supabase   │ │ YouTube API  │
│  PostgreSQL  │             │ │   Storage    │ │  (v3 Shorts) │
└──────────────┘             │ └──────┬───────┘ └──────┬───────┘
                             │        │ (Public URL)   │
                             ▼        ▼                │
                       ┌────────────────┐              │
                       │ Instagram Graph│              │
                       │   Reels API    │              │
                       └────────┬───────┘              │
                                │                      │
                                ▼                      ▼
                        ┌──────────────┐       ┌──────────────┐
                        │  Instagram   │       │   YouTube    │
                        │    Reels     │       │    Shorts    │
                        └──────────────┘       └──────────────┘
```

---

## 🛠️ Voraussetzungen & Setup

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

4. Erstelle unter **Storage** einen neuen Bucket namens `videos`.
   - **WICHTIG:** Stelle den Bucket auf **Public** (Öffentlich), damit die Instagram Graph API temporär Lesezugriff auf das Video hat.
   - Setze ggf. die RLS-Policies (Row Level Security) für den Bucket so, dass Uploads (`INSERT`) und Deletions (`DELETE`) für authentifizierte/anonyme Nutzer möglich sind (je nachdem, welchen API-Schlüssel du verwendest).

---

### 2. API-Zugänge einrichten

#### A. YouTube Shorts API (Google Cloud)
1. Erstelle ein Projekt in der [Google Cloud Console](https://console.cloud.google.com/).
2. Aktiviere die **YouTube Data API v3** für dieses Projekt.
3. Konfiguriere den **OAuth-Zustimmungsbildschirm** (Typ: Extern, füge deine E-Mail hinzu und setze den Status auf "Testen").
4. Erstelle unter **Vorab-Zugangsdaten (Credentials)** eine **OAuth-Client-ID** (Anwendungstyp: *Webanwendung* oder *Desktop-App*).
5. Lade die Client-ID und das Client-Secret herunter.
6. Generiere einen **Refresh Token**. Hierfür kannst du Tools wie das offizielle Google OAuth2 Playground verwenden oder lokal ein kleines Python-Skript laufen lassen, um den Autorisierungscode gegen den Refresh Token einzutauschen. 
   - *Benötigter Scope:* `https://www.googleapis.com/auth/youtube.upload`

#### B. Instagram Reels API (Meta for Developers)
1. Registriere dich als Meta Developer auf [Meta for Developers](https://developers.facebook.com/).
2. Erstelle eine App (Typ: Business).
3. Verknüpfe deine Instagram Business-Seite mit einer Facebook-Seite.
4. Generiere im **Graph API Explorer** einen User Access Token mit den Rechten:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
5. Tausche diesen kurzlebigen Token in einen **langlebigen Token** (60 Tage oder zeitlich unbegrenzt) um.
6. Hole die **Instagram Business Account ID** über eine Graph-API-Abfrage oder die Facebook-Seiten-Einstellungen.

---

## 🚀 Lokale Entwicklung

1. Klone das Repository.
2. Erstelle eine virtuelle Umgebung und installiere die Abhängigkeiten:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Unter Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Kopiere die Datei `.env.example` zu `.env`:
   ```bash
   cp .env.example .env
   ```
4. Befülle die `.env` mit deinen API-Zugangsdaten.
5. Starte das Skript manuell:
   ```bash
   python main.py
   ```

---

## ⚙️ GitHub Actions CI/CD einrichten

Um den automatischen Cronjob zu aktivieren, musst du den Code in dein GitHub-Repository pushen und die Umgebungsvariablen als **Repository Secrets** hinterlegen:

1. Gehe in deinem GitHub-Repository auf **Settings > Secrets and variables > Actions**.
2. Erstelle über die Schaltfläche **New repository secret** folgende Secrets:

| Secret Name | Beschreibung | Beispiel |
| :--- | :--- | :--- |
| `TIKTOK_USERNAME` | TikTok-Benutzername (ohne `@`) | `muster_creator` |
| `SUPABASE_URL` | Die URL deines Supabase-Projekts | `https://xxxx.supabase.co` |
| `SUPABASE_KEY` | Supabase API-Key (Service Role Key empfohlen für Write-Rechte) | `eyJhbGciOi...` |
| `SUPABASE_BUCKET_NAME` | Name deines öffentlichen Storage-Buckets | `videos` |
| `YOUTUBE_CLIENT_ID` | Google OAuth2 Client ID | `12345-abcde.apps.googleusercontent.com` |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth2 Client Secret | `GOCSPX-xxxxxx` |
| `YOUTUBE_REFRESH_TOKEN`| YouTube API OAuth2 Refresh Token | `1//0xxxxxx` |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Instagram Business Account ID | `178414xxxxxx` |
| `INSTAGRAM_ACCESS_TOKEN` | Langlebiger Meta Graph API Access Token | `EAAGxxxxx` |

Das GitHub Actions Skript (`.github/workflows/cross_poster.yml`) führt den Workflow ab sofort **alle 30 Minuten** aus. Du kannst den Lauf auch manuell im GitHub Tab **Actions** starten.
