# Push feature/2.5.63 Through the Pre-Push Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 6 failing `test_translations` tests (48 untranslated + 6 fuzzy msgids in de/fr/it), fix the `requirements-confluence.txt` deploy-exclusion gap, commit, reset the test DB, and push `feature/2.5.63` to `origin/feature/2.5.63` through the pre-push gate.

**Architecture:** Flask-Babel i18n: `nx_lib/**/*.py` + `templates/**/*.html` → `messages.pot` → per-locale `.po` → compiled `.mo`. The pre-push gate runs `branch-name-guard` (PowerShell) then `python -m pytest tests --reruns 2 --only-rerun flaky_e2e`. Both SQL hooks (`sql-migrate-int`, `sql-sync-check`) are `stages: [pre-commit]` only and do NOT fire at push.

**Tech Stack:** Python 3 / Flask-Babel / pybabel CLI, pytest + pytest-rerunfailures, PowerShell, Git pre-commit framework.

---

## Context an engineer needs (read first)

**Branch and remote.** Working branch is `feature/2.5.63`. The remote `origin/feature/2.5.63` is 172 commits behind HEAD. The branch name matches the guard regex `^(main|feature/[0-9]+\.[0-9]+\.[0-9]+)$` — confirmed by reading `scripts/git-hooks/branch-name-guard.ps1` (variable `$allowed = '^(main|feature/[0-9]+\.[0-9]+\.[0-9]+)$'`).

**Remote-push tension and decision.** The standing remote-session memory says "stop at commit; owner pushes." This issue explicitly requests a push, and the n8n autopilot lane that runs this agent has auto-push wired and gated on the pre-push validation. The terminal action in this plan IS a `git push`. If running in a manual remote session and the owner prefers to push themselves, stop after Task 5 (the commit) and hand off the exact push command from Task 7.

**Anchor-on-snippets rule.** Every reference to code anchors on a quoted snippet or named test/function identifier, never on a line number. Line numbers in `.po` files shift constantly.

**Jinja template cache.** Jinja templates are cached for the process lifetime of the dev server. This plan does not touch templates, so no restart is needed.

**E2E constraint and test_db_reset.** The `pytest-pre-push` hook runs `python -m pytest tests --reruns 2 --only-rerun flaky_e2e`. Only tests marked `@pytest.mark.flaky_e2e` are retried; all other failures are fatal on first hit. Order-dependent e2e tests (e.g. `ReportingSqlAck`) fail if `NEXORA_TEST` DB has stale state. Run `python scripts/test_db_reset.py` immediately before `git push` — the script reads `env/TEST.env`, connects to `NEXORA_TEST`, and exits non-zero if `env/TEST.env` is absent or `DB_NEXORA` is not exactly `"NEXORA_TEST"`. Verify those preconditions before Task 6.

**SQL_SYNC_SKIP — commit-time only, not push-time.** The SQL hooks (`sql-migrate-int`, `sql-sync-check`) declare `stages: [pre-commit]` in `.pre-commit-config.yaml` — they do NOT run at pre-push. Verified directly: `db-migrate.py` checks `os.environ.get("SQL_SYNC_SKIP") == "1"` at line `294` and exits 0 immediately; `sync-from-db.py` documents the same in its module docstring and honours it at line `259`. `SQL_SYNC_SKIP=1` is still required for `git commit` on this branch on Windows to bypass the CRLF-drift failure. Never use `--no-verify`.

**i18n cycle (from `docs/howto/babel.md`).** `messages.pot` is already in sync (`test_pot_is_in_sync` passes). The cycle here is:
1. `pybabel update -i messages.pot -d translations` — merges new msgids into the three .po files.
2. Edit each `translations/<locale>/LC_MESSAGES/messages.po`: fill every empty `msgstr`, remove every `#, fuzzy` flag line.
3. `pybabel compile -d translations` — regenerates all three `.mo` files (`.gitattributes` marks `*.mo binary` — git never mangles them).

**Authoritative msgid forms.** The test output from `python -m pytest tests/unit/test_translations.py -v` is the ground truth for exact msgid strings after `pybabel update`. Some msgids contain em-dashes (`—`) rendered as `—`, the warning symbol `⚠` (`⚠`), or embedded newlines (`\n`). These must match verbatim in the `.po` file. If any msgid from the translation tables below is not found verbatim in the `.po` file after `pybabel update`, use the form printed by Task 1's test output, not the table.

**`*.po eol=lf` in `.gitattributes`.** Verified present — `.gitattributes` contains `*.po text eol=lf`. The `mixed-line-ending` hook excludes `sql/` but NOT `translations/`. If `pybabel update` produces mixed line endings on Windows and the `mixed-line-ending` hook modifies a `.po` file during commit, the commit aborts with "files were modified by a hook" — run `git add translations/` and retry with `SQL_SYNC_SKIP=1`.

**Migrations.** None authored in this plan. The pending migrations already in the branch auto-apply via `deploy.yml` on merge to main.

**Deploy exclusion: `sql/requirements.txt` is already covered.** The robocopy `/XD` list includes `sql`, which excludes the entire directory. Only root-level `requirements-confluence.txt` needs to be added to `/XF`. Verified: the `/XD` line in `.github/workflows/deploy.yml` reads `/XD .git .github ... sql ...`.

---

## Decisions locked in

| Decision | Rationale |
|---|---|
| Skip `pybabel extract` | `test_pot_is_in_sync` passes — `messages.pot` is already current |
| Run `pybabel update` before editing .po | Normalizes catalog structure; inserts new msgid stubs cleanly even though the pot is current |
| Machine-translate all 48 new strings + correct the 6 fuzzy | Internal portal; acceptable precedent on this project |
| Fix deploy-exclusion gap (`requirements-confluence.txt`) in the same commit | Small chore, avoids a separate commit |
| Do NOT add `*.sql text eol=lf` to `.gitattributes` in this plan | F2 confirmed: 74 of 93 tracked SQL files currently have `w/crlf` working-tree representation; adding the rule without a deliberate `git add --renormalize sql/` pass would silently re-stage all 74 files as LF when the ruff-format recovery step runs `git add -u`, producing a massive unintended diff. Deferred to Owner actions. |
| `SQL_SYNC_SKIP=1` on the commit only, not on the push | SQL hooks are `stages: [pre-commit]` — the var is irrelevant at push time |
| Push to `origin/feature/2.5.63` | Fast-forward confirmed (no divergence); the plan's terminal action |

## Owner actions (not in this plan)

