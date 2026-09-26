window.PLAYBOOK_GLOSSARY = {
  adapter: {
    title: "Adapter",
    def: "A thin layer at the edge of the system whose only job is to translate between the outside world and the canonical internal form."
  },
  adr: {
    title: "ADR",
    def: "Architecture Decision Record - a one-page note explaining why a hard-to-reverse choice was made, so future-you does not have to guess."
  },
  afkhitl: {
    title: "AFK / HITL",
    def: "AFK = away from keyboard: the agent can finish this alone. HITL = human in the loop: it needs a person's input partway through."
  },
  atomiccommit: {
    title: "Atomic commit",
    def: "One commit that captures a single, complete change - the slice plus its tests - so it can be understood or undone as one unit."
  },
  ballofmud: {
    title: "Ball of mud",
    def: "Slang for a codebase so tangled that no part can be changed safely without risking breakage somewhere else."
  },
  benchmark: {
    title: "Benchmark",
    def: "A baseline measurement of how fast or reliable something is, so you can tell if a change made it better or worse."
  },
  branch: {
    title: "Branch",
    def: "A safe parallel copy of the code where you can build something without affecting the main version."
  },
  browsercheck: {
    title: "Browser check",
    def: "Opening the actual app in a browser to look at the real screen, not just trusting the code or the tests."
  },
  build: {
    title: "Build",
    def: "Turning the source code into the runnable app. A failed build usually means a syntax or wiring error."
  },
  canary: {
    title: "Canary",
    def: "Watching new code closely in production right after release, ready to pull it back at the first sign of trouble."
  },
  ci: {
    title: "CI",
    def: "Continuous Integration - automated checks that run every time you push, to catch problems before a human looks."
  },
  commit: {
    title: "Commit",
    def: "A saved snapshot of your changes with a short message describing what they do."
  },
  contextmd: {
    title: "CONTEXT.md",
    def: "A file holding the project's glossary of real-world terms, so the agent uses your exact words everywhere."
  },
  designreview: {
    title: "Design review",
    def: "A check of how a screen looks and behaves - layout, spacing, and how it holds up at different screen sizes."
  },
  diff: {
    title: "Diff",
    def: "The exact list of lines that were added, removed, or changed between two versions."
  },
  docclose: {
    title: "Doc-close",
    def: "The tidy-up at ship: lasting decisions and vocabulary move into permanent docs, finished planning notes get archived, and the cleanup is committed on purpose."
  },
  draftpr: {
    title: "Draft PR",
    def: "A pull request marked not ready to merge yet - used to share work in progress without inviting the merge button."
  },
  featurebranch: {
    title: "Feature branch",
    def: "A branch made specifically to build one feature on. It exists until the work is merged, then is thrown away."
  },
  gbrain: {
    title: "GBrain",
    def: "The agent's long-term memory that persists across sessions and projects, so lessons learned are not forgotten next time."
  },
  github: {
    title: "GitHub",
    def: "The website where the team's code, pull requests, and review discussions live."
  },
  headinghierarchy: {
    title: "Heading hierarchy",
    def: "The nested structure of titles and subtitles. It should match what the eye sees, which also lets screen readers navigate the page."
  },
  interface: {
    title: "Interface",
    def: "The way you use a module from outside - its buttons and dials - as opposed to the machinery hidden behind them."
  },
  ladder: {
    title: "Verification ladder",
    def: "A simple rule that scales how hard you check a change to how costly it would be to get wrong."
  },
  main: {
    title: "main",
    def: "The shared, live version of the code that everyone works from. Nothing in main should be broken."
  },
  merge: {
    title: "Merge",
    def: "Combining the changes from one branch into another - usually pulling finished work into main."
  },
  mockup: {
    title: "Mockup",
    def: "A drawing or fake version of the screen, used to agree what something should look like before real code is written."
  },
  module: {
    title: "Module",
    def: "A self-contained piece of the program that does one job, with a defined way of being used from outside."
  },
  nontrivial: {
    title: "Non-trivial",
    def: "Not a tiny one-line fix - a real piece of work big enough to deserve the full process: branch, tests, and PR."
  },
  playbook: {
    title: "The playbook",
    def: "This collection of guides - the process the agent follows on every project."
  },
  pr: {
    title: "Pull request (PR)",
    def: "A proposal to add changes to the main code. A person has to review and accept it before it lands."
  },
  productcall: {
    title: "Product call",
    def: "A decision about what something should do, not how to build it. Those decisions belong to the human project owner."
  },
  publicinterface: {
    title: "Public interface",
    def: "The official, supported way to use a piece of code - its front door - rather than reaching into its internal wiring."
  },
  push: {
    title: "Push",
    def: "Uploading your local commits to GitHub so the rest of the world, and the PR, can see them."
  },
  redgreen: {
    title: "Red / green",
    def: "A failing test is red; the smallest implementation that makes it pass turns it green. Structural tidy-up belongs to the later review stage."
  },
  refactor: {
    title: "Refactor",
    def: "Rewriting code so it is cleaner or easier to change, without changing what it actually does."
  },
  regression: {
    title: "Regression test",
    def: "A test added after fixing a bug, so that exact bug is caught automatically if it ever reappears."
  },
  repo: {
    title: "Repo",
    def: "Short for repository - the folder where the project's code and its full history live."
  },
  retro: {
    title: "Retro",
    def: "Short for retrospective - a brief review after a piece of work to capture what went well and what to do differently."
  },
  slice: {
    title: "Slice (vertical slice)",
    def: "A small piece of the feature that works end-to-end, from screen to database, rather than building one whole layer first."
  },
  smokefloor: {
    title: "Smoke floor",
    def: "The minimum set of quick checks a screen must pass before it counts as done - a floor, not a full test plan."
  },
  sourceoftruth: {
    title: "Source of truth",
    def: "The one canonical place a piece of data lives. Everything else reads it or works it out from there - never keeps its own rival copy."
  },
  tdd: {
    title: "Test-driven development (TDD)",
    def: "Writing a small test describing the desired behaviour before writing the code that satisfies it."
  },
  test: {
    title: "Test",
    def: "A small piece of code that automatically checks a bit of your app behaves the way it should."
  },
  touchtarget: {
    title: "Touch target",
    def: "The tappable area of a button or link. Roughly 44 pixels square is the floor for it to be comfortable to hit on a phone."
  },
  tracerbullet: {
    title: "Tracer bullet",
    def: "A single thin feature built all the way through every layer, so you can see it work end-to-end and adjust."
  },
  triggerphrase: {
    title: "Trigger phrase",
    def: "A short, standard thing you type to start a stage. The agent recognises the phrase and runs the right process."
  },
  trunk: {
    title: "Trunk",
    def: "Slang for the main branch - the trusted, shared version everyone builds from."
  },
  typecheck: {
    title: "Typecheck",
    def: "A quick automated check that you are using data of the right shape - catches lots of bugs without running the app."
  },
  urlstate: {
    title: "URL state",
    def: "When the web address itself remembers which drawer, filter, or tab you have open - so a refresh or shared link lands you back in the same place."
  }
};
