# Acme code map by ticket area

Paths are relative to the repository root. Start from the files listed for the ticket's Area, then follow imports. Backend tests live in `apps/backend/tests/` (autofill tests in `apps/backend/tests/autofill/`). The frontend has no automated tests.

## Wizard (creating a order)
- Frontend: `apps/frontend/app/(dashboard)/new/` (`page-client.tsx`, `steps/`), `apps/frontend/lib/order-steps.ts`, `apps/frontend/lib/orders-api.ts`
- Backend: `apps/backend/app/api/orders/crud.py`, `schemas.py`
- Order list and detail: `apps/frontend/app/(dashboard)/orders/page.tsx`, `orders/[id]/order-detail-client.tsx`

## Autofill (extraction from documents, field mapping, LLM)
- Orchestration: `apps/backend/app/services/autofill/compiler.py`, `apps/backend/app/services/autofill_service.py`
- Deterministic mapping: `autofill/resolver.py`; LLM fallback: `autofill/llm_resolver.py`
- Rules: `autofill/constraints.py` (exclusion groups, derived fields), `autofill/conflicts` logic in `compiler.py`
- Extraction from uploaded PDFs: `autofill/extractors.py`, `autofill/extraction_schema.py`
- Template config validation: `autofill/config_validation.py`, `autofill/config_schema/`
- API: `apps/backend/app/api/orders/autofill.py`; background jobs: `apps/backend/app/worker.py`
- Frontend: `apps/frontend/lib/autofill-api.ts`, `components/autofilling-overlay.tsx`

## Export PDF (download of compiled documents, ZIP)
- Backend: `apps/backend/app/api/orders/export.py`, `services/render_service.py`, `services/pdf_service.py`, `services/pdf_editor_service.py`, `services/docx_render_service.py`
- Frontend: `apps/frontend/lib/export-api.ts`, `apps/frontend/app/(dashboard)/orders/[id]/order-detail-client.tsx` (buttons "Esporta ZIP" and per-document "Scarica")
- Extra holders pages: `render_service._insert_extra_holder_pages`, `components/extra-holders-dialog.tsx`

## Documenti secondari (photos, procura, relazione tecnica, dichiarazione sismica)
- Backend: `apps/backend/app/api/secondary_documents/`, `services/secondary_document_service.py`, `secondary_field_service.py`, `photo_embedder_service.py`, `relazione_tecnica_service.py`, `autofill/secondary_kinds.py`
- Frontend: `apps/frontend/components/secondary-docs/`, `apps/frontend/lib/secondary-documents-api.ts`

## Admin (templates, users, usage, extractor test)
- Frontend: `apps/frontend/app/(dashboard)/admin/`, `apps/frontend/components/admin/`
- Backend: `apps/backend/app/api/templates/` (`admin.py`, `upload.py`, `read.py`), `admin_users.py`, `admin_usage.py`, `admin_extractor_test.py`, `services/template_service.py`, `services/usage_service.py`

## Rubrica (address book)
- Backend: `apps/backend/app/api/address_book.py`
- Frontend: `apps/frontend/app/(dashboard)/address-book/page.tsx`, `components/address-book-picker.tsx`, `lib/address-book-api.ts`

## Billing (plans, Stripe)
- Backend: `apps/backend/app/api/billing.py`, `services/plan_service.py`
- Frontend: `apps/frontend/app/choose-plan/page.tsx`, `lib/billing-api.ts`, `app/(dashboard)/admin/billing/`
- High risk area.

## Auth (login, MFA, impersonation, session)
- Backend: `apps/backend/app/core/auth.py`, `api/mfa.py`, `api/auth_lookup.py`, `services/supabase_admin_service.py`
- Frontend: `apps/frontend/app/login/`, `verify-email/`, `lib/supabase/`, `lib/auth-api.ts`, `lib/impersonation*.ts`, `components/session-cookie-enforcer.tsx`
- High risk area.

## Altro / cross-cutting
- Profile: `apps/backend/app/api/profile.py`, `apps/frontend/app/(dashboard)/profile/`, `components/profile-form.tsx`
- Layout and navigation: `components/dashboard-shell.tsx`, `sidebar.tsx`, `header.tsx`
- Design tokens: `apps/frontend/app/styles/tokens/`; UI primitives: `apps/frontend/components/ui/`
- Config and env: `apps/backend/app/core/config.py`; models: `apps/backend/app/models/`
