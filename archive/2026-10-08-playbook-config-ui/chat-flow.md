# Configuration chat flow — approved direction

> Archived feature record: S8 accepted on 2026-10-08; shipped in PR #20 as
> `0a3770e7306ec80fdf6b07aab88008cf2897aa77`. Earlier pending gates and failures
> below are dated history, not current instructions. See [closeout](closeout.md)
> for final candidate evidence, durable source pointers and remaining closeout.

Status: ASCII flow confirmed by the user on 2026-09-29; revised interactive mockup approved by the user. This is a chat experience, not a proposed browser settings page. Model placeholders below illustrate the layout rather than recommend a particular model.

## First setup

```text
/ai-playbook-configure
          |
          v
Read project context and saved personal preferences
Discover available model routes and eligible skills
          |
          v
New model/version? Check official docs for changes
Refresh affected recommendations and their evidence
          |
          v
Ask only for missing preferences
(goal/context, billing mode, guided/expert preference)
          |
          v
Recommended configuration + changes to review
          |
          +-- Edit ------> change one item ---------+
          |                                         |
          +-- Explain ---> reasons and sources -----+--> refreshed proposal
          |
          +-- Not now ---> exit without applying
          |
          +-- Apply -----> recheck current inputs
                                  |
                      +-----------+------------+
                      |                        |
               changed / blocked            still valid
                      |                        |
               revised proposal         save and validate
               or recovery choice       report what changed
                                        no build starts
```

The proposal includes scope, destination files and before/after changes before Apply is offered. Discovery and explanation do not install packages, run paid model comparisons or invoke candidate skills as an experiment. Any further proof needed for a custom skill is a separately scoped task, not an invisible setup side effect.

## Example proposal

```text
PLAYBOOK SETUP                     Project: current project

Preset: Recommended               Billing: confirmed mode

Role       Proposed choice        Why it fits
Plan       <verified model>       <task-fit and cost rationale>
Build      <verified model>       <task-fit and cost rationale>
Verify     <verified model>       <task-fit and cost rationale>
Repair     <verified model>       <reason for escalation choice>

QA uses Verify. Coordinator: <observed current route>.

Skill choices
Alignment       (<source>) <eligible skill or explicit manual route>
Specification   (<source>) <eligible skill or explicit manual route>
Implementation  (<source>) <eligible skill or explicit manual route>
Code review     (<source>) <eligible skill or explicit manual route>
Application QA  (<source>) <eligible skill or adopted verification route>

Changes
  Project settings: <before -> after, destination>
  Personal settings: <before -> after, local destination>
  Active feature choices: unchanged

1 Apply   2 Edit   3 Explain   4 Not now
```

Prefix each skill with its verified collection, for example `(Matt Pocock) tdd` or `(gstack) qa`; label Playbook workflows, project routes and custom skills explicitly. Apply the same labels in editing choices and change previews.

This is a complete proposal, not an instruction to ask about every row. Only propose personal-setting writes when the user selected that scope. Respect existing skill contracts: an application verification harness is not created merely by choosing its route.

## Explain one recommendation

```text
Explain Build

Choice: <model, runner and reasoning>
Why:    <connection to this project's work and risk>
Cost:   <verified API rates + labelled estimate, or known
         subscription usage implications; otherwise unknown>
Basis:  <official guidance link and checked date>
Change: <new model / changed advice or prices, when relevant>
        <relevant project evidence, when available>
Limits: <uncertainty, missing evidence, important trade-off>

Return to proposal; Explain does not select or launch a model.
```

Provider documentation informs suitability. It does not prove present account access, a cross-provider ranking or a guaranteed total saving. Where comparative evidence is weak, say so.

## Editing and presets

Reopening the skill shows existing values and their origins. Edit targets one model role, skill job or preference; it does not replay onboarding. Loading updated personal defaults or a saved preset produces a reviewable proposal for this project. Saving a personal preset does not update other projects. Feature-specific overrides remain separate from defaults.

## When a new model becomes available

During discovery, check relevant official provider guidance and pricing for changes. Reassess the affected recommendations and explain any proposed model or reasoning change. A new model does not automatically replace the current choice. Review and apply changes through the same proposal flow; existing active features retain their approved selections.

If documentation cannot be checked, show that limitation and the date of the last evidence. Do not present an old comparison as a fresh recommendation for the new model.

## Recovery

```text
Saved model unavailable
          |
Recommend an available replacement + explain why
          |
          +-- Accept replacement --> updated proposal --> Apply
          +-- Choose another model -> role editor -------> proposal
          +-- Not now -------------> exit without saving
```


- When a saved model is unavailable, recommend one verified replacement for the affected role, explaining task fit, route, cost implications and evidence limits. Offer **Accept replacement**, **Choose another model**, or **Not now**. Accepting updates the draft proposal and returns to the before/after preview; it does not save settings or launch a model. Choosing another opens the ordinary model editor for that role. Keep the unavailable saved choice visible until Apply succeeds; preserve active feature selections. If no eligible replacement is available, explain the limitation and offer recovery without inventing a recommendation.
- An ineligible custom skill shows the unmet job requirement and a supported/manual alternative. A warning does not make it eligible.
- Missing price or usage data is labelled unknown. An explanation may still describe suitability, but cannot claim an evidenced cost saving.
- If project files or availability change between preview and Apply, return to a refreshed proposal or a specific recovery action before writing.
- A failed apply reports the result and recovery action; the design must prevent partial settings from being reported as successful.

## Review request

The ASCII flow and revised local interactive artifact at `.lavish/playbook-config-ui-mockup.html` are approved. The specification and technical recommendations are accepted for breakdown. The [implementation slices](slices.md) are now approved and ticketed. The mockup is a review artifact, not a browser product interface.
