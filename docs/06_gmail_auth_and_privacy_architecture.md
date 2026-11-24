# Gmail Sign-In Architecture, Per-User Privacy Isolation & Production Setup Guide (`M5`)

## 1. Executive Summary

Milestone M5 replaces the legacy single-household shared profile behavior with a **clean unauthenticated guest experience** and **private, per-user Gmail authentication and persistence**:

- **Unauthenticated Visitors (Clean Guest Mode)**: Opening `https://breezyflights.com` starts in a neutral state (`2` adults, `0` children, `0` El Al Matmid points). Guests can freely search holidays or manual dates, filter multiple destinations, and enter temporary children's ages (`0–18`), school frameworks, and Matmid balances **without signing in** and with **zero SQLite writes**.
- **Gmail-Authenticated Users (Private Persistence & Notification Readiness)**: Signing in with Gmail via server-side **OAuth 2.0 / OpenID Connect (Authorization Code + PKCE `S256`)** binds a revocable, SHA-256-hashed server session cookie (`__Host-fvp_session`) to the user's immutable Google subject (`google_sub`). Signed-in users can privately save and reload their family composition (including children's integer ages and frameworks), manage explicit opt-in consent for future email notifications, and delete their saved data or account at any time.

---

## 2. Gmail Sign-In Architecture & Design Trade-Offs

### 2.1 Production Runtime & Privacy Constraints

1. **Minimal Production VM Dependencies (`deploy_argolis_gcp.sh`)**: The production Compute Engine VM (`family-vacation-planner-vm`, Debian 12, `zone=me-west1-a`) runs `/usr/bin/python3` behind Caddy HTTPS and installs only `python3`, `python3-yaml`, `sqlite3`, and `caddy` (`requirements.txt` contains `PyYAML>=6.0.1` only — no `google-auth`, `cryptography`, `PyJWT`, or `requests`).
2. **Zero Third-Party Frontend Scripts**: Loading external JavaScript SDKs on initial page load exposes unauthenticated visitors to third-party tracking requests and violates the application's strict static-asset/no-CDN boundary.
3. **XSS-Immune Credential Handling**: Authentication tokens and session identifiers must never be readable by client-side JavaScript (`localStorage` / `sessionStorage`) or cached by the PWA Service Worker (`sw.js`).

### 2.2 Evaluation of Candidate Authentication Mechanisms

| Mechanism | Runtime Dependencies | Guest Privacy & Page Load | Security Posture | Verdict |
|---|---|---|---|---|
| **1. Server-Side Google OAuth 2.0 / OIDC Auth Code + PKCE (`S256`) + Direct TLS Token Exchange** | **100% Python 3 stdlib** (`urllib.request`, `ssl`, `hmac`, `hashlib`, `secrets`, `http.cookies`, `sqlite3`) | **Zero third-party scripts**; guests make zero requests to Google | Full Login-CSRF binding (`state` + `fvp_oauth_bind` cookie), PKCE `S256`, OIDC `nonce`, TLS-verified token exchange (OIDC Core 1.0 §3.1.3.7 Rule 6), `HttpOnly; Secure; SameSite=Lax` `__Host-` session cookie | **Selected & Implemented** |
| **2. Client-Side Google Identity Services (`gsi/client` JS SDK) + Backend JWT RSA Verify** | External Google JS script + Python `cryptography` / `google-auth` + JWKS rotation cache | Loads Google JS on every visit; blocked by strict tracker blockers & offline browsers | Exposes raw `id_token` to browser JS prior to backend exchange; requires RSA/JWKS libraries absent on VM | Rejected |
| **3. Email Magic Links / One-Time Passcodes (OTP)** | Requires outbound SMTP / transactional email provider API + deliverability DNS (`SPF`/`DKIM`/`DMARC`) | Clean initial load, high login friction (inbox context switch) | Vulnerable to link forwarding, email pre-fetching scanners, and inbox delays | Rejected |
| **4. Third-Party Hosted Auth SDK (Firebase / Auth0)** | External JS SDKs + third-party tenant/keys + Python JWT verifier | External network dependencies on boot | Stores user identities in an external vendor platform outside self-hosted SQLite | Rejected |

