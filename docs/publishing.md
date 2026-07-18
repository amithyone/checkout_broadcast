# Publishing Checkout Broadcast

Developers expect one-line installs. This guide covers **PyPI**, **npm**, **Maven (Android)**, and **Swift Package Manager (iOS)**.

## Overview

| Platform | Package name | Install command |
|----------|--------------|-----------------|
| Python (POS) | `checkout-broadcast` | `pip install checkout-broadcast` |
| Python + BLE | same | `pip install "checkout-broadcast[ble]"` |
| Python bank API | same | `pip install "checkout-broadcast[bank]"` |
| Web / Node | `@checkout-broadcast/web` | `npm install @checkout-broadcast/web` |
| Android | `com.checkoutbroadcast:checkout-broadcast` | Gradle dependency (see below) |
| iOS | `CheckoutBroadcast` | Swift Package Manager from Git tag |

---

## Prerequisites (all platforms)

1. **Public GitHub repo** — e.g. `github.com/your-org/checkout-broadcast`
2. **Update URLs** in `pyproject.toml`, `package.json`, and Gradle files to match your repo
3. **Choose a version** — keep in sync: `1.0.0` across Python, npm, Android
4. **Tag releases** — `git tag v1.0.0 && git push origin v1.0.0`

---

## 1. Python — PyPI (`pip install checkout-broadcast`)

### One-time setup

1. Create accounts: [pypi.org](https://pypi.org) and [test.pypi.org](https://test.pypi.org)
2. Enable **2FA** on PyPI
3. Create an **API token** (scope: entire account or project `checkout-broadcast`)
4. Install build tools:

```bash
pip install build twine
```

### Build & publish

From the **project root** (`checkout_broadcast/`):

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info sdk/python/*.egg-info

# Build wheel + sdist
python -m build

# Test on TestPyPI first (recommended)
twine upload --repository testpypi dist/*
pip install -i https://test.pypi.org/simple/ checkout-broadcast

# Production PyPI
twine upload dist/*
```

### Credentials

```bash
# ~/.pypirc or env vars
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-AgEIcHlwaS5vcmcCJ...   # your API token
```

### What users install

```bash
pip install checkout-broadcast
pip install "checkout-broadcast[ble]"    # Windows/Linux POS + BLE
pip install "checkout-broadcast[bank]"   # reference bank API deps
```

CLI after install:

```bash
checkout-broadcast run-bank
checkout-broadcast register-terminal --help
```

### Version bumps

Edit `version` in `pyproject.toml`, update `CHANGELOG.md`, tag `v1.0.1`, rebuild, upload.

---

## 2. npm — Web SDK (`npm install @checkout-broadcast/web`)

### One-time setup

1. npm account: [npmjs.com](https://www.npmjs.com)
2. Login: `npm login`
3. Create org **@checkout-broadcast** on npm (for scoped package), or publish unscoped if name is free

### Build & publish

```bash
cd sdk/typescript
npm install
npm run build          # produces dist/
npm pack --dry-run     # preview files included
npm publish --access public   # required for scoped @checkout-broadcast/*
```

### Test locally before publish

```bash
npm pack
# In another project:
npm install /path/to/checkout-broadcast-web-1.0.0.tgz
```

### What users install

```bash
npm install @checkout-broadcast/web
```

```typescript
import { CheckoutBroadcastAddon } from "@checkout-broadcast/web";
```

### Version bumps

Edit `version` in `sdk/typescript/package.json`, `npm publish`.

---

## 3. Android — Maven Central (`com.checkoutbroadcast:checkout-broadcast`)

Android requires a full Gradle module. Skeleton lives in `sdk/android/`.

### One-time setup

1. [Maven Central (Sonatype)](https://central.sonatype.org/register/) account
2. Prove domain/group ownership for `com.checkoutbroadcast`
3. GPG key for signing artifacts
4. Set secrets in GitHub Actions: `OSSRH_USERNAME`, `OSSRH_PASSWORD`, `SIGNING_KEY`, `SIGNING_PASSWORD`

### Build & publish (local)

```bash
cd sdk/android
./gradlew :checkout-broadcast:assembleRelease
./gradlew :checkout-broadcast:publishToMavenLocal   # test locally
```

### What users add (after publish)

```kotlin
// build.gradle.kts
dependencies {
    implementation("com.checkoutbroadcast:checkout-broadcast:1.0.0")
}
```

```xml
<!-- AndroidManifest.xml -->
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
```

### Until Maven Central is set up

Consumers can use the module as a **local composite build**:

```kotlin
// settings.gradle.kts
includeBuild("path/to/checkout-broadcast/sdk/android")
```

---

## 4. iOS — Swift Package Manager (no Maven)

iOS uses **SPM from Git**, not Maven.

### Publish

1. Tag release on GitHub: `v1.0.0`
2. Users add in Xcode → **File → Add Package Dependencies**:

```
https://github.com/your-org/checkout-broadcast
```

Package path: `sdk/ios/CheckoutBroadcast`

Or in `Package.swift`:

```swift
.package(url: "https://github.com/your-org/checkout-broadcast.git", from: "1.0.0")
```

---

## 5. Automated releases (GitHub Actions)

See [`.github/workflows/release.yml`](../.github/workflows/release.yml).

On push tag `v*`:

- Runs tests
- Builds Python wheel → uploads to PyPI (needs `PYPI_API_TOKEN` secret)
- Builds npm package → publishes (needs `NPM_TOKEN` secret)

Android Maven publish is manual until Sonatype credentials are configured.

### Required GitHub secrets

| Secret | Used for |
|--------|----------|
| `PYPI_API_TOKEN` | Python PyPI upload |
| `NPM_TOKEN` | npm publish |
| `OSSRH_USERNAME` | Maven Central (optional) |
| `OSSRH_PASSWORD` | Maven Central (optional) |

---

## 6. Checklist before first public release

- [ ] Repo is public on GitHub
- [ ] `LICENSE`, `README.md`, `SECURITY.md` in root
- [ ] No secrets in git (`.env`, `data/*.db` gitignored)
- [ ] Version synced: `pyproject.toml`, `package.json`, Android `build.gradle.kts`
- [ ] TestPyPI + local `npm pack` smoke test passed
- [ ] CHANGELOG updated for `1.0.0`
- [ ] Git tag `v1.0.0` created
- [ ] PyPI project name `checkout-broadcast` available (check pypi.org)

---

## 7. Name availability

Check before publishing:

- PyPI: https://pypi.org/project/checkout-broadcast/
- npm: https://www.npmjs.com/package/@checkout-broadcast/web
- Maven: `com.checkoutbroadcast` group ID registration via Sonatype

If `checkout-broadcast` is taken on PyPI, alternatives: `checkout-broadcast-ng`, `naija-checkout-broadcast`.

---

## Quick reference

```bash
# Full release prep (maintainer)
cd checkout_broadcast
pytest tests/ -v
python -m build
cd sdk/typescript && npm run build && npm publish --access public
git tag v1.0.0 && git push origin v1.0.0
twine upload dist/*
```