| Action | Why deferred |
|---|---|
| Durable CRLF fix: add `*.sql text eol=lf` to `.gitattributes` + run `git add --renormalize sql/` in an isolated commit + re-bless INT SchemaMigrations checksums for 0001–0003 | Requires deliberate renormalization pass over 74 SQL files and a live-DB touch; must not be bundled with i18n work |
| Provision `DB_REPORTING_RO_USER/PWD` (StatisticsDB) and `DB_REPORTING_OCTO_RO_USER/PWD` (OctoDB) on PROD | SQL sandbox returns 503 until done |
| Wire `ops/run_scheduled_reports.py` on SYAPP01 Task Scheduler | Scheduled email delivery silently fails until done |
| Provision Confluence bot account, API token, and GitHub runner secrets | `confluence-docs.yml` fails on first push to main if absent |
| Promote `[Unreleased]` → dated `[2.5.63]` in `CHANGELOG.md` | On merge to main only |
| Open PR `feature/2.5.63` → `main` | Per standing remote-session policy, owner opens the PR after reviewing the pushed branch |

---

# PHASE 1 — Confirm the Red Baseline

### Task 1: Verify the failing tests

**Estimated time:** 2 min

- [ ] Run the translation test suite in isolation to confirm the exact failure counts before touching anything:

```powershell
python -m pytest tests/unit/test_translations.py -v
```

**Expected output (red):** 1 PASSED (`test_pot_is_in_sync`), 6 FAILED:
```
PASSED  tests/unit/test_translations.py::test_pot_is_in_sync
FAILED  tests/unit/test_translations.py::test_all_strings_translated[de]
FAILED  tests/unit/test_translations.py::test_all_strings_translated[fr]
FAILED  tests/unit/test_translations.py::test_all_strings_translated[it]
FAILED  tests/unit/test_translations.py::test_mo_files_up_to_date[de]
FAILED  tests/unit/test_translations.py::test_mo_files_up_to_date[fr]
FAILED  tests/unit/test_translations.py::test_mo_files_up_to_date[it]
```

The `test_all_strings_translated` failures will list `UNTRANSLATED (N):` and `FUZZY (M):` per locale. If the counts differ from 48/6, the authoritative msgid list is whatever the test output prints — use that, not the tables in this plan.

---

# PHASE 2 — Fix the Translation Catalog

### Task 2: Run `pybabel update` to refresh the .po stubs

**Estimated time:** 2 min

- [ ] From the repo root (`C:\dev\nexora`), run:

```powershell
pybabel update -i messages.pot -d translations
```

If `pybabel` is not on PATH, use the venv binary:

```powershell
.\venv\Scripts\pybabel update -i messages.pot -d translations
```

**Expected output:** Three lines like:
```
updating catalog translations/de/LC_MESSAGES/messages.po (N translations updated, M are now fuzzy)
updating catalog translations/fr/LC_MESSAGES/messages.po (N translations updated, M are now fuzzy)
updating catalog translations/it/LC_MESSAGES/messages.po (N translations updated, M are now fuzzy)
```

No errors. Do NOT run `pybabel extract` — `messages.pot` is already current.

---

### Task 3: Fill all 48 untranslated msgids and de-fuzz all 6 fuzzy entries in DE, FR, and IT

**Estimated time:** 15 min

Work through all three locale files. The gap set is identical across all three locales.

**Editing rules:**

1. **Untranslated entries:** Find every block where `msgstr ""` is the complete value (not a multiline continuation). Replace the empty `""` with the correct translation in double quotes. Preserve all Python-format placeholders (`%(name)s`) and Unicode characters (`—`, `⚠`) verbatim.
2. **Fuzzy entries:** Find every `#, fuzzy` comment line. Replace the current `msgstr` value with the correct translation (it will be wrong — pybabel guessed from a similar old string). Then delete the `#, fuzzy` line entirely, including its newline. Leaving the flag in — even with a correct `msgstr` — causes `test_all_strings_translated` to fail because the test checks `"fuzzy" in msg.flags`.
3. Save each file as UTF-8 (the header declares `charset=UTF-8`).

**After editing each file**, run this PowerShell check before proceeding to the next locale:

```powershell
Select-String -Pattern '#, fuzzy' translations\de\LC_MESSAGES\messages.po
```

(Substitute `fr` / `it` for the other locales.) No output = all fuzzy flags removed.

---

**The 48 untranslated msgids and their translations** (authoritative form verified from the live .po file — if any differs after `pybabel update`, use the test output form):

