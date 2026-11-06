"""Sicherheitswissen fuer Secure Pro: Ports, Malware-Familien, Luecken und Abwehr.

Alles hier ist festes, gepruefetes Wissen ohne Netz. Secure Pro nutzt es fuer Befunde,
das Modell liest es mit dem Werkzeug secure_knowledge. Ein offener Port oder ein Treffer
hier ist ein Verdacht, kein Beweis: Viele Ports nutzen auch harmlose Programme.
"""

from __future__ import annotations

import re
from typing import Any

# Ports, die typische Schadsoftware, Fernsteuerungen (RAT) oder Krypto-Miner nutzen.
# Quelle: oeffentliche Analysen von CERT, CISA, MITRE ATT&CK und Herstellern.
MALWARE_PORTS: dict[int, tuple[str, str]] = {
    1080: ("SOCKS-Proxy", "Schadsoftware macht Geräte oft zum Proxy für fremden Verkehr."),
    1337: ("Hintertür (1337)", "Beliebter Port für Hintertüren und Test-Shells."),
    1604: ("DarkComet-RAT", "Fernsteuerung, die Bildschirm, Tastatur und Dateien liest."),
    2323: ("Telnet-Ersatz (Mirai)", "Mirai und Nachfolger suchen hier schwache Passwörter."),
    3333: ("Mining-Pool (Stratum)", "Krypto-Miner melden sich oft über diesen Port."),
    4444: ("Metasploit/Hintertür", "Standardport vieler Reverse-Shells und Hintertüren."),
    5552: ("njRAT", "Fernsteuerung, oft über Raubkopien und Spiele-Cheats verbreitet."),
    5555: ("Android-Debugging (ADB)", "Offenes ADB lässt Fremde Apps installieren. Botnetze "
                                      "wie ADB.Miner nutzen das."),
    6666: ("IRC-Botnetz", "Alte Botnetze steuern Geräte über IRC."),
    6667: ("IRC-Botnetz", "Alte Botnetze steuern Geräte über IRC."),
    7547: ("TR-069 offen", "Fernwartung von Routern. 2016 nutzte Mirai eine Lücke darin."),
    12345: ("NetBus-Hintertür", "Klassische Hintertür. Heute selten, aber ein starkes Zeichen."),
    14444: ("Mining-Pool (Stratum)", "Krypto-Miner wie XMRig nutzen diesen Port."),
    20000: ("Hintertür (20000)", "Port mehrerer bekannter Trojaner."),
    27374: ("SubSeven-Hintertür", "Alte Fernsteuerung. Heute selten."),
    31337: ("Back Orifice", "Klassische Hintertür („elite“). Ein starkes Warnzeichen."),
    45700: ("Mining-Pool (Stratum)", "Krypto-Miner nutzen diesen Port oft."),
}

