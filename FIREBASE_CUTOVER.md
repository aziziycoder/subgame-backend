# Firebase cutover

Django becomes the only source of truth for auth, licenses, games, sliders, orders and uploaded files.
Run the steps in this order.

## 1. Before deploying

- Set `GOOGLE_CLIENT_ID=542403988321-67fapm1qe6oqih3rvl8obu9hqpacuf4v.apps.googleusercontent.com` in the production backend `.env`. The previous value does not exist in Google, and the audience check now rejects anything else.
- In Google Cloud Console (project `subgame-ca4ed`), open that OAuth Web Client and add
  `https://subgame.uz` and `https://www.subgame.uz` to its Authorized JavaScript origins. Sign-in fails with `redirect_uri_mismatch` until this is done.
- Confirm `CLICK_SECRET_KEY` is set in the backend `.env`. The webhook now rejects every request without it.
- Confirm Click's Prepare/Complete URLs point at this backend (`/api/click/...` or `/api/v1/payments/click/...`).
  The Vercel functions in `Game-sub/api/click` are gone.

## 2. Deploy the backend

Includes migration `licenses/0004_firebase_cutover`. Firebase-signed ID tokens are still accepted, so the
current site keeps working.

## 3. Deploy the site

From this point the site writes only to Django. Do step 4 straight after.

## 4. Final data copy (run once)

Needs Firestore read quota. Re-running later would overwrite HWID resets made in Django.

```bash
# in Game-sub
node scripts/export_firestore_all.mjs
```

Copy `data/firestore_full_export.json` to `/var/www/subgame-backend/data/` on the server, then in `/var/www/subgame-backend` with the virtualenv active:

```bash
python scripts/import_firestore_data.py
python manage.py rehost_firebase_files --dry-run
python manage.py rehost_firebase_files
```

For licenses, Firestore wins on HWID, because the launcher only ever wrote there. Games are replaced only
when the Firestore copy is newer. The import prints how many user+game pairs had duplicate documents.

## 5. Release the launcher

1. Bump `version` in `SubGame-Launcher/package.json`, build and publish it.
2. Update `public/downloads/version.json` on the site.

The update is mandatory. Users sign in again once, because old sessions have no JWT.

Users whose old HWID was computed differently may see "Qurilma mos kelmadi" once. One admin reset fixes it,
and the HWID stays fixed afterwards.

## 6. After the rollout

Wait until installed launchers have updated, then:

- Remove the `verify_firebase_token` entry from `apps/users/views.py` and `FIREBASE_PROJECT_ID` from settings.
- In `Game-sub`, remove `firebase` and `firebase-admin` from `devDependencies`, plus
  `scripts/export_firestore_all.mjs`, `tools/seed_*`, `firebase.json`, `.firebaserc`, `firestore.rules`, `storage.rules`.
- Remove `data/firestore_full_export.json` from this repository. It contains user emails and is tracked in git.
- Keep a backup, then shut down the Firebase project. Check first that `rehost_firebase_files` reports nothing left.
