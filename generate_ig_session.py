import json
import getpass
from instagrapi import Client
from instagrapi.exceptions import TwoFactorRequired

def main():
    print("==================================================")
    print("Instagram Session Generator (instagrapi)")
    print("Dieses Hilfsskript loggt dich einmalig lokal ein")
    print("und gibt deinen Session-String für GitHub Secrets aus.")
    print("==================================================\n")
    
    username = input("Instagram Benutzername: ").strip()
    password = getpass.getpass("Instagram Passwort: ")
    
    cl = Client()
    
    # Randomisiertes Standard-Device-Setup initialisieren
    cl.delay_range = [1, 3]
    
    try:
        print("\nVersuche einzuloggen...")
        cl.login(username, password)
        print("Erfolgreich eingeloggt!")
    except TwoFactorRequired as e:
        print("\n[INFO] Zwei-Faktor-Authentifizierung (2FA) ist für diesen Account aktiv.")
        verification_code = input("Bitte gib den 2FA-Code (SMS oder Authenticator App) ein: ").strip()
        try:
            cl.login(username, password, verification_code=verification_code)
            print("Erfolgreich eingeloggt mit 2FA!")
        except Exception as login_err:
            print(f"\n[FEHLER] Login mit 2FA fehlgeschlagen: {login_err}")
            return
    except Exception as e:
        print(f"\n[FEHLER] Login fehlgeschlagen: {e}")
        return
        
    # JSON Session-String generieren
    try:
        session_settings = cl.get_settings()
        session_str = json.dumps(session_settings)
        
        print("\n" + "="*80)
        print("ERFOLG! Kopiere die komplette folgende Zeile und füge sie als")
        print("GitHub Secret unter dem Namen 'INSTAGRAM_SESSION' ein:")
        print("="*80)
        print(session_str)
        print("="*80 + "\n")
    except Exception as e:
        print(f"\n[FEHLER] Konnte Session-Einstellungen nicht auslesen: {e}")

if __name__ == "__main__":
    main()
