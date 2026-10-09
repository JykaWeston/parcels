# Parcels — suivi de colis Ship24 dans Home Assistant

Intégration Home Assistant personnalisée qui suit vos colis du mois via
l'API [Ship24](https://www.ship24.com) et les remonte dans Home Assistant :
capteurs par colis, notifications de changement de statut et tableau de bord.

## Fonctionnalités

- **Un appareil Home Assistant par colis** avec trois capteurs :
  - **Statut** (`info_received`, `in_transit`, `out_for_delivery`,
    `failed_attempt`, `available_for_pickup`, `exception`, `delivered`) avec
    transporteur, pays d'origine/destination, date de livraison réelle, lien
    de suivi public
  - **Livraison estimée** (capteur timestamp : estimation Ship24, sinon la
    fenêtre du transporteur)
  - **Dernier événement** (texte du transporteur + date, lieu)
- **Ajout de colis** via l'interface (Paramètres → Appareils et services →
  Ship24 → Configurer) ou via le service `ship24.add_parcel`
- **Notifications** : l'intégration émet l'événement `ship24_status_changed`
  à chaque changement de statut → automatisations fournies clés en main
- **Tableau de bord** YAML fourni (100 % natif), qui liste automatiquement
  les colis actifs, les dates estimées et les livrés
- **Hygiène du quota** : désabonnement automatique des trackers livrés depuis
  plus de 7 jours (Ship24 arrête de les suivre) ; polling espacé par défaut
  de 30 min (configurable de 5 à 240 min)

## Étape 1 — Créer le compte Ship24 (gratuit)

1. Créez un compte sur [dashboard.ship24.com](https://dashboard.ship24.com)
   (inscription avec e-mail).
2. Dans le dashboard, section **API** → **Manage API keys** → créez une clé.
   Elle ressemble à `apik_kNjW...`.
3. Le **plan gratuit** couvre **10 colis par mois** — largement suffisant
   pour quelques colis, et les webhooks sont inclus.

> ⚠️ Gardez la clé secrète : elle donne accès à votre quota d'API.

## Étape 2 — Installer l'intégration

Le plus simple : installer directement depuis GitHub via **HACS** :

1. **HACS → ⋮ (en haut à droite) → Dépôts personnalisés**
2. Ajouter `https://github.com/JykaWeston/parcels`, catégorie **Intégration**
3. HACS → **Explorer et télécharger** → chercher **Ship24 Parcels** → Télécharger
4. Redémarrer Home Assistant

Ou manuellement : copiez le dossier `custom_components/ship24` dans
`/config/custom_components/` de votre instance HAOS, pour obtenir :

```
/config/custom_components/ship24/
├── __init__.py, api.py, coordinator.py, config_flow.py
├── const.py, entity.py, exceptions.py, models.py, sensor.py
├── manifest.json, services.yaml
└── translations/ (fr.json, en.json) + strings.json
```

Selon votre moyen d'accès au système de fichiers :

- **File editor / Studio Code Server** (add-on) : créer l'arborescence et
  coller les fichiers un par un (activer « Afficher les fichiers cachés ») ;
- **Samba share** (add-on) : copier le dossier depuis votre Mac via
  `smb://homeassistant.local/config/custom_components/` ;
- **SSH** (add-on Terminal & SSH) :
  ```bash
  scp -r custom_components/ship24 root@homeassistant.local:/config/custom_components/
  ```

Redémarrez Home Assistant après la copie.

## Étape 3 — Configurer

1. **Paramètres → Appareils et services → Ajouter une intégration** →
   chercher **Ship24**.
2. Collez votre clé API (`apik_...`) — elle est validée immédiatement.
3. Dans l'entrée Ship24 → **Configurer** :
   - **Numéro de suivi à ajouter** + **libellé** (ex. « Clavier mécanique »)
   - supprimer des colis via la liste à cocher
   - ajuster l'intervalle de mise à jour (30 min par défaut)

   Le premier ajout d'un numéro peut prendre **jusqu'à une minute** :
   Ship24 interroge les transporteurs en direct.

On peut aussi ajouter un colis par service (utile depuis une automatisation) :

```yaml
action: ship24.add_parcel
data:
  tracking_number: "9400115901047177598206"
  label: "Clavier mécanique"
```

et forcer une mise à jour avec `ship24.refresh`.

## Étape 4 — Notifications

Recopiez le contenu de [`automations/notifications.yaml`](automations/notifications.yaml)
dans votre `automations.yaml` (adaptez `notify.mobile_app_mon_telephone`).
Deux automatisations sont fournies : changement de statut, et « livré 🎉 ».

## Étape 5 — Tableau de bord

Suivez les instructions en tête de
[`lovelace/parcels-dashboard.yaml`](lovelace/parcels-dashboard.yaml) :
déclarer un tableau de bord YAML pointant sur ce fichier. Il liste
automatiquement colis en cours, dates estimées et livrés (aucune entité en dur).

## Fonctionnement

```
HA ── DataUpdateCoordinator (30 min) ──> GET /public/v1/trackers/{id}/results
   │                                        (une requête par colis)
   ├── capteurs (statut / livraison estimée / dernier événement)
   ├── événement ship24_status_changed ──> automatisations de notification
   └── désabonnement auto 7 j après livraison (PATCH isSubscribed=false)
```

- L'ajout d'un colis utilise `POST /public/v1/trackers/track`, idempotent :
  ré-ajouter un numéro déjà suivi ne crée pas de doublon côté Ship24.
- Une erreur d'API sur un colis ne bloque pas les autres ; seule une erreur
  d'authentification passe l'entrée en « nécessite une reconfiguration ».

## Quota et bonnes pratiques

- Plan gratuit : **10 colis/mois**. Les colis livrés n'ont plus d'activité —
  l'intégration les désabonne automatiquement 7 jours après livraison.
- Le suivi d'un même numéro ré-ajouté plus tard est détecté par Ship24
  (idempotence) mais peut compter comme un nouveau colis selon le plan.
- Pour tester sans consommer de quota : les numéros de démo de la doc
  (<https://files.ship24.com/docs/s24-tracking-numbers-sample.txt>.

## Développement

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # 22 tests (API réelle sur serveur local, intégration HA)

# Test manuel contre l'API Ship24 (nécessite votre clé) :
.venv/bin/python scripts/test_api.py apik_votre_cle [numéro_de_suivi]
```

Arborescence du dépôt :

```
custom_components/ship24/   ← l'intégration (à copier dans /config)
lovelace/                   ← tableau de bord YAML
automations/                ← automatisations de notification
scripts/test_api.py         ← test rapide contre l'API réelle
tests/                      ← pytest (client API, parsing, intégration HA)
```

Suivi des tâches : `bd` (beads) — voir AGENTS.md.