# Dienste, die im Heimnetz ein Risiko sind, wenn sie offen und nicht noetig sind.
RISK_SERVICES: dict[int, tuple[str, str, str]] = {
    21: ("FTP", "Passwörter gehen unverschlüsselt durchs Netz.",
         "Nutze SFTP oder schalte FTP am Gerät aus."),
    23: ("Telnet", "Unverschlüsselt. Mirai und andere Botnetze probieren hier Passwörter.",
         "Schalte Telnet aus. Nutze SSH mit Schlüssel."),
    135: ("Windows-RPC", "Wird für Angriffe innerhalb des Netzes genutzt.",
          "Nur im eigenen Netz erlauben. Windows aktuell halten."),
    139: ("NetBIOS", "Alter Windows-Dienst. Verrät Namen und Freigaben.",
          "NetBIOS über TCP/IP ausschalten, wenn du es nicht brauchst."),
    445: ("SMB (Windows-Freigabe)", "WannaCry und NotPetya verbreiteten sich über SMBv1.",
          "SMBv1 ausschalten, Updates einspielen, Freigaben mit Passwort."),
    1433: ("Microsoft SQL", "Datenbank. Oft Ziel von Passwort-Angriffen.",
           "Nur vom eigenen Rechner erreichbar machen."),
    1883: ("MQTT ohne TLS", "Smart-Home-Nachrichten oft ohne Passwort lesbar.",
           "Passwort und TLS (Port 8883) einschalten."),
    1900: ("UPnP", "Geräte öffnen damit selbst Ports im Router.",
           "UPnP am Router ausschalten, wenn du es nicht brauchst."),
    2375: ("Docker-API ohne TLS", "Wer sie erreicht, steuert den ganzen Rechner.",
           "Docker-API nur über den lokalen Socket oder mit TLS freigeben."),
    3306: ("MySQL", "Datenbank. Oft Ziel von Passwort-Angriffen.",
           "Nur auf 127.0.0.1 lauschen lassen."),
    3389: ("Windows-Fernwartung (RDP)", "Häufiger Weg für Erpressersoftware (Ransomware).",
           "RDP ausschalten oder nur über VPN, mit starkem Passwort und NLA."),
    5432: ("PostgreSQL", "Datenbank. Sollte nicht für alle Geräte offen sein.",
           "Nur auf 127.0.0.1 lauschen lassen."),
    5900: ("VNC", "Bildschirmfreigabe, oft mit schwachem oder ohne Passwort.",
           "VNC ausschalten oder nur über SSH-Tunnel nutzen."),
    6379: ("Redis", "Oft ohne Passwort. Angreifer schreiben damit Dateien.",
           "Passwort setzen und nur auf 127.0.0.1 lauschen."),
    9200: ("Elasticsearch", "Oft ohne Anmeldung. Daten sind dann für alle lesbar.",
           "Anmeldung einschalten, nur lokal lauschen."),
    10250: ("Kubernetes-Kubelet", "Offen erlaubt das Befehle in Containern.",
            "Anmeldung erzwingen, Port nicht im Heimnetz freigeben."),
    11211: ("Memcached", "Ohne Passwort. Wurde für riesige DDoS-Angriffe genutzt.",
            "Nur auf 127.0.0.1 lauschen."),
    27017: ("MongoDB", "Oft ohne Anmeldung. Erpresser löschen Daten und fordern Geld.",
            "Anmeldung einschalten, nur lokal lauschen."),
}