| English msgid | German (de) | French (fr) | Italian (it) |
|---|---|---|---|
| `Cannot delete: used in %(p)d profile(s) and %(o)d override(s). Remove all assignments first.` | `Kann nicht gelöscht werden: Wird in %(p)d Profil(en) und %(p)d Override(s) verwendet. Bitte zuerst alle Zuweisungen entfernen.` | `Impossible de supprimer : utilisé dans %(p)d profil(s) et %(o)d substitution(s). Veuillez d'abord supprimer toutes les affectations.` | `Impossibile eliminare: utilizzato in %(p)d profilo/i e %(o)d sostituzione/i. Rimuovere prima tutte le assegnazioni.` |
| `We received a request to reset the password for your account. You can reset your password by clicking the button below.` | `Wir haben eine Anfrage erhalten, das Passwort für Ihr Konto zurückzusetzen. Sie können Ihr Passwort zurücksetzen, indem Sie auf die Schaltfläche unten klicken.` | `Nous avons reçu une demande de réinitialisation du mot de passe de votre compte. Vous pouvez réinitialiser votre mot de passe en cliquant sur le bouton ci-dessous.` | `Abbiamo ricevuto una richiesta di reimpostazione della password per il suo account. Può reimpostare la password facendo clic sul pulsante qui sotto.` |
| `If you did not request a password reset, please ignore this email. This link is valid for 15 minutes.` | `Falls Sie keine Passwortzurücksetzung angefordert haben, ignorieren Sie diese E-Mail bitte. Dieser Link ist 15 Minuten gültig.` | `Si vous n'avez pas demandé de réinitialisation de mot de passe, veuillez ignorer cet e-mail. Ce lien est valable 15 minutes.` | `Se non ha richiesto una reimpostazione della password, ignori questa e-mail. Il link è valido per 15 minuti.` |
| `You have reached the daily AI request limit (%(limit)s). Please try again tomorrow.` | `Sie haben das tägliche KI-Anfragelimit (%(limit)s) erreicht. Bitte versuchen Sie es morgen erneut.` | `Vous avez atteint la limite quotidienne de requêtes IA (%(limit)s). Veuillez réessayer demain.` | `Ha raggiunto il limite giornaliero di richieste IA (%(limit)s). Riprovi domani.` |
| `Pick up to three — the first is the chart axis, the second becomes the colored series.` | `Wählen Sie bis zu drei — die erste ist die Diagrammachse, die zweite wird zur farbigen Datenreihe.` | `Choisissez jusqu'à trois — le premier est l'axe du graphique, le deuxième devient la série colorée.` | `Scelga fino a tre — il primo è l'asse del grafico, il secondo diventa la serie colorata.` |
| `No problem. Enter the email address associated with your account and we'll send you a link to reset your password` | `Kein Problem. Geben Sie die mit Ihrem Konto verknüpfte E-Mail-Adresse ein und wir senden Ihnen einen Link zum Zurücksetzen Ihres Passworts.` | `Pas de problème. Saisissez l'adresse e-mail associée à votre compte et nous vous enverrons un lien pour réinitialiser votre mot de passe.` | `Nessun problema. Inserisca l'indirizzo e-mail associato al suo account e le invieremo un link per reimpostare la password.` |
| `Welcome to nexora. Securely monitor your document's journey from import to validation and final delivery in real-time. Access a complete, auditable history 24/7.` | `Willkommen bei nexora. Verfolgen Sie den Weg Ihres Dokuments von der Einlieferung bis zur Validierung und abschließenden Zustellung in Echtzeit. Greifen Sie rund um die Uhr auf eine vollständige, nachvollziehbare Historie zu.` | `Bienvenue sur nexora. Suivez en temps réel le parcours de votre document de l'import à la validation et à la livraison finale. Accédez à un historique complet et traçable 24h/24 et 7j/7.` | `Benvenuto su nexora. Monitori in tempo reale il percorso del suo documento dall'importazione alla validazione e alla consegna finale. Acceda a uno storico completo e verificabile 24 ore su 24.` |
| `Our automated system handles every step with precision and security. Follow along as a document is processed in real-time.` | `Unser automatisiertes System verarbeitet jeden Schritt präzise und sicher. Verfolgen Sie in Echtzeit, wie ein Dokument verarbeitet wird.` | `Notre système automatisé gère chaque étape avec précision et sécurité. Suivez en temps réel le traitement d'un document.` | `Il nostro sistema automatizzato gestisce ogni fase con precisione e sicurezza. Segua in tempo reale l'elaborazione di un documento.` |
| `Monitor your document's journey from import to validation and final delivery, every step of the way` | `Überwachen Sie den Weg Ihres Dokuments von der Einlieferung bis zur Validierung und abschließenden Zustellung — Schritt für Schritt.` | `Suivez le parcours de votre document de l'import à la validation et à la livraison finale, étape par étape.` | `Monitori il percorso del suo documento dall'importazione alla validazione e alla consegna finale, passo dopo passo.` |
| `Access a complete, auditable history of all your processed documents available 24/7.` | `Greifen Sie rund um die Uhr auf eine vollständige, nachvollziehbare Historie aller verarbeiteten Dokumente zu.` | `Accédez 24h/24 à un historique complet et traçable de tous vos documents traités.` | `Acceda 24 ore su 24 a uno storico completo e verificabile di tutti i documenti elaborati.` |
| `Your data is protected with industry-leading security protocols, ensuring complete confidentiality` | `Ihre Daten sind mit branchenführenden Sicherheitsprotokollen geschützt und vollständige Vertraulichkeit ist gewährleistet.` | `Vos données sont protégées par des protocoles de sécurité de pointe garantissant une confidentialité totale.` | `I suoi dati sono protetti con protocolli di sicurezza all'avanguardia nel settore, garantendo la massima riservatezza.` |
| `Log in to your portal to access real-time tracking, view your history, and manage your workflow with confidence.` | `Melden Sie sich bei Ihrem Portal an, um Echtzeit-Verfolgung zu nutzen, Ihre Historie einzusehen und Ihren Workflow souverän zu verwalten.` | `Connectez-vous à votre portail pour accéder au suivi en temps réel, consulter votre historique et gérer votre flux de travail en toute confiance.` | `Acceda al suo portale per il monitoraggio in tempo reale, consultare lo storico e gestire il flusso di lavoro con sicurezza.` |
| `The assistant drafts a report definition from the sources you can access — it never sees result data. Review it, then open it in the builder and run it yourself.` | `Der Assistent erstellt einen Berichtsentwurf aus den Quellen, auf die Sie zugreifen können — er sieht niemals Ergebnisdaten. Überprüfen Sie ihn, öffnen Sie ihn im Builder und führen Sie ihn selbst aus.` | `L'assistant rédige une définition de rapport à partir des sources auxquelles vous avez accès — il ne voit jamais les données de résultats. Examinez-la, ouvrez-la dans le générateur et exécutez-la vous-même.` | `L'assistente redige una definizione di report dalle fonti a cui ha accesso — non vede mai i dati dei risultati. La esamini, la apra nel builder e la esegua lei stesso.` |
| `The assistant drafts read-only SQL from the database schema. It never sees result data. Review the SQL, then run it yourself.` | `Der Assistent erstellt schreibgeschütztes SQL aus dem Datenbankschema. Er sieht niemals Ergebnisdaten. Überprüfen Sie das SQL und führen Sie es dann selbst aus.` | `L'assistant rédige du SQL en lecture seule à partir du schéma de base de données. Il ne voit jamais les données de résultats. Examinez le SQL, puis exécutez-le vous-même.` | `L'assistente redige SQL in sola lettura dallo schema del database. Non vede mai i dati dei risultati. Esamini l'SQL, quindi lo esegua lei stesso.` |
| `The agent works step by step, showing each tool it uses. It can run read-only queries and report the actual numbers from the data it fetched.` | `Der Agent arbeitet Schritt für Schritt und zeigt jedes verwendete Werkzeug. Er kann schreibgeschützte Abfragen ausführen und die tatsächlichen Zahlen aus den abgerufenen Daten melden.` | `L'agent travaille étape par étape, montrant chaque outil qu'il utilise. Il peut exécuter des requêtes en lecture seule et rapporter les chiffres réels des données qu'il a récupérées.` | `L'agente lavora passo dopo passo, mostrando ogni strumento che utilizza. Può eseguire query in sola lettura e riportare i dati effettivi recuperati.` |
| `The agent works step by step, showing each tool it uses to validate and draft — grounded only in the schema you can access. It never sees result data.` | `Der Agent arbeitet Schritt für Schritt und zeigt jedes verwendete Werkzeug zur Validierung und Entwurfserstellung — nur auf Basis des Schemas, auf das Sie zugreifen können. Er sieht niemals Ergebnisdaten.` | `L'agent travaille étape par étape, montrant chaque outil qu'il utilise pour valider et rédiger — ancré uniquement dans le schéma auquel vous avez accès. Il ne voit jamais les données de résultats.` | `L'agente lavora passo dopo passo, mostrando ogni strumento utilizzato per convalidare e redigere — ancorato solo allo schema a cui ha accesso. Non vede mai i dati dei risultati.` |
| `⚠ The drafted SQL did not pass the read-only check — review it before running.` | `⚠ Das entworfene SQL hat die Schreibschutzprüfung nicht bestanden — bitte überprüfen Sie es vor der Ausführung.` | `⚠ Le SQL rédigé n'a pas passé la vérification en lecture seule — vérifiez-le avant de l'exécuter.` | `⚠ L'SQL redatto non ha superato il controllo in sola lettura — lo esamini prima di eseguirlo.` |
| `Choose a source on the left, add columns and filters, then press Run — or switch to Ask AI to draft one in plain language.` | `Wählen Sie links eine Quelle aus, fügen Sie Spalten und Filter hinzu und drücken Sie dann Ausführen — oder wechseln Sie zu KI fragen, um einen Entwurf in einfacher Sprache zu erstellen.` | `Choisissez une source à gauche, ajoutez des colonnes et des filtres, puis appuyez sur Exécuter — ou passez à Demander à l'IA pour en rédiger un en langage courant.` | `Scelga una fonte a sinistra, aggiunga colonne e filtri, quindi prema Esegui — oppure passi a Chiedi all'IA per redigerne uno in linguaggio naturale.` |
| `You are about to run read-only SQL against a live reporting database. Queries cannot modify data, and every run is logged. Double-check your query before running.` | `Sie sind dabei, schreibgeschütztes SQL gegen eine Live-Berichtsdatenbank auszuführen. Abfragen können keine Daten ändern, und jede Ausführung wird protokolliert. Überprüfen Sie Ihre Abfrage vor dem Ausführen sorgfältig.` | `Vous êtes sur le point d'exécuter du SQL en lecture seule sur une base de données de reporting en production. Les requêtes ne peuvent pas modifier les données, et chaque exécution est journalisée. Vérifiez votre requête avant de l'exécuter.` | `Sta per eseguire SQL in sola lettura su un database di reporting in produzione. Le query non possono modificare i dati e ogni esecuzione viene registrata. Controlli la query prima di eseguirla.` |
| `The threshold is checked against the report's grand total (or its row count when the report has no measure).` | `Der Schwellenwert wird mit dem Gesamtergebnis des Berichts verglichen (oder der Zeilenanzahl, wenn der Bericht kein Maß enthält).` | `Le seuil est vérifié par rapport au total général du rapport (ou au nombre de lignes lorsque le rapport n'a pas de mesure).` | `La soglia viene verificata rispetto al totale generale del report (o al conteggio delle righe quando il report non ha una misura).` |
| `Canonical metrics are named server-side aggregations bound to a source. A report's selected columns become the grouping; each metric adds an aggregated column.` | `Kanonische Metriken sind benannte serverseitige Aggregationen, die an eine Quelle gebunden sind. Die ausgewählten Spalten eines Berichts werden zur Gruppierung; jede Metrik fügt eine aggregierte Spalte hinzu.` | `Les métriques canoniques sont des agrégations nommées côté serveur liées à une source. Les colonnes sélectionnées d'un rapport deviennent le regroupement ; chaque métrique ajoute une colonne agrégée.` | `Le metriche canoniche sono aggregazioni nominate lato server legate a una fonte. Le colonne selezionate di un report diventano il raggruppamento; ogni metrica aggiunge una colonna aggregata.` |
| `Registry rows augment or override the built-in sources — relabel, enable/disable, reorder, re-permission, or register new ones. Curated sources bind to a provider: 'docprocessing' (built-in) or 'table' (generic single-object, configured with a base object + columns).` | `Registrierungszeilen ergänzen oder überschreiben die integrierten Quellen — umbenennen, aktivieren/deaktivieren, neu anordnen, Berechtigungen ändern oder neue registrieren. Kuratierte Quellen binden sich an einen Anbieter: 'docprocessing' (integriert) oder 'table' (generisches Einzelobjekt, konfiguriert mit einem Basisobjekt + Spalten).` | `Les lignes de registre complètent ou remplacent les sources intégrées — renommer, activer/désactiver, réordonner, modifier les autorisations ou en enregistrer de nouvelles. Les sources organisées se lient à un fournisseur : 'docprocessing' (intégré) ou 'table' (objet unique générique, configuré avec un objet de base + colonnes).` | `Le righe del registro aumentano o sostituiscono le fonti integrate — rinomina, abilita/disabilita, riordina, modifica le autorizzazioni o registrane di nuove. Le fonti curate si legano a un provider: 'docprocessing' (integrato) o 'table' (oggetto singolo generico, configurato con un oggetto base + colonne).` |
| `Use this PowerShell script to extract images from the exported CSV. Requires execution policy` | `Verwenden Sie dieses PowerShell-Skript, um Bilder aus der exportierten CSV-Datei zu extrahieren. Erfordert Ausführungsrichtlinie.` | `Utilisez ce script PowerShell pour extraire des images du CSV exporté. Nécessite une stratégie d'exécution.` | `Usa questo script PowerShell per estrarre immagini dal CSV esportato. Richiede criteri di esecuzione.` |
| `When enabled and the window is active, users without admin.maintenance.bypass are logged out and shown a maintenance page. Make sure you have the bypass permission before turning this on.` | `Wenn aktiviert und das Fenster aktiv ist, werden Benutzer ohne admin.maintenance.bypass abgemeldet und auf eine Wartungsseite weitergeleitet. Stellen Sie sicher, dass Sie die Umgehungsberechtigung haben, bevor Sie dies aktivieren.` | `Lorsqu'activée et que la fenêtre est active, les utilisateurs sans admin.maintenance.bypass sont déconnectés et redirigés vers une page de maintenance. Assurez-vous d'avoir l'autorisation de contournement avant d'activer cela.` | `Se abilitata e la finestra è attiva, gli utenti senza admin.maintenance.bypass vengono disconnessi e visualizzano una pagina di manutenzione. Assicurarsi di avere l'autorizzazione di bypass prima di attivarlo.` |
| `The actual permission set this user has — profile combined with any per-user overrides.` | `Der tatsächliche Berechtigungssatz dieses Benutzers — Profil kombiniert mit eventuellen benutzerspezifischen Überschreibungen.` | `L'ensemble réel d'autorisations de cet utilisateur — profil combiné avec les remplacements par utilisateur éventuels.` | `Il set di autorizzazioni effettivo di questo utente — profilo combinato con eventuali sostituzioni per utente.` |
| `Override the access profile on a per-permission basis. Leave as None to inherit from the profile.` | `Überschreiben Sie das Zugriffsprofil auf Berechtigungsebene. Lassen Sie es auf Keine, um vom Profil zu erben.` | `Remplacez le profil d'accès autorisation par autorisation. Laissez sur Aucun pour hériter du profil.` | `Sostituisci il profilo di accesso per singola autorizzazione. Lascia su Nessuno per ereditare dal profilo.` |
| `The page slipped beyond the event horizon. We searched the void but could not find what you are looking for.` | `Die Seite ist über den Ereignishorizont hinaus verschwunden. Wir haben die Leere durchsucht, konnten aber nicht finden, was Sie suchen.` | `La page a glissé au-delà de l'horizon des événements. Nous avons fouillé le vide mais n'avons pas pu trouver ce que vous cherchez.` | `La pagina è scivolata oltre l'orizzonte degli eventi. Abbiamo cercato nel vuoto ma non siamo riusciti a trovare quello che cerchi.` |
| `A spacetime fracture occurred while processing your request. Our team has been notified.` | `Beim Verarbeiten Ihrer Anfrage ist ein Raum-Zeit-Riss aufgetreten. Unser Team wurde benachrichtigt.` | `Une fracture spatio-temporelle s'est produite lors du traitement de votre demande. Notre équipe a été notifiée.` | `Si è verificata una frattura spazio-temporale durante l'elaborazione della tua richiesta. Il nostro team è stato informato.` |
| `No chart — this report is a single total. Adjust it in the wizard and pick a breakdown to get one.` | `Kein Diagramm — dieser Bericht ist eine Einzelsumme. Passen Sie ihn im Assistenten an und wählen Sie eine Aufschlüsselung aus, um ein Diagramm zu erhalten.` | `Pas de graphique — ce rapport est un total unique. Ajustez-le dans l'assistant et choisissez une décomposition pour en obtenir un.` | `Nessun grafico — questo report è un totale singolo. Modificalo nel wizard e scegli un raggruppamento per ottenerne uno.` |
| `Too many data points to chart — choose a coarser granularity or a shorter time range.` | `Zu viele Datenpunkte für ein Diagramm — wählen Sie eine gröbere Granularität oder einen kürzeren Zeitraum.` | `Trop de points de données pour un graphique — choisissez une granularité plus grossière ou une plage de temps plus courte.` | `Troppi punti dati per un grafico — scegli una granularità più grossolana o un intervallo di tempo più breve.` |
| `Use this dropdown to filter all the data on this page by a specific document process, like 'Inbox' or 'Invoice'.` | `Verwenden Sie diese Dropdown-Liste, um alle Daten auf dieser Seite nach einem bestimmten Dokumentprozess zu filtern, z. B. 'Posteingang' oder 'Rechnung'.` | `Utilisez cette liste déroulante pour filtrer toutes les données de cette page par un processus de document spécifique, comme 'Boîte de réception' ou 'Facture'.` | `Usa questo menu a discesa per filtrare tutti i dati di questa pagina in base a un processo documentale specifico, come 'Posta in arrivo' o 'Fattura'.` |
| `These cards show a live summary of your documents: Processed Today, Processed This Week, and the Current Backlog.` | `Diese Karten zeigen eine Live-Zusammenfassung Ihrer Dokumente: Heute verarbeitet, Diese Woche verarbeitet und den aktuellen Rückstand.` | `Ces cartes affichent un résumé en direct de vos documents : Traités aujourd'hui, Traités cette semaine et le Backlog actuel.` | `Queste schede mostrano un riepilogo in tempo reale dei tuoi documenti: Elaborati oggi, Elaborati questa settimana e il Backlog attuale.` |
| `Visualize your throughput and status distribution with these interactive charts.` | `Visualisieren Sie Ihren Durchsatz und Ihre Statusverteilung mit diesen interaktiven Diagrammen.` | `Visualisez votre débit et votre distribution de statuts avec ces graphiques interactifs.` | `Visualizza il tuo throughput e la distribuzione degli stati con questi grafici interattivi.` |
| `This section provides a real-time view of the specific steps documents are actively going through right now.` | `Dieser Abschnitt bietet eine Echtzeit-Ansicht der spezifischen Schritte, die Dokumente gerade aktiv durchlaufen.` | `Cette section offre une vue en temps réel des étapes spécifiques que les documents traversent activement en ce moment.` | `Questa sezione fornisce una visualizzazione in tempo reale dei passaggi specifici che i documenti stanno attraversando attivamente in questo momento.` |
| `Use this powerful form to find specific workitems by process, search terms, or tags.` | `Verwenden Sie dieses leistungsstarke Formular, um bestimmte Arbeitselemente nach Prozess, Suchbegriffen oder Tags zu finden.` | `Utilisez ce formulaire puissant pour trouver des éléments de travail spécifiques par processus, termes de recherche ou balises.` | `Usa questo potente modulo per trovare specifici workitem per processo, termini di ricerca o tag.` |
| `Need more specific results? Click here to filter by date range, priority, assigned user, or specific document field values.` | `Benötigen Sie spezifischere Ergebnisse? Klicken Sie hier, um nach Datumsbereich, Priorität, zugewiesenem Benutzer oder bestimmten Dokumentfeldwerten zu filtern.` | `Besoin de résultats plus spécifiques ? Cliquez ici pour filtrer par plage de dates, priorité, utilisateur assigné ou valeurs de champ de document spécifiques.` | `Hai bisogno di risultati più specifici? Fai clic qui per filtrare per intervallo di date, priorità, utente assegnato o valori specifici del campo documento.` |
| `Your filtered results appear here. You can sort columns by clicking on their headers.` | `Ihre gefilterten Ergebnisse werden hier angezeigt. Sie können Spalten sortieren, indem Sie auf deren Überschriften klicken.` | `Vos résultats filtrés apparaissent ici. Vous pouvez trier les colonnes en cliquant sur leurs en-têtes.` | `I tuoi risultati filtrati appaiono qui. Puoi ordinare le colonne facendo clic sulle intestazioni.` |
| `Click this arrow button to expand a workitem. The tour will do this automatically for the next step.` | `Klicken Sie auf diese Pfeilschaltfläche, um ein Arbeitselement zu erweitern. Die Tour führt dies automatisch für den nächsten Schritt durch.` | `Cliquez sur ce bouton flèche pour développer un élément de travail. La visite guidée le fera automatiquement pour l'étape suivante.` | `Fai clic su questo pulsante freccia per espandere un workitem. La visita guidata lo farà automaticamente per il passo successivo.` |
| `Track the exact stage of your document (Import, Extraction, Validation, Delivery) with this visual progress bar.` | `Verfolgen Sie den genauen Stand Ihres Dokuments (Import, Extraktion, Validierung, Lieferung) mit diesem visuellen Fortschrittsbalken.` | `Suivez l'étape exacte de votre document (Importation, Extraction, Validation, Livraison) avec cette barre de progression visuelle.` | `Tieni traccia dell'esatta fase del tuo documento (Importazione, Estrazione, Validazione, Consegna) con questa barra di avanzamento visiva.` |
| `View the document image here. If permitted, you can interact with the file.` | `Sehen Sie sich das Dokumentbild hier an. Wenn erlaubt, können Sie mit der Datei interagieren.` | `Affichez l'image du document ici. Si autorisé, vous pouvez interagir avec le fichier.` | `Visualizza l'immagine del documento qui. Se consentito, puoi interagire con il file.` |
| `Here you can set a priority level, assign the workitem to a colleague, add tags, and leave comments for your team.` | `Hier können Sie eine Prioritätsstufe festlegen, das Arbeitselement einem Kollegen zuweisen, Tags hinzufügen und Kommentare für Ihr Team hinterlassen.` | `Ici, vous pouvez définir un niveau de priorité, attribuer l'élément de travail à un collègue, ajouter des balises et laisser des commentaires pour votre équipe.` | `Qui puoi impostare un livello di priorità, assegnare il workitem a un collega, aggiungere tag e lasciare commenti per il tuo team.` |
| `This Kanban-style board helps you visualize the workload and task distribution across your entire team.` | `Dieses Kanban-Board hilft Ihnen, die Arbeitsbelastung und Aufgabenverteilung im gesamten Team zu visualisieren.` | `Ce tableau de style Kanban vous aide à visualiser la charge de travail et la distribution des tâches dans toute votre équipe.` | `Questa bacheca in stile Kanban ti aiuta a visualizzare il carico di lavoro e la distribuzione dei compiti in tutto il team.` |
| `Quickly find what you're looking for by filtering tasks by process or priority level.` | `Finden Sie schnell, was Sie suchen, indem Sie Aufgaben nach Prozess oder Prioritätsstufe filtern.` | `Trouvez rapidement ce que vous cherchez en filtrant les tâches par processus ou niveau de priorité.` | `Trova rapidamente quello che cerchi filtrando i compiti per processo o livello di priorità.` |
| `Each column represents a team member. All tasks assigned to them will appear here.` | `Jede Spalte repräsentiert ein Teammitglied. Alle ihnen zugewiesenen Aufgaben werden hier angezeigt.` | `Chaque colonne représente un membre de l'équipe. Toutes les tâches qui leur sont assignées apparaîtront ici.` | `Ogni colonna rappresenta un membro del team. Tutti i compiti assegnati a loro appariranno qui.` |
| `The header shows the team member's name and the total number of tasks currently assigned to them.` | `Die Überschrift zeigt den Namen des Teammitglieds und die Gesamtzahl der ihm aktuell zugewiesenen Aufgaben.` | `L'en-tête affiche le nom du membre de l'équipe et le nombre total de tâches qui lui sont actuellement assignées.` | `L'intestazione mostra il nome del membro del team e il numero totale di compiti attualmente assegnati a loro.` |
| `Each card is a workitem. It shows key details like the barcode, last modification time, and priority. Click a card to jump to its detailed view.` | `Jede Karte ist ein Arbeitselement. Sie zeigt wichtige Details wie den Barcode, die letzte Änderungszeit und die Priorität. Klicken Sie auf eine Karte, um zur Detailansicht zu springen.` | `Chaque carte est un élément de travail. Elle affiche des détails clés comme le code-barres, la dernière modification et la priorité. Cliquez sur une carte pour accéder à sa vue détaillée.` | `Ogni scheda è un workitem. Mostra dettagli chiave come il codice a barre, l'ora dell'ultima modifica e la priorità. Fai clic su una scheda per accedere alla vista dettagliata.` |
| `Locate specific invoices by searching for the invoice number, selecting a date range, or filtering by payment status.` | `Suchen Sie nach bestimmten Rechnungen, indem Sie die Rechnungsnummer suchen, einen Datumsbereich auswählen oder nach Zahlungsstatus filtern.` | `Localisez des factures spécifiques en recherchant le numéro de facture, en sélectionnant une plage de dates ou en filtrant par statut de paiement.` | `Individua fatture specifiche cercando il numero di fattura, selezionando un intervallo di date o filtrando per stato di pagamento.` |
| `Your filtered invoices appear here. You can view details, amounts, and download PDF copies from the Actions column.` | `Ihre gefilterten Rechnungen werden hier angezeigt. Sie können Details, Beträge einsehen und PDF-Kopien aus der Aktionsspalte herunterladen.` | `Vos factures filtrées apparaissent ici. Vous pouvez consulter les détails, les montants et télécharger des copies PDF depuis la colonne Actions.` | `Le tue fatture filtrate appaiono qui. Puoi visualizzare i dettagli, gli importi e scaricare copie PDF dalla colonna Azioni.` |

