import os
import sys
import json
import time
import logging
import tempfile
from pathlib import Path
import requests
from dotenv import load_dotenv

# Supabase
from supabase import create_client, Client

# Google & YouTube API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Instagram instagrapi
from instagrapi import Client as InstagramClient
from instagrapi.exceptions import LoginRequired, ClientError

# Logging initialisieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Umgebungsvariablen laden
load_dotenv()

# Konfigurationswerte auslesen
TIKTOK_USERNAME = os.getenv("TIKTOK_USERNAME")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

INSTAGRAM_SESSION = os.getenv("INSTAGRAM_SESSION")

# Supabase Client initialisieren
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase Client erfolgreich initialisiert.")
    except Exception as e:
        logger.error(f"Fehler bei der Initialisierung des Supabase Clients: {e}")
else:
    logger.warning("Supabase Zugangsdaten fehlen. Datenbank-Funktionen sind deaktiviert.")


def is_already_processed(video_id: str) -> bool:
    """
    Prüft in der Supabase-Datenbank, ob das Video bereits verarbeitet wurde.
    """
    if not supabase:
        logger.warning("Supabase nicht konfiguriert. Überspringe Duplikatsprüfung (wird als nicht verarbeitet gewertet).")
        return False
    
    try:
        response = supabase.table("processed_videos").select("video_id").eq("video_id", video_id).execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Fehler bei der Duplikatsprüfung für Video {video_id}: {e}")
        return False


def mark_as_processed(video_id: str, title: str) -> bool:
    """
    Speichert die Video-ID in der Supabase-Datenbank, um doppeltes Posten zu verhindern.
    """
    if not supabase:
        return False
    
    try:
        data = {"video_id": video_id, "title": title[:255] if title else "Untitled TikTok Video"}
        supabase.table("processed_videos").insert(data).execute()
        logger.info(f"Video {video_id} erfolgreich in der PostgreSQL-Datenbank als 'verarbeitet' markiert.")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern der verarbeiteten Video-ID {video_id} in Supabase: {e}")
        return False


def download_tiktok_video(download_url: str) -> str:
    """
    Lädt das TikTok-Video über die TikWM-URL ohne Wasserzeichen in eine temporäre Datei herunter.
    Gibt den Pfad zur temporären Datei zurück.
    """
    logger.info("Starte Download des wasserzeichenfreien Videos von TikWM...")
    try:
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
        temp_file.close()
        
        logger.info(f"Video erfolgreich heruntergeladen: {temp_file.name}")
        return temp_file.name
    except Exception as e:
        logger.error(f"Fehler beim Herunterladen des TikTok-Videos: {e}")
        raise