# Malware-Familien und wie man sie im Netz erkennt. Kurz und fuer Laien.
MALWARE_FAMILIES: tuple[dict[str, Any], ...] = (
    {"name": "Mirai und Nachfolger (IoT-Botnetz)",
     "signs": "Gerät probiert viele Adressen auf Port 23, 2323 oder 7547. Kameras und "
              "Router mit Standardpasswort sind betroffen.",
     "defense": "Gerät vom Netz nehmen, auf Werkseinstellung zurücksetzen, Firmware "
                "aktualisieren, Standardpasswort ändern, Telnet ausschalten."},
    {"name": "Erpressersoftware (Ransomware)",
     "signs": "Viele SMB-Verbindungen (445) zu anderen Geräten, plötzlich viele geänderte "
              "Dateien, RDP (3389) von außen offen.",
     "defense": "Betroffenen Rechner sofort vom Netz trennen. Nicht zahlen. Aus einer "
                "Sicherung zurückspielen, die nicht verbunden war. Passwörter ändern."},
    {"name": "Emotet, QakBot und andere Banking-Trojaner",
     "signs": "Kommen per Mail-Anhang (Office-Makros, ZIP, OneNote). Danach Verbindungen "
              "zu vielen fremden Servern und SMB-Verkehr im Netz.",
     "defense": "Rechner trennen, mit aktuellem Virenscanner prüfen, Passwörter von einem "
                "sauberen Gerät ändern. Makros in Office ausschalten."},
    {"name": "Fernsteuerung (RAT: njRAT, DarkComet, AsyncRAT, Remcos)",
     "signs": "Dauerhafte Verbindung zu einem unbekannten Server, oft auf Ports wie 1604, "
              "5552, 4444 oder hohen Ports. Kamera-Licht geht ohne Grund an.",
     "defense": "Rechner trennen, Autostart und geplante Aufgaben prüfen, mit Virenscanner "
                "prüfen, besser neu aufsetzen. Alle Passwörter ändern."},
    {"name": "Krypto-Miner (XMRig und andere)",
     "signs": "Hohe Prozessorlast ohne Grund, Verbindungen zu Mining-Pools (Stratum, "
              "Ports 3333, 4444, 14444, 45700).",
     "defense": "Prozess finden und beenden, Herkunft suchen (Docker, Redis, SSH-Passwort), "
                "Lücke schließen, Passwörter ändern."},
    {"name": "Proxy-Malware (Residential Proxy, SOCKS)",
     "signs": "Gerät leitet fremden Verkehr weiter, offener Port 1080, viele Verbindungen "
              "zu fremden Adressen. Oft in billigen TV-Boxen ab Werk.",
     "defense": "Gerät aus dem Netz nehmen. Bei TV-Boxen ohne Updates: nicht mehr nutzen."},
    {"name": "ARP-Spoofing (Mann in der Mitte)",
     "signs": "Die Hardware-Adresse (MAC) des Routers ändert sich, oder ein Gerät gibt "
              "sich für viele Adressen aus.",
     "defense": "Fremdes Gerät suchen und trennen, WLAN-Passwort ändern, am Router "
                "Client-Isolation oder ein Gast-WLAN nutzen."},
    {"name": "DNS-Umleitung (DNSChanger)",
     "signs": "Der Router nutzt fremde DNS-Server. Bekannte Seiten zeigen falsche "
              "Zertifikate oder Werbung.",
     "defense": "DNS im Router prüfen und zurücksetzen, Router-Passwort ändern, "
                "Firmware aktualisieren, Fernwartung aus."},
)

# Haeufige Schwachstellen im Heimnetz.
WEAKNESSES: tuple[dict[str, str], ...] = (
    {"name": "Standardpasswörter",
     "text": "Viele Router, Kameras und Drucker haben ab Werk bekannte Passwörter. "
             "Ändere sie bei jedem Gerät."},
    {"name": "Veraltete Firmware",
     "text": "Alte Firmware hat bekannte Lücken (CVE). Schalte automatische Updates ein. "
             "Geräte ohne Updates gehören in ein Gast-WLAN."},
    {"name": "UPnP und Portweiterleitungen",
     "text": "Geräte öffnen damit selbst Ports nach außen. Prüfe die Liste im Router."},
    {"name": "Fernwartung von außen",
     "text": "RDP, VNC, SSH mit Passwort oder die Router-Oberfläche sollten nicht aus "
             "dem Internet erreichbar sein. Nutze ein VPN."},
    {"name": "SMBv1",
     "text": "Altes Windows-Protokoll. Ermöglichte WannaCry. In Windows ausschalten."},
    {"name": "Schwaches WLAN",
     "text": "WEP, WPA mit TKIP und WPS sind unsicher. Nutze WPA2-AES oder WPA3 und ein "
             "langes Passwort."},
    {"name": "Unverschlüsselte Dienste",
     "text": "Telnet, FTP und HTTP-Anmeldungen schicken Passwörter lesbar durchs Netz."},
    {"name": "Offene Datenbanken",
     "text": "Redis, MongoDB, Elasticsearch und Memcached oft ohne Passwort. Nur lokal "
             "lauschen lassen."},
    {"name": "Smart-Home ohne Trennung",
     "text": "Kameras und Steckdosen gehören in ein eigenes Netz (Gast-WLAN oder VLAN)."},
    {"name": "Fremder DHCP-Server",
     "text": "Ein zweites Gerät verteilt Adressen und leitet Verkehr um. Prüfe, welche "
             "Router-Adresse deine Geräte bekommen."},
)


