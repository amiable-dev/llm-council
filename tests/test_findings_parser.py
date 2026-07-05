"""ADR-051 C2 (#486): parse structured findings from the chairman JSON.

The chairman's BINARY verdict is already JSON (parse_binary_verdict); C2 adds a
`findings` array to that JSON and parses it. Soft-fail: a missing/malformed
findings block degrades to `fallback` with a reason, never raises.
"""

from llm_council.verification.findings import parse_findings


class TestParseFindings:
    def test_well_formed(self):
        text = '''{"verdict":"rejected","confidence":0.9,"rationale":"r",
          "findings":[
            {"severity":"critical","description":"null deref","location":"a.py:5"},
            {"severity":"minor","description":"nit"}
          ]}'''
        findings, source, reason = parse_findings(text)
        assert source == "structured" and reason is None
        assert len(findings) == 2
        assert findings[0].severity == "critical"
        assert findings[0].location == "a.py:5"
        assert findings[1].severity == "minor" and findings[1].location is None

    def test_findings_in_fenced_json(self):
        text = 'prose\n```json\n{"verdict":"approved","confidence":0.8,"rationale":"r",' \
               '"findings":[{"severity":"major","description":"d"}]}\n```\ntrailing'
        findings, source, _ = parse_findings(text)
        assert source == "structured" and findings[0].severity == "major"

    def test_no_findings_key_is_fallback(self):
        findings, source, reason = parse_findings(
            '{"verdict":"approved","confidence":0.8,"rationale":"r"}')
        assert findings == [] and source == "fallback" and reason == "no_findings_key"

    def test_unparseable_is_fallback(self):
        findings, source, reason = parse_findings("not json at all")
        assert findings == [] and source == "fallback"
        assert reason.startswith("json_parse")

    def test_findings_not_a_list_is_fallback(self):
        findings, source, reason = parse_findings(
            '{"verdict":"approved","confidence":0.8,"rationale":"r","findings":"oops"}')
        assert source == "fallback" and reason == "findings_not_list"

    def test_unknown_severity_coerced_visible_not_dropped(self):
        # A blocker-ish unknown severity must stay visible (mapped to major),
        # never silently dropped — the mechanical gate (C3) can't act on what
        # it can't see.
        text = '{"findings":[{"severity":"blocker","description":"d"}]}'
        findings, source, _ = parse_findings(text)
        assert source == "structured"
        assert findings[0].severity == "major"  # coerced, not dropped

    def test_items_without_description_skipped(self):
        text = '{"findings":[{"severity":"critical"},{"severity":"minor","description":"d"}]}'
        findings, source, _ = parse_findings(text)
        assert len(findings) == 1 and findings[0].description == "d"

    def test_non_dict_items_skipped(self):
        text = '{"findings":["oops",{"severity":"info","description":"d"}]}'
        findings, source, _ = parse_findings(text)
        assert len(findings) == 1

    def test_empty_findings_list_is_structured(self):
        # An explicit empty list means "reviewed, nothing found" — structured.
        findings, source, reason = parse_findings(
            '{"verdict":"approved","confidence":0.9,"rationale":"r","findings":[]}')
        assert findings == [] and source == "structured" and reason is None


class TestBuildResultWiring:
    def _stage3(self, response):
        return {"response": response}

    def test_flag_off_no_findings(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_STRUCTURED_FINDINGS", raising=False)
        from llm_council.verification.verdict_extractor import build_verification_result
        r = build_verification_result([], [], self._stage3(
            '{"verdict":"rejected","confidence":0.9,"rationale":"r",'
            '"findings":[{"severity":"critical","description":"d"}]}'))
        assert r["findings"] == []
        assert r["diagnostics"]["findings_source"] == "fallback"

    def test_flag_on_findings_flow_through(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        from llm_council.verification.verdict_extractor import build_verification_result
        r = build_verification_result([], [], self._stage3(
            '{"verdict":"rejected","confidence":0.9,"rationale":"r",'
            '"findings":[{"severity":"critical","description":"boom","location":"a.py:1"}]}'))
        assert r["diagnostics"]["findings_source"] == "structured"
        assert len(r["findings"]) == 1
        assert r["findings"][0]["severity"] == "critical"

    def test_flag_on_malformed_is_fallback(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_STRUCTURED_FINDINGS", "true")
        from llm_council.verification.verdict_extractor import build_verification_result
        r = build_verification_result([], [], self._stage3("no json here"))
        assert r["diagnostics"]["findings_source"] == "fallback"
        assert "fallback_reason" in r["diagnostics"]


class TestExtractionRobustness:
    def test_braces_inside_string_values(self):
        # A description containing braces must not break brace-matching.
        text = '{"verdict":"rejected","confidence":0.9,"rationale":"r",' \
               '"findings":[{"severity":"critical","description":"use {x} and }{ here"}]}'
        findings, source, _ = parse_findings(text)
        assert source == "structured"
        assert findings[0].description == "use {x} and }{ here"

    def test_escaped_quote_in_string(self):
        text = r'{"findings":[{"severity":"minor","description":"a \"quoted\" bit"}]}'
        findings, source, _ = parse_findings(text)
        assert source == "structured" and '"quoted"' in findings[0].description

    def test_multiple_fenced_blocks_takes_first_object(self):
        text = 'first:\n```json\n{"findings":[{"severity":"info","description":"d"}]}\n```\n' \
               'second:\n```json\n{"other":1}\n```'
        findings, source, _ = parse_findings(text)
        assert source == "structured" and len(findings) == 1