def post_to_youtube(video_path: str, title: str, description: str) -> bool:
    """
    Lädt das Video auf YouTube Shorts hoch.
    """
    logger.info("Starte Upload auf YouTube Shorts...")
    if not all([YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN]):
        logger.warning("YouTube API Zugangsdaten fehlen. Überspringe YouTube-Upload.")
        return False

    try:
        creds = Credentials(
            token=None,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET
        )
        
        youtube = build("youtube", "v3", credentials=creds)

        shorts_title = title if len(title) <= 100 else title[:90] + "..."
        if "#Shorts" not in shorts_title and "#shorts" not in shorts_title:
            if len(shorts_title) <= 92:
                shorts_title += " #Shorts"
            else:
                shorts_title = shorts_title[:90] + " #Shorts"

        body = {
            "snippet": {
                "title": shorts_title,
                "description": description if description else "Cross-posted from TikTok #Shorts",
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        logger.info(f"Lade Video '{shorts_title}' auf YouTube hoch...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"YouTube Upload-Fortschritt: {int(status.progress() * 100)}%")

        logger.info(f"YouTube-Upload erfolgreich abgeschlossen! Video ID: {response.get('id')}")
        return True

    except HttpError as e:
        logger.error(f"YouTube API Fehler: {e.content.decode() if e.content else e}")
        return False
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim YouTube Upload: {e}")
        return False


def post_to_instagram(video_path: str, caption: str) -> bool:
    """
    Veröffentlicht ein Reel auf Instagram via instagrapi und dem Session-Trick.
    Führt bei abgelaufener Session absichtlich zu sys.exit(1), um Fehlermeldungen via GitHub Actions zu triggern.
    """
    logger.info("Starte Upload auf Instagram Reels via instagrapi...")
    if not INSTAGRAM_SESSION:
        logger.warning("INSTAGRAM_SESSION fehlt in den Umgebungsvariablen. Überspringe Instagram-Upload.")
        return False

    cl = InstagramClient()
    
    # Session laden
    try:
        session_data = json.loads(INSTAGRAM_SESSION)
        cl.set_settings(session_data)
        logger.info("Instagram-Session erfolgreich geladen.")
    except Exception as e:
        logger.error(f"Ungültiges JSON-Format in INSTAGRAM_SESSION: {e}")
        logger.error("Beende Ausführung mit sys.exit(1), um Workflow-Alarm auszulösen.")
        sys.exit(1)

    # Session verifizieren
    try:
        # Ein einfacher API-Aufruf, um die Gültigkeit der Cookies zu prüfen
        cl.get_timeline_feed()
        logger.info("Instagram-Session erfolgreich verifiziert (ist noch aktiv).")
    except LoginRequired as e:
        logger.error(f"Instagram-Session ist abgelaufen oder ungültig (LoginRequired): {e}")
        logger.error("Beende Ausführung mit sys.exit(1), damit GitHub den Administrator benachrichtigt.")
        sys.exit(1)
    except ClientError as e:
        # Falls es ein anderer Client-Fehler bezüglich der Authentifizierung ist
        if "login" in str(e).lower() or "checkpoint" in str(e).lower():
            logger.error(f"Instagram Authentifizierungs- oder Challenge-Fehler: {e}")
            sys.exit(1)
        else:
            logger.error(f"Instagram Client-Fehler beim Verifizieren der Session: {e}")
            return False
    except Exception as e:
        # Falls Instagram rate-limited oder temporär blockiert
        logger.error(f"Unerwarteter Fehler bei der Instagram-Session-Verifizierung: {e}")
        return False

    # Reel hochladen
    try:
        logger.info(f"Lade Reel '{caption[:30]}...' hoch...")
        media = cl.clip_upload(
            path=Path(video_path),
            caption=caption
        )
        logger.info(f"Instagram Reel erfolgreich veröffentlicht! Media ID: {media.id}")
        return True
    except LoginRequired as e:
        logger.error(f"Instagram-Session während des Uploads abgelaufen (LoginRequired): {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fehler beim Hochladen des Reels auf Instagram: {e}")
        return False


def check_new_video():
    """
    Holt die neuesten Videos des TikTok-Benutzers, prüft auf Duplikate und stößt das Cross-Posting an.
    """
    logger.info("Überprüfe TikTok auf neue Videos...")
    if not TIKTOK_USERNAME:
        logger.error("TIKTOK_USERNAME fehlt in den Umgebungsvariablen. Beende Ausführung.")
        return

    tikwm_url = "https://www.tikwm.com/api/user/posts"
    unique_id = TIKTOK_USERNAME if TIKTOK_USERNAME.startswith("@") else f"@{TIKTOK_USERNAME}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "unique_id": unique_id,
        "count": 5
    }
    
    try:
        response = requests.post(tikwm_url, data=payload, headers=headers, timeout=30)
        response.raise_for_status()
        res_json = response.json()
    except Exception as e:
        logger.error(f"Fehler bei der Anfrage an die TikWM API: {e}")
        return

    if res_json.get("code") != 0:
        logger.error(f"TikWM API Fehler: {res_json.get('msg')}")
        return

    videos = res_json.get("data", {}).get("videos", [])
    if not videos:
        logger.info(f"Keine Videos für den Benutzer {unique_id} gefunden.")
        return

    logger.info(f"{len(videos)} Videos von TikTok geladen. Verarbeite chronologisch (ältestes zuerst)...")
    videos.reverse()

    for video in videos:
        video_id = video.get("video_id")
        title = video.get("title", "")
        play_url = video.get("play")
        
        if not video_id or not play_url:
            continue
            
        logger.info(f"Prüfe Video ID: {video_id} - '{title[:30]}...'")
        
        if is_already_processed(video_id):
            logger.info(f"Video {video_id} wurde bereits verarbeitet. Überspringe.")
            continue
            
        logger.info(f"Neues Video gefunden! ID: {video_id}. Starte Cross-Posting...")
        
        local_video_path = None
        try:
            # 1. Video herunterladen
            local_video_path = download_tiktok_video(play_url)
            
            # 2. Uploads starten
            yt_success = post_to_youtube(local_video_path, title, title)
            ig_success = post_to_instagram(local_video_path, title)
            
            # 3. Datenbank-Eintrag schreiben
            # Wir markieren es als verarbeitet, wenn mindestens eine Plattform erfolgreich war,
            # um doppelten Content bei teilweisen Fehlschlägen im nächsten Lauf zu verhindern.
            if yt_success or ig_success:
                mark_as_processed(video_id, title)
                logger.info(f"Cross-Posting für Video {video_id} abgeschlossen.")
            else:
                logger.warning(f"Cross-Posting für Video {video_id} auf allen Plattformen fehlgeschlagen. Wird nicht als verarbeitet markiert.")

        except Exception as e:
            logger.error(f"Fehler im Workflow für Video {video_id}: {e}")
        finally:
            if local_video_path and os.path.exists(local_video_path):
                try:
                    os.remove(local_video_path)
                    logger.info("Lokale temporäre Datei gelöscht.")
                except Exception as e:
                    logger.warning(f"Konnte lokale temporäre Datei nicht löschen: {e}")


if __name__ == "__main__":
    logger.info("=== TikTok Cross-Poster Job gestartet ===")
    check_new_video()
    logger.info("=== TikTok Cross-Poster Job beendet ===")
