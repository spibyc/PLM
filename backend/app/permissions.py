"""Permission registry (fixed in code) and default role definitions.

Permissions are granted to roles; roles to users. Signature permissions ("sign:*") represent the
authority to apply a specific signature meaning. The Administrator role deliberately holds none.
"""

PERMISSIONS: dict[str, str] = {
    "users:admin": "Manage user accounts and role assignments",
    "admin:override": "Superuser: edit controlled records and permanently delete eligible records",
    "audit:read": "View and export the audit trail",
    "item:read": "View parts/items",
    "item:write": "Create items, edit Draft revisions, submit for review",
    "aml:write": "Propose manufacturer parts / AML entries",
    "files:upload": "Upload files to Draft records and lots",
    "files:verify": "Run file integrity verification",
    "location:read": "View storage locations",
    "location:delete": "Retire storage locations and move their stock to Unallocated",
    "location:write": "Create and edit storage locations",
    "inventory:read": "View lots, balances and transactions",
    "inventory:receive": "Receive stock into new lots",
    "inventory:transact": "Issue, return, reserve and transfer stock",
    "inventory:adjust": "Post inventory adjustments and scrap",
    "inventory:quarantine": "Place lots into quarantine",
    "sign:engineering_approved": "Sign 'Engineering Approved'",
    "sign:quality_approved": "Sign 'Quality Approved' and lifecycle changes",
    "sign:released": "Sign 'Released for Production'",
    "sign:material_released": "Sign 'Material Released' (incoming inspection / quarantine release)",
    "sign:aml_approved": "Approve AML entries",
    "supplier:read": "View suppliers", "supplier:write": "Create and edit suppliers",
    "po:read": "View purchase orders", "po:write": "Create and edit purchase orders", "po:receive": "Receive against purchase orders",
    "bom:read": "View BOMs", "bom:write": "Create and edit draft BOM revisions",
    "build:read": "View builds, serials and genealogy", "build:write": "Create builds and issue material",
    "sign:supplier_approved": "Approve suppliers", "sign:po_approved": "Approve purchase orders",
    "sign:bom_released": "Release BOM revisions", "sign:build_released": "Release production builds and serials",
    "document:read": "View the controlled document register and revision history",
    "document:write": "Create controlled documents and draft revisions",
    "document:upload": "Upload files to draft controlled document revisions",
    "sign:document_released": "Approve and release controlled document revisions",
    "sign:document_obsolete": "Obsolete controlled documents",
}

DEFAULT_ROLES: dict[str, tuple[str, list[str]]] = {
    "ADMIN": ("Administrator / Superuser", list(PERMISSIONS.keys())),
    "QUALITY": ("Quality", [
        "audit:read", "item:read", "location:read", "inventory:read", "inventory:quarantine",
        "inventory:adjust", "files:upload", "files:verify",
        "sign:quality_approved", "sign:released", "sign:material_released", "sign:aml_approved", "supplier:read", "po:read", "bom:read", "build:read", "sign:supplier_approved", "sign:bom_released", "sign:build_released", "document:read", "document:write", "document:upload", "sign:document_released", "sign:document_obsolete",
    ]),
    "ENGINEERING": ("Engineering", [
        "item:read", "item:write", "aml:write", "files:upload", "location:read", "inventory:read",
        "inventory:quarantine", "sign:engineering_approved", "sign:released", "sign:aml_approved", "supplier:read", "po:read", "bom:read", "bom:write", "build:read", "sign:bom_released", "document:read", "document:write", "document:upload",
    ]),
    "PURCHASING": ("Purchasing", [
        "item:read", "aml:write", "location:read", "inventory:read", "inventory:receive", "files:upload", "supplier:read", "supplier:write", "po:read", "po:write", "po:receive", "bom:read", "sign:po_approved", "document:read",
    ]),
    "PRODUCTION": ("Production", [
        "item:read", "location:read", "location:write", "inventory:read", "inventory:receive",
        "inventory:transact", "inventory:adjust", "inventory:quarantine", "files:upload", "supplier:read", "po:read", "bom:read", "build:read", "build:write", "document:read",
    ]),
    "READONLY": ("Read Only", ["item:read", "location:read", "inventory:read", "supplier:read", "po:read", "bom:read", "build:read", "document:read"]),
}
