"""Read-only official evidence and bounded advice; never a selection authority."""

from copy import deepcopy
from datetime import datetime, timezone
from html.parser import HTMLParser
import math
import hashlib
import re
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


SOURCES = (
    "https://developers.openai.com/api/docs/models",
    "https://developers.openai.com/api/docs/guides/reasoning",
    "https://developers.openai.com/api/docs/pricing",
    "https://platform.claude.com/docs/en/about-claude/models/choosing-a-model",
    "https://platform.claude.com/docs/en/about-claude/pricing",
)
LIMITATIONS = "Provider guidance is not account availability or project verification. No benchmark, savings guarantee or cheapest verified outcome claim. Existing authority, permissions, independence, repair ceilings and feature gates still apply."


def ambiguous_task_text(text):
    return bool(re.search(
        r"reasoning[._ ](?:effort|context)|reasoning_effort|all_turns|current_turn|"
        r"\b(?:not|no|never|without|avoid|excluding|except|unless|if|when|whether|"
        r"may|might|can|cannot|could|would|should|possibly|perhaps|potentially|unknown|unclear|uncertain|unsupported|"
        r"unsuitable|unproven|poor|unverified|ill-suited)\b|"
        r"\bother than\b|n't\b|\?", text, re.I))


def explicit_task_fit(text):
    if ambiguous_task_text(text):
        return []
    tasks = []
    for sentence in re.split(r"\.\s+|\n", text):
        fit = re.fullmatch(
            r"\s*(?:is\s+)?(?:suitable for|well[- ]suited for|recommended for|ideal for|best at|"
            r"(?:designed|built|optimized) (?:for|to)|"
            r"(?:our |the |a )?(?:most )?(?:capable|advanced|flagship|powerful) "
            r"(?:cybersecurity )?model for)\s+(.{1,400})", sentence, re.I)
        if not fit:
            continue
        if not re.fullmatch(
                r"(?:(?:complex|advanced|demanding|long-running|reasoning|data|deep|authorized|"
                r"vulnerability|scientific|life sciences|agentic|and|or|security testing|tasks|"
                r"workloads|work|coding|code generation|software development|programming|"
                r"analysis|research|knowledge work)[,\s]*)+[.!]?", fit[1].strip(), re.I):
            continue
        for task, pattern in (("coding", r"\bcoding\b|code generation|software development|programming"),
                              ("analysis", r"\banalysis\b|\bresearch\b|knowledge work")):
            if task not in tasks and re.search(pattern, fit[1], re.I):
                tasks.append(task)
    return tasks


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if urlparse(newurl).scheme != "https" or urlparse(newurl).hostname != urlparse(request.full_url).hostname:
            raise URLError("Nonofficial redirect blocked")
        return super().redirect_request(request, response, code, message, headers, newurl)


def valid_rate_number(value):
    return type(value) in (int, float) and 0 <= value <= 2 ** 53 - 1 and math.isfinite(value)


