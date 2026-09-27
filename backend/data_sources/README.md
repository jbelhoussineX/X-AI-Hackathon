# Collecte officielle intégrée à Pipelex local

Code repris de la contribution `feat/pipelex-comparison`, commit `f5d79fc`,
avec adaptation au parcours local existant. Aucun compte Pipelex hébergé requis.

## Utilisation

Le mode réel de Streamlit utilise par défaut `POLITICAL_DATA_SOURCE=official`.
Aucune clé n'est nécessaire pour les exports publics ; `OPENAI_API_KEY` reste
nécessaire pour les deux appels de modèle (évaluation des manques et rédaction).
Une collecte vide ne déclenche aucun appel de modèle. Aucun appel web OpenAI
n'est fait dans ce mode, même en cas d'indisponibilité d'un inventaire.

Commencer avec `logement`, `transport` ou `énergie`. La correspondance est lexicale,
pas sémantique : tous les mots significatifs doivent figurer dans le titre ou les
thèmes. Un LLM peut décider d'un complément avec un autre mot-clé, au plus une fois.

Le collecteur peut aussi être utilisé sans IA, depuis l'environnement Python :

```bash
python -m backend.data_sources.official --topic logement --start 2024-01-01 --end 2026-09-27 --output data/local/collecte-logement.json
```

Cette commande télécharge des données publiques. Utiliser un nom de sortie neuf.
`data/local/` est ignoré par Git. Il ne s'agit pas d'une base SQLite synchronisée :
les exports sont téléchargés à la demande et le corpus est construit en mémoire.

## Sources et limites

- Assemblée : archive JSON publique de la **17e législature**, limites de taille
  réseau et de décompression, sans extraction ZIP sur disque.
- Sénat : export CSV DOSLEG et lecture de pages HTML/PDF liées aux dossiers.
- Trois notices par institution et par collecte. La présélection filtre le
  **dépôt initial**, distinct de la publication filtrée lors de la validation du
  rapport. Cela peut exclure des textes dont la publication serait dans la période.
- Le corpus initial et le complément réunis sont limités à 60 000 caractères.
  Les pages tronquées et indisponibles sont signalées ; pas d'OCR ni de JavaScript.
- Les citations sont recherchées dans le texte effectivement transmis, en
  normalisant uniquement espaces et composition Unicode. Cela ne valide pas
  leur interprétation, la date ou l'actualité juridique.
- Légifrance/PISTE n'est pas connecté. Aucune clé Assemblée/Sénat n'est attendue.

L'ancien mode web reste disponible via `POLITICAL_DATA_SOURCE=web` ; il utilise
3 à 4 appels de modèle et l'outil web payant. Aucun basculement automatique.

## Vérifications

Les tests importés de l'équipe couvrent les archives, CSV, dates, limites et liens.
Les tests d'intégration utilisent le moteur Pipelex réel et les deux transports
HTTP simulés (`httpx` pour les données, `httpx2` pour le SDK OpenAI). Ils couvrent
le complément décidé par le modèle, les corpus vides et le refus des citations
absentes. Aucun test réel des fournisseurs n'a été lancé pour cette intégration.
