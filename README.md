# Starforge

**A budgeted OpenCode + DeepSeek loop for building small tools from real demand.**

Starforge collects public GitHub issues, asks DeepSeek Flash to identify a bounded use case, uses OpenCode to implement it, reviews the result, and tests it on GitHub Actions before publishing a source prototype. It records spend estimates and actual repository feedback. It does not manufacture stars or promise adoption.

The controller is Python standard library code. OpenCode is a separate executable you install. Credentials are provided through environment variables or Windows user-bound DPAPI files, outside this repository.

## The loop

1. Collect up to 36 public issue signals from three configured searches. No model call is needed for collection.
2. Require two real demand references before a candidate can proceed. The model may choose to do nothing.
3. Build one small, dependency-free Python CLI, behavior tests, and English/Chinese READMEs.
4. Apply static file and credential checks, then ask for a separate model review. This review is not independent human verification.
5. Push an explicitly unreleased candidate branch to the incubator. GitHub runners execute tests and public CLI commands on Python 3.10 and 3.13.
6. Promote only a passing candidate to an `sf-*` repository and a prerelease. Record its evidence, commit, and CI run.

The default is one published prototype per Hong Kong calendar day and a new demand scan every six hours. Failed or rejected attempts remain recorded instead of being regenerated indefinitely. Existing repositories' stars, forks, and issue counts are sampled for later evaluation; the first version does **not** claim a learned prediction of star growth or automatically optimize from those metrics.

## Run

Python 3.10+ and OpenCode 1.18.5 (the tested version) are required. The GitHub account needs permission to create repositories and push workflows. The incubator repository must already exist and have GitHub Actions enabled.

```sh
git clone https://github.com/waiteddegree608-ship-it/starforge.git
cd starforge
cp config.example.json config.local.json
# Set paths, owner, searches, price review dates, and budget in config.local.json.
# Supply GH_TOKEN and DEEPSEEK_API_KEY in the parent service environment.
python -m unittest discover -s tests -v
python -m starforge --config config.local.json probe
python -m starforge --config config.local.json once
python -m starforge --config config.local.json loop
```

`probe` makes one small paid model request and tests the real OpenCode → loopback gateway → DeepSeek path. `once` discovers/builds a candidate or polls a pending CI result; call it again after CI completes. `loop` checks pending CI every minute and starts new discovery only when the interval allows.

```sh
python -m starforge --config config.local.json status
python -m starforge --config config.local.json pause
python -m starforge --config config.local.json resume
```

Pause prevents the next cycle; an already running operation may finish. Stopping the parent process interrupts local orchestration, but cannot cancel a provider request already accepted. A process lock prevents overlapping controllers. No scheduler or startup task is installed by these commands.

## Budget controls

The configured daily ceiling is at most ¥20. Before **every** model request, a SQLite ledger reserves a conservative amount using serialized input bytes plus overhead, capped output tokens, the configured peak price, a currency ceiling, and a safety multiplier. Successful responses settle using provider-reported token counts, conservatively treating cached input as uncached. Unknown outcomes retain the reservation and stop that cycle; they are not automatically retried upstream.

Defaults reflect the [DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing/) checked on 2026-10-10: Flash peak input $0.30 and output $1.20 per million tokens. The example uses **8 CNY/USD as a budget conversion ceiling, not a claimed exchange rate**, plus 25% headroom. Price configuration expires after seven days and requires review before further paid work. Off-peak/cache discounts create additional margin; the ledger is not an invoice. Provider price changes or charges made by other applications are outside this controller's ceiling.

Daily budget resets use Asia/Hong_Kong (UTC+8). A request is attributed to its reservation day. State files include `budget.sqlite3`, `state.json`, `metrics.json`, `signals-latest.json`, per-job files, and local OpenCode logs. Keep them out of public Git repositories.

## Execution and publication boundaries

- The coding agent receives a short-lived loopback token, not your real DeepSeek or GitHub keys. Provider authentication stays in the parent gateway.
- OpenCode can read/write its candidate directory; shell, external-directory access, subagents, web tools, and Git operations are denied. Provider choices are restricted to the local budget gateway.
- Generated code is never executed locally by Starforge. Tests run on ephemeral GitHub-hosted runners with no supplied secrets and read-only repository permissions.
- Candidate branches are **public before tests finish**, clearly marked as unreleased. Do not use this loop for private documents or confidential specifications.
- The first version generates only small standard-library Python tools. It does not change EKina/Paperfect, run installers, delete repositories, modify account settings, contact people, or post promotion messages.
- File gates, AI review, and CI reduce mistakes but do not prove usefulness or security. Review released prototypes before relying on them. A second model pass can share the first pass's blind spots.

Windows DPAPI support reads `.dpapi` files created with `ConvertFrom-SecureString` under the current Windows account. Never commit credentials, encrypted secret files, or transcripts. OpenCode gateway keys are unnecessary when calling DeepSeek directly; no automatic paid fallback is enabled.

## References

[OpenCode CLI](https://opencode.ai/docs/cli/) · [Permissions](https://opencode.ai/docs/permissions/) · [DeepSeek API pricing](https://api-docs.deepseek.com/quick_start/pricing/)

MIT for project-owned source. Third-party services and tools retain their own terms and licenses.