### 2.3 End-to-End OAuth 2.0 + PKCE (`S256`) Authentication Flow

```text
Browser (User)                     Family Vacation Planner (Backend)             Google OAuth 2.0 / OIDC
      |                                            |                                        |
      |  1. GET /api/v1/auth/google/login          |                                        |
      |------------------------------------------->|                                        |
      |     - Generate CSPRNG state, PKCE S256     |                                        |
      |       (code_verifier, code_challenge),     |                                        |
      |       OIDC nonce, and raw_bind token       |                                        |
      |     - Store SHA-256(state), code_verifier, |                                        |
      |       nonce, SHA-256(raw_bind) in SQLite   |                                        |
      |       `oauth_login_states` (10-min TTL)    |                                        |
      |<-------------------------------------------|                                        |
      |  302 Redirect -> accounts.google.com       |                                        |
      |  Set-Cookie: fvp_oauth_bind (HttpOnly)     |                                        |
      |                                            |                                        |
      |  2. User authenticates & selects Gmail     |                                        |
      |------------------------------------------------------------------------------------>|
      |<------------------------------------------------------------------------------------|
      |  302 Redirect -> /api/v1/auth/google/callback?code=...&state=...                    |
      |                                            |                                        |
      |  3. GET /api/v1/auth/google/callback       |                                        |
      |     Cookie: fvp_oauth_bind=...             |                                        |
      |------------------------------------------->|                                        |
      |     - Atomically consume & delete state    |                                        |
      |       row (prevents replay)                |                                        |
      |     - Constant-time verify fvp_oauth_bind  |                                        |
      |     - POST code + code_verifier + secret   |  4. HTTPS POST /token (TLS verified)   |
      |       over verified TLS                    |--------------------------------------->|
      |                                            |<---------------------------------------|
      |     - Validate id_token claims: iss, aud,  |     { id_token, access_token }         |
      |       exp, iat, nonce, sub, email_verified,|                                        |
      |       allowed Gmail domain                 |                                        |
      |     - Discard access_token immediately     |                                        |
      |     - Upsert `users` by immutable `sub`    |                                        |
      |     - Insert SHA-256(session_token) + CSRF |                                        |
      |       in `auth_sessions` (14-day TTL)      |                                        |
      |<-------------------------------------------|                                        |
      |  302 Redirect -> /                         |                                        |
      |  Set-Cookie: __Host-fvp_session=...        |                                        |
      |              (HttpOnly; Secure; SameSite=Lax; Path=/)                               |
```

### 2.4 SQLite Relational Schema Additions (`11` Tables Total)

Defined identically in `backend/app/storage_cache/schema.sql` and `backend/app/db/schema.sql`:

1. **`users`**: Stores `id` (UUID v4), `google_sub` (`UNIQUE`, immutable Google OIDC subject), `email` (`UNIQUE`, lowercase verified Gmail address), `email_verified` (`1`), `display_name`, `notification_email` (locked to verified `email`), `notifications_enabled` (`DEFAULT 0` opt-in), `notification_preferences_json`, `notification_consent_updated_at`, `created_at`, `updated_at`, and `last_login_at` (`idx_users_email`).
2. **`auth_sessions`**: Stores `id`, `user_id` (`REFERENCES users(id) ON DELETE CASCADE`), `token_sha256` (`UNIQUE` — raw cookie token is never written to disk), `csrf_token`, `created_at`, `last_seen_at`, `expires_at`, and `revoked_at` (`idx_auth_sessions_user_id`, `idx_auth_sessions_expires`).
3. **`oauth_login_states`**: Stores single-use 10-minute `state_sha256`, `code_verifier`, `nonce`, `browser_binding_sha256`, `return_to`, `created_at`, and `expires_at`.
4. **`family_profiles` Ownership Columns**: Adds `user_id TEXT REFERENCES users(id) ON DELETE CASCADE`, `is_legacy_quarantined INTEGER NOT NULL DEFAULT 0`, and unique partial index `idx_family_profiles_user_id ON family_profiles(user_id) WHERE user_id IS NOT NULL`.
5. **Nullable `flight_search_queries.family_profile_id`**: Allows standalone/offline search persistence without forcing personal profile creation while preserving `ON DELETE CASCADE` for user-owned queries.

