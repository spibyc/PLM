// Mirrors the server's MEANING_PERMISSION map; used only to decide which options to show.
// The server enforces signing authority independently.
export const MEANING_PERMS: Record<string, string[]> = {
  "Engineering Approved": ["sign:engineering_approved"],
  "Quality Approved": ["sign:quality_approved"],
  "Released for Production": ["sign:released"],
  Rejected: ["sign:engineering_approved", "sign:quality_approved", "sign:released"],
  "NRND Approved": ["sign:quality_approved"],
  "Obsolescence Approved": ["sign:quality_approved"],
  "Prohibition Approved": ["sign:quality_approved"],
  "Material Released": ["sign:material_released"],
  "Material Rejected": ["sign:material_released"],
  "AML Approved": ["sign:aml_approved"],
  "AML Disqualified": ["sign:aml_approved"],
};
export const COMMENT_REQUIRED = ["Rejected", "NRND Approved", "Obsolescence Approved", "Prohibition Approved",
  "Material Rejected", "AML Disqualified"];

export const REV_MEANINGS: Record<string, string[]> = {
  "Under Review": ["Engineering Approved", "Quality Approved", "Rejected"],
  Approved: ["Released for Production", "Rejected"],
  Released: ["NRND Approved", "Obsolescence Approved", "Prohibition Approved"],
  NRND: ["Obsolescence Approved", "Prohibition Approved"],
  Prohibited: ["Obsolescence Approved"],
};

export const allowedMeanings = (meanings: string[], can: (p: string) => boolean) =>
  meanings.filter((m) => (MEANING_PERMS[m] ?? []).some(can));
