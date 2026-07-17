import unittest
from core.skill_extractor import extract_skills

class TestSkillExtractor(unittest.TestCase):
    def test_basic_extraction(self):
        text = "We are looking for a Python engineer with experience in PyTorch, AWS Lambda, and React.js."
        skills = extract_skills(text)
        self.assertIn("Python", skills)
        self.assertIn("PyTorch", skills)
        self.assertIn("AWS", skills)
        self.assertIn("React", skills)  # React.js should map to React
        self.assertNotIn("Lambda", skills)  # Lambda is not in our taxonomy (unless we add it)
        # Ensure no duplicates
        self.assertEqual(len(skills), len(set(skills)))

    def test_composite_without_space(self):
        text = "Experience with ReactJS and NodeJS required."
        skills = extract_skills(text)
        self.assertIn("React", skills)
        self.assertIn("Node.js", skills)  # Our taxonomy has Node.js

    def test_empty_and_unknown(self):
        self.assertEqual(extract_skills(""), [])
        self.assertEqual(extract_skills("No relevant skills here."), [])

    def test_case_insensitive(self):
        text = "python pytorch aws"
        skills = extract_skills(text)
        self.assertIn("Python", skills)
        self.assertIn("PyTorch", skills)
        self.assertIn("AWS", skills)

    def test_new_resume_skill_terms(self):
        text = (
            "We need Azure OpenAI, LangSmith, RAGAS, ChromaDB, BM25, reranking, "
            "Databricks, Snowflake, Delta Lake, dbt, Airflow, microservices, and Kubernetes."
        )
        skills = extract_skills(text)
        for expected in [
            "Azure OpenAI",
            "LangSmith",
            "RAGAS",
            "ChromaDB",
            "BM25",
            "Reranking",
            "Databricks",
            "Snowflake",
            "Delta Lake",
            "dbt",
            "Airflow",
            "Microservices",
            "Kubernetes",
        ]:
            self.assertIn(expected, skills)

if __name__ == "__main__":
    unittest.main()