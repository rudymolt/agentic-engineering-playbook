```text
    ____  __            __                __
   / __ \/ /___ ___  __/ /_  ____  ____  / /__
  / /_/ / / __ `/ / / / __ \/ __ \/ __ \/ //_/
 / ____/ / /_/ / /_/ / /_/ / /_/ / /_/ / ,<
/_/   /_/\__,_/\__, /_.___/\____/\____/_/|_|
              /____/
```

# Agentic Engineering Playbook

**A practical guide and toolkit for building software with AI coding agents. If you are new to developing software or have no engineering background the playbook will keep you on track and help your agent to code like a pro.**

Turn an idea into a clear specification, build it in manageable pieces, verify the result, and carry lessons into the next feature. You bring the goals and judgement. The playbook gives your agent a repeatable way to work.

**Current release:** V0.5.0 · [Release notes](v0.5/CHANGELOG.md)

**Humans:** [Get started](#get-started) · **Agents:** [Read the agent digest](v0.5/AGENT-DIGEST.md)

## What is it?

The playbook is a collection of **Markdown instructions, reusable project templates, agent skills, and verification scripts** that you apply to your own software project. Your agent reads the instructions, sets up shared project context, and follows the appropriate workflow for the task.

It works alongside your application's language, framework, and development tools. You keep your application in its own repository and keep a stable copy of the playbook available to your agent.

Use it when you are building a new product or working on an existing codebase and want help with three recurring problems:

- **Building the wrong thing.** Agree on the goal and what success looks like before implementation starts.
- **Losing context between sessions.** Keep terminology, decisions, and progress in project files that the next agent can read.
- **Accepting work without proof.** Require tests, review, and evidence that the result meets the agreed goal. Larger changes receive independent verification from a fresh agent context.

The human owns goals, acceptance criteria, and consequential decisions. The agent plans, implements, checks, and records the work within the agreed scope.

## How it works

This is the core loop for a feature:

```text
  Explain the goal
         |
         v
  Agree on success --> Plan small pieces --> Build + test
         ^                                       |
         | next feature                          v
  Capture lessons <-------- Ship <--------- Review + QA
```

The [full workflow](v0.5/10-process/README.md) has 13 stages covering prerequisites, alignment, context, specification, breakdown, triage, architecture, implementation, review, QA, shipping, debugging, and retrospectives. The agent routes each request to the relevant stage; debugging and periodic architecture checks happen when needed.

For example, “add a way to export reports” starts with questions about who needs the export, what it contains, and how you will judge it. Once that is settled, the agent writes a specification, divides the work into small deliverable pieces, and builds and verifies them before shipping.

For UI work, the playbook also keeps a shared design vocabulary and asks for an approved ASCII layout sketch before implementation, followed by an HTML mockup for interactive or substantial changes.

## Get started

You need a coding agent (Claude, ChatGPT, Gemini, Grok, Kimi etc) that can read local files and run project commands, Git, and Python 3.10 or newer for the playbook scripts. Setup checks which tools and review routes your environment supports. Additional skill packages can accelerate the workflow; the [prerequisite guide](v0.5/10-process/00-prereqs.md) describes the available routes.

### 1. Keep a stable copy of the playbook

Clone this repository into a separate directory using the repository URL from GitHub's **Code** button:

```sh
git clone --branch v0.5.0 --depth 1 REPOSITORY_URL playbook
```

Replace `REPOSITORY_URL` with the copied URL. Keep this checkout at the release tag so development changes cannot silently change the instructions your project uses.

### 2. Open your project and give your agent this prompt

Replace `PLAYBOOK_CHECKOUT` with the location of your playbook checkout. Run this conversation in the application project you want to set up:

```text
Set up this project with the Agentic Engineering Playbook at
PLAYBOOK_CHECKOUT.

Read v0.5/AGENT-DIGEST.md in that checkout, then read and follow
v0.5/skills/ai-playbook-bootstrap-project/SKILL.md.

