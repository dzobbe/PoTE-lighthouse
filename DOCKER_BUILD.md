# Docker Build Guide

This guide explains how to build Lighthouse Docker images with optional features, including TEE attestation support.

## Building with TEE Attestation

To build a Docker image with TEE attestation support, pass the `tee-attestation` feature:

```bash
docker build --build-arg FEATURES="tee-attestation" -t lighthouse:tee .
```

Or combine with other features:

```bash
docker build --build-arg FEATURES="gnosis,slasher-lmdb,tee-attestation" -t lighthouse:tee .
```

## How It Works

The Dockerfiles automatically detect when `tee-attestation` is included in the `FEATURES` build argument and install the required TSS2 libraries:

- `pkg-config`
- `libtss2-dev`
- `libtss2-tctildr-dev`
- `libtss2-tcti-dev`
- `libtss2-tcti-device0`

These libraries are only installed when the `tee-attestation` feature is requested, keeping the base image minimal when not needed.

## Examples

### Standard Build (without TEE attestation)

```bash
docker build -t lighthouse:latest .
```

### Build with TEE Attestation

```bash
docker build --build-arg FEATURES="tee-attestation" -t lighthouse:tee .
```

### Reproducible Build with TEE Attestation

```bash
docker build \
  --build-arg FEATURES="gnosis,slasher-lmdb,slasher-mdbx,slasher-redb,jemalloc,tee-attestation" \
  -f Dockerfile.reproducible \
  -t lighthouse:reproducible-tee .
```

## Notes

- TEE attestation features require Linux and TSS2 libraries
- The feature is optional and off by default
- Building without the feature will result in a smaller image
- Runtime TEE hardware/drivers are still required for attestation to work

