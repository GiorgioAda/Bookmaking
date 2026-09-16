"""Scarica i calendari delle competizioni da openfootball, e li tiene aggiornati.

I calendari erano il collo di bottiglia: cinque divisioni su undici, perche' i
file venivano da cloni fatti a mano e nessuno li rinfrescava. Qui le fonti sono
dichiarate una volta e riscaricate a comando, quindi "aggiornare" e' rieseguire
questo script invece di ricordarsi quale repository conteneva cosa.

Le fonti non stanno tutte nello stesso posto: Ligue 1 e Primeira Liga vivono nel
repository 'europe', con un altro schema di nomi, mentre Serie A e Premier hanno
un repository per nazione. Questa tabella e' il risultato di averlo verificato
URL per URL, non di averlo supposto: le righe commentate sono quelle che oggi
rispondono 404, e restano scritte perche' la prossima volta si controlla se sono
comparse invece di ricominciare la ricerca da zero.

    python examples/scarica_calendari.py            # stagione corrente
    python examples/scarica_calendari.py 2027-28    # un'altra stagione
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RADICE = "https://raw.githubusercontent.com/openfootball/"

# divisione -> (percorso remoto con {s} = stagione, percorso locale)
FONTI = {
    "IT1": ("italy/master/{s}/1-seriea.txt", "italy/{s}/1-seriea.txt"),
    "EN1": ("england/master/{s}/1-premierleague.txt", "england/{s}/1-premierleague.txt"),
    "EN2": ("england/master/{s}/2-championship.txt", "england/{s}/2-championship.txt"),
    "DE1": ("deutschland/master/{s}/1-bundesliga.txt", "deutschland/{s}/1-bundesliga.txt"),
    "ES1": ("espana/master/{s}/1-liga.txt", "espana/{s}/1-liga.txt"),
    # Francia e Portogallo: nel repository 'europe', schema di nomi diverso.
    "FR1": ("europe/master/france/{s}_fr1.txt", "france/{s}/1-ligue1.txt"),
    "PT1": ("europe/master/portugal/{s}_pt1.txt", "portugal/{s}/1-liga.txt"),
    # Non ancora pubblicate per il 2026-27, verificate il 16/09/2026:
    "IT2": ("italy/master/{s}/2-serieb.txt", "italy/{s}/2-serieb.txt"),
    "DE2": ("deutschland/master/{s}/2-bundesliga2.txt", "deutschland/{s}/2-bundesliga2.txt"),
    "ES2": ("espana/master/{s}/2-liga2.txt", "espana/{s}/2-liga2.txt"),
    "FR2": ("europe/master/france/{s}_fr2.txt", "france/{s}/2-ligue2.txt"),
    # Coppe europee: il file esiste solo a stagione iniziata. Contiene anche i
    # risultati, quindi serve sia da calendario sia da fonte per il registro.
    "UCL": ("champions-league/master/{s}/cl.txt", "champions-league/{s}/cl.txt"),
    "UEL": ("champions-league/master/{s}/el.txt", "champions-league/{s}/el.txt"),
    "UECL": ("champions-league/master/{s}/ecl.txt", "champions-league/{s}/ecl.txt"),
}


def stagione_corrente(oggi: datetime | None = None) -> str:
    """La stagione calcistica in corso. Cambia a luglio, non a gennaio."""
    oggi = oggi or datetime.now(timezone.utc)
    inizio = oggi.year if oggi.month >= 7 else oggi.year - 1
    return f"{inizio}-{str(inizio + 1)[2:]}"


def _contesto() -> ssl.SSLContext:
    """Il proxy di questo ambiente ha una CA propria: senza, ogni fetch fallisce
    sulla verifica del certificato, che non va mai disattivata."""
    ctx = ssl.create_default_context()
    ca = Path("/root/.ccr/ca-bundle.crt")
    if ca.exists():
        ctx.load_verify_locations(str(ca))
    return ctx


def scarica(dest: Path, stagione: str) -> dict:
    ctx = _contesto()
    esito = {"stagione": stagione, "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "presi": {}, "assenti": []}
    for div, (remoto, locale) in FONTI.items():
        url = RADICE + remoto.format(s=stagione)
        try:
            with urllib.request.urlopen(url, timeout=30, context=ctx) as r:
                testo = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                esito["assenti"].append(div)
                print(f"  {div:5s} non ancora pubblicato")
                continue
            raise
        f = dest / locale.format(s=stagione)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(testo, encoding="utf-8")
        righe = sum(1 for _ in testo.splitlines())
        esito["presi"][div] = {"url": url, "file": str(f), "righe": righe}
        print(f"  {div:5s} {righe:5d} righe  ->  {f}")
    return esito


def main() -> int:
    stagione = sys.argv[1] if len(sys.argv) > 1 else stagione_corrente()
    dest = Path("/home/user/openfootball")
    print(f"calendari stagione {stagione}")
    esito = scarica(dest, stagione)
    Path("data").mkdir(exist_ok=True)
    Path("data/calendari.json").write_text(
        json.dumps(esito, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(esito['presi'])} calendari presi, {len(esito['assenti'])} non pubblicati"
          f" ({', '.join(esito['assenti']) or '-'})")
    print("registrato in data/calendari.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
