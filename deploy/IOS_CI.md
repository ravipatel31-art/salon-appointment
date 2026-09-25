# iOS CI (GitHub Actions → IPA) — salon-integration (phase 18)

Workflow: **`.github/workflows/ios-ipa.yml`**
Runs on a hosted **macOS runner**, builds the Flutter app in `mobile/` and
uploads an artifact. The **signed** artifact is what you install or upload to
App Store Connect; the **unsigned** one is a compile/packaging proof only
(see the warning below).

| Trigger | When |
|---|---|
| `workflow_dispatch` | GitHub → **Actions** tab → *iOS IPA* → **Run workflow** |
| `push` of tag `v*` | `git tag v1.0.0 && git push origin v1.0.0` |

| Artifact | Produced when | Contents | Retention |
|---|---|---|---|
| `ios-ipa` | signing secrets configured | `mobile/build/ios/ipa/*.ipa` (signed, installable) | 14 days |
| `ios-unsigned-ipa` | signing secrets **missing** (fail-soft) | `mobile/build/ios/ipa/Salon-unsigned.ipa` (real IPA file: zip of `Payload/Runner.app` — compile + packaging proof, **not signed**) | 7 days |

Both paths are green. Missing Apple certificates only change *which* artifact
appears — contributors without an Apple Developer account never see a red run.

**Downloading either artifact:** the run page gives you a `.zip` — download it
and unzip **once**; inside you find the `.ipa` file (e.g. `Salon-unsigned.ipa`
or `<name>.ipa`). Nothing else to unpack: the artifact's payload *is* the IPA.

> **Warning — `Salon-unsigned.ipa` will NOT install on a stock iPhone.** It is
> zipped correctly (`Payload/Runner.app`) but carries **no code signature**, so
> iOS refuses to install it, and it cannot go to TestFlight/App Store either. It
> only proves
> the app compiles and packages on CI. A real install needs the four signing
> secrets below (→ signed `ios-ipa`), TestFlight, or an ad-hoc/development
> profile whose device UDIDs are registered.

Every artifact bakes in the compile-time Dart defines (they are **not** runtime
config — see `deploy/NOTES.md` §3 and `docs/CONTRACT.md` Flutter notes):

```
API_BASE_URL  https://salonapp.unonomercysound.online   (workflow_dispatch input)
USE_MOCK_API  false                                     (workflow_dispatch input)
PAYMENT_MOCK  false                                     (always — never true in a release)
```

---

## 1) Required GitHub secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Required | Value |
|---|---|---|
| `P12_BASE64` | ✅ for signed IPA | base64 of the signing certificate (`.p12`) |
| `PROVISION_PROFILE_BASE64` | ✅ for signed IPA | base64 of the `.mobileprovision` for `com.salon.salonMobile` |
| `KEYCHAIN_PASSWORD` | ✅ for signed IPA | any random string — password of the throwaway keychain created on the runner |
| `APPLE_DEVELOPMENT_TEAM` | ✅ for signed IPA | 10-char Apple **Team ID** (Xcode → Accounts → Team, or the profile's *Team ID*) |
| `P12_PASSWORD` | optional | password the `.p12` was exported with (leave unset if none) |

Optional **repository variables** (same page, *Variables* tab — not secret):

| Variable | Value |
|---|---|
| `EXPORT_METHOD` | `app-store-connect` (default) \| `release-testing` \| `debugging`. Legacy Xcode ≤ 12 names: `app-store` \| `ad-hoc` \| `development`. Must match the **profile type** you uploaded. |
| `CODE_SIGN_IDENTITY` | Signing identity name. Auto-detected from the imported `.p12` when empty (Distribution certs for `app-store-connect`/`release-testing`, Development certs for `debugging`). |

The bundle id is **`com.salon.salonMobile`** (`mobile/ios/Runner.xcodeproj`) —
the provisioning profile must be created for exactly this App ID.

---

## 2) Exporting the certificate and provisioning profile

### a) Certificate → `.p12`

**From Xcode (development cert, fastest):**

1. Xcode → **Settings… → Accounts** → select the team → **Manage Certificates…**
2. **+** → *Apple Development* → create.
3. Open **Keychain Access** → *login* keychain → *My Certificates*.
4. Find `Apple Development: <name> (<ID>)` → expand → right-click the **private
   key** beneath it → **Export…** → save `cert.p12`, set an export password
   (that password = the `P12_PASSWORD` secret, or leave it empty).

**From the Apple Developer portal (distribution cert, needed for
App Store / ad-hoc):**

1. <https://developer.apple.com/account/resources/certificates/list> → **+**
   → *Apple Distribution* → CSR from Keychain Access → download `distribution.cer`.
2. Double-click the `.cer` so it lands in the *login* keychain.
3. Keychain Access → *My Certificates* → expand the cert → right-click the
   **private key** → **Export…** → `cert.p12`.

> The `.p12` must contain the **private key**, not just the certificate. Export
> from the row *under* the certificate, otherwise `security import` succeeds
> but no identity appears.

### b) Provisioning profile → `.mobileprovision`

<https://developer.apple.com/account/resources/profiles/list> → **+** →

| Export method | Profile type | Certificate to tick |
|---|---|---|
| `app-store-connect` | **App Store** | Apple Distribution |
| `release-testing` | **Ad Hoc** | Apple Distribution (+ device UDIDs) |
| `debugging` | **iOS App Development** | Apple Development |

App ID = `com.salon.salonMobile` (register it under *Identifiers* first if it
is not there), certificate = the one exported above → **Generate** → download.

### c) Base64-encode both files

```bash
# macOS (strip newlines — the secret must be one line)
base64 -i cert.p12        | tr -d '\n' | pbcopy   # → P12_BASE64
base64 -i app.mobileprovision | tr -d '\n' | pbcopy   # → PROVISION_PROFILE_BASE64

# Linux
base64 -w0 cert.p12       # → P12_BASE64
base64 -w0 app.mobileprovision   # → PROVISION_PROFILE_BASE64
```

Paste the clipboard value into the corresponding GitHub secret. **Nothing is
ever committed**: values live only in GitHub's secret store, are masked in job
logs, and exist on disk only inside the job's keychain (the runner is wiped
after the run).

