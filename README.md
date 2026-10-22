# QFRadio-Releases

Official binary releases and self-update manifest for the QF platform (UIS7862 / QF001):
QFRadio, SmartRDS, wDSP Pro and other apps by the same author.

APKs are published as **GitHub Release assets**, never committed to this repository. This repo holds only
the small JSON manifests and the release tool.

## `version.json` — the shared self-update manifest

Each app's installed copy reads `version.json` over plain HTTPS (no token, public repo), finds its **own**
entry by Android package id, and offers an update only when the manifest `version_code` is higher than the
installed one. One manifest serves every app.

```jsonc
{
  "version_code": 73, "version_name": "...", "download_url": "...", "changelog": "...",  // legacy top-level,
  "min_supported_version": 1,                                                            // read by QFRadio
  "wdsp_pro": {
    "package": "com.communityofdevs.wdsp_pro",  // the app matches ITS OWN entry by this
    "version_code": 27,                          // compared to the installed versionCode
    "version_name": "1.2",
    "download_url": ".../releases/download/<tag>/<file>.apk",
    "sha256": "…",                               // the app rejects a download that does not match
    "size": 20253332,
    "changelog": "…"
  },
  "qfradio": { … }, "smartrds": { … }
}
```

**Integrity.** The installing app's real check is the signing certificate: it installs the downloaded APK
only if its signer matches the running app's own signer. `sha256` guards against a corrupt or truncated
download — not a malicious one, since this manifest is public and anyone who could swap the APK could
rewrite the hash too. "Install from unknown sources" is granted by the head-unit owner in the UI.

The legacy top-level block duplicates the `qfradio` entry; the radio's current updater still reads it, so
`tools/release.py` keeps the two in step whenever it writes the `qfradio` entry.

## Cutting a release

```bash
# 1. update the manifest entry from the built, signed APK (computes sha256, size, download URL)
python3 tools/release.py set \
    --app wdsp_pro --package com.communityofdevs.wdsp_pro \
    --apk path/to/wDSP_Pro.apk --version-code 27 --version-name 1.2 \
    --tag wdsp-v1.2 --changelog "..."

# 2. upload the APK as the release asset (the tool prints this; needs your GitHub auth)
gh release create wdsp-v1.2 path/to/wDSP_Pro.apk -R kostyamat/QFRadio-Releases -t "wdsp_pro 1.2" -n "..."

# 3. commit version.json

python3 tools/release.py check   # validate the manifest any time: every entry complete, packages unique
```

`packs.json` is unrelated to app updates — it is the radio-logo pack index (per-country ZIPs, also release
assets).