---

## 3. Implemented Privacy & Security Protections

1. **Server-Enforced Identity & IDOR Prevention**:
   - `GET /api/v1/profile`, `PUT /api/v1/profile`, and `DELETE /api/v1/profile` require an active verified session (`HTTP 401` when unauthenticated) and resolve ownership exclusively from `session.user_id` on the server.
   - Any client-supplied `id`, `profile_id`, `family_profile_id`, `user_id`, or `email` in query strings or JSON bodies is ignored/stripped.
   - `POST /api/v1/vacations/search` and `GET /api/v1/moe-calendar/*` ignore client `profile_id` / `family_profile_id` parameters; `BonusVacationPlannerService.resolve_proposal_for_requester` enforces strict owner scoping across ephemeral and persisted proposals.
   - Child and loyalty-wallet primary keys are server-namespaced (`user-profile-<user_id>:child:<idx>`, `user-profile-<user_id>:wallet:<idx>`) so cross-user primary-key collisions or overwrites are impossible.
2. **Children's Data Minimization**:
   - Only integer `child_age_years` (`0..18`, required for infant `<2` / child `2–11` / youth `12–17` fare rules) and optional `MoEFrameworkType` (`DAYCARE_SUPERVISED` .. `HIGH_SCHOOL_10_12`) are collected.
   - Children's names and exact dates of birth are never requested in the UI; saved records default `child_name` to a generic label and `birth_date` to `NULL`, and proposal cards render aggregate household traveler counts without per-passenger breakdowns.
3. **Zero-Persistence Guest Isolation**:
   - Unauthenticated visitors never call `GET /api/v1/profile` or `PUT /api/v1/profile`.
   - Guest vacation searches pass inline household parameters (`inline_profile`) evaluated purely in memory (`persist_results=False`), writing **zero** rows to `family_profiles`, `child_frameworks`, `flight_search_queries`, `flight_itineraries`, or `vacation_option_proposals`.
4. **Hashed Session Tokens, `__Host-` Cookies & OAuth Token Disposal**:
   - Google `access_token` and `refresh_token` values are discarded immediately in memory after reading verified OIDC `id_token` claims (`scope=openid email profile` — never Gmail inbox scopes!).
   - Session cookies use `__Host-fvp_session` (`HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1209600`) over HTTPS, and SQLite stores only `SHA-256(raw_token)`.
5. **CSRF & CORS Hardening**:
   - Every cookie-authenticated mutating endpoint (`POST /api/v1/auth/logout`, `PUT /api/v1/profile`, `DELETE /api/v1/profile`, `PUT /api/v1/auth/notifications`, `DELETE /api/v1/auth/account`) enforces constant-time `X-CSRF-Token` verification and same-host `Origin` validation (`HTTP 403` on failure).
   - Wildcard `Access-Control-Allow-Origin: *` is omitted on `/api/v1/auth/*` and `/api/v1/profile*`.
6. **HTTP Cache, Service Worker & Sign-Out Scrubbing**:
   - All `/api/v1/auth/*` and `/api/v1/profile*` responses emit `Cache-Control: no-store, private` and `Vary: Cookie`.
   - `frontend/public/sw.js` (`family-vacation-planner-v3`) explicitly bypasses all `/api/` paths so personal profiles and auth responses are never written to persistent `CacheStorage`.
   - Clicking **Sign out** revokes the server session in SQLite, clears cookies, resets JS `state` and DOM inputs to clean guest defaults, clears `sessionStorage` and `localStorage`, and evicts any `/api/` entries from `window.caches`.
7. **Opt-In Future Notification Readiness, Self-Service Deletion & Log Redaction**:
   - `users.notifications_enabled` defaults to `0` (OFF) on account creation, `notification_email` is locked to the verified Gmail address (preventing third-party email harassment), and consent changes record `notification_consent_updated_at`.
   - Signed-in users can erase their saved family profile (`DELETE /api/v1/profile`) or delete their entire account (`DELETE /api/v1/auth/account`, cascading via `ON DELETE CASCADE`).
   - Error responses pass through `redact_pii()` so email addresses, cookies, OAuth codes, and secrets are never echoed in error payloads.

