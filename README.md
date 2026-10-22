# Inventory Management System

Python FastAPI server with index.html frontend. No Node build step is required.

## Start locally (Windows / terminal)

Open a terminal inside the extracted `inventory` folder:

```powershell
python -m pip install -r requirements.txt
python server.py
```

Open http://127.0.0.1:8000

Login ID: `admin@123`  
Password: `admin@123`

The private `.env` already contains the supplied Groq API key and a generated session secret. Do not commit `.env`; `.gitignore` excludes it. `.env.example` is safe to commit and contains no API key.

## Connect your Upstash database

Open your database named **inventory managment system** in the Upstash console. Open its connection / REST API section and copy BOTH values into `.env`:

```dotenv
UPSTASH_REDIS_REST_URL=https://YOUR-ENDPOINT.upstash.io
UPSTASH_REDIS_REST_TOKEN=YOUR-REST-TOKEN
```

The console data-browser URL and database name are not connection credentials. Use the standard writable REST token, not a read-only token. The application uses the namespaced key `inventory:v1:state` and login-rate-limit keys. It does not modify other database data. Existing arbitrary Redis keys are not auto-imported.

Restart the Python server after changing `.env`. The workspace status identifies the active storage. With no Redis credentials, local development uses `data/inventory.sqlite3`. SQLite data is not automatically transferred when Redis is enabled. Export local records before switching; import source business rows through the review screen, taking care not to import derived ledger/account-balance sheets twice. Vercel requires Redis and never silently writes temporary local storage.

## Deploy to Vercel

