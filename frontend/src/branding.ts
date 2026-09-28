export type Branding = { productName: string; organizationName: string; tagline: string; logoPath: string; logoAlt: string };
declare global { interface Window { PLM_BRANDING?: Partial<Branding>; } }
const defaults: Branding = { productName: "PLM", organizationName: "", tagline: "Product Lifecycle Management", logoPath: "/branding/logo.png", logoAlt: "PLM logo" };
export const branding: Branding = { ...defaults, ...(window.PLM_BRANDING ?? {}) };
export const subtitle = branding.organizationName ? `${branding.organizationName} — ${branding.tagline}` : branding.tagline;