def port_info(port: int) -> dict[str, str]:
    """Was ein Port bedeutet -- leer, wenn er weder riskant noch verdaechtig ist."""
    if port in MALWARE_PORTS:
        name, text = MALWARE_PORTS[port]
        return {"port": str(port), "art": "verdächtig", "name": name, "text": text,
                "hint": "Prüfe, welches Programm den Port nutzt. Oft ist es harmlos, "
                        "zum Beispiel ein Entwicklungsserver."}
    if port in RISK_SERVICES:
        name, text, fix = RISK_SERVICES[port]
        return {"port": str(port), "art": "riskant", "name": name, "text": text, "hint": fix}
    return {}


def lookup(query: str, limit: int = 8) -> dict[str, Any]:
    """Sucht im festen Wissen: Portnummer, Dienst, Malware-Name oder Stichwort."""
    text = " ".join(str(query or "").split())[:120]
    if not text:
        return {"error": "Nenne einen Port, einen Dienst, eine Malware oder ein Stichwort."}
    treffer: list[dict[str, Any]] = []
    for nummer in re.findall(r"\b\d{1,5}\b", text):
        info = port_info(int(nummer))
        if info:
            treffer.append(info)
    worte = [w for w in re.findall(r"[\wäöüß-]{3,}", text.casefold())]
    if worte:
        for port in sorted(set(MALWARE_PORTS) | set(RISK_SERVICES)):
            info = port_info(port)
            inhalt = (info["name"] + " " + info["text"]).casefold()
            if info not in treffer and any(w in inhalt for w in worte):
                treffer.append(info)
        for familie in MALWARE_FAMILIES:
            inhalt = " ".join(familie.values()).casefold()
            if any(w in inhalt for w in worte):
                treffer.append({"art": "malware", **familie})
        for schwaeche in WEAKNESSES:
            inhalt = " ".join(schwaeche.values()).casefold()
            if any(w in inhalt for w in worte):
                treffer.append({"art": "schwachstelle", **schwaeche})
    return {"query": text, "results": treffer[:max(1, min(limit, 20))],
            "note": "Festes Wissen ohne Netz. Ein Treffer ist ein Verdacht, kein Beweis. "
                    "Für aktuelle Lücken nutze secure_advisories."}


def topics() -> dict[str, Any]:
    """Ueberblick fuer das Modell: welche Themen es gibt."""
    return {"malware_ports": sorted(MALWARE_PORTS), "risk_ports": sorted(RISK_SERVICES),
            "malware": [f["name"] for f in MALWARE_FAMILIES],
            "weaknesses": [w["name"] for w in WEAKNESSES]}


def _liste(adressen: list[str]) -> str:
    adressen = sorted(set(adressen), key=lambda a: tuple(int(t) for t in a.split(".")))
    mehr = len(adressen) - 4
    return ", ".join(adressen[:4]) + (f" und {mehr} weitere" if mehr > 0 else "")