---

**The 6 fuzzy entries** (identical across all three locales). For each: replace the wrong `msgstr`, then delete the `#, fuzzy` line.

**Example — before and after for a fuzzy entry in DE:**

Before:
```
#: templates/init_2FA.html:42
#, fuzzy
msgid "Scan the QR code below with your Authenticator App (Microsoft or Google Authenticator)."
msgstr "Bitte geben Sie den Code aus Ihrer Authenticator-App ein, um fortzufahren."
```

After:
```
#: templates/init_2FA.html:42
msgid "Scan the QR code below with your Authenticator App (Microsoft or Google Authenticator)."
msgstr "Scannen Sie den QR-Code unten mit Ihrer Authenticator-App (Microsoft oder Google Authenticator)."
```

| English msgid | Correct German msgstr | Correct French msgstr | Correct Italian msgstr |
|---|---|---|---|
| `Scan the QR code below with your Authenticator App (Microsoft or Google Authenticator).` | `Scannen Sie den QR-Code unten mit Ihrer Authenticator-App (Microsoft oder Google Authenticator).` | `Scannez le code QR ci-dessous avec votre application Authenticator (Microsoft ou Google Authenticator).` | `Scansiona il codice QR qui sotto con la tua app Authenticator (Microsoft o Google Authenticator).` |
| `Document\n                  fields` | `Dokument-\n                  felder` | `Champs du\n                  document` | `Campi del\n                  documento` |
| `Full timeline of all stages — only available for selections of up to 10 workitems` | `Vollständige Zeitleiste aller Phasen — nur für Auswahlen von bis zu 10 Workitems verfügbar` | `Chronologie complète de toutes les étapes — disponible uniquement pour des sélections de 10 éléments de travail au maximum` | `Cronologia completa di tutte le fasi — disponibile solo per selezioni fino a 10 workitem` |
| `Up to 5 images per workitem — only available for selections of up to 10 workitems` | `Bis zu 5 Bilder pro Workitem — nur für Auswahlen von bis zu 10 Workitems verfügbar` | `Jusqu'à 5 images par élément de travail — disponible uniquement pour des sélections de 10 éléments au maximum` | `Fino a 5 immagini per workitem — disponibile solo per selezioni fino a 10 workitem` |
| `All workitems matching the current filters will be exported (not just the current page).` | `Alle Workitems, die den aktuellen Filtern entsprechen, werden exportiert (nicht nur die aktuelle Seite).` | `Tous les éléments de travail correspondant aux filtres actuels seront exportés (pas seulement la page actuelle).` | `Tutti i workitem corrispondenti ai filtri attuali verranno esportati (non solo la pagina corrente).` |
| `Are you sure you want to delete this Organization? This action cannot be undone.` | `Sind Sie sicher, dass Sie diese Organisation löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.` | `Êtes-vous sûr de vouloir supprimer cette organisation ? Cette action est irréversible.` | `Sei sicuro di voler eliminare questa organizzazione? Questa azione non può essere annullata.` |

