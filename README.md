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

**Current release:** V0.5.1 · [Release notes](v0.5/CHANGELOG.md#v051--2026-10-08)

**Humans:** [Get started](#get-started) · **Agents:** [Read the agent digest](v0.5/AGENT-DIGEST.md)

**Explore the [interactive guides](https://rudymolt.github.io/agent-engineering-playbook)** for practical examples, the stage map, cloud build options and explanations of technical terms.

## What is it?

The playbook is a collection of **Markdown instructions, reusable project templates, agent skills, and verification scripts** that you apply to your own software project. Your agent reads the instructions, sets up shared project context, and follows the appropriate workflow for the task.

It works alongside your application's language, framework, and development tools. You keep your application in its own repository and keep a stable copy of the playbook available to your agent.

Use it when you are building a new product or working on an existing codebase and want help with three recurring problems:

- **Building the wrong thing.** Agree on the goal and what success looks like before implementation starts.
- **Losing context between sessions.** Keep terminology, decisions, and progress in project files that the next agent can read.
- **Accepting work without proof.** Require tests, review, and evidence that the result meets the agreed goal. Larger changes receive independent verification from a fresh agent context.

The human owns goals, acceptance criteria, and consequential decisions. The agent plans, implements, checks, and records the work within the agreed scope.

## What's new in V0.5.1

- **Configure model and skill choices in chat.** `/ai-playbook-configure` shows the current Plan, Build, Verify, and repair defaults, plus the skills used for alignment, specification, implementation, review, and application QA. You can inspect sources, edit a draft, and review the exact destination before applying it. Personal defaults and named presets can be saved locally and loaded into a draft for another project. [Configuration guide](v0.5/README.md#existing-projects)
- **Get evidence-backed model advice.** At a Plan, Build, or Verify choice, the agent can show task-specific suggestions with source dates, limitations, and available pricing information. Suggestions do not change a saved preference or launch a model; the usual route and approval checks still apply. [Model routing guide](v0.5/93-model-routing-track.md)
- **Choose the amount of build work.** After planning, choose `build one`, `build all`, or `build to <slice>` for eligible slices. Add `fast` to a Build choice when an available Codex route supports it. Fresh verification and the same quality gates apply. [Build choices](v0.5/10-process/07-implementation-tdd.md#the-build-choice-v0316)
- **Keep setup and upgrades safe.** Bootstrap can preview project model seeds, and upgrades preserve adopted configuration and project content. Retained Apply recovery files are ignored by Git while the shareable configuration remains trackable. [Bootstrap](v0.5/skills/ai-playbook-bootstrap-project/SKILL.md) · [Upgrade](v0.5/skills/ai-playbook-upgrade-project/SKILL.md)

See the [V0.5.1 changelog](v0.5/CHANGELOG.md#v051--2026-10-08) for the full set of changes and fixes.

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

## The playbook is powered by skills

A **skill** is a reusable set of instructions that teaches an agent how to perform a particular task, such as writing a specification, investigating a bug, or reviewing code. The playbook connects these skills into a complete engineering workflow, telling the agent when to use them and what evidence to produce.

The suggested skills draw on several projects:

- **[Matt Pocock's skills](https://github.com/mattpocock/skills)** are small, composable engineering workflows for clarifying requirements, building shared terminology, writing specifications, splitting work into tickets, testing, and improving code. They help the human and agent agree on the work and carry it out in manageable steps.
- **Garry Tan's [gstack](https://github.com/garrytan/gstack)** provides specialist workflows for product thinking, design, engineering review, browser-based QA, security, and shipping. It gives an agent procedures for examining work from different professional perspectives, from questioning the product idea to testing the finished experience.
- **Lauren Tan's [pstack](https://github.com/cursor/plugins/tree/main/pstack)** combines engineering principles with skills for understanding existing code, investigating why it works that way, assessing the impact of changes, and proving results. The playbook includes adaptations of selected investigation and verification skills, with their upstream notices preserved.

Here is how they map to the specific parts of the workflow.

| Part of the workflow | Examples of skills and sources |
| --- | --- |
| Clarify the goal | Matt Pocock's `grill-with-docs`; gstack's `office-hours` and planning reviews. |
| Explore an unclear route before writing a specification | Matt Pocock's `wayfinder`, through the playbook's optional [Wayfinder track](v0.5/92-wayfinder-track.md). |
| Specify and divide the work | Matt Pocock's `to-spec` and `to-tickets`. |
| Implement and investigate | Matt Pocock's `tdd` and `diagnosing-bugs`; gstack's `investigate`. |
| Review and test the experience | Review and QA procedures drawing on Matt Pocock's skills and gstack, with compatibility checks before running upstream reviewers. |
| Understand and verify the codebase | Playbook adaptations of [Lauren Tan's pstack](https://github.com/cursor/plugins/tree/main/pstack), including `how`, `why`, `blast-radius`, and verification-harness creation and maintenance. |
| Set up and coordinate the project | Playbook-specific bootstrap, upgrade, next-step routing, model-routing, and delivery skills. |

**Wayfinder is for when you know the destination but still need to work out how to get there.** If the uncertainty spans several sessions or connected decisions, it organises research, prototypes, and questions before you commit to a specification. The agent can suggest it, but you choose whether to invoke `/wayfinder`. Straightforward features go directly through normal alignment and specification.

### What do I need to install?

**Matt Pocock's skills and gstack are separate installations.** Cloning this playbook or running its bootstrap does not automatically install either collection. If you already have them installed, setup checks whether the required skills are discoverable and compatible with the playbook's procedures.

- **Matt Pocock's skills:** the playbook targets released v1.3.1. Use `npx skills@1.7.1 add https://github.com/mattpocock/skills/tree/v1.3.1` and select the skills and agent environments you need. Leave Matt's bare `retro` unselected: bootstrap/upgrade provide `/matt-retro` (`$matt-retro` in Codex), alongside gstack's `/retro` (`$gstack-retro`). Follow [stage 00](v0.5/10-process/00-prereqs.md) for selection and installed-source checks; existing projects first complete the [glossary migration](v0.5/skills/ai-playbook-upgrade-project/MIGRATIONS.md). Preserve local skill customizations and avoid automatic updates beyond the tested pin. The optional `setup-matt-pocock-skills` skill helps configure tracker and documentation choices.
- **gstack:** follow its [installation guide](https://github.com/garrytan/gstack#install--30-seconds) for your coding-agent environment. It has its own setup script and prerequisites, including Bun for its tooling. The guide covers Claude Code and other supported agents, including Codex.
- **pstack adaptations and playbook-local skills:** the selected adaptations are already included in this repository and installed into the target project by the playbook bootstrap. You do not need the full upstream pstack package to use those adaptations.
- **Autonomous delivery:** full project bootstrap installs the delivery runtime and `/ai-playbook-deliver`. Installation alone does not authorise unattended work: the [delivery workflow](v0.5/10-process/delivery-mission.md) still requires capability checks and approval of the mission's scope, limits, and stopping conditions.

You can start without Matt's collection or gstack if every required stage has a working manual or alternative route. Here, “manual” means following the documented stage procedure directly, without invoking a packaged skill; the agent can still perform the work. Setup records those routes, and pauses if a required capability has no usable route.

Installing a package does not automatically make every version compatible. The playbook records its verified upstream versions and checks reviewer compatibility before use. Where a skill is unavailable or incompatible, the stage's documented fallback preserves the same required outputs and evidence.

These are recommended starting points. You can add your own skills or adapt the workflow to tools your team already uses. A replacement should fulfil the stage's requirements: the same decisions, outputs, and verification evidence still need to exist. Document and verify the replacement route before relying on it.

See the [prerequisite guide](v0.5/10-process/00-prereqs.md) for skill packages and capability checks, and the [local skill guide](v0.5/skills/README.md) for the skills maintained here.

## Use the playbook with your choice of coding agent

The core workflow is designed to be portable across coding-agent environments, or **harnesses**, such as Codex, Claude Code, Grok Build or Conductor. A harness is the software that lets a model read your project, use tools, and carry out development work.

Setup checks how your environment reads project instructions, runs commands, loads skills, and supports independent review. Available automation depends on those capabilities. The [capability profiles](v0.5/10-process/prereqs-capability-profiles.md) describe the supported routes and their requirements.

### [Conductor.build](https://www.conductor.build/) Support

[Conductor](https://conductor.build) lets you run a team of coding agents in separate workspaces on your Mac or in the cloud. Its local app has a free plan; Cloud workspaces require a paid plan. You bring your own model subscriptions or API keys. See [Conductor's current plans](https://www.conductor.build/pricing) for pricing.

The playbook includes Conductor-specific setup and delivery procedures alongside its general engineering workflow. During setup, the agent inspects the project and proposes appropriate setup commands, development commands, files to copy, and port or shared-resource handling. You review those changes before they are applied.

After setup, `/ai-playbook-configure` can show the project's saved model and skill choices in the active agent chat. The Plan, Build, and Verify stages explain whether a selected route uses the current tab, a sidecar, or a new Conductor tab before work starts.

### Building features autonomously

Once you have planned a feature and sliced it up into smaller chunks you are ready to build. With the playbook you can choose how much work the agent completes before handing control back:

- **Build one:** implement and verify the next slice, then report back.
- **Build all:** work through the current feature's remaining slices that are approved for unattended execution, with independent checks between slices and a final review across the feature.
- **Deliver to PR:** use the optional delivery workflow to carry approved work through implementation, independent verification, quality assurance (QA), and a pull request for review. This route requires its own setup, capability checks, and explicit approval.

```text
  WITH YOU                 APPROVED UNATTENDED WORK
  --------                 ------------------------
  Goal + specification --> Build --> Verify --> QA --> Pull request
  Scope + limits              ^         |
                              +-- Fix --+
```

The delivery workflow supports local execution and Conductor Cloud. Once you have approved the specification, scope, and execution limits, the agent can build and verify eligible work without routine human prompts. A fully specified feature can proceed through that workflow unattended when all its slices are eligible.

Independent checks remain part of the process. The agent can repair eligible findings and send the changes through fresh verification, but pauses for decisions requiring your judgement, unresolved ambiguity, repeated failures, or a stopping limit.

Ordinary delivery ends with a pull request for review. Merging requires human action or a separately approved merge route; deployment and release remain separate steps.

See the [build choices](v0.5/10-process/07-implementation-tdd.md#the-build-choice-v0316) and [delivery workflow](v0.5/10-process/delivery-mission.md) for the full requirements.

## Get started

You need a coding-agent environment, such as Codex or Claude Code, that can read local files and run project commands, plus Git and Python 3.10 or newer for the playbook scripts. Setup checks which tools and review routes your environment supports. Additional skill packages can accelerate the workflow; the [prerequisite guide](v0.5/10-process/00-prereqs.md) describes the available routes.

### 1. Keep a stable copy of the playbook

Clone this repository into a separate directory using the repository URL from GitHub's **Code** button:

```sh
git clone --branch v0.5.1 --depth 1 REPOSITORY_URL playbook
```

Replace `REPOSITORY_URL` with the copied URL. Keep this checkout at the release tag so development changes cannot silently change the instructions your project uses.
When a later release is available, read its changelog and use the
[upgrade skill](v0.5/skills/ai-playbook-upgrade-project/SKILL.md) to check
compatibility and preview the migration while preserving your project's
instructions, model choices, skill bindings, and other customisations.

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

Full setup adds or proposes safe merges for project instructions (`AGENTS.md` and `CLAUDE.md`), domain vocabulary (`GLOSSARY.md`), planning and archive folders, progress and cadence files, and selected local skills. Existing project content is preserved for review.

Once setup passes, describe the work in ordinary language:

| You want to… | Try asking… |
| --- | --- |
| Build a feature | “Help me plan a report export. Let's agree on what it needs to do.” |
| Fix a bug | “Investigate why saving this form sometimes creates two records.” |
| Review work | “Review this change and show the evidence that it is ready.” |
| Adjust model or skill defaults | “Run `/ai-playbook-configure` and show me the choices before applying.” |
| Build planned slices | “Build one,” “build all,” or “build to slice 3”; add “fast” when available. |
| Resume a project | “What should we work on next?” or `/whats-next` |

You do not need to memorise every stage or command. The agent uses the playbook to find the right next step and brings decisions back to you when your judgement is needed.

For more detail, read the [setup reference](v0.5/README.md) or [worked example](v0.5/80-quickstart.md). To explore the interactive guides, open `v0.5/index.html` from your checkout in a browser; GitHub displays HTML source rather than the rendered guide.

## Start here as an agent

Read [v0.5/AGENT-DIGEST.md](v0.5/AGENT-DIGEST.md) first. It is the compact operating entry point and owns the stage map, routing rules, and session-start procedure.

- **Setting up a target project:** follow the [bootstrap skill](v0.5/skills/ai-playbook-bootstrap-project/SKILL.md) from a pinned release checkout. Complete its setup review and prerequisite checks before declaring the project ready.
- **Resuming an adopted project:** read its local instructions and state, then follow the digest's session-start route. Project-local rules take precedence over general playbook guidance.
- **Upgrading an adopted project:** follow the [upgrade skill](v0.5/skills/ai-playbook-upgrade-project/SKILL.md) to review changes while preserving project-owned content.
- **Configuring an adopted project:** use the [configure skill](v0.5/skills/ai-playbook-configure/SKILL.md) for model defaults and eligible skill jobs. Keep preferences and evidence local; project changes require a reviewed preview and explicit Apply.
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
