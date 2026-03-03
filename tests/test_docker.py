"""
Tests for the Dockerized deployment configuration.

No Docker daemon required. These tests validate:
- Dockerfile structure and required directives
- docker-compose.yml service definitions
- .dockerignore exclusions
- Python entry point: the FastAPI app is importable and healthy
- All production runtime dependencies are importable
"""

import importlib
import os
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

# Project root is two levels up from this test file
_PROJECT_ROOT = Path(__file__).parent.parent


def _read(filename: str) -> str:
    return (_PROJECT_ROOT / filename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# TestDockerfile
# ---------------------------------------------------------------------------

class TestDockerfile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.content = _read("Dockerfile")
        cls.lines = cls.content.splitlines()
        cls.from_lines = [ln.strip() for ln in cls.lines if ln.strip().upper().startswith("FROM")]

    def test_dockerfile_exists(self):
        """Dockerfile exists at project root."""
        self.assertTrue((_PROJECT_ROOT / "Dockerfile").exists())

    def test_dockerfile_uses_python_base(self):
        """Dockerfile uses a Python base image."""
        self.assertTrue(
            any("python:" in ln.lower() for ln in self.from_lines),
            "No Python base image found in Dockerfile",
        )

    def test_dockerfile_is_multistage(self):
        """Dockerfile uses a multi-stage build (multiple FROM directives)."""
        self.assertGreaterEqual(
            len(self.from_lines), 2,
            "Expected at least 2 FROM lines for a multi-stage build",
        )

    def test_dockerfile_has_builder_stage(self):
        """Dockerfile defines a 'builder' stage."""
        self.assertTrue(
            any("builder" in ln.lower() for ln in self.from_lines),
            "No 'builder' stage found",
        )

    def test_dockerfile_has_runtime_stage(self):
        """Dockerfile defines a 'runtime' stage."""
        self.assertTrue(
            any("runtime" in ln.lower() for ln in self.from_lines),
            "No 'runtime' stage found",
        )

    def test_dockerfile_sets_workdir(self):
        """Dockerfile sets a WORKDIR."""
        self.assertIn("WORKDIR", self.content)

    def test_dockerfile_exposes_port_8000(self):
        """Dockerfile exposes port 8000."""
        self.assertIn("EXPOSE 8000", self.content)

    def test_dockerfile_has_cmd(self):
        """Dockerfile has a CMD directive."""
        self.assertIn("CMD", self.content)

    def test_dockerfile_cmd_uses_uvicorn(self):
        """CMD directive starts the uvicorn server."""
        self.assertIn("uvicorn", self.content)

    def test_dockerfile_cmd_binds_all_interfaces(self):
        """CMD binds to 0.0.0.0 so the container is reachable externally."""
        self.assertIn("0.0.0.0", self.content)

    def test_dockerfile_has_healthcheck(self):
        """Dockerfile defines a HEALTHCHECK directive."""
        self.assertIn("HEALTHCHECK", self.content)

    def test_dockerfile_healthcheck_polls_health_endpoint(self):
        """HEALTHCHECK polls the /health endpoint."""
        self.assertIn("/health", self.content)

    def test_dockerfile_creates_nonroot_user(self):
        """Dockerfile creates a non-root user."""
        self.assertTrue(
            "adduser" in self.content or "useradd" in self.content,
            "No user creation directive found in Dockerfile",
        )

    def test_dockerfile_copies_pyproject(self):
        """Dockerfile copies pyproject.toml for dependency installation."""
        self.assertIn("pyproject.toml", self.content)

    def test_dockerfile_installs_with_pip(self):
        """Dockerfile installs dependencies with pip."""
        self.assertIn("pip install", self.content)


# ---------------------------------------------------------------------------
# TestDockerCompose
# ---------------------------------------------------------------------------

class TestDockerCompose(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.content = _read("docker-compose.yml")

    def test_docker_compose_exists(self):
        """docker-compose.yml exists at project root."""
        self.assertTrue((_PROJECT_ROOT / "docker-compose.yml").exists())

    def test_docker_compose_defines_services(self):
        """docker-compose.yml has a 'services' section."""
        self.assertIn("services:", self.content)

    def test_docker_compose_has_spatial_api_service(self):
        """docker-compose.yml defines the 'spatial-api' service."""
        self.assertIn("spatial-api", self.content)

    def test_docker_compose_maps_port_8000(self):
        """docker-compose.yml maps container port 8000 to the host."""
        self.assertIn("8000:8000", self.content)

    def test_docker_compose_has_healthcheck(self):
        """docker-compose.yml includes a healthcheck for the service."""
        self.assertIn("healthcheck", self.content)

    def test_docker_compose_mounts_output_volume(self):
        """docker-compose.yml mounts an output volume."""
        self.assertIn("output", self.content)

    def test_docker_compose_sets_restart_policy(self):
        """docker-compose.yml has a restart policy."""
        self.assertIn("restart", self.content)

    def test_docker_compose_references_dockerfile(self):
        """docker-compose.yml references the Dockerfile for building."""
        self.assertIn("Dockerfile", self.content)

    def test_docker_compose_sets_pythonunbuffered(self):
        """docker-compose.yml sets PYTHONUNBUFFERED for real-time log output."""
        self.assertIn("PYTHONUNBUFFERED", self.content)


# ---------------------------------------------------------------------------
# TestDockerignore
# ---------------------------------------------------------------------------

class TestDockerignore(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.content = _read(".dockerignore")

    def test_dockerignore_exists(self):
        """.dockerignore exists at project root."""
        self.assertTrue((_PROJECT_ROOT / ".dockerignore").exists())

    def test_dockerignore_excludes_venv(self):
        """.dockerignore excludes the venv/ directory."""
        self.assertIn("venv/", self.content)

    def test_dockerignore_excludes_tests(self):
        """.dockerignore excludes the tests/ directory."""
        self.assertIn("tests/", self.content)

    def test_dockerignore_excludes_pyc(self):
        """.dockerignore excludes compiled Python bytecode."""
        self.assertIn("*.pyc", self.content)

    def test_dockerignore_excludes_git(self):
        """.dockerignore excludes the .git directory."""
        self.assertIn(".git", self.content)

    def test_dockerignore_excludes_pytest_cache(self):
        """.dockerignore excludes pytest cache."""
        self.assertIn(".pytest_cache", self.content)

    def test_dockerignore_excludes_output_dir(self):
        """.dockerignore excludes the output/ directory (bind-mounted at runtime)."""
        self.assertIn("output/", self.content)


# ---------------------------------------------------------------------------
# TestProductionEntryPoint
# ---------------------------------------------------------------------------

class TestProductionEntryPoint(unittest.TestCase):
    """
    Verify the production entry point without a running container.
    These tests exercise the same import and HTTP path that uvicorn would use.
    """

    def test_spatial_api_app_importable(self):
        """gis_bootcamp.spatial_api.app is importable."""
        from gis_bootcamp.spatial_api import app
        self.assertIsNotNone(app)

    def test_health_endpoint_returns_ok(self):
        """GET /health returns 200 and {status: ok}."""
        from gis_bootcamp.spatial_api import app
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_uvicorn_importable(self):
        """uvicorn is installed (required by the Dockerfile CMD)."""
        import uvicorn
        self.assertIsNotNone(uvicorn)

    def test_fastapi_importable(self):
        """fastapi is importable (core web framework)."""
        import fastapi
        self.assertIsNotNone(fastapi)

    def test_geopandas_importable(self):
        """geopandas is importable (primary vector GIS library)."""
        import geopandas
        self.assertIsNotNone(geopandas)

    def test_rasterio_importable(self):
        """rasterio is importable (primary raster GIS library)."""
        import rasterio
        self.assertIsNotNone(rasterio)

    def test_shapely_importable(self):
        """shapely is importable (geometry operations)."""
        import shapely
        self.assertIsNotNone(shapely)

    def test_pyproj_importable(self):
        """pyproj is importable (CRS transformations)."""
        import pyproj
        self.assertIsNotNone(pyproj)

    def test_scipy_importable(self):
        """scipy is importable (KDE density analysis)."""
        import scipy
        self.assertIsNotNone(scipy)

    def test_sqlalchemy_importable(self):
        """sqlalchemy is importable (PostGIS client)."""
        import sqlalchemy
        self.assertIsNotNone(sqlalchemy)

    def test_all_gis_bootcamp_modules_importable(self):
        """All gis_bootcamp modules are importable (no missing deps)."""
        modules = [
            "gis_bootcamp.spatial_api",
            "gis_bootcamp.postgis_client",
            "gis_bootcamp.spatial_qa",
            "gis_bootcamp.gis_linter",
            "gis_bootcamp.density_analysis",
            "gis_bootcamp.map_renderer",
            "gis_bootcamp.enrichment_pipeline",
            "gis_bootcamp.batch_geocoder",
            "gis_bootcamp.nearest_feature_lookup",
        ]
        for mod in modules:
            with self.subTest(module=mod):
                m = importlib.import_module(mod)
                self.assertIsNotNone(m)


if __name__ == "__main__":
    unittest.main()