---

## 4. Safe Quarantine of Existing Shared/Seeded Profile Data

To ensure zero exposure of the legacy shared household profile (`id = 'default-family-profile'`) while preserving all live synced flight data:

1. **New Databases**: `SQLiteRepository.seed_initial_data()` no longer seeds `build_default_family_profile()` into `family_profiles`. Fresh databases initialize with `0` rows in `family_profiles`, `child_frameworks`, and `passenger_loyalty_wallets`.
2. **Existing Production Database (`/opt/family_vacation_planner/data/vacation_planner.db`)**:
   - On startup, `SQLiteRepository._initialize_database()` runs an idempotent `PRAGMA table_info` migration that adds `user_id` and `is_legacy_quarantined` to `family_profiles` (if absent), migrates `flight_search_queries.family_profile_id` to nullable (preserving all existing rows), and executes:
     ```sql
     UPDATE family_profiles
     SET is_legacy_quarantined = 1
     WHERE user_id IS NULL AND is_legacy_quarantined = 0;
     ```
   - Every repository and API profile/proposal query enforces `is_legacy_quarantined = 0` and explicit `user_id` ownership (with the old `ORDER BY created_at ASC LIMIT 1` fallback removed).
   - Result: Any pre-existing unowned shared profile row and its legacy proposals are immediately quarantined and unreachable by both guests and signed-in users, while **100% of synced `#live` rows in `elal_bonus_availability` (`7,903+` award flights) and `moe_vacation_windows` remain completely intact**.

---

## 5. Step-by-Step Production Setup Guide (`https://breezyflights.com`)

Follow these steps to enable live Gmail Sign-In on the production GCE VM (`family-vacation-planner-vm`, `project=family-trip-planner-514920`, `zone=me-west1-a`).

### Step 1 — Create Google Cloud OAuth 2.0 Web Credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select project **`family-trip-planner-514920`** (or your dedicated OAuth project).
2. Navigate to **APIs & Services → Google Auth Platform / OAuth consent screen**:
   - **User Type**: `External`
   - **App name**: `Smart Family Vacation Planner`
   - **User support email & Developer contact email**: your Gmail address
   - **Authorized domains**: `breezyflights.com`
   - **Data Access / Scopes**: select **only** `openid`, `.../auth/userinfo.email`, and `.../auth/userinfo.profile` (minimal OIDC identity scopes; do **not** add Gmail read/send scopes).
   - **Publishing status**: click **Publish App** (to allow any Gmail user to sign in) or add specific Gmail addresses under **Test users** while in Testing mode.
3. Navigate to **APIs & Services → Credentials → + Create Credentials → OAuth client ID**:
   - **Application type**: `Web application`
   - **Name**: `Family Vacation Planner Production Web`
   - **Authorized JavaScript origins**:
     ```text
     https://breezyflights.com
     ```
   - **Authorized redirect URIs**:
     ```text
     https://breezyflights.com/api/v1/auth/google/callback
     ```
4. Click **Create** and copy the generated **Client ID** (`...apps.googleusercontent.com`) and **Client secret**.

### Step 2 — Configure `/etc/family_vacation_planner/auth.env` on the VM

Secrets are stored in `/etc/family_vacation_planner/auth.env` (`0600` permissions inside a `0700` root-owned directory) rather than inside `/opt/family_vacation_planner` or `/etc/systemd/system/family-vacation-planner.service` (which is world-readable `0644`), ensuring code syncs never overwrite credentials:

```bash
gcloud compute ssh family-vacation-planner-vm \
  --project=family-trip-planner-514920 \
  --zone=me-west1-a
```

On the VM, create `/etc/family_vacation_planner/auth.env`:

