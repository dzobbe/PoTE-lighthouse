# Docker Build Guide

This guide explains how to build Lighthouse Docker images with optional features.

## TEE Attestation Support

TEE attestation support is **always enabled** in Lighthouse builds. The Dockerfiles automatically install the required TSS2 libraries:

- `pkg-config`
- `libtss2-dev` (includes all TSS2 development headers and runtime dependencies)

## Examples

### Standard Build

```bash
docker build -t lighthouse:latest .
```

This build includes TEE attestation support by default.

### Build with Additional Features

```bash
docker build --build-arg FEATURES="gnosis,slasher-lmdb" -t lighthouse:custom .
```

### Reproducible Build

```bash
docker build \
  --build-arg FEATURES="gnosis,slasher-lmdb,slasher-mdbx,slasher-redb,jemalloc" \
  -f Dockerfile.reproducible \
  -t lighthouse:reproducible .
```

## Notes

- TEE attestation features require Linux and TSS2 libraries
- TEE attestation is always enabled (no feature flag needed)
- Runtime TEE hardware/drivers are still required for attestation to work

