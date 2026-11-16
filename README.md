# DocuFlow — PDF & Word Converter

A Flask document-conversion website with PDF → editable DOCX, DOCX → PDF, account registration/login, private conversion history, downloads, and an admin dashboard.

## Features
- Responsive landing page and workspace
- Secure password hashing and session-based authentication
- PDF to Word conversion using `pdf2docx`
- Word (DOCX) to PDF conversion using headless LibreOffice
- Per-user conversion history and access-controlled downloads
- Admin dashboard with user and conversion overview
- 25 MB upload limit and extension validation
- Dockerfile and Render Blueprint for deployment

## Run locally (macOS)
1. Install Python 3.11+ and LibreOffice. On macOS: `brew install --cask libreoffice`.
2. Open Terminal in this folder and run:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   export SECRET_KEY='replace-with-a-long-random-secret'
   export ADMIN_USERNAME='admin'
   export ADMIN_PASSWORD='use-a-strong-password'
   python app.py
   ```
3. Visit http://127.0.0.1:5000.

The first launch creates the admin account from `ADMIN_USERNAME` and `ADMIN_PASSWORD`. If you change these after the admin already exists, the existing account is not renamed or reset automatically.

## Deploy to Render
1. Push this folder to a new GitHub repository.
2. In Render, choose **New → Blueprint**, connect the repository, and apply `render.yaml`.
3. Set the secret `ADMIN_PASSWORD` in the Render environment prompt. Keep `SECRET_KEY` private; Render generates it in the blueprint.
4. The blueprint provisions PostgreSQL and a persistent disk mounted at `/app/storage` for converted files. The Docker image installs LibreOffice.
5. Open the deployed URL and sign in with the configured admin username/password. Change the default admin username if desired before first deployment.

## Important production notes
- Do not deploy with the fallback `ChangeMe123!` password. Always set a unique `ADMIN_PASSWORD` and strong `SECRET_KEY`.
- For production, add HTTPS (Render provides it), periodic cleanup/retention for stored files, malware scanning, CSRF protection, rate limiting, and backups.
- PDF-to-DOCX layout fidelity varies with the source PDF. Scanned/image-only PDFs need OCR; this starter does not include OCR.
- The included disk is persistent storage. If you scale to multiple instances, move files to shared object storage and use a shared database.
- This app accepts DOCX, not legacy `.doc` files.
