# pr-route-workout

Route une pull request GymLogic : faits GitHub, fan-out Jev, politiques, disposition.

```bash
pipx install "git+https://github.com/PierreTsia/ai-pr-routing-workout.git"
pr-route-workout https://github.com/PierreTsia/workout-app/pull/N --json
```

Pour brancher ça sur un autre dépôt, suis [PROMPT.md](PROMPT.md). Les domaines et les skills sont ceux de GymLogic tant que `domains.py` et `questions.py` n’ont pas été réécrits.