---

## 3) Running the workflow

1. Push this repo to GitHub (`.github/workflows/ios-ipa.yml` must be on the
   default branch for the *Run workflow* button to list the inputs).
2. **Settings → Actions → General** → *Actions permissions*: allow actions
   (default "Allow all actions" is fine).
3. **Actions** tab → **iOS IPA** → **Run workflow** → optionally override
   `api_base_url` / `use_mock_api` / `export_method`.
4. Wait for the job → bottom of the run page → **Artifacts** → download
   `ios-ipa` (signed) or `ios-unsigned-ipa` (no signing secrets), unzip the
   downloaded zip once → you get the `.ipa` to upload to TestFlight/App Store
   or to install on a device.

Tag-driven builds use the same defaults (no inputs):

```bash
git tag v1.0.0 && git push origin v1.0.0
```

### Installing the IPA

- **App Store Connect / TestFlight:** open Apple **Transporter** (Mac App
  Store) → deliver → drag the `.ipa` in, or
  `xcrun altool --upload-app -f file.ipa -t ios --apiKey <key> --apiIssuer <issuer>`.
- **Ad hoc / development IPA:** install with Xcode → *Window → Devices and
  Simulators → +*, Apple Configurator, or `ios-deploy -i <udid> -b Runner.app`.
- **`ios-unsigned-ipa` (`Salon-unsigned.ipa`):** a correctly shaped IPA
  (`Payload/Runner.app`) that is **not code-signed → it will NOT install on a
  stock iPhone** (and can't be uploaded to TestFlight). Use it only as a
  compile/packaging proof. To actually install, configure the four signing
  secrets and re-run the workflow to get the signed `ios-ipa`, or distribute
  via TestFlight/ad-hoc with your own Apple account.

---

## 4) How the signing path works (no secrets in the repo)

1. `.p12` + `.mobileprovision` are decoded and installed on the runner:
   a throwaway keychain (job-scoped, unlocked, first in the search list) and
   `~/Library/MobileDevice/Provisioning Profiles/`.
2. `ExportOptions.plist` is generated in `$RUNNER_TEMP` (method, teamID,
   `signingStyle = manual`, `provisioningProfiles[<bundle id>] = <profile name>`).
3. Signing build settings are injected through **`FLUTTER_XCODE_*` environment
   variables** (`DEVELOPMENT_TEAM`, `CODE_SIGN_STYLE=Manual`,
   `PROVISIONING_PROFILE_SPECIFIER`, `CODE_SIGN_IDENTITY`). The Flutter tool
   forwards those to `xcodebuild` as build settings — so `mobile/ios` needs **no
   committed signing config** and stays untouched.
4. `flutter build ipa --release --dart-define=… --export-options-plist=…`
   archives the app and runs `xcodebuild -exportArchive` → `build/ios/ipa/*.ipa`.
5. `actions/upload-artifact@v4` publishes `ios-ipa`.

### Fail-soft path (no signing secrets) — how the unsigned `.ipa` is made

1. `flutter build ios --release --no-codesign` → `build/ios/iphoneos/Runner.app`.
2. The runner packages it into a real IPA file structure:

   ```bash
   mkdir -p build/ios/ipa_payload/Payload build/ios/ipa
   cp -R build/ios/iphoneos/Runner.app build/ios/ipa_payload/Payload/
   cd build/ios/ipa_payload && zip -qry ../../ios/ipa/Salon-unsigned.ipa Payload
   ```

   (`-y` keeps `.framework` symlinks as links, as Apple expects.)
3. The job asserts the zip starts with `Payload/` and contains
   `Payload/Runner.app/Info.plist`, then uploads `ios-unsigned-ipa`
   from `mobile/build/ios/ipa/*.ipa`.

So the artifact zip always contains an actual `.ipa` file — but again: without
a certificate + provisioning profile it is unsigned and **will not install**.

Equivalent local command (macOS with certificates already in your keychain):

```bash
cd mobile
flutter build ipa --release \
  --dart-define=USE_MOCK_API=false \
  --dart-define=API_BASE_URL=https://salonapp.unonomercysound.online \
  --export-method=app-store-connect        # or debugging / release-testing
# → build/ios/ipa/*.ipa
```

(`flutter build ipa --export-options-plist=<file>` is the lower-level variant
used by CI, where the plist also carries `teamID`, `signingStyle = manual` and
`provisioningProfiles`; `flutter build ios --release --no-codesign` is the
unsigned compile check.)

---

## 5) Troubleshooting

| Symptom | Fix |
|---|---|
| Job green, artifact `ios-unsigned-ipa` | Signing secrets missing/partial — expected. Unzip once → `Salon-unsigned.ipa` (compile proof, **not installable** without signing). Add the four required secrets and re-run to get `ios-ipa`. |
| `No signing certificate "…" found` | `.p12`/profile type mismatch — set the `CODE_SIGN_IDENTITY` variable to your identity (see `security find-identity -v -p codesigning` locally) or re-export the right certificate. |
| `Provisioning profile … doesn't include the selected signing certificate` | Profile and certificate were created for different certificates/teams — regenerate the profile picking the exported certificate, or fix `P12_PASSWORD`. |
| `No signing identity found in the imported .p12` | The `.p12` has no private key, or `P12_PASSWORD` is wrong. Re-export from the private-key row. |
| `No .ipa in build/ios/ipa` (exportArchive error) | `EXPORT_METHOD` does not match the profile type / Xcode version. Use `app-store-connect`, `release-testing` or `debugging` (Xcode 13+), and make sure the downloaded profile matches that type. |
| `profile … not found` / `PROVISIONING_PROFILE_SPECIFIER` | Profile name must match exactly — it is read from the file automatically, so this only breaks if the variable `CODE_SIGN_IDENTITY`/`EXPORT_METHOD` was changed mid-run. |
| Runner image / Xcode drift after a GitHub image update | Pin `runs-on: macos-14` (or select Xcode explicitly) in `.github/workflows/ios-ipa.yml`. The app's `IPHONEOS_DEPLOYMENT_TARGET` is 12.0 — raise it in `mobile/ios` (salon-flutter owns that file) if a future Xcode drops it. |
| CocoaPods / `Podfile missing` | Not an issue: `ios/Podfile` is generated automatically by the Flutter tool (only `Pods/` output is gitignored). CocoaPods ships on GitHub macOS runners. |

## 6) Security checklist

- [ ] No `.p12`, `.mobileprovision`, passwords or Team IDs in the repo — only in
      GitHub **secrets** (values are masked in logs).
- [ ] `P12_PASSWORD` never appears in workflow YAML or docs.
- [ ] `PAYMENT_MOCK` stays `false` for every release IPA; `RAZORPAY_MOCK` stays
      `0` on the API (`deploy/.env.example`).
- [ ] `permissions: contents: read` — the workflow cannot write to the repo.
- [ ] Artifacts are short-lived (7/14 days) and contain no secrets.
