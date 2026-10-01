"""S6 read-only Configure and lane advice contracts; values are synthetic."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from playbook_config import Configuration, ROLES
from model_recommendations import OfficialSources


NOW = "2026-10-01T12:00:00Z"
GUIDANCE = "https://developers.openai.com/api/docs/models"
PRICING = "https://developers.openai.com/api/docs/pricing"


def claim(url, **values):
    return dict(source_url=url, checked_at=NOW, uncertainty="Synthetic controlled evidence, not current rates.", **values)


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.state = self.project / ".playbook-state.yml"
        self.state.write_text("model_routing:\n  allowed_runners: [codex]\npending_model_routes: [keep]\nactive_features: [keep]\nlast_run: {history: keep}\n")
        self.original = self.state.read_bytes()
        self.routes = [{"model_id": model, "runner": "codex", "reasoning": "high", "provider": "openai", "roles": list(ROLES)}
                       for model in ("fixture-code", "fixture-analysis")]
        self.evidence = {"guidance": [claim(GUIDANCE, model_id=model, provider="openai", tasks=[task], risks=["ordinary", "high"],
                                          reasoning=["high"], text="Controlled task capability")
                                      for model, task in (("fixture-code", "coding"), ("fixture-analysis", "analysis"))],
                         "rates": [claim(PRICING, model_id="fixture-code", provider="openai", currency="USD", unit="1M tokens",
                                         input=2, output=6, billing_route="standard-short-context-uncached")], "sources": []}
        self.calls = []
        self.context = {"goal": "Implement parser", "task": "coding", "risk": "ordinary", "billing": "api"}

    def discover(self, request):
        self.calls.append(request["purpose"])
        return dict(request_id=request["request_id"], checked_at=request["started_at"], revision="fixture",
                    authority="host-reported-selection", routes=deepcopy(self.routes))

    def service(self, context=None, sources=None):
        return Configuration(self.project, self.discover, lambda: NOW, context=context or self.context,
                             recommendation_sources=sources or (lambda: deepcopy(self.evidence)))

    def test_configure_recommends_all_roles_without_selection_or_writes(self):
        service = self.service()
        draft = service.read()
        self.assertEqual(draft["state"], "decision_required")
        for role in ROLES:
            advice = draft["recommendations"][role]
            self.assertEqual(advice["choice"]["model_id"], "fixture-code")
            self.assertEqual(advice["guidance"]["source_url"], GUIDANCE)
            self.assertIn("Implement parser", advice["rationale"])
            self.assertIsNone(advice["cost"]["estimate"])
            self.assertEqual(advice["cost"]["rates"]["unit"], "1M tokens")
            self.assertIsNone(advice["local_outcomes"])
        explained = service.reply(draft, "Explain Verify")
        self.assertEqual(explained["after"], draft["after"])
        self.assertFalse(explained["launched"])
        self.assertEqual(self.calls, ["current-availability"])
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertFalse((self.project / ".playbook-config.json").exists())

    def test_task_and_billing_change_advice_not_defaults(self):
        initial = self.service().read()
        other = self.service({**self.context, "task": "analysis", "billing": "subscription"}).read()
        self.assertEqual(other["recommendations"]["implementation"]["choice"]["model_id"], "fixture-analysis")
        self.assertEqual(other["after"], initial["after"])
        self.assertIsNone(other["recommendations"]["implementation"]["cost"]["rates"])
        self.assertIsNone(other["recommendations"]["implementation"]["cost"]["estimate"])

    def test_labeled_api_estimate_and_unknown_billing_routes(self):
        context = {**self.context, "workload": {"input_tokens": 1000, "output_tokens": 500, "retries": 2,
                   "billing_route": "standard-short-context-uncached"}}
        advice = self.service(context).read()["recommendations"]["implementation"]
        self.assertAlmostEqual(advice["cost"]["estimate"]["amount"], .015)
        self.assertEqual(advice["cost"]["estimate"]["assumptions"], context["workload"])
        for billing in ("mixed", "unknown", "subscription"):
            advice = self.service({**context, "billing": billing}).read()["recommendations"]["implementation"]
            self.assertIsNone(advice["cost"]["rates"])
            self.assertIsNone(advice["cost"]["estimate"])

    def test_missing_rates_unsupported_reasoning_unavailable_and_constraints(self):
        self.evidence["rates"] = []
        self.routes.append({**self.routes[0], "runner": "unapproved"})
        self.routes[0]["reasoning"] = "unsupported"
        draft = self.service().read()
        self.assertIsNone(draft["recommendations"]["implementation"]["choice"])
        self.routes[0]["reasoning"] = "high"
        context = {**self.context, "constraints": {"verification": {"independent": False}}}
        draft = self.service(context).read()
        self.assertIsNone(draft["recommendations"]["verification"]["choice"])
        self.assertIsNone(draft["recommendations"]["implementation"]["cost"]["rates"])

    def test_lane_gate_advice_preserves_feature_preference_and_approvals(self):
        service = self.service()
        feature = {"model_id": "explicit-feature", "runner": "codex", "reasoning": "high"}
        advice = service.advise("verification", feature)
        self.assertEqual(advice["effective"], {"origin": "feature", "choice": feature})
        self.assertIsNone(advice["recommendation"]["choice"])
        context = {**self.context, "constraints": {"verification": {"authority": True, "permission": True, "independent": True}}}
        advice = self.service(context).advise("verification", feature)
        self.assertEqual(advice["recommendation"]["choice"]["model_id"], "fixture-code")
        self.assertFalse(advice["launched"])
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_failed_retrieval_never_stamps_old_evidence_fresh(self):
        def failed():
            raise OSError("private source failure")
        draft = self.service(sources=failed).read()
        self.assertIsNone(draft["recommendations"]["implementation"]["choice"])
        self.assertNotIn("private source failure", json.dumps(draft))
        previous = claim(GUIDANCE, model_id="fixture-code", provider="openai", tasks=["coding"], risks=["ordinary"], reasoning=["high"], text="old")
        previous["checked_at"] = "2026-09-01T12:00:00Z"
        adapter = OfficialSources(lambda: NOW, fetch=lambda url: (_ for _ in ()).throw(OSError()), previous={GUIDANCE: previous})
        source = adapter.retrieve()["sources"][0]
        self.assertEqual(source["checked_at"], previous["checked_at"])
        self.assertEqual(source["status"], "stale")

    def test_official_adapter_fetches_all_sources_and_parses_controlled_tables(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if url == GUIDANCE:
                return '<main><a href="/api/docs/models/fixture-code">fixture-code For coding tasks</a></main>'
            if url == PRICING:
                return '<main><p>Prices in USD per 1M tokens</p><h2>Standard</h2><table><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Output</th></tr><tr><td>fixture-code</td><td>$2.00</td><td>$0.20</td><td>$6.00</td></tr></table></main>'
            return '<main>General guidance only</main>'
        evidence = OfficialSources(lambda: NOW, fetch=fetch).retrieve()
        self.assertEqual(len(calls), 5)
        self.assertEqual(evidence["rates"][0]["input"], 2)
        self.assertEqual(evidence["guidance"][0]["model_id"], "fixture-code")
        self.assertTrue(all(source["retrieved_at"] == NOW for source in evidence["sources"]))
        self.assertTrue(all(source["checked_at"] is None for source in evidence["sources"] if source["status"] == "incomplete"))

    def test_comparable_local_outcomes_are_separate_and_never_provider_claims(self):
        workload = {"input_tokens": 100, "output_tokens": 50, "retries": 0, "billing_route": "standard-short-context-uncached"}
        outcome = claim("project-evidence://controlled-outcome", model_id="fixture-code", runner="codex", reasoning="high", provider="openai",
                        task="coding", risk="ordinary", workload=workload, verified=True, summary="Controlled accepted outcome; not a cheapest-outcome comparison.")
        context = {**self.context, "workload": workload, "outcomes": [outcome]}
        advice = self.service(context).read()["recommendations"]["implementation"]
        self.assertEqual(advice["local_outcomes"]["source_url"], outcome["source_url"])
        self.assertEqual(advice["guidance"]["source_url"], GUIDANCE)
        self.assertEqual(advice["cost"]["rates"]["source_url"], PRICING)
        context["outcomes"][0]["workload"] = {**workload, "retries": 8}
        self.assertIsNone(self.service(context).read()["recommendations"]["implementation"]["local_outcomes"])

    def test_observed_subscription_usage_and_route_specific_mixed_billing(self):
        observation = claim("host-usage://controlled-observation", usage_or_limit="Synthetic 3 of 10 requests, period unknown.")
        context = {**self.context, "billing": "mixed", "observations": {"codex": observation}}
        advice = self.service(context).read()["recommendations"]["implementation"]
        self.assertEqual(advice["cost"]["observable"], observation)
        self.assertIn("Only the attached usage/limit is observed", advice["cost"]["limitations"])
        self.assertIsNone(advice["cost"]["rates"])
        context["route_billing"] = {"codex": "api"}
        self.assertIsNotNone(self.service(context).read()["recommendations"]["implementation"]["cost"]["rates"])
        context["route_billing"]["fixture-code@codex@high"] = "subscription"
        self.assertIsNone(self.service(context).read()["recommendations"]["implementation"]["cost"]["rates"])
        context["observations"]["codex"]["checked_at"] = "unknown"
        self.assertIsNone(self.service(context).read()["recommendations"]["implementation"]["cost"]["observable"])

    def test_bad_sources_risk_and_owning_gate_fail_closed(self):
        for mutation in ({"source_url": "https://example.test/unofficial"}, {"checked_at": None},
                         {"status": "stale"}, {"risks": ["ordinary"]}):
            with self.subTest(mutation=mutation):
                self.evidence["guidance"][0] = {**claim(GUIDANCE, model_id="fixture-code", provider="openai", tasks=["coding"],
                     risks=["ordinary", "high"], reasoning=["high"], text="Controlled guidance"), **mutation}
                draft = self.service({**self.context, "risk": "high"}).read()
                self.assertIsNone(draft["recommendations"]["implementation"]["choice"])
        self.evidence["guidance"][0]["risks"] = ["ordinary", "high"]
        for gate in ("authority", "permission", "independent"):
            constraints = dict(authority=True, permission=True, independent=True)
            constraints[gate] = False
            advice = self.service({**self.context, "constraints": {"verification": constraints}}).advise("verification")
            self.assertIsNone(advice["recommendation"]["choice"])

    def test_recommended_and_explain_preserve_personal_and_execution_bytes(self):
        with tempfile.TemporaryDirectory() as local:
            path = Path(local) / "preferences.json"
            path.write_text('{"schema_version":1,"presentation":"expert","billing":"subscription"}\n')
            original = path.read_bytes()
            approval = self.project / "approval.json"
            approval.write_text('{"approved":"keep"}\n')
            service = Configuration(self.project, self.discover, lambda: NOW, context=self.context,
                                    preferences_dir=Path(local), recommendation_sources=lambda: deepcopy(self.evidence))
            draft = service.read()
            for reply in ("Explain Plan", "Explain Build", "Explain Verify", "Explain Repair", "Presets", "Recommended"):
                draft = service.reply(draft, reply)
                self.assertFalse(draft["launched"])
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(self.state.read_bytes(), self.original)
                self.assertEqual(approval.read_text(), '{"approved":"keep"}\n')

    def test_public_cli_configure_and_lane_selection_seams(self):
        import subprocess
        import sys
        adapter = self.project / "discovery.py"
        adapter.write_text("import json,sys\nrequest=json.load(sys.stdin)\nprint(json.dumps(dict(request_id=request['request_id'],checked_at=request['started_at'],revision='controlled',authority='host-reported-selection',routes=" + repr(self.routes) + ")))\n")
        fixture = self.project / "evidence.json"
        fixture.write_text(json.dumps(self.evidence))
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")), "--project", str(self.project),
                   "--discovery-command", json.dumps([sys.executable, str(adapter)]), "--now", NOW, "--evidence-fixture", str(fixture)]
        def run(action, request):
            result = subprocess.run(command + [action], input=json.dumps(request), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        draft = run("read", {"context": self.context})
        self.assertIsNotNone(draft["recommendations"]["implementation"]["choice"])
        explained = run("reply", {"proposal": draft, "reply": "Explain Build"})
        self.assertEqual(explained["after"], draft["after"])
        feature = dict(model_id="explicit", runner="codex", reasoning="high")
        context = {**self.context, "constraints": {"implementation": {"authority": True, "permission": True}}}
        advised = run("advise", {"role": "implementation", "feature_choice": feature, "context": context})
        self.assertEqual(advised["effective"]["choice"], feature)
        self.assertIsNotNone(advised["recommendation"]["choice"])
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_every_displayed_cost_needs_currency_units_route_source_and_date(self):
        original = deepcopy(self.evidence["rates"][0])
        for mutation in ({"currency": None}, {"unit": "tokens"}, {"billing_route": None}, {"source_url": GUIDANCE},
                         {"checked_at": "not-a-date"}, {"uncertainty": ""}, {"input": -1}, {"output": float("nan")}):
            with self.subTest(mutation=mutation):
                self.evidence["rates"][0] = {**original, **mutation}
                advice = self.service().read()["recommendations"]["implementation"]
                self.assertTrue(advice["cost"] is None or advice["cost"]["rates"] is None)
                self.assertTrue(advice["cost"] is None or advice["cost"]["estimate"] is None)

    def test_estimates_require_all_assumptions_and_exact_billing_route(self):
        workload = dict(input_tokens=1000, output_tokens=200, retries=1, billing_route="standard-short-context-uncached")
        for key in workload:
            with self.subTest(missing=key):
                incomplete = {name: value for name, value in workload.items() if name != key}
                advice = self.service({**self.context, "workload": incomplete}).read()["recommendations"]["implementation"]
                self.assertIsNone(advice["cost"]["estimate"])
        advice = self.service({**self.context, "workload": {**workload, "billing_route": "batch"}}).read()["recommendations"]["implementation"]
        self.assertIsNone(advice["cost"]["estimate"])

    def test_gate_allowed_models_and_reasoning_are_applied_before_comparison(self):
        for rule in ({"allowed_models": ["other"]}, {"allowed_reasoning": ["medium"]}, {"excluded_models": ["fixture-code"]}):
            with self.subTest(rule=rule):
                context = {**self.context, "constraints": {"implementation": rule}}
                self.assertIsNone(self.service(context).read()["recommendations"]["implementation"]["choice"])
        for rule in ({"permission": "true"}, {"allowed_models": "fixture-code"}):
            self.assertEqual(self.service({**self.context, "constraints": {"implementation": rule}}).read()["state"], "blocked")

    def test_anthropic_rates_require_exact_official_identity_and_table_shape(self):
        def fetch(url):
            if url.endswith("choosing-a-model"):
                return '<p>Claude Fixture 1.0 (claude-fixture-1-0) is built for complex coding and research.</p>'
            if url == "https://platform.claude.com/docs/en/about-claude/pricing":
                return '<p>All prices are in USD.</p><h2>Model pricing</h2><table><tr><th>Name</th><th>Input</th><th>Output</th><th>5m writes</th><th>1h writes</th><th>Hits and refreshes</th></tr><tr><td>Claude Fixture 1.0 For coding</td><td>$3 / MTok</td><td>$8 / MTok</td><td>$4 / MTok</td><td>$6 / MTok</td><td>$1 / MTok</td></tr></table>'
            return '<p>No model-specific records.</p>'
        evidence = OfficialSources(lambda: NOW, fetch=fetch).retrieve()
        self.assertEqual(evidence["rates"][0]["model_id"], "claude-fixture-1-0")
        self.assertEqual(evidence["rates"][0]["input"], 3)
        self.assertEqual(evidence["rates"][0]["source_url"], "https://platform.claude.com/docs/en/about-claude/pricing")
        broken = OfficialSources(lambda: NOW, fetch=lambda url: fetch(url).replace("<th>Input</th>", "<th>Unknown</th>")).retrieve()
        self.assertEqual(broken["rates"], [])

    def test_initial_retrieval_only_and_explicit_task_edits_are_read_only(self):
        calls = []
        def sources():
            calls.append("retrieve")
            return deepcopy(self.evidence)
        service = self.service(sources=sources)
        draft = service.read()
        initial = deepcopy(draft["after"])
        for reply in ("Task analysis", "Risk high", "Explain Plan"):
            draft = service.reply(draft, reply)
            self.assertEqual(draft["after"], initial)
        self.assertEqual(draft["recommendations"]["planning"]["choice"]["model_id"], "fixture-analysis")
        self.assertEqual(calls, ["retrieve"])
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_redirects_cannot_leave_the_official_host(self):
        from model_recommendations import OfficialRedirect
        from urllib.request import Request
        from urllib.error import URLError
        for target in ("https://example.test/page", "http://developers.openai.com/page"):
            with self.assertRaises(URLError):
                OfficialRedirect().redirect_request(Request(GUIDANCE), None, 302, "redirect", {}, target)

    def test_catalogue_descriptions_outside_links_remain_model_specific(self):
        sample = ('<p>Use <a href="/api/docs/models/fixture-code">Fixture Code</a> for complex reasoning and coding. '
                  'Choose <a href="/api/docs/models/fixture-small">Fixture Small</a> for high-volume workloads.</p>'
                  '<p><a href="/api/docs/models/fixture-audio">Fixture Audio</a> Advanced reasoning for audio and voice.</p>')
        evidence = OfficialSources(lambda: NOW, fetch=lambda url: sample if url == GUIDANCE else '<p>Unknown</p>').retrieve()
        self.assertEqual([record["model_id"] for record in evidence["guidance"]], ["fixture-code"])
        self.assertEqual(evidence["guidance"][0]["tasks"], ["coding"])
        self.assertEqual(evidence["guidance"][0]["risks"], ["ordinary", "high"])

    def test_reasoning_controls_and_generic_capabilities_are_not_task_fit(self):
        reasoning = ('<p><a href="/api/docs/models/fixture-policy">Fixture Policy</a> does not support none reasoning effort. '
                     'It supports reasoning.context all_turns for code generation.</p>')
        catalogue = ('<p><a href="/api/docs/models/fixture-realtime">Fixture Realtime</a> Reasoning model with tool use.</p>'
                     '<p><a href="/api/docs/models/fixture-controls">Fixture Controls</a> Supports reasoning effort for API coding options.</p>')
        def fetch(url):
            return reasoning if url.endswith("reasoning") else catalogue if url == GUIDANCE else '<p>Unknown</p>'
        evidence = OfficialSources(lambda: NOW, fetch=fetch).retrieve()
        self.assertEqual(evidence["guidance"], [])
        record = claim("https://developers.openai.com/api/docs/guides/reasoning", model_id="fixture-code", provider="openai",
                       tasks=["coding"], risks=["ordinary"], reasoning=["high"], text="Only a control/capability statement")
        self.evidence["guidance"] = [record]
        self.assertIsNone(self.service().read()["recommendations"]["implementation"]["choice"])

    def test_analysis_requires_explicit_model_task_fit_not_the_word_reasoning(self):
        sample = ('<p>Use <a href="/api/docs/models/fixture-code">Fixture Code</a> for complex reasoning and coding.</p>'
                  '<p>Use <a href="/api/docs/models/fixture-analysis">Fixture Analysis</a> for research and data analysis.</p>')
        evidence = OfficialSources(lambda: NOW, fetch=lambda url: sample if url == GUIDANCE else '<p>Unknown</p>').retrieve()
        records = {record["model_id"]: record for record in evidence["guidance"]}
        self.assertEqual(records["fixture-code"]["tasks"], ["coding"])
        self.assertEqual(records["fixture-analysis"]["tasks"], ["analysis"])

    def assert_unknown_official_advice(self, sample):
        evidence = OfficialSources(lambda: NOW, fetch=lambda url: sample if url == GUIDANCE else '<p>Unknown</p>').retrieve()
        self.assertEqual(evidence["guidance"], [])
        service = self.service(sources=lambda: evidence)
        draft = service.read()
        original = deepcopy(draft["after"])
        for reply in ("Explain Build", "Recommended", "Explain Verify"):
            draft = service.reply(draft, reply)
            for advice in draft["recommendations"].values():
                self.assertIsNone(advice["choice"])
                self.assertIsNone(advice["guidance"])
                self.assertNotIn("supports task fit", advice["rationale"])
            self.assertEqual(draft["after"], original)
            self.assertFalse(draft["launched"])
        self.assertIsNone(draft["explanation"]["recommendation"]["choice"])
        self.assertEqual(self.state.read_bytes(), self.original)
        self.assertEqual(self.calls, ["current-availability"])

    def test_control_paragraph_never_supplies_task_suitability(self):
        self.assert_unknown_official_advice(
            '<p><a href="/api/docs/models/fixture-code">Fixture Code</a> supports reasoning_effort '
            'and reasoning.context all_turns. For coding, use high. For research use the high setting.</p>')

    def test_nonaffirmative_task_statements_remain_unknown(self):
        for description in ("Not intended for coding or research.", "Not ideal for coding.",
                            "If enabled, ideal for coding.", "May be useful for coding.",
                            "Possibly best at research.", "Designed to avoid coding.",
                            "For coding support is unknown.", "Whether it is ideal for coding is unclear.",
                            "Recommended for tasks other than coding.", "Can be useful for coding.",
                            "For coding, support is unsupported.", "For comparison with coding models.",
                            "For coding-adjacent experiments.", "For discussion of research suitability."):
            with self.subTest(description=description):
                self.calls.clear()
                self.assert_unknown_official_advice(
                    '<p><a href="/api/docs/models/fixture-code">Fixture Code</a> ' + description + '</p>')

    def test_model_description_stops_at_paragraph_and_catalogue_section(self):
        samples = (
            '<p><a href="/api/docs/models/fixture-code">Fixture Code</a> General tool use.</p>'
            '<p>For research and coding, choose a specialist.</p>',
            '<section><p><a href="/api/docs/models/fixture-code">Fixture Code</a> General tool use.</p>'
            '</section><section><h2>Research</h2><p>For coding and analysis use specialists.</p></section>',
            '<div><a href="/api/docs/models/fixture-code"><div><div>Fixture Code</div>'
            '<div>General-purpose models with safeguards.</div></div></a></div>'
            '<div class="h-px"></div><div><div id="life-sciences"><div>'
            '<div>Life sciences</div><div>Models for life sciences research</div></div></div></div>',
            '<p>Supports reasoning_effort. <a href="/api/docs/models/fixture-code">Fixture Code</a>'
            ' For coding use high.</p>',
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.calls.clear()
                self.assert_unknown_official_advice(sample)

    def pricing_sample(self, context):
        return ('<p>Prices in USD per 1M tokens</p>' + context +
                '<table><tr><th>Model</th><th>Input</th><th>Cached input</th><th>Output</th></tr>'
                '<tr><td>fixture-code</td><td>$0.75</td><td>$0.05</td><td>$4.50</td></tr></table>')

    def test_nonstandard_tables_cannot_supply_standard_estimates(self):
        for context in ('<h2>Standard</h2><p>Other routes below.</p><h2>Batch</h2>',
                        '<h2>Standard</h2><h3>Priority</h3>', '<h2>Standard</h2><p>Batch</p>',
                        '<h2>Standard</h2><h2>Long context</h2>', '<h2>Pricing</h2>',
                        '<div><h2>Standard</h2></div><div>',
                        '<h2>Standard</h2><div data-content-switcher-pane="true" data-value="batch">'):
            with self.subTest(context=context):
                evidence = OfficialSources(lambda: NOW, fetch=lambda url: self.pricing_sample(context)
                                           if url == PRICING else '<p>Unknown</p>').retrieve()
                self.assertEqual(evidence["rates"], [])
                evidence["guidance"] = deepcopy(self.evidence["guidance"])
                service = self.service({**self.context, "workload": {"input_tokens": 3000, "output_tokens": 1000, "retries": 2,
                                                                   "billing_route": "standard-short-context-uncached"}},
                                       sources=lambda: evidence)
                draft = service.reply(service.read(), "Recommended")
                draft = service.reply(draft, "Explain Build")
                advice = draft["explanation"]["recommendation"]
                self.assertIsNotNone(advice["choice"])
                self.assertIsNone(advice["cost"]["rates"])
                self.assertIsNone(advice["cost"]["estimate"])
                self.assertFalse(draft["launched"])
                self.assertEqual(self.state.read_bytes(), self.original)

    def test_affirmative_sample_and_exact_standard_table_have_public_evidence(self):
        def fetch(url):
            if url == GUIDANCE:
                return '<p>Use <a href="/api/docs/models/fixture-code">Fixture Code</a> for complex coding.</p>'
            if url == PRICING:
                return self.pricing_sample('<h2>Standard</h2>')
            return '<p>Unknown</p>'
        evidence = OfficialSources(lambda: NOW, fetch=fetch).retrieve()
        service = self.service({**self.context, "workload": {"input_tokens": 3000, "output_tokens": 1000, "retries": 2,
                                                           "billing_route": "standard-short-context-uncached"}},
                               sources=lambda: evidence)
        draft = service.read()
        original = deepcopy(draft["after"])
        draft = service.reply(draft, "Recommended")
        draft = service.reply(draft, "Explain Build")
        advice = draft["explanation"]["recommendation"]
        self.assertEqual(advice["choice"]["model_id"], "fixture-code")
        self.assertEqual(advice["guidance"]["source_url"], GUIDANCE)
        self.assertEqual(advice["guidance"]["checked_at"], NOW)
        self.assertEqual(advice["cost"]["rates"]["source_url"], PRICING)
        self.assertEqual(advice["cost"]["rates"]["checked_at"], NOW)
        self.assertEqual(advice["cost"]["rates"]["billing_route"], "standard-short-context-uncached")
        self.assertAlmostEqual(advice["cost"]["estimate"]["amount"], 0.02025)
        self.assertEqual(draft["after"], original)
        self.assertFalse(draft["launched"])
        self.assertEqual(self.state.read_bytes(), self.original)

    def test_official_switcher_shape_binds_short_context_to_its_own_pane(self):
        sample = ('<h2>Flagship models</h2><p>Prices per 1M tokens.</p>'
                  '<button>Standard</button><button>Batch</button><button>Flex</button>'
                  '<div data-content-switcher-pane="true" data-value="batch"><div>Batch</div>'
                  '<table><tr><th></th><th>Short context</th><th>Long context</th></tr>'
                  '<tr><th>Model</th><th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th>'
                  '<th>Input</th><th>Cached input</th><th>Cache writes</th><th>Output</th></tr>'
                  '<tr><td>fixture-code</td><td>$1</td><td>$0.1</td><td>$2</td><td>$3</td>'
                  '<td>$4</td><td>$0.4</td><td>$5</td><td>$6</td></tr></table></div>')
        def retrieve(html):
            return OfficialSources(lambda: NOW, fetch=lambda url: html if url == PRICING else '<p>Unknown</p>').retrieve()
        self.assertEqual(retrieve(sample)["rates"], [])
        standard = sample.replace('data-value="batch"><div>Batch', 'data-value="standard"><div>Standard')
        rates = retrieve(standard)["rates"]
        self.assertEqual([(rate["input"], rate["output"], rate["billing_route"]) for rate in rates],
                         [(1, 3, "standard-short-context-uncached")])
        self.assertEqual(retrieve(standard.replace('Short context', 'Unknown context'))["rates"], [])
        self.assertEqual(retrieve(standard.replace('<table>', '<table><caption>Batch rates</caption>'))["rates"], [])
        for label in ('Batch', 'Long context', 'Unspecified tier'):
            with self.subTest(label=label):
                self.assertEqual(retrieve(standard.replace('<table>', '<h3>' + label + '</h3><table>'))["rates"], [])

    def test_anthropic_nonaffirmative_paragraph_prefix_is_not_task_fit(self):
        for prefix in ('If enabled, ', 'Supports reasoning_effort. ', 'Not recommended: '):
            with self.subTest(prefix=prefix):
                sample = '<p>' + prefix + 'Claude Fixture 1.0 (claude-fixture-1-0) is built for coding.</p>'
                evidence = OfficialSources(lambda: NOW, fetch=lambda url: sample if url.endswith('choosing-a-model')
                                           else '<p>Unknown</p>').retrieve()
                self.assertEqual(evidence["guidance"], [])


if __name__ == "__main__":
    unittest.main()
