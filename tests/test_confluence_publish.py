"""Unit tests for scripts/confluence-publish.py (no network access)."""

import importlib.util
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "confluence_publish", REPO_ROOT / "scripts" / "confluence-publish.py"
)
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)


class TestExtractTitle:
    def test_h1_on_first_line(self):
        assert cp.extract_title("# Reporting\n\nBody.") == "Reporting"

    def test_h1_with_inline_code_and_dash(self):
        assert cp.extract_title("# nx — the nexora dev CLI\n") == "nx — the nexora dev CLI"

    def test_missing_h1_raises(self):
        with pytest.raises(ValueError, match="no H1"):
            cp.extract_title("body without heading\n")


class TestStaging:
    def test_stage_docs_layout(self, tmp_path):
        staged = cp.stage_docs(REPO_ROOT, tmp_path)
        rel = sorted(str(s.staged.relative_to(tmp_path)).replace("\\", "/") for s in staged)
        # root files keep their names; dirs map to howto/ + design/; indexes generated
        assert "README.md" in rel
        assert "CONTRIBUTING.md" in rel
        assert "CHANGELOG.md" in rel
        assert "howto/index.md" in rel
        assert "design/index.md" in rel
        assert "howto/ngrok.md" in rel
        assert "design/reporting-ai-assistant.md" in rel
        # nothing outside the publish set leaks in
        assert not any(r.startswith("superpowers") for r in rel)

    def test_staged_copies_are_byte_exact(self, tmp_path):
        cp.stage_docs(REPO_ROOT, tmp_path)
        src = (REPO_ROOT / "CHANGELOG.md").read_bytes()
        assert (tmp_path / "CHANGELOG.md").read_bytes() == src

    def test_stage_wipes_previous_content(self, tmp_path):
        leftover = tmp_path / "howto" / "deleted-doc.md"
        leftover.parent.mkdir(parents=True)
        leftover.write_text("# Old\n")
        cp.stage_docs(REPO_ROOT, tmp_path)
        assert not leftover.exists()


class TestIndexGeneration:
    def test_index_lists_titles_sorted_with_links(self):
        entries = [("Zeta guide", "zeta.md"), ("Alpha guide", "alpha.md")]
        text = cp.generate_index("How-to guides", entries)
        assert text.startswith("# How-to guides\n")
        alpha = text.index("[Alpha guide](alpha.md)")
        zeta = text.index("[Zeta guide](zeta.md)")
        assert alpha < zeta


class TestPreflight:
    def test_duplicate_titles_rejected(self, tmp_path):
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("# Same Title\n")
        b.write_text("# Same Title\n")
        staged = [
            cp.StagedFile(source=a, staged=a, title="Same Title"),
            cp.StagedFile(source=b, staged=b, title="Same Title"),
        ]
        with pytest.raises(SystemExit):
            cp.preflight_titles(staged)

    def test_real_corpus_titles_unique(self, tmp_path):
        staged = cp.stage_docs(REPO_ROOT, tmp_path)
        cp.preflight_titles(staged)  # must not raise


def _converted(stage: Path, staged_rel: str) -> str:
    """Return the locally-converted XML for one staged file."""
    out = stage / staged_rel
    candidates = [out.with_suffix(".csf"), out.with_suffix(".xml")]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    raise AssertionError(f"no converted output for {staged_rel}: tried {candidates}")


@pytest.fixture(scope="session")
def converted_corpus(tmp_path_factory):
    stage = tmp_path_factory.mktemp("stage")
    cp.stage_docs(REPO_ROOT, stage)
    cp.convert_local(stage)
    return stage


