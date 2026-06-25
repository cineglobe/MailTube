from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_automatic_release_waits_for_all_required_checks() -> None:
    workflow = (ROOT / ".github/workflows/auto-release.yml").read_text(encoding="utf-8")

    assert "workflow_run:" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "wait_for_workflow security.yml" in workflow
    assert "wait_for_workflow codeql.yml" in workflow
    assert "gh workflow run release.yml" in workflow


def test_release_supports_automatic_dispatch_and_validates_versions() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "Validate release version and source" in workflow
    assert "tag_name: v${{ steps.release.outputs.version }}" in workflow
    assert "target_commitish: ${{ steps.release.outputs.sha }}" in workflow
    assert '"Dockerfile"' in workflow


def test_runtime_cosign_is_built_with_the_patched_go_toolchain() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM --platform=$BUILDPLATFORM golang:1.26.4-alpine3.23 AS cosign-builder" in dockerfile
    assert "GOOS=$TARGETOS GOARCH=$TARGETARCH" in dockerfile
    assert "github.com/sigstore/cosign/v3/cmd/cosign@v3.0.6" in dockerfile
    assert "FROM gcr.io/projectsigstore/cosign:v3.0.6" not in dockerfile
