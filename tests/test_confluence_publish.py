"""Unit tests for scripts/confluence-publish.py (no network access)."""

import importlib.util
from pathlib import Path

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