---

### Task 4: Compile the catalogs and verify green

**Estimated time:** 3 min

- [ ] Compile all three locales:

```powershell
pybabel compile -d translations
```

**Expected output:**
```
compiling catalog translations/de/LC_MESSAGES/messages.po to translations/de/LC_MESSAGES/messages.mo
compiling catalog translations/fr/LC_MESSAGES/messages.po to translations/fr/LC_MESSAGES/messages.mo
compiling catalog translations/it/LC_MESSAGES/messages.po to translations/it/LC_MESSAGES/messages.mo
```

If pybabel warns `X messages are marked as fuzzy, skipping` on any locale, a `#, fuzzy` line was missed. Go back to Task 3, find it, remove it, and recompile.

- [ ] Run the translation test suite to confirm all 7 pass:

```powershell
python -m pytest tests/unit/test_translations.py -v
```

**Expected output (green):**
```
PASSED  tests/unit/test_translations.py::test_pot_is_in_sync
PASSED  tests/unit/test_translations.py::test_all_strings_translated[de]
PASSED  tests/unit/test_translations.py::test_all_strings_translated[fr]
PASSED  tests/unit/test_translations.py::test_all_strings_translated[it]
PASSED  tests/unit/test_translations.py::test_mo_files_up_to_date[de]
PASSED  tests/unit/test_translations.py::test_mo_files_up_to_date[fr]
PASSED  tests/unit/test_translations.py::test_mo_files_up_to_date[it]
7 passed in Xs
```

