# Aider nightly coding kit - v0.1

**Goal.** Orient you: what this kit is, how to get it running, and where every
file lives.

**Contents.** A short overview and the file inventory. The procedure is
`MANUAL.md`, step by step; the Ollama settings for your hardware are
`CONFIG_OLLAMA.md`; the coding rules the model obeys are `config/rules.md`. This
file points at those rather than repeating them.

Two local models, one driver. One writes code and its tests, a different one
reviews at the end of every plan and can never edit. Nothing leaves the machine.

## Start here

Read **MANUAL.md**. It is eight numbered steps from a bare machine to a project
that codes overnight.

| Step | What it does |
|---|---|
| 1 | install uv, aider and Ollama, and set the daemon variables |
| 2 | unblock the files and run `setup.ps1` |
| 3 | test the computer: prove the tools offline, then measure the hardware |
| 4 | tune Ollama and build the tag you actually run |
| 5 | create a project |
| 6 | write the three inputs, or take the worked example |
| 7 | dry run, then run the night |
| 8 | read the result |

Steps 1 and 2 are roughly this, but read them rather than pasting: each carries
a reason and a check.

```powershell
winget install --id=astral-sh.uv -e
uv tool install --force --python python3.12 --with pip aider-chat@latest
cd "$HOME\aider-kit"
Get-ChildItem -Recurse -Include *.ps1,*.bat | Unblock-File
.\setup.ps1 -DryRun
.\setup.ps1
```

## Before you trust a number

Every measured figure in this kit was taken on one machine, and yours is not
that machine. `ollama-tune.bat` measures yours, and `CONFIG_OLLAMA.md` says what
the numbers mean.

Two readings mislead, and both are worth knowing before you debug anything:

- `ollama ps` reports a **memory** ratio, not a layer ratio. For the real split
  read `offloaded N/M layers` from the Ollama server log.
- Task Manager's GPU graphs default to the 3D engine. CUDA work appears under
  `Cuda` or `Compute_0`, so a busy card can read 0 percent. Use
  `nvidia-smi --query-gpu=utilization.gpu --format=csv`.

## Proving it works, before spending a night on it

Each of these prints its own count of checks and whether they passed. Read that
count rather than a number quoted here.

```powershell
python bin\Test\test_aider_gpu_probe.py        # the GPU probe
python bin\Test\test_aider_thread_probe.py     # the measurement probe
python bin\Test\test_aider_ollama_config.py    # the configurator
bin\Test\verify-aider-plan.ps1                 # the driver
```

All four are offline: no model is loaded, no network is used, and no Ollama
installation is needed.

## What is in here

| Path | What it is |
|---|---|
| `MANUAL.md` | the procedure, in eight steps. Read this first |
| `CONFIG_OLLAMA.md` | how to configure Ollama for YOUR machine, and what each measurement means |
| `setup.ps1` | installs the kit into your home directory. Adds, never silently replaces |
| `new-project.ps1` | scaffolds one project: git, hooks, plans skeleton, tests, its own venv |
| `install-hooks.ps1` | the branch-protection hooks alone, for a repository you already have |
| `ollama-tune.bat`, `ollama-tune.ps1` | measures this machine: bandwidth, threads, GPU offload, context cost |
| `config/aider.conf.yml` | the one file aider finds by name |
| `config/model-settings.yml` | per-model settings. The `num_ctx` here overrides a tuned tag's own Modelfile |
| `config/conventions.md` | the working protocol the model reads on every call |
| `config/rules.md` | the coding rules, generated. Do not edit |
| `config/rules-local/` | where a rule of your own goes, as a bolded `**Rn - statement.**` |
| `config/context-budget.json` | every token ceiling, each with a comment saying where its number came from |
| `config/skills.json` | which skill reaches the model at which stage, and its ceiling |
| `config/skills/` | the skill files themselves, copied so no upstream update can change them mid-project |
| `examples/robot-planning-prompt.md` | the prompt that produced the worked example, and why it is shaped that way |
| `examples/robot-planner-plans/` | the nine documents it produced: a seven-plan robot simulator that fits the ceilings |
| `bin/aider-night.ps1`, `bin/aider-night.bat` | the night entry point: one command, skills wired |
| `bin/aider-plan.ps1` | the driver: plans, tests, audit, archiving |
| `bin/aider-plan-core.ps1` | the driver's pure half. It must sit beside the driver, which refuses without it |
| `bin/aider-rules-sync.py` | regenerates `rules.md` from a rules directory |
| `bin/aider-gpu-probe.py`, `.json` | measures which model and context actually puts layers on YOUR card |
| `bin/aider-thread-probe.py`, `.json` | measures what bounds a model here: memory bandwidth, threads, offload, window cost |
| `bin/aider-ollama-config.py` | turns the budget plus a measurement into a tuned tag, and reads the tag back |
| `bin/Test/` | the offline suites for all of the above |
| `new-project.ps1` | scaffold one isolated project |
| `install-hooks.ps1` | add the hooks to an existing repository |
| `git-hooks/` | per-repository branch protection |
| `project-template/` | the three documents a project starts from |

## What a skill does here, and what it does not

A skill is a Markdown file handed to the model as read-only context at one stage
of the loop. It is not code, it is not executed, and it cannot edit anything.
`config/skills.json` decides which file reaches the model when. Some are
third-party: `config/skills/LICENSE-superpowers.txt` records their licence and
states which were modified and how.

## What is proven, and what is not

The offline suites above prove the tools. What they do not prove is a night: that
takes hours of real model time on real hardware, and the only way to know your
machine handles it is to run one. Start with the worked example in `examples/`,
which is known to fit the ceilings.
