import os
import time
import logging
import tempfile
import requests
from dotenv import load_dotenv

# Supabase
from supabase import create_client, Client

# Google & YouTube API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

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
SUPABASE_BUCKET_NAME = os.getenv("SUPABASE_BUCKET_NAME", "videos")

YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

INSTAGRAM_BUSINESS_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")

# Supabase Client initialisieren
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase Client erfolgreich initialisiert.")
    except Exception as e:
        logger.error(f"Fehler bei der Initialisierung des Supabase Clients: {e}")
else:
    logger.warning("Supabase Zugangsdaten fehlen. Datenbank- und Storage-Funktionen sind deaktiviert.")


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
        # Im Zweifel nicht posten, um Doppelposts zu vermeiden, oder posten? 
        # Standardmäßig geben wir False zurück, um Fehler nicht blockierend zu machen, 
        # aber loggen den Fehler deutlich.
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
        
        # Temporäre Datei erstellen, die nach Gebrauch gelöscht werden kann
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


def upload_to_supabase(local_path: str, filename: str) -> str:
    """
    Lädt das Video in den Supabase Storage Bucket hoch.
    Gibt die öffentliche URL des Videos zurück.
    """
    if not supabase:
        raise ValueError("Supabase Client ist nicht initialisiert.")
    
    logger.info(f"Lade Video in Supabase Storage hoch: {filename} ...")
    try:
        with open(local_path, "rb") as f:
            # Datei in den Bucket hochladen (MIME-Type explizit auf video/mp4 setzen)
            supabase.storage.from_(SUPABASE_BUCKET_NAME).upload(
                path=filename,
                file=f,
                file_options={"content-type": "video/mp4", "x-upsert": "true"}
            )
        
        # Öffentliche URL abrufen
        public_url = supabase.storage.from_(SUPABASE_BUCKET_NAME).get_public_url(filename)
        logger.info(f"Video erfolgreich hochgeladen. Öffentliche URL: {public_url}")
        return public_url
    except Exception as e:
        logger.error(f"Fehler beim Upload in Supabase Storage: {e}")
        raise


def delete_from_supabase(filename: str):
    """
    Löscht das temporäre Video aus dem Supabase Storage Bucket.
    """
    if not supabase:
        return
    
    logger.info(f"Lösche temporäres Video aus Supabase Storage: {filename} ...")
    try:
        supabase.storage.from_(SUPABASE_BUCKET_NAME).remove([filename])
        logger.info("Temporäres Video erfolgreich aus Supabase Storage gelöscht.")
    except Exception as e:
        logger.error(f"Fehler beim Löschen des Videos {filename} aus Supabase Storage: {e}")


def post_to_youtube(video_path: str, title: str, description: str) -> bool:
    """
    Lädt das Video auf YouTube Shorts hoch.
    Nutzt standardmäßig OAuth2 Refresh Tokens zur Authentifizierung in GitHub Actions.
    """
    logger.info("Starte Upload auf YouTube Shorts...")
    if not all([YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN]):
        logger.warning("YouTube API Zugangsdaten fehlen. Überspringe YouTube-Upload.")
        return False

    try:
        # Credentials aufbauen aus dem Refresh Token
        creds = Credentials(
            token=None,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET
        )
        
        youtube = build("youtube", "v3", credentials=creds)

        # Snippet und Status definieren
        # YouTube Shorts benötigen meistens #Shorts im Titel oder in der Beschreibung
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
                "categoryId": "22"  # People & Blogs (Standard)
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        # Medien-Datei vorbereiten
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024  # 1MB Chunks
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


def post_to_instagram(video_url: str, caption: str) -> bool:
    """
    Veröffentlicht ein Reel auf Instagram via Instagram Graph API.
    Benötigt eine öffentlich erreichbare Video-URL (z. B. von Supabase Storage).
    """
    logger.info("Starte Upload auf Instagram Reels...")
    if not all([INSTAGRAM_BUSINESS_ACCOUNT_ID, INSTAGRAM_ACCESS_TOKEN]):
        logger.warning("Instagram API Zugangsdaten fehlen. Überspringe Instagram-Upload.")
        return False

    api_version = "v20.0"
    base_url = f"https://graph.facebook.com/{api_version}"
    
    try:
        # Schritt 1: Medien-Container erstellen
        logger.info("Erstelle Instagram Reels Container...")
        container_url = f"{base_url}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }
        
        response = requests.post(container_url, data=payload)
        response_json = response.json()
        
        if "id" not in response_json:
            logger.error(f"Fehler beim Erstellen des Containers: {response_json}")
            return False
            
        container_id = response_json["id"]
        logger.info(f"Container erfolgreich erstellt. ID: {container_id}. Warte auf Verarbeitung...")

        # Schritt 2: Status-Polling (Reels werden asynchron verarbeitet)
        max_attempts = 30
        attempt = 0
        status_url = f"{base_url}/{container_id}"
        
        while attempt < max_attempts:
            time.sleep(15)  # 15 Sekunden warten pro Poll
            attempt += 1
            
            status_params = {
                "fields": "status_code,status",
                "access_token": INSTAGRAM_ACCESS_TOKEN
            }
            status_response = requests.get(status_url, params=status_params)
            status_json = status_response.json()
            
            status_code = status_json.get("status_code")
            logger.info(f"Instagram Polling-Versuch {attempt}/{max_attempts} - Status: {status_code}")
            
            if status_code == "FINISHED":
                logger.info("Instagram-Verarbeitung abgeschlossen. Veröffentliche Reel...")
                break
            elif status_code == "ERROR":
                logger.error(f"Fehler bei der Instagram-Videoverarbeitung: {status_json}")
                return False
                
        else:
            logger.error("Timeout bei der Instagram-Videoverarbeitung (max. Versuche erreicht).")
            return False

        # Schritt 3: Container veröffentlichen
        publish_url = f"{base_url}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish"
        publish_payload = {
            "creation_id": container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }
        
        publish_response = requests.post(publish_url, data=publish_payload)
        publish_json = publish_response.json()
        
        if "id" in publish_json:
            logger.info(f"Instagram Reel erfolgreich veröffentlicht! Media ID: {publish_json['id']}")
            return True
        else:
            logger.error(f"Fehler bei der Veröffentlichung des Reels: {publish_json}")
            return False

    except Exception as e:
        logger.error(f"Fehler beim Instagram Upload: {e}")
        return False


