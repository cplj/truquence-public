"""Offline regression checks for immutable, unprivileged release inputs."""
from pathlib import Path
import re
import unittest


ROOT = next(p for p in Path(__file__).resolve().parents
            if (p / "pyproject.toml").exists() and (p / "Dockerfile").exists())
CI = ROOT / ".github" / "workflows"


class SupplyChainTests(unittest.TestCase):
    def test_actions_use_full_commit_ids(self):
        workflows = list(CI.glob("*.yml"))
        self.assertTrue(workflows)
        for workflow in workflows:
            self.assertNotIn("ubuntu-latest", workflow.read_text())
        for workflow in workflows:
            for action in re.findall(r"uses:\s*([^\s#]+)", workflow.read_text()):
                self.assertRegex(action, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", str(workflow))

    def test_only_publish_jobs_receive_write_permissions(self):
        for name, scope in (("image.yml", "packages"), ("release.yml", "id-token")):
            source = (CI / name).read_text()
            build, publish = source.split("  publish:\n", 1)
            self.assertNotIn(f"{scope}: write", build)
            self.assertIn("needs: build", publish)
            self.assertIn(f"{scope}: write", publish)
        image = (CI / "image.yml").read_text()
        self.assertIn("push: false", image.split("  publish:\n", 1)[0])
        self.assertNotIn("docker/login-action", image.split("  publish:\n", 1)[0])

    def test_container_pins_base_and_drops_root_and_packaging_tools(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertRegex(dockerfile, r"(?m)^FROM python:3\.12\.15-slim@sha256:[0-9a-f]{64}$")
        self.assertIn("USER 65532:65532", dockerfile)
        for tool in ("pip", "setuptools", "wheel", "ensurepip"):
            self.assertIn(tool, dockerfile)
        self.assertNotIn("pip install", dockerfile)
        self.assertNotIn("COPY . ", dockerfile)

    def test_build_backend_and_explicit_ci_tools_are_pinned(self):
        self.assertIn('requires = ["setuptools==83.0.0"]', (ROOT / "pyproject.toml").read_text())
        for workflow in CI.glob("*.yml"):
            source = workflow.read_text()
            for command in re.findall(r"python -m pip install ([^\n]+)", source):
                if "dist/*.whl" in command or command.endswith(" ."):
                    self.assertIn("--no-deps", command)
                    continue
                for requirement in re.findall(r'"([^"\n]+)"', command):
                    self.assertRegex(requirement, r"^[\w-]+==\d[\w.]*$")
            if "python -m build" in source:
                self.assertIn("python -m build --no-isolation", source)

    def test_container_context_excludes_local_build_artifacts(self):
        source = (ROOT / ".dockerignore").read_text().splitlines()
        for excluded in (".git", "**/__pycache__", "**/*.pyc", "**/*.egg-info", "build", "dist"):
            self.assertIn(excluded, source)


if __name__ == "__main__":
    unittest.main()
