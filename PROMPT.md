# Prompt — brancher `pr-route-workout` sur un nouveau dépôt

Colle ce texte dans le fil de l’agent qui prépare le nouveau projet. Le script décide d’une disposition. Il ne merge pas, et il n’exécute pas les skills.

Tu installes le routeur de pull requests `pr-route-workout` (`https://github.com/PierreTsia/ai-pr-routing-workout`) et tu le branches sur ce dépôt. Le CLI s’appelle `pr-route-workout`. Il lit une PR GitHub, envoie un fan-out à Jev (OpenCode Zen, modèle `jev-1.13-free`), puis applique des politiques. La sortie est une disposition, la politique gagnante, les skills armés, et une tâche.

## Installer

```bash
pipx install "git+https://github.com/PierreTsia/ai-pr-routing-workout.git"
```

Python `>= 3.11`. Pour travailler le code : cloner le dépôt et `pip install -e ".[dev]"`, puis `python -m unittest tests.test_routing`.

## Lancer

```bash
pr-route-workout https://github.com/OWNER/REPO/pull/N --json
pr-route-workout OWNER/REPO#N --json
pr-route-workout --fixture dependabot --json
```

Autres fixtures locales, sans GitHub ni Jev : `frontend-form`, `backend-api`, `achievement-track`, `mcp-tool`, `docs-only`, `no-issue`.

`--json` est la sortie à parser. Sans `--json`, le CLI écrit un résumé texte. `--serve` ouvre un dashboard local. Sans clé Jev, le fan-out est construit mais pas envoyé : `judgments` vaut `unavailable`, aucun skill n’est armé.

## Secrets

| Variable | Rôle |
|---|---|
| `GH_TOKEN` ou `GITHUB_TOKEN` | API GitHub. Sinon le CLI tente `gh auth token`. Un dépôt public peut répondre sans token. Un 401/403/404 sans token demande `GH_TOKEN`. |
| `OPENCODE_API_KEY` | Clé Jev. Alias lus dans l’ordre : `ZEN_API_KEY`, `TYPESAFE_API_KEY`, `JEV_API_KEY`, puis `~/.local/share/opencode/auth.json`. |

Dans GitHub Actions, `GITHUB_TOKEN` suffit pour lire la PR. `OPENCODE_API_KEY` est un secret du dépôt. Ne le commite pas.

## Lire le JSON

Champs qui décident de la suite :

- `disposition.value` : une de `blocked`, `needs_author`, `agent_ready`, `ready_for_hitl`, `waiting_for_checks`, `ready_for_merge`
- `disposition.policy_id` : la politique gagnante
- `ai_review.skills` : skills armés (`id`, `noul`). `ai_review.trigger` est vrai seulement si la disposition est `agent_ready`
- `ai_review.task` : phrase à exécuter, du type `Pass pr-review on .github/workflows/pr-route.yml.`
- `facts.jira_keys` : numéros trouvés dans le titre ou le corps (`#123`, `GH-123`, ou `PROJET-123`). `HTTP-2` et `SHA-256` sont ignorés
- `fan_out` : `blast_radius` et `review_depth` sont des scores. Un skill est préselectionné quand son `noul` est `>= 0.6`

## Qui gagne

La sévérité la plus haute gagne. `blocked` bat tout. `needs_author` bat l’agent.

| Disposition | Quand |
|---|---|
| `blocked` | Au moins un check en échec. |
| `needs_author` | Pas de `#123` dans le titre ou le corps, et le diff n’est ni docs-only ni un lockfile seul. |
| `agent_ready` | Au moins un skill `>= 0.6`, et `blast_radius` et `review_depth` sont tous les deux `< 1.5`. Le diff n’a pas besoin d’être du frontend. La tâche cite les fichiers changés. |
| `ready_for_hitl` | `blast_radius >= 1.5` ou `review_depth >= 1.5`. Un libellé « feature » ou une confiance basse ne suffit pas. |
| `waiting_for_checks` | Rien d’autre n’a matché et les checks tournent encore. |
| `ready_for_merge` | Auteur bot (`dependabot[bot]` ou `renovate[bot]`), PR non draft, checks verts, diff limité à un manifest de dépendances. |

Si plusieurs skills passent le seuil, ils sont tous armés. La tâche affichée est celle du premier job dans l’ordre du paquet : `tdd`, `microcopy`, `epic-brief`, `tech-plan`, `new-achievement-track`, `pr-review`, `blog-post`, `split-tickets`.

`agent_ready` veut dire : un agent reste sur la PR et exécute les skills armés jusqu’à ce qu’elle soit merge-ready. Le script ne le fait pas. `ready_for_hitl` veut dire : le rayon est large, une personne tranche. N’active pas l’auto-merge.

## Action GitHub

Déclencheurs utiles : `pull_request` `opened`, `synchronize`, `reopened`, `ready_for_review`, plus un `workflow_dispatch` avec le numéro de PR. Éditer la description ne relance pas `pull_request`. Permissions : `contents: read`, `pull-requests: write`, `checks: read`, `issues: read`.

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.11"
- run: pipx install git+https://github.com/PierreTsia/ai-pr-routing-workout.git
- id: route
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
  run: pr-route-workout "$PR_URL" --json > routing_result.json
```

Ensuite, lis `disposition.value` dans le JSON. Pose un commentaire et un label `routing:*` (`blocked`, `needs-author`, `agent-ready`, `hitl`, `waiting`, `auto-merge`). Mets à jour le même commentaire (marqueur HTML stable) au lieu d’en créer un nouveau à chaque run.

Le workflow de référence vit dans `PierreTsia/workout-app`, fichier `.github/workflows/pr-route.yml`. Il crée encore un commentaire par run. Ne copie pas cette partie.

## Avant de faire confiance aux dispositions

Le paquet est calé sur GymLogic. Pour un autre produit, remplace d’abord :

- `pr_route_workout/domains.py` : les domaines métier et le mapping des chemins. `apps/web` et `apps/api` sont des applications, pas des domaines.
- `pr_route_workout/questions.py` : la liste `SKILLS`. Chaque skill est une phrase que Jev score de 0 à 1. Le seuil d’armement est `0.6`.
- `pr_route_workout/policies.py` : `AGENT_JOBS`, une tâche `Pass <skill> on {files}.` par skill armable. `grill-with-docs` est scoré mais n’a pas de job.
- `pr_route_workout/fixtures.py` : les PR en mémoire, pour les tests.

Ne change les seuils `1.5` et `0.6` que si le nouveau produit a une raison mesurée. Les tests dans `tests/test_routing.py` verrouillent le cas « petit diff non-frontend + skill préselectionné → `agent_ready` » et le cas « blast radius large → `ready_for_hitl` ».

Sur chaque PR non triviale, le titre ou le corps doit contenir `#N` (ou `GH-N`). Sinon la disposition reste `needs_author`, même si un skill est au-dessus du seuil.
