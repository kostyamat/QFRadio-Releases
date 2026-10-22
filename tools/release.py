#!/usr/bin/env python3
"""
QFRadio-Releases — release helper for the shared self-update manifest.

One public repo serves updates for several apps (QFRadio, SmartRDS, wDSP Pro, …). Each app's installed
copy reads version.json over plain HTTPS (no token), finds its OWN entry by Android package id, and
updates itself only when the manifest's version_code is higher than its own. The APK is distributed as a
GitHub Release ASSET, never committed to this repo.

version.json layout (this tool only ever touches the per-app objects, never your app's bytes):

    {
      "version_code": 73, "version_name": "...", "download_url": "...", "changelog": "...",   # legacy
      "min_supported_version": 1,                                                             # top-level
      "<app-key>": {                 # e.g. "qfradio", "smartrds", "wdsp_pro"
        "package": "com.example.app",       # Android applicationId — the app matches ITS OWN entry by this
        "version_code": 73,                 # compared to the installed versionCode; higher = update offered
        "version_name": "1.1",
        "download_url": "https://github.com/kostyamat/QFRadio-Releases/releases/download/<tag>/<file.apk>",
        "sha256": "…",                      # of the APK; the app rejects a download that does not match
        "size": 20253332,
        "changelog": "…"
      }
    }

The app's own safety check is the signing certificate: it installs the downloaded APK only if its signer
matches the running app's signer. sha256 here guards against a corrupt or truncated download, not a
malicious one — this manifest is public and an attacker who could swap the APK could rewrite the hash too.

Usage:
    release.py set  --app wdsp_pro --package com.communityofdevs.wdsp_pro --apk out.apk \\
                    --version-code 27 --version-name "1.2" --tag wdsp-v1.2 [--changelog "..."]
    release.py check          # validate version.json: JSON well-formed, every app entry complete

`set` rewrites version.json and prints the `gh` commands to create the release and upload the APK; it does
NOT upload anything itself (that needs your GitHub auth). When --app is qfradio it also refreshes the
legacy top-level block, which the radio's current updater still reads.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import OrderedDict

REPO = "kostyamat/QFRadio-Releases"
ASSET_BASE = f"https://github.com/{REPO}/releases/download"
REQUIRED = ("package", "version_code", "version_name", "download_url", "sha256", "changelog")
# Keys at the top level that are not per-app objects.
NON_APP_KEYS = {"version_code", "version_name", "download_url", "changelog", "min_supported_version"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=OrderedDict)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_set(args):
    if not os.path.isfile(args.apk):
        sys.exit(f"APK not found: {args.apk!r}")
    if args.version_code <= 0:
        sys.exit("--version-code must be a positive integer")
    data = load(args.manifest)
    apk_name = os.path.basename(args.apk)
    digest = sha256_of(args.apk)
    size = os.path.getsize(args.apk)
    url = f"{ASSET_BASE}/{args.tag}/{apk_name}"

    entry = data.get(args.app)
    if not isinstance(entry, OrderedDict):
        entry = OrderedDict()
    entry["package"] = args.package
    entry["version_code"] = args.version_code
    entry["version_name"] = args.version_name
    entry["download_url"] = url
    entry["sha256"] = digest
    entry["size"] = size
    if args.changelog is not None:
        entry["changelog"] = args.changelog
    elif "changelog" not in entry:
        entry["changelog"] = ""
    data[args.app] = entry

    # The radio's current updater reads the legacy top-level block; keep it in step with qfradio.
    if args.app == "qfradio":
        data["version_code"] = args.version_code
        data["version_name"] = args.version_name
        data["download_url"] = url
        data["changelog"] = entry["changelog"]

    save(args.manifest, data)

    # Self-check: the file must still parse and hold the entry we wrote.
    back = load(args.manifest)
    got = back.get(args.app, {})
    for k in REQUIRED:
        if k not in got:
            sys.exit(f"self-check failed: {args.app}.{k} missing after write")
    if got["sha256"] != digest or got["version_code"] != args.version_code:
        sys.exit("self-check failed: written values do not read back")

    print(f"Updated {args.manifest}: {args.app} -> vc {args.version_code} ({args.version_name}), "
          f"{size} B, sha256 {digest[:16]}…")
    print("\nNow upload the APK as the release asset (needs your GitHub auth):")
    print(f"  gh release create {args.tag} \"{args.apk}\" "
          f"-R {REPO} -t \"{args.app} {args.version_name}\" -n \"{args.changelog or ''}\"")
    print(f"  # or, if the release tag already exists:")
    print(f"  gh release upload {args.tag} \"{args.apk}\" -R {REPO} --clobber")
    print(f"\nThen commit {args.manifest}. The download URL will be:\n  {url}")


def cmd_check(args):
    data = load(args.manifest)
    apps = [k for k, v in data.items() if isinstance(v, (dict, OrderedDict)) and k not in NON_APP_KEYS]
    if not apps:
        sys.exit("no per-app entries found")
    problems = 0
    seen_pkgs = {}
    for app in apps:
        entry = data[app]
        for k in REQUIRED:
            if k not in entry:
                print(f"  {app}: missing '{k}'")
                problems += 1
        pkg = entry.get("package")
        if pkg:
            if pkg in seen_pkgs:
                print(f"  {app}: package '{pkg}' also used by '{seen_pkgs[pkg]}' — apps must be unique")
                problems += 1
            seen_pkgs[pkg] = app
        vc = entry.get("version_code")
        if not isinstance(vc, int) or vc <= 0:
            print(f"  {app}: version_code must be a positive integer, got {vc!r}")
            problems += 1
        url = entry.get("download_url", "")
        if not url.startswith("https://"):
            print(f"  {app}: download_url must be https, got {url!r}")
            problems += 1
    if problems:
        sys.exit(f"{len(apps)} app(s) checked, {problems} problem(s)")
    print(f"OK: {len(apps)} app(s) — {', '.join(apps)} — all entries complete, packages unique")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default_manifest = os.path.join(os.path.dirname(here), "version.json")
    ap = argparse.ArgumentParser(description="QFRadio-Releases self-update manifest helper")
    ap.add_argument("--manifest", default=default_manifest, help="path to version.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("set", help="add or update one app's entry from a built APK")
    s.add_argument("--app", required=True, help="app key in the manifest, e.g. wdsp_pro")
    s.add_argument("--package", required=True, help="Android applicationId the app matches itself by")
    s.add_argument("--apk", required=True, help="path to the built, signed APK")
    s.add_argument("--version-code", type=int, required=True)
    s.add_argument("--version-name", required=True)
    s.add_argument("--tag", required=True, help="GitHub release tag the asset lives under")
    s.add_argument("--changelog", default=None)
    s.set_defaults(func=cmd_set)

    c = sub.add_parser("check", help="validate the manifest")
    c.set_defaults(func=cmd_check)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
