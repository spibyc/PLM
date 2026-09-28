# 04 — Permissions Model and Electronic Approvals

## 1. Three separate concepts

| Concept | Grants | Managed by |
|---------|--------|-----------|
| **Permission** (via role) | Ability to *perform* an operation (`item:create`, `stock:issue`) | Administrator, audited |
| **Signing authority** | Ability to *sign a meaning* on a scope (`Quality Approved` for document class SOP) | Quality-controlled grant **[REC]**: granting requires a Quality signature; Administrator cannot self-grant |
| **Separation-of-duties rules** | Constraints between signers (author ≠ approver; ≥ N distinct signers) | Configuration, versioned, audited |

Administrator role manages users, roles, configuration and operations. It holds **no signing authority by default** and cannot grant signing authority to itself.

## 2. Initial role → permission matrix

R = read, C = create/edit drafts, T = transact, S = may sign (subject to signing authority), A = administer.

| Capability | Admin | Quality | Engineering | Purchasing | Production | Read Only |
|------------|:-----:|:-------:|:-----------:|:----------:|:----------:|:---------:|
| Items / AML / BOM drafts | R | R | C | R | R | R |
| Submit / review / approve items, BOMs | R | S | S | – | – | R |
| Release items / BOMs | R | S | S¹ | – | – | R |
| Documents / CAD drafts | R | C | C | – | – | R |
| Approve / make effective documents | R | S | S | – | – | R |
| Suppliers | R | S (approve) | R | C | R | R |
| Purchase orders | R | R | R | C, S (approve)² | R | R |
| Receive against PO | R | R | – | T | T | R |
| Incoming inspection / material release | R | S | – | – | – | R |
| Stock transfer / issue / reserve | R | T | – | – | T | R |
| Adjust / scrap | R | S | – | – | T³ | R |
| Quarantine | R | T | T | – | T | R |
| Release from quarantine / NCR disposition | R | S | – | – | – | R |
| Builds (create, issue) | R | R | R | – | T | R |
| Build / unit release | R | S | – | – | – | R |
| ECR raise | R | C | C | C | C | – |
| ECO approve | R | S | S | – | – | R |
| Audit trail view / export | R | R | – | – | – | – |
| Integrity verification run | A | T | – | – | – | – |
| Users, roles, config | A | – | – | – | – | – |
| Signing-authority grants | propose | S | – | – | – | – |
| Backups | A | R | – | – | – | – |

¹ Release typically requires both Engineering Approved and Quality Approved signatures (configurable).
² Above a configurable value threshold, a second approver.
³ Adjustments/scrap above a threshold, or of released material, require Quality signature.

Roles are configurable; permissions are a fixed registry defined in code (adding a permission is a software change).

## 3. Signature meanings (initial)

Authored · Reviewed · Engineering Approved · Quality Approved · Released for Production · Supplier Approved · Material Released · Disposition Approved · Concession Authorised · Build Released · Unit Released · ECO Approved · Rejected.

## 4. Signing procedure

1. User opens the object at a specific revision; UI shows the content summary and the `content_hash`.
2. User selects meaning, enters comment (required for Rejected, concessions and configurable meanings).
3. Re-authentication: password (+ TOTP where configured) submitted with the signing request. No "remember me" for signatures.
4. Server, in one transaction:
   - verifies credentials (failed attempts count toward lockout and are audited);
   - verifies permission, active signing authority for the meaning and scope;
   - verifies SoD rules (e.g. signer did not sign *Authored* on this revision);
   - recomputes `content_hash` and compares with the hash the client displayed;
   - inserts `signature` (printed name, meaning, UTC time, hash, auth method);
   - evaluates the approval rule; if satisfied, performs the state transition;
   - writes audit events.
5. Signature manifestation (name, meaning, date/time) is shown on the record and printed on every PDF of it **[EXT: 21 CFR 11.50 if in scope; REC otherwise]**.

Signatures are never edited or deleted. Withdrawal before completion of an approval set = a new `Rejected`/`Withdrawn` signature and return to Draft.

## 5. Authentication controls

- Argon2id; configurable password policy; breached-password check against a local list **[REC]**.
- Lockout after N failures (rate limit per account and per IP).
- Server-side sessions, HttpOnly + Secure + SameSite=Strict cookie, absolute and idle timeouts, revocation on password/role change.
- CSRF: synchroniser token for all unsafe methods.
- No shared accounts: usernames unique, one person per account **[ORG]** (software cannot prove this).
- Break-glass admin account: documented, sealed credentials, use audited **[ORG]**.

## 0.2 authorities

New permissions separate supplier maintenance, PO maintenance/receipt, BOM authoring, build execution, and read access. New signature meanings are **Supplier Approved**, **Purchase Order Approved**, **BOM Released**, **Build Released**, and **Serial Released**. Administrator retains system administration but is not automatically granted controlled approval authority. Purchasing approves POs; Quality approves suppliers and final build/serial release; Engineering authors and may release BOMs according to configured role grants.