1. Push the contents of the `inventory` folder to a Git repository (or select `inventory` as Vercel's Root Directory). Do not push its parent ZIP folder.
2. Import that repository in Vercel. Use **Other** if a framework choice is needed; leave build/output overrides empty. `vercel.json` routes requests to `server.py`.
3. Add these Environment Variables in the Vercel project settings before deploying:
   - `GROQ_API_KEY`: copy from your private `.env`.
   - `GROQ_MODEL`: `qwen/qwen3.8-27b`.
   - `UPSTASH_REDIS_REST_URL`: your database's actual HTTPS REST endpoint.
   - `UPSTASH_REDIS_REST_TOKEN`: your writable REST token.
   - `SESSION_SECRET`: copy your generated value from `.env` (use the same value across deployments).
   - `ADMIN_USERNAME`: `admin@123`.
   - `ADMIN_PASSWORD`: `admin@123`.
   - `COOKIE_SECURE`: `true`.
   - Optional `REDIS_KEY_PREFIX`: `inventory:v1` (keep consistent to use the same data).
4. Deploy. Sign in and check that the workspace status says **Upstash Redis**.

The `.env` file is also excluded from deployment uploads. Setting these environment variables is required. No live deployment or external database configuration is performed by this ZIP.

## Workflow

- **Dashboard:** actual billed sales, costed profit/loss, customer receivables, stock cost, cash collections, expenses, customer advances; daily sales/collections/expenses graph and stock-value bars. Refreshes from the server every 10 seconds when no edit/import is in progress.
- **Inventory:** acquired quantity, RMB unit price, per-item RMB→PKR rate, PKR selling price, sold and remaining units, total RMB cost, remaining potential sales and margin.
- **Bills:** customer, date, bill number, amount. Optional linked inventory lines set the bill amount, deduct stock and snapshot purchase cost. Prevents overselling. Editing/removing a bill recalculates stock and balances. Billed stock cannot be deleted unless its bill links are removed first.
- **Payments:** customer collections lower the customer's outstanding balance. Overpayments appear as customer credit. Enter supplier/business costs under Expenses rather than customer Payments.
- **Accounts ledger:** derived debits, credits and running customer balances. Edit its source bills, payments or opening accounts to change the ledger.
- **Accounts list:** customer sheet numbers, opening balances and current balances. Names match without case differences; avoid spelling variations. Set opening balances only for records before the system's starting point. Auto-generated accounts are edited through their source transactions; add an opening account if a sheet number is required.
- **Expenses:** operating expenses reduce the reported net profit.
- **AI assistant:** suggestions about restocking, receivables and margins based on current saved figures. Suggested question buttons fill the input; sending calls Groq. Advice does not modify records.
- **Settings:** default exchange rate for new records and the business name. Stored for AI/context; the navigation brand remains Inventory. No automatic live exchange-rate feed.
- **Exports:** Excel contains source tables and derived reports; JSON contains a complete state backup for archival/developer recovery. There is no one-click raw JSON restore. Re-uploaded reports go through import review, not an identity-preserving database restore.

## Excel compatibility fix

The XLSX reader streams actual cells from EVERY worksheet, including hidden sheets, without trusting missing or incorrect row/column dimension metadata. One workbook may contain Inventory List, Bill List and Payment List in any order; select Auto-detect all tables and review/save once. Standard headers and shuffled columns map directly without Groq. The preview shows each worksheet name, detected entry count, mapping method and any unmapped rows. Common header aliases and multiple vertically stacked tables in one sheet are supported. Derived account balances are excluded when source bills/payments are available.

Limits: 1,000 extracted business records, 2,000 nonempty source rows across all sheets, 60 data columns and 10,000 physical rows per sheet. Unknown layouts use AI fallback per sheet (up to 120 rows / 45,000 characters per fallback). Unmapped data is explicitly reported; save only after reviewing warnings. Formula cells need saved calculated results: open/save in Excel or LibreOffice to calculate them, or fill missing fields in the review. Pasted photos embedded inside Excel are not read as cell data; upload those photos separately.

## AI capture and review

Upload or drag a file, or paste text. Groq Qwen reads images directly. Python reads every spreadsheet sheet and maps recognizable headers directly to the required tables; only unrecognized layouts are sent to Qwen for mapping. No Tesseract or OCR installation is needed.

Supported:
- JPG/JPEG, PNG, WEBP, BMP, single-page TIFF register photos and screenshots.
- Excel `.xlsx`, `.xls`, `.xlsm` (macros are never run), CSV/TSV.
- TXT, JSON, Markdown, text-based PDF (up to 8 pages).
- For scanned PDFs, upload individual page images instead.

The target dropdown is a mapping hint. A source can produce rows across several tables. Before saving, edit every detected value, remove unwanted rows and fill missing fields marked for review. Savings are atomic: invalid rows prevent the entire import. The same exact file/text cannot be committed twice. Same customer/bill-number duplicates are rejected. Review semantically duplicate payments/items yourself; different files can contain overlapping records.

AI maps source rows; it cannot guarantee accurate handwriting, dates or ambiguous columns. Missing required data remains incomplete for review. AI-derived bills initially contain amounts only. Edit a bill after import to link its inventory items and calculate stock/profit. Derived account sheets should not be imported alongside their source bills/payments; check warnings carefully.

## Accounting definitions

All financial reports use PKR unless marked RMB:

- Unit purchase cost PKR = RMB unit cost × saved item exchange rate.
- Remaining stock = total acquired quantity − linked sold quantity.
- Potential stock sales = remaining quantity × unit selling price.
- Potential stock margin = remaining quantity × (sell price − cost); this is not earned profit.
- Billed sales = all bill amounts; collections are separate cash movement.
- Costed gross profit = linked-item bill sales − their snapshotted purchase costs.
- Net profit/loss = costed gross profit − expenses.
- Amount-only bills are **uncosted sales** and excluded from net profit until linked to inventory.
- Customer balance = opening balance + bills − payments. Positive means receivable; negative means customer advance.

Use the total acquired units for inventory quantity. Editing it sets the total, not an additional stock purchase. For purchases with different RMB costs/rates, create separate item/batch rows to preserve correct costing. Linked bills freeze their cost basis; later inventory-cost edits do not rewrite the historical sale cost. The model does not include tax, returns, multi-currency ledgers, FIFO, supplier payables or refunds.

## Limits and persistence

- Files: maximum 4 MB each, one file per analysis. This keeps multipart requests below Vercel's 4.5 MB platform limit.
- Imports: up to 1,000 extracted Excel/CSV records with standard headers, across all worksheets. Source scanning allows 2,000 nonempty rows, 60 data columns and 10,000 physical rows per sheet. AI-only imports/fallbacks allow 120 entries, 45,000 text characters and 20-megapixel images. Split inputs that exceed these limits.
- Expanded XLSX archive: maximum 25 MB. One worksheet can still require cleaning if it has excessively formatted empty rows.
- 5,000 rows per source table; entire serialized workspace capped at 3.5 MB. This is a small-business single-admin workspace, not an unlimited ERP.
- All tables are saved atomically using a Redis Lua compare-and-set operation (SQLite transactions locally). Stale edits receive a conflict rather than overwriting another device's changes.
- Redis receives business records and import metadata. Source file bytes are not retained by the app. Images/text are sent to Groq for analysis; do not upload data you do not want processed by that provider.
- Cookies are HttpOnly, SameSite=Strict, Secure on Vercel; writes require a session CSRF token. Login attempts are rate limited. API keys stay server-side.
- Charts use local SVG and CSS; no external scripts/CDNs required for UI.

## Verification

```powershell
python -m pip install pytest
python -m pytest tests -q
```

Tests cover accounting, stock, frozen costs, authentication, atomic imports, deduplication, file parsing, exports, conflicts, Redis command construction and mandatory Redis configuration on Vercel. Live Groq and live Redis require valid credentials/network access and are separate integration checks.

Official references:
- https://console.groq.com/docs/vision
- https://upstash.com/docs/redis/features/restapi
- https://vercel.com/docs/functions/limitations

## Included samples and updating an existing installation

- `examples/Sample_All_Sheets.xlsx`: one small workbook with shuffled sheets and columns; 6 inventory items, 2 bills, 2 payments. Expected billed sales 18,000 PKR, payments 6,000 PKR, outstanding 12,000 PKR. Native header mapping requires no Groq call.
- `examples/Handwritten_Register_20.png`: AI-generated handwritten register test image containing 10 inventory rows, 5 payments and 5 bills. Expected bill total 41,000 PKR, payment total 15,500 PKR and outstanding 25,500 PKR. Check the AI preview against the image; live handwriting extraction is not guaranteed or validated here.
- `examples/TEST_SAMPLES.md`: exact testing instructions and expected results.

For an existing installation, back up your folder and retain your `.env` and `data/` directory. Replace application code (including new `excel_import.py`), reinstall requirements and restart the server; on Vercel push all changed application files and redeploy. Keep the same Redis settings and `SESSION_SECRET` to retain stored records and sessions. The ZIP has no business database or test records preloaded. Samples must be explicitly uploaded to add them.
