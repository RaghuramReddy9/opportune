import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from resume import resume_profile


class ResumeProfileUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.profile_patch = patch.object(
            resume_profile,
            "_PROFILE_PATH",
            Path(self.tmp.name) / "missing-local-profile.md",
        )
        self.profile_patch.start()
        resume_profile._profile = None

    def tearDown(self):
        resume_profile._profile = None
        self.profile_patch.stop()
        self.tmp.cleanup()

    def test_public_template_identity_and_keywords_are_loaded(self):
        profile = resume_profile.load_profile()
        raw = profile["raw_text"]

        self.assertIn("applied ai engineer", raw)
        self.assertIn("generative ai engineer", raw)
        self.assertIn("agentic ai/rag systems", raw)
        self.assertIn("forward deployed ai", raw)
        self.assertNotIn("dell technologies", raw)
        self.assertNotIn("candidate", raw)

        skills = profile["all_skills"]
        for skill in [
            "python",
            "fastapi",
            "databricks",
            "delta lake",
            "rag pipelines",
            "agentic ai",
            "guardrails",
            "logging",
            "ai security",
            "backend ai systems",
        ]:
            self.assertIn(skill, skills)

        keywords = profile["strong_keywords"]
        for keyword in [
            "agentic ai",
            "rag pipelines",
            "llm applications",
            "embeddings",
            "vector search",
            "backend ai systems",
        ]:
            self.assertIn(keyword, keywords)

    def test_public_project_names_are_loaded_for_matching(self):
        profile = resume_profile.load_profile()
        project_names = set(profile["project_names"])

        self.assertIn("ai retrieval inspector — rag evaluation, observability, and reliability platform", project_names)
        self.assertIn("multi-agent support assistant — agentic rag workflow", project_names)

    def test_free_text_resume_extraction_returns_search_profile(self):
        extracted = resume_profile.extract_profile_from_text(
            "AI Engineer building Python RAG systems. Open to remote US roles."
        )

        self.assertIn("ai engineer", extracted["roles"])
        self.assertIn("python", extracted["skills"])
        self.assertIn("rag", extracted["skills"])
        self.assertIn("Remote", extracted["locations"])
        self.assertIn("United States", extracted["locations"])


if __name__ == "__main__":
    unittest.main()