class TestConversionGoldenInvariants:
    def test_whole_corpus_converts(self, converted_corpus):
        # convert_local raises SystemExit(1) on any failure; reaching here is the assertion
        assert converted_corpus.exists()

    def test_changelog_angle_brackets_escaped(self, converted_corpus):
        xml = _converted(converted_corpus, "CHANGELOG.md")
        # raw HTML tag names that appear as inline code in CHANGELOG must not
        # survive as live tags in storage XML
        assert "<thead>" not in xml
        assert "&lt;thead&gt;" in xml or "thead" in xml  # escaped or inside CDATA

    def test_changelog_mojibake_survives(self, converted_corpus):
        src = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        marker = "Generali â€"
        if marker in src:  # the intentional mojibake literal documenting the 0011 bug
            xml = _converted(converted_corpus, "CHANGELOG.md")
            assert marker in xml

    def test_nx_table_escaped_pipes(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/nx.md")
        # the '`int` \| `staging`' cell must render both words, not truncate at the pipe
        assert "int" in xml and "staging" in xml
        assert "<table" in xml

    def test_iis_ordered_list_survives_embedded_fence(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/iis.md")
        assert "<ol" in xml  # numbering not flattened by the in-list code fence

    def test_code_macro_emitted_for_powershell(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/ngrok.md")
        assert 'ac:name="code"' in xml

    def test_unicode_preserved(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/babel.md")
        assert "→" in xml  # arrows in headings must not be mangled


class TestEnvFile:
    def test_parses_quoted_and_bare_values(self, tmp_path):
        f = tmp_path / "CONFLUENCE.env"
        f.write_text(
            "# comment\n"
            'CONFLUENCE_DOMAIN="sydocteam.atlassian.net"\n'
            "CONFLUENCE_USER_NAME=bot@sydoc.ch\n"
            'CONFLUENCE_API_KEY="s3cret"\n'
            'CONFLUENCE_SPACE_KEY="nexora"\n'
            "\n",
            encoding="utf-8",
        )
        env = cp.load_env_file(f)
        assert env["CONFLUENCE_DOMAIN"] == "sydocteam.atlassian.net"
        assert env["CONFLUENCE_USER_NAME"] == "bot@sydoc.ch"

    def test_missing_required_key_exits_2(self, tmp_path):
        f = tmp_path / "CONFLUENCE.env"
        f.write_text('CONFLUENCE_DOMAIN="x"\n', encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            cp.load_env_file(f)
        assert e.value.code == 2

    def test_missing_file_exits_2(self, tmp_path):
        with pytest.raises(SystemExit) as e:
            cp.load_env_file(tmp_path / "nope.env")
        assert e.value.code == 2


def _resp(status=200, json_data=None, headers=None):
    r = mock.Mock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = json_data or {}
    r.raise_for_status.side_effect = None
    return r


def _client():
    return cp.ConfluenceClient("sydocteam.atlassian.net", "bot@sydoc.ch", "token")


class TestClientRetry:
    def test_retries_on_429_with_retry_after(self):
        c = _client()
        ok = _resp(200, {"ok": True})
        with (
            mock.patch.object(
                c.session, "request", side_effect=[_resp(429, headers={"Retry-After": "0"}), ok]
            ) as req,
            mock.patch.object(cp.time, "sleep") as slept,
        ):
            out = c.request("GET", "/wiki/api/v2/spaces")
        assert out is ok
        assert req.call_count == 2
        slept.assert_called_once()

    def test_retries_on_500(self):
        c = _client()
        ok = _resp(200)
        with (
            mock.patch.object(c.session, "request", side_effect=[_resp(500), ok]),
            mock.patch.object(cp.time, "sleep"),
        ):
            assert c.request("GET", "/x") is ok

    def test_401_exits_2_with_rotation_hint(self, capsys):
        c = _client()
        with (
            mock.patch.object(c.session, "request", return_value=_resp(401)),
            pytest.raises(SystemExit) as e,
        ):
            c.request("GET", "/x")
        assert e.value.code == 2
        assert "token" in capsys.readouterr().err.lower()

    def test_gives_up_after_max_attempts(self):
        c = _client()
        with (
            mock.patch.object(c.session, "request", return_value=_resp(429, headers={})),
            mock.patch.object(cp.time, "sleep"),
            pytest.raises(RuntimeError, match="attempts"),
        ):
            c.request("GET", "/x", max_attempts=3)


class TestReconcileArithmetic:
    HOMEPAGE = "323944774"

    def test_orphans_strays_and_homepage_exclusion(self):
        current = [
            {"id": "323944774", "title": "nexora"},  # homepage - never touched
            {"id": "1", "title": "Reporting"},  # published this run
            {"id": "2", "title": "Old synced doc"},  # owned, no longer published -> orphan
            {"id": "3", "title": "Random human page"},  # not owned -> stray
        ]
        owned = {"1", "2"}
        published_titles = {"Reporting"}
        orphans, strays = cp.compute_reconcile(current, owned, published_titles, self.HOMEPAGE)
        assert [p["id"] for p in orphans] == ["2"]
        assert [p["id"] for p in strays] == ["3"]

    def test_nothing_to_do(self):
        current = [{"id": "1", "title": "Reporting"}]
        orphans, strays = cp.compute_reconcile(current, {"1"}, {"Reporting"}, self.HOMEPAGE)
        assert orphans == [] and strays == []


class TestArchiveBatching:
    def test_batches_of_100_and_longtask_poll(self):
        c = _client()
        post = _resp(202, {"id": "task-1"})
        done = _resp(200, {"finished": True})
        with mock.patch.object(
            c, "request", side_effect=[post, done, post, done, post, done]
        ) as req:
            c.archive_pages([str(i) for i in range(250)])
        posts = [k for k in req.call_args_list if k.args[0] == "POST"]
        assert len(posts) == 3
        sizes = [len(k.kwargs["json"]["pages"]) for k in posts]
        assert sizes == [100, 100, 50]


class TestSpaceLookup:
    def test_returns_space_and_homepage_id(self):
        c = _client()
        payload = {"results": [{"id": "111", "homepageId": "323944774", "key": "nexora"}]}
        with mock.patch.object(c, "request", return_value=_resp(200, payload)):
            space_id, homepage_id = c.get_space("nexora")
        assert (space_id, homepage_id) == ("111", "323944774")

    def test_missing_space_exits_2(self):
        c = _client()
        with (
            mock.patch.object(c, "request", return_value=_resp(200, {"results": []})),
            pytest.raises(SystemExit) as e,
        ):
            c.get_space("nexora")
        assert e.value.code == 2


class TestMainDryRunWithoutCreds:
    def test_dry_run_local_only_when_no_env_file(self, tmp_path, capsys):
        rc = cp.main(
            [
                "--dry-run",
                "--env-file",
                str(tmp_path / "absent.env"),
                "--stage-dir",
                str(tmp_path / "stage"),
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "no credentials" in out.lower()
        # staged + converted, but never tried to reach Confluence
        assert (tmp_path / "stage" / "README.md").exists()


class TestArgParsing:
    def test_bootstrap_implies_confirmation_unless_yes(self):
        args = cp.parse_args(["--bootstrap"])
        assert args.bootstrap and not args.yes
        args = cp.parse_args(["--bootstrap", "--yes"])
        assert args.yes
