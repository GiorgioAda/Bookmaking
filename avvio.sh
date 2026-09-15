#!/usr/bin/env bash
# Prepara tutto ed esegue le verifiche. Scrive rapporto.txt da rimandare indietro.
#
#   bash avvio.sh
#
set -u
cd "$(dirname "$0")"
RAPPORTO="rapporto.txt"

{
  echo "=== Rapporto Bookmaking ==="
  date
  echo

  echo "--- 1. Ambiente ---"
  python3 --version || { echo "Python 3 non trovato: installalo da python.org"; exit 1; }

  if [ ! -d .venv ]; then
    echo "Creo l'ambiente virtuale..."
    python3 -m venv .venv
  fi
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -e ".[dev]"
  echo "Dipendenze installate."
  echo

  echo "--- 2. Test ---"
  ./.venv/bin/python -m pytest -q 2>&1 | tail -3
  echo

  echo "--- 3. Bonus del tuo conto ---"
  ./.venv/bin/python examples/verifica_bonus.py data/bonus_goldbet.json 2>&1
  echo

  echo "--- 4. Dati veri e taratura (puo' richiedere qualche minuto) ---"
  ./.venv/bin/python examples/scarica_e_tara.py --stagioni 6 2>&1
} 2>&1 | tee "$RAPPORTO"

echo
echo "================================================================"
echo "Finito. Il riepilogo e' in: $RAPPORTO"
echo "Mandamelo insieme alla tabella bonus compilata."
echo "================================================================"