def check_new_video():
    """
    Holt die neuesten Videos des konfigurierten TikTok-Benutzers via TikWM-API.
    Prüft auf neue Videos und stößt das Cross-Posting an.
    """
    logger.info("Überprüfe TikTok auf neue Videos...")
    if not TIKTOK_USERNAME:
        logger.error("TIKTOK_USERNAME fehlt in den Umgebungsvariablen. Beende Ausführung.")
        return

    # TikWM API User Posts abfragen
    tikwm_url = "https://www.tikwm.com/api/user/posts"
    # unique_id kann mit oder ohne '@' übergeben werden
    unique_id = TIKTOK_USERNAME if TIKTOK_USERNAME.startswith("@") else f"@{TIKTOK_USERNAME}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    payload = {
        "unique_id": unique_id,
        "count": 5  # Die letzten 5 Videos genügen für einen Cronjob alle 30 Minuten
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
    
    # Chronologisch sortieren (das älteste gefundene Video zuerst verarbeiten)
    # TikWM liefert die Videos meistens absteigend (neueste zuerst). Daher kehren wir die Liste um.
    videos.reverse()

    for video in videos:
        video_id = video.get("video_id")
        title = video.get("title", "")
        # no-watermark Play-Link
        play_url = video.get("play")
        
        if not video_id or not play_url:
            continue
            
        logger.info(f"Prüfe Video ID: {video_id} - '{title[:30]}...'")
        
        # Prüfen, ob das Video bereits verarbeitet wurde
        if is_already_processed(video_id):
            logger.info(f"Video {video_id} wurde bereits verarbeitet. Überspringe.")
            continue
            
        logger.info(f"Neues Video gefunden! ID: {video_id}. Starte Cross-Posting...")
        
        local_video_path = None
        supabase_filename = f"tiktok_{video_id}.mp4"
        supabase_url = None
        
        try:
            # 1. Video ohne Wasserzeichen herunterladen
            local_video_path = download_tiktok_video(play_url)
            
            # 2. In Supabase Storage hochladen (für Instagram)
            supabase_url = upload_to_supabase(local_video_path, supabase_filename)
            
            # 3. Plattform-Uploads durchführen
            # Wir fangen Fehler pro Plattform ab, damit der Ausfall einer Plattform die andere nicht blockiert.
            yt_success = post_to_youtube(local_video_path, title, title)
            ig_success = post_to_instagram(supabase_url, title)
            
            # 4. Nach dem Posting aufräumen
            # Wenn mindestens ein Upload angestoßen wurde oder erfolgreich war, markieren wir es als verarbeitet,
            # um Endlosschleifen beim nächsten Cronjob zu vermeiden.
            # Alternativ kann man hier auch strikt fordern, dass beide erfolgreich sein müssen.
            # Um Spamming/Doppelposts bei teilweisem Erfolg zu vermeiden, markieren wir es als verarbeitet,
            # sobald ein Versuch unternommen wurde.
            if yt_success or ig_success:
                mark_as_processed(video_id, title)
                logger.info(f"Cross-Posting für Video {video_id} abgeschlossen.")
            else:
                logger.warning(f"Cross-Posting für Video {video_id} auf allen Plattformen fehlgeschlagen. Wird nicht als verarbeitet markiert.")

        except Exception as e:
            logger.error(f"Fehler im Workflow für Video {video_id}: {e}")
        finally:
            # Lokale temporäre Datei löschen
            if local_video_path and os.path.exists(local_video_path):
                try:
                    os.remove(local_video_path)
                    logger.info("Lokale temporäre Datei gelöscht.")
                except Exception as e:
                    logger.warning(f"Konnte lokale temporäre Datei nicht löschen: {e}")
            
            # Supabase Storage Datei löschen
            if supabase_url:
                delete_from_supabase(supabase_filename)


if __name__ == "__main__":
    logger.info("=== TikTok Cross-Poster Job gestartet ===")
    check_new_video()
    logger.info("=== TikTok Cross-Poster Job beendet ===")
