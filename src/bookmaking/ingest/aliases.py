"""Corrispondenza fra i nomi squadra di fonti diverse.

Il calendario scrive "FC Internazionale Milano", lo storico delle quote scrive
"Inter". Finche' i due nomi non vengono uniti, il modello tratta la partita come
se la giocasse una squadra mai vista, le assegna il prior delle sconosciute e
produce una previsione sbagliata **senza segnalare nulla**. E' il guasto piu'
insidioso di tutta la catena, perche' non somiglia a un errore.

Il guasto peggiore, pero', non e' la squadra non riconosciuta: e' quella
riconosciuta male. Semplificando troppo i nomi, "Club Atletico de Madrid" e
"Real Madrid CF" si riducono entrambi a "madrid", e l'Atletico finisce a
giocare con i rating del Real. Da qui le tre difese di questo modulo:

1. **le parole che distinguono restano**. Si tolgono solo le sigle societarie
   che non discriminano mai (FC, CF, RCD, UD...), mai "Real", "Atletico",
   "Athletic", "Deportivo", "Racing", che sono spesso l'unica differenza fra due
   club della stessa citta';
2. **l'abbinamento e' uno-a-uno**. Le coppie candidate vengono ordinate per
   somiglianza e assegnate una sola volta: un nome storico gia' usato non e'
   piu' disponibile, quindi una collisione lascia una squadra scoperta invece di
   duplicarne un'altra;
3. **cio' che resta scoperto viene dichiarato**, non indovinato con una soglia
   piu' permissiva. I casi irriducibili stanno in ``OVERRIDES``, scritti a mano.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path

# Sigle e parole societarie che non distinguono mai due club fra loro.
# "Real", "Atletico", "Athletic", "Deportivo", "Racing", "Sporting" NON sono qui:
# sono spesso l'unica cosa che separa due squadre della stessa citta'.
RUMORE = {
    "fc", "cf", "ac", "as", "ss", "ssc", "us", "sc", "afc", "cd", "rcd", "rc",
    "ud", "sd", "bc", "sv", "sg", "vfl", "vfb", "tsg", "fsv", "bsc", "fsc",
    "club", "calcio", "futbol", "football", "futebol", "balompie", "de", "del",
    "the", "asociacion", "societa", "sportiva", "associazione", "spa", "srl",
    "1846", "1860", "1892", "1899", "1900", "1901", "1902", "1903", "1904",
    "1905", "1906", "1907", "1908", "1909", "1910", "1911", "1912", "1913",
    "1919", "1920", "1921", "1923", "1926", "1927", "1929", "1932", "1946",
}

# Casi che nessuna regola generale prende: abbreviazioni storiche e nomi
# commerciali che non somigliano al nome legale.
OVERRIDES: dict[str, str] = {
    "FC Internazionale Milano": "Inter",
    "Queens Park Rangers FC": "QPR",
    "Wolverhampton Wanderers FC": "Wolves",
    "Athletic Club": "Ath Bilbao",
    "Club Atlético de Madrid": "Ath Madrid",
    "RCD Espanyol de Barcelona": "Espanol",
    "Borussia Mönchengladbach": "M'gladbach",
    # Francia e Portogallo: aggiunti quando i loro calendari sono entrati
    # nell'app. Lo storico delle quote usa la forma corta, il calendario la
    # ragione sociale, e fra le due l'abbinamento automatico non arriva.
    "Paris Saint-Germain FC": "Paris SG",
    "Olympique de Marseille": "Marseille",
    "Olympique Lyonnais": "Lyon",
    "AS Monaco FC": "Monaco",
    "Lille OSC": "Lille",
    "Racing Club de Lens": "Lens",
    "Stade Rennais FC 1901": "Rennes",
    "Stade Brestois 29": "Brest",
    "RC Strasbourg Alsace": "Strasbourg",
    "OGC Nice": "Nice",
    "Toulouse FC": "Toulouse",
    "FC Lorient": "Lorient",
    "Angers SCO": "Angers",
    "AJ Auxerre": "Auxerre",
    "Le Havre AC": "Le Havre",
    "Le Mans FC": "Le Mans",
    "ES Troyes AC": "Troyes",
    "FC Metz": "Metz",
    "FC Nantes": "Nantes",
    "Paris FC": "Paris FC",
    "Sport Lisboa e Benfica": "Benfica",
    "Sporting Clube de Portugal": "Sp Lisbon",
    "Sporting Clube de Braga": "Sp Braga",
    "FC Porto": "Porto",
    "Vitória Guimarães": "Guimaraes",
    "Vitória SC": "Guimaraes",
    "CD Santa Clara": "Santa Clara",
    "CD Nacional": "Nacional",
    "CS Marítimo": "Maritimo",
    "CF Estrela da Amadora": "Estrela",
    "Casa Pia AC": "Casa Pia",
    "FC Famalicão": "Famalicao",
    "FC Arouca": "Arouca",
    "FC Alverca": "Alverca",
    "GD Estoril Praia": "Estoril",
    "Gil Vicente FC": "Gil Vicente",
    "Moreirense FC": "Moreirense",
    "Rio Ave FC": "Rio Ave",
    "Académico de Viseu FC": "Academico Viseu",
    "Rio Ave": "Rio Ave",
}

SOGLIA = 0.62


def chiave(nome: str) -> str:
    """Forma confrontabile di un nome squadra, senza le sigle societarie."""
    s = unicodedata.normalize("NFKD", nome.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    parole = [p for p in s.split() if p not in RUMORE]
    return " ".join(parole) if parole else " ".join(s.split())


def somiglianza(a: str, b: str) -> float:
    ka, kb = chiave(a), chiave(b)
    if ka == kb:
        return 1.0
    ta, tb = set(ka.split()), set(kb.split())
    comune = len(ta & tb) / max(1, min(len(ta), len(tb)))
    # un nome corto contenuto per intero nell'altro ("inter" in "internazionale")
    contiene = 0.0
    if ka and kb and (ka.startswith(kb) or kb.startswith(ka)):
        contiene = 0.8
    return max(comune, contiene, difflib.SequenceMatcher(None, ka, kb).ratio())


def abbina(calendario: list[str], storico: list[str],
           soglia: float = SOGLIA) -> tuple[dict[str, str], list[str]]:
    """Abbina i nomi del calendario a quelli dello storico, uno a uno.

    Restituisce le corrispondenze trovate e l'elenco dei nomi rimasti scoperti,
    che vanno risolti a mano invece che abbassando la soglia.
    """
    trovate: dict[str, str] = {}
    usati: set[str] = set()
    residui = []

    for nome in calendario:
        if nome in OVERRIDES and OVERRIDES[nome] in storico:
            trovate[nome] = OVERRIDES[nome]
            usati.add(OVERRIDES[nome])
        else:
            residui.append(nome)

    # tutte le coppie possibili, assegnate dalla piu' somigliante alla meno:
    # cosi' un abbinamento forte non viene rubato da uno debole
    coppie = []
    for nome in residui:
        for s in storico:
            if s in usati:
                continue
            p = somiglianza(nome, s)
            if p >= soglia:
                coppie.append((p, nome, s))
    coppie.sort(key=lambda c: -c[0])

    for p, nome, s in coppie:
        if nome in trovate or s in usati:
            continue
        trovate[nome] = s
        usati.add(s)

    scoperti = [n for n in calendario if n not in trovate]
    return trovate, scoperti


def verifica(trovate: dict[str, str]) -> list[str]:
    """Controlla che nessun nome storico sia stato assegnato due volte."""
    visti: dict[str, str] = {}
    errori = []
    for cal, st in trovate.items():
        if st in visti:
            errori.append(f"{st!r} assegnato sia a {visti[st]!r} sia a {cal!r}")
        visti[st] = cal
    return errori


def carica(path: str = "data/team_aliases.json") -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