```bash
sudo mkdir -p /etc/family_vacation_planner
sudo chmod 700 /etc/family_vacation_planner

sudo tee /etc/family_vacation_planner/auth.env >/dev/null <<'EOF'
PUBLIC_BASE_URL=https://breezyflights.com
GOOGLE_OAUTH_CLIENT_ID=REPLACE_WITH_YOUR_CLIENT_ID.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=REPLACE_WITH_YOUR_CLIENT_SECRET
GOOGLE_OAUTH_REDIRECT_URI=https://breezyflights.com/api/v1/auth/google/callback
GOOGLE_OAUTH_ALLOWED_DOMAINS=gmail.com,googlemail.com
SESSION_TTL_SECONDS=1209600
EOF

sudo chown root:root /etc/family_vacation_planner/auth.env
sudo chmod 600 /etc/family_vacation_planner/auth.env
```

*(Never set `VACATION_PLANNER_AUTH_TEST_MODE` in production; even if accidentally set, the backend triple-gate disables test mode whenever `ELAL_LIVE_FETCH_ENABLED=1` or `PUBLIC_BASE_URL` / `Host` is non-loopback.)*

### Step 3 — Update `systemd` Unit, Verify Caddy HTTPS & Restart Service

Ensure `/etc/systemd/system/family-vacation-planner.service` includes `EnvironmentFile=-/etc/family_vacation_planner/auth.env` (already added to `deploy_argolis_gcp.sh`):

```ini
[Unit]
Description=Family Vacation Planner Web & API Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/family_vacation_planner
Environment=HOST=127.0.0.1
Environment=PORT=8080
Environment=ELAL_LIVE_FETCH_ENABLED=1
Environment=VACATION_PLANNER_DB_PATH=/opt/family_vacation_planner/data/vacation_planner.db
EnvironmentFile=-/etc/family_vacation_planner/auth.env
ExecStart=/usr/bin/python3 -m backend.app.main --host 127.0.0.1 --port 8080
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Verify `/etc/caddy/Caddyfile` proxies HTTPS traffic to `127.0.0.1:8080` (Caddy automatically sets `X-Forwarded-Proto: https` and `X-Forwarded-Host`, activating `__Host-fvp_session` `Secure` cookies):

```caddyfile
breezyflights.com {
    reverse_proxy 127.0.0.1:8080
}
```

Apply and restart on the VM (after backing up the SQLite DB as standard operational hygiene):

```bash
sudo cp /opt/family_vacation_planner/data/vacation_planner.db \
  /opt/family_vacation_planner/data/vacation_planner.db.pre_m5.bak

sudo systemctl daemon-reload
sudo systemctl restart family-vacation-planner.service
sudo systemctl status family-vacation-planner.service --no-pager
```

### Step 4 — Post-Deploy Production Verification Checklist

1. **Verify Health & `11`-Table Schema Migration**:
   ```bash
   curl -s https://breezyflights.com/api/v1/health
   # Expect: "status": "ok", "tables_count": 11
   ```
2. **Verify Session Readiness & No-Store Headers**:
   ```bash
   curl -i https://breezyflights.com/api/v1/auth/session
   # Expect: HTTP/2 200, Cache-Control: no-store, private
   # Body: {"authenticated": false, "oauth_configured": true, "test_mode": false, "csrf_token": null, "user": null}
   ```
3. **Verify Unauthenticated `/api/v1/profile` Lockdown**:
   ```bash
   curl -i https://breezyflights.com/api/v1/profile
   # Expect: HTTP/2 401 {"error": "Authentication required. Please sign in with Gmail."}
   ```
4. **Verify OAuth 2.0 + PKCE (`S256`) Redirect**:
   ```bash
   curl -i https://breezyflights.com/api/v1/auth/google/login
   # Expect: HTTP/2 302
   # Location: https://accounts.google.com/o/oauth2/v2/auth?...&code_challenge_method=S256...
   # Set-Cookie: fvp_oauth_bind=...; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=600
   ```
5. **End-to-End Browser Check**:
   - Open `https://breezyflights.com` in an Incognito window: confirm `2` adults, `0` children, `0` Matmid points, and full guest search functionality.
   - Click **Sign in with Gmail to Save Profile**, authenticate, add children's ages & Matmid points, click **Save & Refresh**, sign out (confirming immediate reset to clean guest state), and sign back in to confirm your private saved profile reloads cleanly.
