# Goku-Router v1.5.3 Release Notes

## Highlights

- Updated the Docker release workflow to synchronize both QA and PROD GitOps deployment manifests.
- Made release deployment updates fail fast when an expected GitOps manifest file is missing.
- Simplified the GitOps commit message to describe the shared QA/PROD image update.

## Changed

- `.github/workflows/docker.yml`

## Validation

- GitHub Actions release workflow will build, publish, and sync GitOps manifests from this tag.
