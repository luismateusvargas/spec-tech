# Validation toolchains

The three Dockerfiles pin the official multi-platform base images by digest. Build the images before configuring a profile; the validator uses `--pull=never` and has no network during checks.

```sh
docker build -f toolchains/python.Dockerfile -t spec-tech/python:3.12.12-r1 .
docker build -f toolchains/rust.Dockerfile -t spec-tech/rust:1.91.1-r1 .
docker build -f toolchains/go.Dockerfile -t spec-tech/go:1.26-r1 .
```

Resolve a built image to its immutable local ID with `docker image inspect --format '{{.Id}}' spec-tech/python:3.12.12-r1` (or the Rust/Go tag), then put that ID in the profile `image`. Python includes Ruff, strict mypy, and pytest. Rust includes Cargo and Clippy. Go includes its standard compiler, vet, and test tools. Projects with third-party dependencies must vendor them or provide a project-specific image with those dependencies already installed; validation has no network.
