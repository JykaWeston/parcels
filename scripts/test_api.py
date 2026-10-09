#!/usr/bin/env python3
"""Test rapide de l'intégration contre l'API Ship24 réelle.

Usage :
    .venv/bin/python scripts/test_api.py apik_votre_cle
    # avec un numéro de suivi réel :
    .venv/bin/python scripts/test_api.py apik_votre_cle 9400115901047177598206

Le plan gratuit autorise 10 colis/mois : chaque numéro NOUVEAU consomme un
créneau. Pour un test sans consommation, utilisez un numéro déjà tracké dans
votre dashboard Ship24 (il sera reconnu, pas recréé).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

from aiohttp import ClientSession  # noqa: E402

from ship24.api import Ship24ApiClient  # noqa: E402
from ship24.exceptions import Ship24Error  # noqa: E402


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    api_key = sys.argv[1]
    tracking_number = sys.argv[2] if len(sys.argv) > 2 else None

    async with ClientSession() as session:
        client = Ship24ApiClient(session, api_key)

        try:
            trackers = await client.async_validate_key()
        except Ship24Error as err:
            print(f"✗ Clé API invalide ou connexion impossible : {err}")
            return 1

        print(f"✓ Clé API valide — {len(trackers)} tracker(s) existant(s)")
        for tracker in trackers[:10]:
            print(
                f"  • {tracker.get('trackingNumber')} "
                f"(id={tracker.get('trackerId')}, "
                f"abonné={tracker.get('isSubscribed')})"
            )

        if not tracking_number:
            return 0

        print(f"\n→ Suivi de {tracking_number} (premier appel : jusqu'à 1 min)…")
        try:
            data = await client.async_track(tracking_number, label="Test script")
        except Ship24Error as err:
            print(f"✗ Échec : {err}")
            return 1

        print(f"✓ Tracker créé/retrouvé : {data.tracker_id}")
        print(f"  Statut      : {data.status}")
        print(f"  Livraison   : {data.estimated_delivery_date or 'inconnue'}")
        print(f"  Destination : {data.destination_country or '?'}")
        for event in data.events[:5]:
            moment = (
                event.occurrence_datetime.isoformat()
                if event.occurrence_datetime
                else "?"
            )
            print(f"  [{moment}] {event.status} — {event.location or ''}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
