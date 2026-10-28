# Document storage layout

Application account: `ilerastorage` in resource group `Ilera`.
`ileratfstate` is reserved for Terraform state.

| Container | Purpose | Example key |
| --- | --- | --- |
| `forms` | Blank application PDF templates | `CDSS/IHSS/SOC-873.pdf` |
| `reference-guides` | Public explanatory PDFs | `CA/EDD/employment/DE-231D.pdf` |
| Separate private user-document container when needed | Uploaded and completed documents | Case-scoped paths; authenticated access only |

The existing `app-package-*`, `azure-webjobs-hosts`, `azure-webjobs-secrets`,
`ilerahub-applease`, and `ilerahub-largemessages` containers belong to the Azure
Functions deployment/runtime and must retain their names and paths. No runtime
containers, form templates or user documents have been moved in this session.
The contents of `forms` still need inventory before planning any existing-file moves.

## Reference guide hosting

`backend/data/reference_guides/catalog.json` records each guide's source URL,
blob key and display filename. The public `/api/reference-guides/{guide_id}`
endpoint only serves whitelisted public guides. Storage stays private; the API
streams the guide. It cannot expose arbitrary keys or user documents.

The app reads `REFERENCE_GUIDES_BLOB_ACCOUNT_URL` (or, if unset, the existing
`FORMS_BLOB_ACCOUNT_URL`) and `REFERENCE_GUIDES_BLOB_CONTAINER` (default
`reference-guides`). It uses the existing configured managed identity in Azure;
that identity needs Storage Blob Data Reader access to the guide container.
Local development can use Azure CLI login via DefaultAzureCredential with
`FORMS_USE_MANAGED_IDENTITY=false`. Local binaries under
`backend/data/reference_guides/<blob_key>` are a fallback. If no hosted/local PDF
is available, the browser is redirected to the official source.

## Upload the EDD guide

From the repository root, with Azure CLI signed in:

```sh
backend/.venv/bin/python backend/scripts/upload_reference_guide.py \
  edd-multistate-employment --account-name ilerastorage
```

The uploader fetches the official PDF, checks its signature/size, creates the
private `reference-guides` container if needed, and uploads
`CA/EDD/employment/DE-231D.pdf` with source URL and SHA-256 metadata.
It refuses to overwrite an existing file. Future revisions should use a versioned
key and an updated catalog. The code/configuration must be deployed before a
production intake can serve this new container.

## Existing-file migrations

First inventory names, sizes, metadata and every app reference. Application
PDFs remain in `forms`; explanatory documents can move to `reference-guides`.
Copy each reviewed source to its destination and verify byte length/hash before
changing app references. Keep the old key through rollout; remove it only after
all readers use the new location. Never classify or move unknown runtime blobs.

Current session: the user confirmed the container inventory. Azure CLI in the
agent's shell cannot reach Microsoft login due to DNS/network restrictions.
The user confirmed successful EDD and SSA uploads on October 14, 2026.
EDD SHA-256: `91bc5c1221e16f2730c309f1a1860947b06dde4bee1cbb3b35885a5b34b88325`.
SSA SHA-256: `37aa539fed10954dde9ce04b59888897830d0258d1e5e1d2d997c94cbb3f0d82`.
Medi-Cal download validation failed before upload; no existing files were migrated.

## SSA benefit-letter guide

SSA’s source is a live webpage, not a blank PDF. The Ilera-authored static guide
links users to SSA for their personal letter. It lives locally and can be uploaded
to `reference-guides/US/SSA/income/benefit-verification-letter.html`:

```sh
backend/.venv/bin/python backend/scripts/upload_reference_guide.py \
  ssa-benefit-letter --account-name ilerastorage
```

The local fallback is available immediately through `/api/reference-guides/ssa-benefit-letter`.
The user confirmed this guide was uploaded successfully. No personal benefit
letters are stored with public reference guides.

## Medi-Cal reference versus active status

`medi-cal-member-guide` is catalogued for upload to
`CA/DHCS/Medi-Cal/myMedi-Cal-member-guide.pdf`. Run the existing uploader with
`medi-cal-member-guide --account-name ilerastorage` once blob access works.
This upload failed source-content validation and remains pending. The uploader
now validates PDF structure, retries an alternate verified DHCS URL and accepts
`--file` for a browser-downloaded copy.

The intake coverage question instead links to official county BenefitsCal status
instructions and the statewide county-office directory. Its helper explains case
linking and choosing uncertainty when current coverage is not known. The general
member PDF is not used as the primary active-coverage lookup guide.