def network_tips(devices: list[dict[str, Any]], events: list[dict[str, Any]],
                 opts: dict[str, Any], *, router: str = "",
                 nmap_ready: bool = False) -> list[str]:
    """Tipps fuer genau dieses Heimnetz (14.1.3 Terra).

    Aus den Messwerten: offene Dienste je Geraet, nmap-Befunde, Router und die eigenen
    Secure-Pro-Einstellungen. Nur feste Saetze mit Adressen und Ports -- kein Text von Geraeten.
    """
    aktiv = [d for d in devices if d.get("active")]
    je_port: dict[int, list[str]] = {}
    for device in aktiv:
        for port in device.get("ports", []):
            je_port.setdefault(int(port), []).append(str(device["address"]))
    tipps: list[str] = []
    for event in events:
        if event.get("kind") == "vulnerability" and len(tipps) < 4:
            stelle = f"auf Port {event['port']}" if event.get('port') else "am Gerät"
            tipps.append(f"Aktualisiere {event['host']}: nmap meldet dort eine Schwachstelle "
                         f"{stelle}. Suche beim Hersteller nach einem Update.")
    for port in sorted(je_port):
        if port in MALWARE_PORTS:
            name = MALWARE_PORTS[port][0]
            tipps.append(f"Prüfe {_liste(je_port[port])}: Port {port} ({name}) antwortet. "
                         "Finde das Programm dahinter. Kennst du es nicht, nimm das Gerät vom "
                         "Netz.")
    for port in sorted(je_port):
        if port in RISK_SERVICES:
            name, _, abhilfe = RISK_SERVICES[port]
            tipps.append(f"{name} ist offen bei {_liste(je_port[port])}. {abhilfe}")
    nur_http = [str(d["address"]) for d in aktiv
                if set(d.get("ports", [])) & {80, 8080}
                and not set(d.get("ports", [])) & {443, 8443}]
    if nur_http:
        tipps.append(f"{_liste(nur_http)} zeigt eine Weboberfläche nur ohne Verschlüsselung "
                     "(HTTP). Melde dich dort nur im Heimnetz an, mit eigenem Passwort.")
    if je_port.get(22):
        tipps.append(f"SSH ist offen bei {_liste(je_port[22])}. Erlaube dort nur Anmeldung mit "
                     "Schlüssel und schalte die Passwort-Anmeldung aus.")
    kameras = [str(d["address"]) for d in aktiv
               if str(d.get("vendor") or "").startswith(("Hikvision", "Dahua"))]
    if kameras:
        tipps.append(f"Kameras bei {_liste(kameras)}: Halte die Firmware aktuell, ändere das "
                     "Standardpasswort und mach sie nicht aus dem Internet erreichbar.")
    iot = [str(d["address"]) for d in aktiv if d.get("kind") == "Smart-Home-Gerät"]
    if len(iot) >= 3:
        tipps.append(f"{len(iot)} Smart-Home-Geräte antworten. Lege sie in ein Gast-WLAN, "
                     "dann kommen sie nicht an deine PCs.")
    if any(e.get("kind") == "upnp" for e in events):
        tipps.append("UPnP ist am Router an. Schalte es aus, wenn du es nicht brauchst. Dann "
                     "kann kein Gerät selbst Ports ins Internet öffnen.")
    unbekannt = [d for d in aktiv if not d.get("name")]
    if len(unbekannt) >= 3:
        tipps.append("Benenne deine bekannten Geräte in der Geräteliste. Dann fällt ein "
                     "fremdes Gerät sofort auf.")
    if router:
        tipps.append(f"Prüfe deinen Router ({router}): automatische Updates an, UPnP und "
                     "Fernzugriff aus, WLAN mit WPA2-AES oder WPA3, WPS aus.")
    if len(aktiv) > 15:
        tipps.append(f"In deinem Heimnetz antworten {len(aktiv)} Geräte. Lege Kameras, "
                     "Steckdosen und TV-Boxen in ein Gast-WLAN.")
    if opts.get("watch") is False:
        tipps.append("Schalte „Immer überwachen“ ein. Sonst prüft Secure Pro nur auf Knopfdruck.")
    if not opts.get("packets"):
        tipps.append("Schalte „Pakete prüfen“ ein. Dann erkennt Secure Pro auch Portscans und "
                     "ARP-Spoofing.")
    if not opts.get("nmap"):
        tipps.append("Schalte „nmap für Schwachstellen nutzen“ ein. Dann findet Secure Pro "
                     "bekannte Lücken in Diensten." + ("" if nmap_ready else
                                                       " Installiere vorher nmap."))
    if not opts.get("tasks"):
        tipps.append("Lege eine Aufgabe an, zum Beispiel: „Melde dich, wenn ein neues Gerät "
                     "ins Netz kommt.“")
    return tipps[:12]