Do not proceed to Task 5 until all 7 pass. If any `test_all_strings_translated` is still red, the failure message names the exact msgid(s) still missing or fuzzy in which locale — fix those entries, recompile, and re-run.

Note: `test_mo_files_up_to_date` only checks entries that have a non-empty `msgstr` in the `.po` — it does not re-check for untranslated entries (that is `test_all_strings_translated`'s job). A passing `.mo` test is not evidence that all strings are translated.

---

# PHASE 3 — Fix the Deploy Exclusion Gap

### Task 5: Add `requirements-confluence.txt` to deploy.yml /XF

**Estimated time:** 2 min

`requirements-confluence.txt` (verified present at `C:\dev\nexora\requirements-confluence.txt`) was added during the 172 commits and is not in the robocopy `/XF` list. Without this fix, `robocopy /MIR` will copy it to `D:\sydoc\nexora` on the next deploy to `main`. (`sql/requirements.txt` is already safe — the `/XD sql` entry covers the entire directory.)

- [ ] Open `C:\dev\nexora\.github\workflows\deploy.yml` and find the `/XF` line. The current line ends with `uv.lock`:

```
/XF *.env *.env.example ngrok.yaml .gitignore .claudeignore .mcp.json AGENTS.md CLAUDE.md nx.ps1 babel.cfg messages.pot requirements.txt requirements-dev.txt README.md pyproject.toml .editorconfig .gitattributes .gitlint .pre-commit-config.yaml .python-version bootstrap.ps1 CHANGELOG.md CONTRIBUTING.md LICENSE uv.lock
```

- [ ] Append `requirements-confluence.txt` at the end (one space + filename, before the closing backtick):

```
/XF *.env *.env.example ngrok.yaml .gitignore .claudeignore .mcp.json AGENTS.md CLAUDE.md nx.ps1 babel.cfg messages.pot requirements.txt requirements-dev.txt README.md pyproject.toml .editorconfig .gitattributes .gitlint .pre-commit-config.yaml .python-version bootstrap.ps1 CHANGELOG.md CONTRIBUTING.md LICENSE uv.lock requirements-confluence.txt
```

- [ ] Verify the file saves correctly — this must remain a single continuous line (no line break introduced).

---

# PHASE 4 — Commit

### Task 6: Verify the prerequisite for test_db_reset.py

**Estimated time:** 1 min

Before committing, confirm `env/TEST.env` exists and contains `DB_NEXORA=NEXORA_TEST`. The reset script checks this at startup and refuses to run if it finds any other value (error: `Refusing to run: DB_NEXORA in TEST.env must be 'NEXORA_TEST', got '<value>'`).

```powershell
Test-Path C:\dev\nexora\env\TEST.env
Select-String -Pattern 'DB_NEXORA' C:\dev\nexora\env\TEST.env
```

Expected: `True` then a line showing `DB_NEXORA=NEXORA_TEST`. If `env/TEST.env` is absent, copy from `env/TEST.env.example` and fill in values before proceeding.

---

### Task 7: Stage and commit

**Estimated time:** 3 min

- [ ] Stage exactly the changed files:

```powershell
git add translations/de/LC_MESSAGES/messages.po
git add translations/de/LC_MESSAGES/messages.mo
git add translations/fr/LC_MESSAGES/messages.po
git add translations/fr/LC_MESSAGES/messages.mo
git add translations/it/LC_MESSAGES/messages.po
git add translations/it/LC_MESSAGES/messages.mo
git add .github/workflows/deploy.yml
```

- [ ] Verify staged files: `git diff --cached --name-only` should list exactly those 7 files.

- [ ] Commit with `SQL_SYNC_SKIP=1` (required on Windows due to INT CRLF drift for migrations 0001–0003; SQL hooks are pre-commit only, so this var is only needed here, not at push time). Use PowerShell here-string syntax:

```powershell
$env:SQL_SYNC_SKIP = '1'
git commit -m @'
chore(i18n): fill de/fr/it translations for 2.5.63 feature strings

48 untranslated msgids and 6 fuzzy entries resolved across all three
locales (de, fr, it). Strings span reporting AI surfaces A/B/C,
workitem tour tooltips, password reset emails, admin permission UI,
dashboard hero copy, and custom error pages. All #, fuzzy flags
removed. test_translations: 7/7 passing.

Also adds requirements-confluence.txt to deploy.yml /XF so robocopy
does not mirror it to PROD on next deploy.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
'@
Remove-Item Env:\SQL_SYNC_SKIP
```

**Hook abort recovery — covers both ruff hooks (F11 fix):** If `ruff` (linter, `--fix --exit-non-zero-on-fix`) OR `ruff-format` modifies any staged file, the commit aborts with "files were modified by this hook." Both hooks follow the same recovery pattern:

```powershell
git add -u
$env:SQL_SYNC_SKIP = '1'
git commit -m @'
chore(i18n): fill de/fr/it translations for 2.5.63 feature strings
... (same message as above)
'@
Remove-Item Env:\SQL_SYNC_SKIP
```

**Mixed-line-ending hook recovery on .po files (F6 fix):** If the `mixed-line-ending` hook modifies any `.po` file (possible on Windows despite the `*.po eol=lf` gitattribute rule), the commit aborts. Run:

```powershell
git add translations/
$env:SQL_SYNC_SKIP = '1'
# (retry commit as above)
Remove-Item Env:\SQL_SYNC_SKIP
```

**Expected final line:** `[feature/2.5.63 XXXXXXX] chore(i18n): fill de/fr/it translations for 2.5.63 feature strings`

- [ ] Verify: `git log --oneline -1` shows the new commit as HEAD.

---

# PHASE 5 — Reset Test DB and Push

### Task 8: Reset the NEXORA_TEST database

**Estimated time:** 2 min

Run this immediately before `git push` — do not allow other commands between this step and Task 9. Order-dependent e2e tests break if NEXORA_TEST state is stale, and the window between reset and push should be as short as possible.

```powershell
python scripts/test_db_reset.py
```

**Expected output:** `NEXORA_TEST reset complete.`

If the script exits non-zero, investigate before pushing. Common errors:
- `env/TEST.env not found` — the prerequisite from Task 6 was not met; copy and fill `env/TEST.env`.
- `Refusing to run: DB_NEXORA in TEST.env must be 'NEXORA_TEST'` — `DB_NEXORA` is set to the wrong database in `env/TEST.env`.

The PowerShell wrapper `scripts/test-db-reset.ps1` is the CI equivalent (used by `deploy.yml`); the Python script is the local command.

---

### Task 9: Verify branch name and push

**Estimated time:** 5–20 min (pre-push gate runs the full pytest suite)

- [ ] Confirm the current branch (the guard script checks `git rev-parse --abbrev-ref HEAD` against `^(main|feature/[0-9]+\.[0-9]+\.[0-9]+)$`):

```powershell
git rev-parse --abbrev-ref HEAD
```

Expected: `feature/2.5.63`

- [ ] Push to origin:

```powershell
git push origin feature/2.5.63
```

**What the pre-push gate runs (in order, confirmed from `.pre-commit-config.yaml`):**
1. `branch-name-guard` — PowerShell, `always_run: true`, checks branch name. Passes.
2. `pytest-pre-push` — `python -m pytest tests --reruns 2 --only-rerun flaky_e2e`. Full suite including Playwright e2e. This is the main gate.

After the new commit in Task 7, the branch is 173 commits ahead of `origin/feature/2.5.63`. This is a fast-forward push; no force is needed or permitted.

**Expected final output:**
```
[pre-push] branch name 'feature/2.5.63' OK.
... (pytest output — all green) ...
173 passed (or similar)
To https://github.com/sydoc/nexora.git
   <old-sha>..<new-sha>  feature/2.5.63 -> feature/2.5.63
```

**If the push fails — recovery by failure type:**

- _`test_all_strings_translated` still red:_ A msgid was missed or a `#, fuzzy` line was not removed. The failure message names the exact msgid and locale. Fix the `.po` file, recompile, recommit (with `SQL_SYNC_SKIP=1`), re-run `python scripts/test_db_reset.py`, and re-push.
- _Flaky e2e failure (marked `@pytest.mark.flaky_e2e`):_ Retried twice automatically by `--reruns 2`. If still failing after retries, re-run `python scripts/test_db_reset.py` and retry `git push origin feature/2.5.63`.
- _Non-flaky e2e failure (e.g. `ReportingSqlAck` state pollution):_ The test DB reset in Task 8 was either skipped or failed. Run `python scripts/test_db_reset.py` and push again immediately.
- _INT DB transient outage during e2e:_ The SQL hooks do not contact INT at push time. However, e2e tests that make HTTP requests to a locally-running app which itself queries INT will fail if INT is unreachable. Wait for INT to recover and retry the push — no code change needed.
- _Push rejected (non-fast-forward):_ Run `git log --oneline origin/feature/2.5.63..HEAD` to confirm divergence. Do NOT use `--force` without explicit owner authorization and `--force-with-lease`.

---

## Gotchas and notes

**`SQL_SYNC_SKIP=1` scope.** Set it, run `git commit`, clear it with `Remove-Item Env:\SQL_SYNC_SKIP` immediately after. Never leave it in the environment — it silently suppresses the SQL migration check for subsequent commits in the same shell session. It is NOT set for `git push`; the SQL hooks do not run at push (confirmed: both have `stages: [pre-commit]` in `.pre-commit-config.yaml`).

**`--no-verify` is policy-forbidden.** `SQL_SYNC_SKIP=1` is the documented and policy-compliant escape hatch. Never bypass hooks with `--no-verify`.

**Fuzzy entries require two edits, not one.** Replacing the `msgstr` value is not enough — the `#, fuzzy` flag line must also be deleted. Leaving the flag in (even with a correct `msgstr`) causes `test_all_strings_translated` to fail because the test checks `"fuzzy" in msg.flags`.

**`%(var)s` and `{}` placeholders.** Python-format strings use `%(name)s` syntax (flagged `#, python-format` in the `.po`). These must appear verbatim in the translated `msgstr`. Specifically: `%(p)d`, `%(o)d`, and `%(limit)s` must be preserved exactly in the affected strings.

**Multi-line msgstr.** When a `msgid` is multi-line (blank `""` on the first line, content on continuation lines), the `msgstr` must follow the same structure. The `Document\n                  fields` fuzzy entry is an example — the `\n` and leading spaces are part of the string value, not formatting.

**`.mo` files are binary.** `.gitattributes` marks `*.mo binary` — git never mangles their line endings. Always commit `.mo` files alongside their `.po` counterparts or `test_mo_files_up_to_date` will still fail.

**`requirements-confluence.txt` and `sql/requirements.txt`.** Only root-level `requirements-confluence.txt` needs a `/XF` entry. `sql/requirements.txt` is already excluded because `/XD sql` covers the entire `sql/` directory in the robocopy command — verified in `.github/workflows/deploy.yml`.

**test_db_reset.py timing.** Run it as close to `git push` as possible. The pre-push pytest suite can take 5–20 minutes, and other processes writing to NEXORA_TEST during that window could re-introduce stale state for order-dependent e2e tests. This is rare in practice but the reset should not be run hours before the push.

**173-commit push volume.** After Task 7's new commit, the branch is 173 commits ahead of `origin/feature/2.5.63` (172 existing + 1 i18n/deploy fix). Confirmed fast-forward with no divergence.