def base_pricing_context(text):
    normalized = re.sub(r"[\s\-\u2010-\u2015]+", " ", text).strip().lower()
    return normalized in {"", "model pricing", "standard", "base api pricing", "standard base pricing",
                          "short context", "short context only", "short context rates", "short context pricing"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.text = []
        self.links = []
        self.link = None
        self.following = None
        self.block_text = []
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.elements = []
        self.heading = None
        self.heading_text = ""
        self.heading_end = 0
        self.heading_scope = []
        self.caption = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if self.skip:
            return
        attributes = dict(attrs)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.elements.append((tag, attributes, len(self.text)))
        if re.fullmatch(r"h[1-6]", tag):
            self.heading = []
            self.heading_scope = list(self.elements[:-1])
        if tag == "caption":
            self.caption = []
        if tag in {"p", "div", "section", "article", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table"} and self.link is None:
            self.following = None
            self.block_text = []
        if tag == "a":
            self.following = None
            self.link = [dict(attrs).get("href", ""), [], self.block_text]
        if tag == "table":
            panes = [(attributes.get("data-value"), start) for _, attributes, start in self.elements
                     if attributes.get("data-content-switcher-pane") == "true"]
            tier = panes[-1][0] if panes else self.heading_text.lower()
            context_start = panes[-1][1] if panes else self.heading_end
            if not panes and self.elements[:len(self.heading_scope)] != self.heading_scope:
                tier = "unknown"
            if panes and self.heading_end > context_start and self.heading_text.lower() not in {"standard", "short context"}:
                tier = "unknown"
            self.table = {"prefix": " ".join(self.text)[-2500:], "rows": [],
                          "tier": tier, "tier_context": " ".join(self.text[context_start:]),
                          "caption": ""}
        if tag == "tr" and self.table is not None:
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = []
        if tag in {"p", "div", "tr", "h1", "h2", "h3"}:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        for index in range(len(self.elements) - 1, -1, -1):
            if self.elements[index][0] == tag:
                del self.elements[index:]
                break
        if re.fullmatch(r"h[1-6]", tag) and self.heading is not None:
            self.heading_text = re.sub(r"[^a-zA-Z0-9 ]", "", " ".join(self.heading)).strip()
            self.heading_end = len(self.text)
            self.heading = None
        if tag in {"section", "article", "main"}:
            self.heading_text = ""
        if tag == "caption" and self.caption is not None and self.table is not None:
            self.table["caption"] = " ".join(self.caption)
            self.caption = None
        if tag in {"p", "div", "section", "article", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table"} and self.link is None:
            self.following = None
            self.block_text = []
        if tag == "a" and self.link is not None:
            self.links.append(self.link)
            self.following = self.link
            self.link = None
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join(self.cell).strip())
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.table["rows"].append(self.row)
            self.row = None
        if tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None
        if tag in {"p", "div", "section", "article", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table"}:
            self.text.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)
            self.block_text.append(data)
            if self.heading is not None:
                self.heading.append(data)
            if self.caption is not None:
                self.caption.append(data)
            if self.link is not None:
                self.link[1].append(data)
            elif self.following is not None and sum(len(part) for part in self.following[1]) < 600:
                self.following[1].append(data)
            if self.cell is not None:
                self.cell.append(data)


class OfficialSources:
    def __init__(self, clock=None, fetch=None, previous=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.fetch = fetch or self._fetch
        self.previous = previous or {}

    @staticmethod
    def _fetch(url):
        request = Request(url, headers={"User-Agent": "Playbook-read-only-evidence/1", "Accept": "text/html"})
        with build_opener(OfficialRedirect()).open(request, timeout=20) as response:
            if urlparse(response.url).hostname != urlparse(url).hostname:
                raise ValueError("Nonofficial redirect")
            content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Source exceeds bounded retrieval")
            return content.decode("utf-8")

    def retrieve(self, urls=None, retained_guidance=()):
        evidence = {"guidance": [], "rates": [], "sources": []}
        for url in SOURCES if urls is None else urls:
            try:
                page = Page()
                content = self.fetch(url)
                page.feed(content)
                checked = self.clock()
                source = {"source_url": url, "checked_at": self.previous.get(url, {}).get("checked_at"), "retrieved_at": checked, "status": "incomplete",
                          "uncertainty": "Retrieved official page; only unambiguous model-specific records are usable. Other data remains unknown."}
                if url == SOURCES[1]:
                    source["uncertainty"] = "Reasoning/control guidance retrieved separately. Task suitability is unknown from this source; supported reasoning still requires host evidence."
                if not any(part.strip() for part in page.text):
                    raise ValueError("Empty source")
                source['content_fingerprint'] = hashlib.sha256(content.encode()).hexdigest()
                records = self._rates(page, url, checked, [*retained_guidance, *evidence["guidance"]]) if url.endswith("pricing") else self._guidance(page, url, checked)
                evidence["rates" if url.endswith("pricing") else "guidance"].extend(records)
                if records or url == SOURCES[1]:
                    source["status"] = "retrieved"
                    source["checked_at"] = checked
            except (OSError, ValueError, UnicodeError, TimeoutError):
                prior = self.previous.get(url, {})
                source = {"source_url": url, "checked_at": prior.get("checked_at"),
                          "status": "stale" if prior.get("checked_at") else "incomplete",
                          "uncertainty": "Retrieval failed. No fresh comparison; last successful date retained if known."}
            evidence["sources"].append(source)
        return evidence

    @staticmethod
    def _guidance(page, url, checked):
        records = []
        if url not in {SOURCES[0], SOURCES[3]}:
            return records
        for href, parts, block_parts in page.links:
            text = " ".join(parts)
            match = re.fullmatch(r"/api/docs/models/([a-z0-9.-]+)", href)
            if match is None or ambiguous_task_text(" ".join(block_parts)):
                continue
            subject = r"[-.\s]+".join(re.escape(part) for part in re.split(r"[-.]", match[1]))
            description = re.match(r"\s*" + subject + r"\b\s*[,.:]?\s*(.*)", text, re.I | re.S)
            if description is None:
                continue
            predicate = description[1]
            if re.match(r"\s*Use\s+" + subject + r"\b", " ".join(block_parts), re.I):
                predicate = re.sub(r"^for\s+", "recommended for ", predicate, flags=re.I)
            tasks = explicit_task_fit(predicate)
            if not tasks:
                continue
            if re.search(r"audio|voice|speech|transcrib|image generation|embedding", text, re.I):
                continue
            records.append({"model_id": match[1], "provider": "openai", "tasks": tasks,
                            "risks": ["ordinary"] + (["high"] if re.search(r"complex|advanced|demanding", text, re.I) else []),
                            "text": text, "source_url": url, "checked_at": checked,
                            "uncertainty": "Task-fit inference from provider description, not measured project performance; reasoning support comes from host discovery."})
        if url == SOURCES[3]:
            text = " ".join(page.text)
            for match in re.finditer(r"(Claude [A-Za-z]+ [0-9.]+)\s*\(\s*(claude-[a-z0-9-]+)\s*\)([^\n]{1,600})", text):
                paragraph_start = text.rfind("\n", 0, match.start()) + 1
                if ambiguous_task_text(text[paragraph_start:match.end()]):
                    continue
                description = match.group(0)
                tasks = explicit_task_fit(match[3])
                if tasks:
                    records.append({"model_id": match[2], "label": match[1], "provider": "anthropic", "tasks": tasks,
                                    "risks": ["ordinary"] + (["high"] if re.search(r"complex|advanced|demanding|long-running", description, re.I) else []),
                                    "text": description, "source_url": url, "checked_at": checked,
                                    "uncertainty": "Task-fit inference from exact provider model ID and description; integration compatibility and reasoning must be checked by the host."})
        return records

    @staticmethod
    def _rates(page, url, checked, guidance=()):
        records = []
        if url == SOURCES[4]:
            names = {record["label"]: record["model_id"] for record in guidance
                     if record.get("provider") == "anthropic" and record.get("label") and valid_claim(record, "guidance", now=checked)}
            for table in page.tables:
                if (table["tier"] not in {"model pricing", "standard", "base api pricing"}
                        or not base_pricing_context(table["tier_context"])
                        or not base_pricing_context(table["caption"])
                        or "All prices are in USD" not in table["prefix"]
                        or not any(row == ["Name", "Input", "Output", "5m writes", "1h writes", "Hits and refreshes"] for row in table["rows"])):
                    continue
                for row in table["rows"]:
                    name = next((label for label in names if row and row[0] in {label, label + " For coding"}), None)
                    if not name or len(row) != 6:
                        continue
                    if not all(value == "-" or re.fullmatch(r"\$[0-9]+(?:\.[0-9]+)?\s*/\s*MTok", value)
                               for value in row[3:]):
                        continue
                    prices = [re.fullmatch(r"\$([0-9]+(?:\.[0-9]+)?)\s*/\s*MTok", value) for value in row[1:3]]
                    if not all(prices):
                        continue
                    amounts = [float(price[1]) for price in prices]
                    if not all(valid_rate_number(amount) for amount in amounts):
                        continue
                    records.append({"model_id": names[name], "provider": "anthropic", "currency": "USD", "unit": "1M tokens",
                                    "input": amounts[0], "output": amounts[1],
                                    "billing_route": "standard-base-uncached", "source_url": url, "checked_at": checked,
                                    "uncertainty": "Published API base rates, not subscription billing; excludes caching, tools, regional charges, taxes and negotiated billing."})
                break
            return records
        for table in page.tables:
            prefix = table["prefix"]
            rows = table["rows"]
            context = re.sub(r"[\s\-\u2010-\u2015]+", " ", table["tier_context"] + " " + table["caption"]).strip().lower()
            caption = re.sub(r"[\s\-\u2010-\u2015]+", " ", table["caption"]).strip().lower()
            short_label = r"short context(?: only| rates| pricing)?"
            if (url != SOURCES[2] or not re.search(r"per 1M tokens", prefix) or table["tier"] != "standard"
                    or re.search(r"\b(?:batch|priority|flex|fast|ultrafast|long context|extended context|above|over|exceeding)\b|>", context)
                    or caption and not re.fullmatch(short_label, caption)
                    or not rows):
                continue
            headers = next((row for row in rows if row and row[0] == "Model"), [])
            if headers not in (["Model", "Input", "Cached input", "Output"],
                               ["Model", "Input", "Cached input", "Cache writes", "Output", "Input", "Cached input", "Cache writes", "Output"]):
                continue
            output_index = 3 if len(headers) == 4 else 4
            if len(headers) == 4 and not (re.fullmatch(short_label, caption) or any(
                    re.fullmatch(short_label, re.sub(r"[\s\-\u2010-\u2015]+", " ", line).strip().lower())
                    for line in table["tier_context"].splitlines())):
                continue
            if len(headers) == 9 and ["", "Short context", "Long context"] not in rows:
                continue
            for row in rows:
                if len(row) != len(headers) or not re.fullmatch(r"[a-z0-9.-]+", row[0]):
                    continue
                prices = [row[1], row[output_index]]
                if not all(re.fullmatch(r"\$[0-9]+(?:\.[0-9]+)?", value) for value in prices):
                    continue
                amounts = [float(price[1:]) for price in prices]
                if not all(valid_rate_number(amount) for amount in amounts):
                    continue
                records.append({"model_id": row[0], "provider": "openai", "currency": "USD", "unit": "1M tokens",
                                "input": amounts[0], "output": amounts[1],
                                "billing_route": "standard-short-context-uncached", "source_url": url, "checked_at": checked,
                                "uncertainty": "Published API base rates only; excludes cache writes, tools, long context, regional uplifts, taxes and negotiated billing."})
            break
        return records


def successful_date_status(checked_at, now):
    """Classify the original successful date against the evaluation clock."""
    try:
        checked = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        current = datetime.fromisoformat(now.replace("Z", "+00:00")) if isinstance(now, str) else now
        if checked.tzinfo is None or current.tzinfo is None:
            return "incomplete"
        age = (current - checked).total_seconds()
        if age < 0:
            return "incomplete"
        return "retrieved" if age <= 86400 else "stale"
    except (ValueError, TypeError, AttributeError):
        return "incomplete"


def valid_claim(record, kind, now=None, allow_unusable=False):
    if not isinstance(record, dict) or not isinstance(record.get("uncertainty"), str) or not record["uncertainty"]:
        return False
    url = record.get("source_url")
    allowed = {SOURCES[0], SOURCES[3]} if kind == "guidance" else {SOURCES[2], SOURCES[4]}
    if not isinstance(url, str) or url not in allowed:
        return False
    # Cache assembly retains inadequate records for dated, honest display only.
    if allow_unusable:
        return True
    status = record.get("status")
    # An absent status is the official adapter's successful-claim format.
    # Every explicit status must affirm success; untrusted containers must
    # never reach hash-based membership or become evidence authority.
    if status is not None and (not isinstance(status, str) or status != "retrieved"):
        return False
    return successful_date_status(record.get("checked_at"),
                                  now if now is not None else datetime.now(timezone.utc)) == "retrieved"


def supported_estimate(estimate, rate, requested_workload):
    """Validate a supplied subtotal against its selected rate, without replacing it."""
    if not isinstance(estimate, dict) or not isinstance(rate, dict):
        return False
    workload = estimate.get("assumptions")
    if (not isinstance(workload, dict) or not isinstance(requested_workload, dict)
            or workload != requested_workload
            or estimate.get("status") not in (None, "retrieved")
            or workload.get("billing_route") != rate.get("billing_route")
            or any(type(counts.get(key)) is not int or not 0 <= counts[key] <= 2 ** 53 - 1
                   for counts in (workload, requested_workload)
                   for key in ("input_tokens", "output_tokens", "retries"))
            or any(estimate.get(key) != rate.get(key)
                   for key in ("currency", "source_url", "checked_at"))
            or any(not isinstance(estimate.get(key), str) or not estimate[key]
                   for key in ("label", "uncertainty"))):
        return False
    expected = (workload["input_tokens"] * rate["input"]
                + workload["output_tokens"] * rate["output"]) / 1_000_000 * (1 + workload["retries"])
    amount = estimate.get("amount")
    # Bounded inputs make expected finite. Equality also rejects nonfinite and
    # arbitrarily large caller amounts without converting huge integers to float.
    return type(amount) in (int, float) and math.isfinite(expected) and amount == expected


def project_advice(advice, now, requested_workload=None):
    """Recheck only original selected claims; never retrieve or rank a substitute."""
    result = deepcopy(advice) if isinstance(advice, dict) else {}
    result.setdefault("choice", None)
    result.setdefault("guidance", None)
    result.setdefault("cost", None)
    result.setdefault("limitations", LIMITATIONS)
    retained = result.get("withheld_evidence", {})
    withheld = deepcopy(retained) if isinstance(retained, dict) else {"guidance": retained}
    guidance = result.get("guidance")
    billing = result.get("cost")
    if billing is not None and not isinstance(billing, dict):
        withheld["rates"] = billing
        result["cost"] = {"rates": None, "estimate": None}
    pricing = (result.get("cost") or {}).get("rates")
    if guidance is None and result.get("choice") is not None:
        withheld["guidance"] = {"checked_at": None, "status": "incomplete"}
    if result.get("cost") and pricing is None:
        result["cost"]["estimate"] = None
    for kind, claim in (("guidance", guidance), ("rates", pricing)):
        try:
            usable = (isinstance(claim, dict) and claim.get("status") in (None, "retrieved")
                      and valid_claim(claim, kind, now=now))
            if usable and kind == "rates":
                choice = result.get("choice")
                usable = (isinstance(choice, dict) and billing.get("billing") == "api"
                          and billing.get("route") == choice
                          and all(isinstance(choice.get(key), str) and choice[key]
                                  and claim.get(key) == choice[key] for key in ("model_id", "provider"))
                          and claim.get("currency") == "USD" and claim.get("unit") == "1M tokens"
                          and isinstance(claim.get("billing_route"), str) and bool(claim["billing_route"])
                          and all(valid_rate_number(claim.get(key)) for key in ("input", "output")))
        except (TypeError, ValueError, AttributeError):
            usable = False
        if claim is not None and not usable:
            withheld[kind] = deepcopy(claim)
    if not isinstance(advice, dict):
        withheld["guidance"] = advice
    if "guidance" in withheld:
        # Withholding suitability also hides cost. Retain its independently
        # dated selected claim before dropping the public cost projection.
        if pricing is not None:
            withheld.setdefault("rates", deepcopy(pricing))
        result.update(choice=None, guidance=None, cost=None, local_outcomes=None,
                      rationale="Original task-fit evidence is inadequate; suitability unknown. Retain the saved or edited choice.")
    elif "rates" in withheld and result.get("cost"):
        result["cost"].update(rates=None, estimate=None)
        result["cost"]["limitations"] = "Original pricing evidence is inadequate; rates and token subtotal unknown."
    elif result.get("cost"):
        estimate = result["cost"].get("estimate")
        if estimate is not None and not supported_estimate(estimate, pricing, requested_workload):
            withheld["estimate"] = deepcopy(estimate)
            result["cost"]["estimate"] = None
            result["cost"]["limitations"] = "Original subtotal is unsupported by the selected rate and workload assumptions; token subtotal unknown."
    if withheld:
        for kind, claim in list(withheld.items()):
            if not isinstance(claim, dict):
                claim = {"original": claim, "checked_at": None}
                withheld[kind] = claim
            status = successful_date_status(claim.get("checked_at"), now)
            if status != "retrieved":
                claim["status"] = status
            elif claim.get("status") not in ("stale", "incomplete", "failed"):
                claim["status"] = "incomplete"
        result["withheld_evidence"] = withheld
        result["limitations"] = (LIMITATIONS + " Original successful dates retained in withheld evidence; "
                                 "stale or incomplete claims cannot support advice or costs. "
                                 "Use explicit Refresh or the ordinary role editor to recover.")
    return result


def local_outcome(choice, context):
    workload = context.get("workload")
    if not isinstance(workload, dict) or not workload:
        return None
    for record in context.get("outcomes", []):
        if not isinstance(record, dict):
            continue
        source = record.get("source_url", "")
        if (not isinstance(source, str) or not re.fullmatch(r"project-evidence://[A-Za-z0-9_-]+", source)
                or record.get("verified") is not True or record.get("task") != context.get("task")
                or record.get("risk") != context.get("risk", "ordinary") or record.get("workload") != workload
                or any(record.get(key) != choice.get(key) for key in ("model_id", "runner", "reasoning", "provider"))
                or not record.get("uncertainty") or not isinstance(record.get("summary"), str)):
            continue
        try:
            if datetime.fromisoformat(record["checked_at"].replace("Z", "+00:00")).tzinfo is None:
                continue
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        return {key: deepcopy(record[key]) for key in ("source_url", "checked_at", "uncertainty", "summary", "workload")}
    return None


def cost(choice, context, evidence, now=None):
    now = now if now is not None else datetime.now(timezone.utc)
    route_key = "@".join(choice[key] for key in ("model_id", "runner", "reasoning"))
    billing = context.get("route_billing", {}).get(route_key, context.get("route_billing", {}).get(choice["runner"], context.get("billing", "unknown")))
    result = {"billing": billing, "route": deepcopy(choice), "rates": None, "estimate": None, "observable": None,
              "limitations": "Usage, allowance and verified total outcome cost are unknown. API rates are not subscription bills."}
    if billing != "api":
        observation = context.get("observations", {}).get(route_key, context.get("observations", {}).get(choice["runner"]))
        if isinstance(observation, dict) and all(observation.get(key) for key in ("source_url", "checked_at", "uncertainty", "usage_or_limit")):
            try:
                checked = datetime.fromisoformat(observation["checked_at"].replace("Z", "+00:00"))
                if checked.tzinfo is not None and isinstance(observation["source_url"], str) and urlparse(observation["source_url"]).scheme:
                    result["observable"] = {key: observation[key] for key in ("source_url", "checked_at", "uncertainty", "usage_or_limit")}
                    result["limitations"] = "Only the attached usage/limit is observed. Unobserved consumption, allowance periods and verified outcome costs remain unknown; API rates are not subscription bills."
            except (ValueError, TypeError, AttributeError):
                pass
        return result
    rates = [record for record in evidence.get("rates", []) if valid_claim(record, "rates", now=now)
             and record.get("model_id") == choice["model_id"] and record.get("provider") == choice.get("provider")
             and record.get("currency") == "USD" and record.get("unit") == "1M tokens"
             and isinstance(record.get("billing_route"), str)
             and all(valid_rate_number(record.get(key)) for key in ("input", "output"))]
    workload = context.get("workload", {})
    selected = [record for record in rates if record["billing_route"] == workload.get("billing_route")]
    if len(selected) == 1:
        result["rates"] = deepcopy(selected[0])
    elif len(rates) == 1:
        result["rates"] = deepcopy(rates[0])
    rate = result["rates"]
    if (rate and workload.get("billing_route") == rate["billing_route"]
            and all(type(workload.get(key)) is int and workload[key] >= 0 for key in ("input_tokens", "output_tokens", "retries"))):
        if any(workload[key] > 2 ** 53 - 1 for key in ("input_tokens", "output_tokens", "retries")):
            result["limitations"] += " Workload exceeds numeric bounds (each count must be at most 2^53 - 1); token subtotal unknown."
            return result
        amount = (workload["input_tokens"] * rate["input"] + workload["output_tokens"] * rate["output"]) / 1_000_000 * (1 + workload["retries"])
        if math.isfinite(amount):
            result["estimate"] = {"amount": amount, "currency": rate["currency"], "label": "Assumed API token subtotal, not a bill or verified outcome",
                                  "assumptions": deepcopy(workload), "source_url": rate["source_url"], "checked_at": rate["checked_at"],
                                  "uncertainty": "Every retry assumes the same tokens; excludes all charges outside the published base rate."}
    return result


def recommendations(routes, context, evidence, allowed_runners, lane=False, now=None):
    now = now if now is not None else datetime.now(timezone.utc)
    inferred = context is None or "task" not in context or "risk" not in context
    context = deepcopy(context or {})
    for key in ("constraints", "workload", "route_billing", "observations"):
        if key in context and not isinstance(context[key], dict):
            raise ValueError("Advice context requires structured, local evidence; no defaults changed.")
    if not isinstance(context.get("outcomes", []), list):
        raise ValueError("Project outcomes must be a local list of comparable observations.")
    if any(not isinstance(value, dict) for value in context.get("constraints", {}).values()):
        raise ValueError("Each role constraint must be an owning-gate record.")
    for constraint in context.get("constraints", {}).values():
        if any(key in constraint and type(constraint[key]) is not bool for key in ("authority", "permission", "independent")):
            raise ValueError("Gate checks must be explicit booleans.")
        for key in ("allowed_models", "allowed_reasoning", "excluded_models"):
            if key in constraint and (not isinstance(constraint[key], list) or any(not isinstance(value, str) for value in constraint[key])):
                raise ValueError("Gate exclusions and allowed identities must be lists.")
    goal = context.get("goal", "")
    if "task" not in context:
        if re.search(r"implement|cod(e|ing)|software|test|repair|parser|\bapi\b|application|build|refactor", goal, re.I):
            context["task"] = "coding"
        elif re.search(r"analy[sz]|research|reason|plan|document", goal, re.I):
            context["task"] = "analysis"
    if "risk" not in context:
        context["risk"] = "high" if re.search(r"security|billing|financial|medical|privacy|authentication|permission", goal, re.I) else "ordinary"
    task, risk = context.get("task"), context.get("risk", "ordinary")
    result = {}
    for role, alternatives in routes.items():
        constraints = context.get("constraints", {}).get(role, {})
        required = ["authority", "permission"] + (["independent"] if role == "verification" else [])
        permitted = all(constraints.get(key) is True for key in required) if lane else not any(constraints.get(key) is False for key in required)
        eligible = []
        for choice in alternatives:
            if not permitted or choice["runner"] not in allowed_runners:
                continue
            if (constraints.get("excluded_models") and choice["model_id"] in constraints["excluded_models"]
                    or constraints.get("allowed_models") is not None and choice["model_id"] not in constraints["allowed_models"]
                    or constraints.get("allowed_reasoning") is not None and choice["reasoning"] not in constraints["allowed_reasoning"]):
                continue
            for record in evidence.get("guidance", []):
                if (valid_claim(record, "guidance", now=now) and record.get("model_id") == choice["model_id"]
                        and record.get("provider") == choice.get("provider") and task in record.get("tasks", [])
                        and risk in record.get("risks", []) and record.get("text")
                        and choice["reasoning"] in record.get("reasoning", [choice["reasoning"]])):
                    eligible.append((choice, record))
                    break
        advice = {"role": role, "choice": None, "guidance": None, "cost": None, "local_outcomes": None,
                  "rationale": "No verified suitable route for this task/risk and gate constraints; retain effective preference and choose explicitly.",
                  "limitations": LIMITATIONS, "sources": deepcopy(evidence.get("sources", []))}
        if eligible:
            choice, guidance = eligible[0]
            advice.update(choice=deepcopy(choice), guidance=deepcopy(guidance), cost=cost(choice, context, evidence, now=now), local_outcomes=local_outcome(choice, context),
                          rationale=f"For {context.get('goal', 'the current task')}: {task}, {risk} risk; provider guidance supports task fit. {role} uses host-supported {choice['reasoning']} reasoning on {choice['runner']}. First eligible route in discovery order, not a price or performance ranking. Local comparative outcomes unknown.")
            if advice["local_outcomes"]:
                advice["rationale"] = advice["rationale"].replace("Local comparative outcomes unknown.", "Comparable local observation attached separately; no cross-model cheapest-outcome claim.")
            if inferred:
                advice["limitations"] += " Task/risk inferred from goal, not measured; supply explicit task and risk to correct advice."
        result[role] = advice
    return result