Inspect this project, explain the setup choices, and show me the proposed
file changes before applying them. Preserve existing project content.
After setup, verify the prerequisites and tell me the next step.
```

This prompt points directly to the bootstrap instructions, so the skill does not need to be installed first. Where the skill is already available, invoke `/ai-playbook-bootstrap-project`.

### 3. Review the setup, then start a task

Bootstrap presents a dry-run before writing files. It helps you choose UI and CI options and checks whether the project qualifies for the smaller [lite workflow](v0.5/70-lite-mode.md).

Full setup adds or proposes safe merges for project instructions (`AGENTS.md` and `CLAUDE.md`), shared context (`CONTEXT.md`), planning and archive folders, progress and cadence files, and selected local skills. Existing project content is preserved for review.

Once setup passes, describe the work in ordinary language:

| You want to… | Try asking… |
| --- | --- |
| Build a feature | “Help me plan a report export. Let's agree on what it needs to do.” |
| Fix a bug | “Investigate why saving this form sometimes creates two records.” |
| Review work | “Review this change and show the evidence that it is ready.” |
| Resume a project | “What should we work on next?” or `/whats-next` |

You do not need to memorise every stage or command. The agent uses the playbook to find the right next step and brings decisions back to you when your judgement is needed.

For more detail, read the [setup reference](v0.5/README.md) or [worked example](v0.5/80-quickstart.md). To explore the interactive guides, open `v0.5/index.html` from your checkout in a browser; GitHub displays HTML source rather than the rendered guide.

## Start here as an agent

Read [v0.5/AGENT-DIGEST.md](v0.5/AGENT-DIGEST.md) first. It is the compact operating entry point and owns the stage map, routing rules, and session-start procedure.

- **Setting up a target project:** follow the [bootstrap skill](v0.5/skills/ai-playbook-bootstrap-project/SKILL.md) from a pinned release checkout. Complete its setup review and prerequisite checks before declaring the project ready.
- **Resuming an adopted project:** read its local instructions and state, then follow the digest's session-start route. Project-local rules take precedence over general playbook guidance.
- **Upgrading an adopted project:** follow the [upgrade skill](v0.5/skills/ai-playbook-upgrade-project/SKILL.md) to review changes while preserving project-owned content.
- **Changing this repository:** read [AGENTS.md](AGENTS.md) and the [maintenance guide](v0.5/MAINTENANCE.md).

Load detailed stage instructions when the digest routes you to them. The versioned documents remain the operating source of truth.

## What's included

| Resource | What it helps you do |
| --- | --- |
| [Foundations](v0.5/00-foundations.md) | Set expectations for collaboration, architecture, security, and verification. |
| [Stage guides](v0.5/10-process/) | Move from an idea through implementation, review, shipping, and learning. |
| [Project templates](v0.5/templates/) | Keep instructions, vocabulary, decisions, and progress available across sessions. |
| [Frontend track](v0.5/20-frontend-track.md) | Keep UI vocabulary, visual examples, and interaction rules consistent. |
| [Local skills](v0.5/skills/README.md) | Set up projects, investigate code, verify behaviour, choose next steps, and upgrade. |
| [Document lifecycle](v0.5/30-document-lifecycle.md) and [learning loop](v0.5/40-self-improvement.md) | Keep durable decisions useful and turn lessons into better practices. |

Optional tracks cover [discovery before specification](v0.5/92-wayfinder-track.md), [delegating larger changes](v0.5/91-delegation-track.md), [model selection](v0.5/93-model-routing-track.md), and [autonomous loops](v0.5/90-loop-track.md). Start with the core workflow; these tracks have their own prerequisites and approval boundaries.

## Acknowledgements

This playbook brings together practical experience and ideas from people advancing agent-assisted software engineering:

- **[Matt Pocock](https://github.com/mattpocock)** — composable engineering skills and practices from [mattpocock/skills](https://github.com/mattpocock/skills).
- **[Garry Tan](https://github.com/garrytan)** — the engineering workflows and review practices in [gstack](https://github.com/garrytan/gstack).
- **[Lauren Tan (@poteto)](https://github.com/poteto)** — [pstack](https://github.com/cursor/plugins/tree/main/pstack), including the investigation and verification skills adapted here: `how`, `why`, `blast-radius`, and verification-harness creation and maintenance.
- **[Intelligent Internet](https://github.com/Intelligent-Internet)** — [Zenith](https://github.com/Intelligent-Internet/zenith), whose autonomous-loop work informed the emphasis on independent verification, stopping discipline, and evidence. Zenith is inspiration and prior art, rather than a dependency.

Adapted skills retain their upstream attribution and license notices. Explore the original projects for their full approaches.

## Contributing and license

Development changes go through review into `main`; projects consuming the playbook stay pinned to a release tag. See the [maintenance guide](v0.5/MAINTENANCE.md) for contribution and release checks. Before shipping changes, run:

```sh
python3 v0.5/scripts/verify-playbook.py
```

Original public work is licensed under [Apache-2.0](LICENSE). Adapted upstream skills retain their individual `NOTICE` files and license terms; preserve those notices when redistributing.
