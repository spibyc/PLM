import { createTheme, defaultVariantColorsResolver, parseThemeColor, type MantineColorsTuple } from "@mantine/core";

// Neutral blue-gray application palette.
const mask: MantineColorsTuple = [
  "#f2f6f7", "#e2eaec", "#c7d5d9", "#a9c0c6", "#88aab2", "#668f99", "#566877",
  "#3f5662", "#31454F", "#192D40",
];

export const theme = createTheme({
  primaryColor: "mask",
  primaryShade: { light: 8, dark: 4 },
  autoContrast: true,
  // Mantine 7's default resolver calculates filled text contrast using the light shade.
  // Resolve both schemes so a lighter dark-mode button also gets readable text.
  variantColorResolver: (input) => {
    const result = defaultVariantColorsResolver(input);
    if (input.variant !== "filled" || input.autoContrast === false) return result;
    const text = (colorScheme: "light" | "dark") =>
      parseThemeColor({ color: input.color, theme: input.theme, colorScheme }).isLight
        ? "var(--mantine-color-black)" : "var(--mantine-color-white)";
    return { ...result, color: `light-dark(${text("light")}, ${text("dark")})` };
  },
  colors: { mask },
  fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', ui-monospace, monospace",
  headings: { fontFamily: "'IBM Plex Sans', system-ui, sans-serif", fontWeight: "600" },
  defaultRadius: "sm",
  black: "#192D40",
  components: {
    Button: { defaultProps: { radius: "sm" } },
    Table: { defaultProps: { verticalSpacing: 6, horizontalSpacing: "sm" } },
  },
});

export const STATUS_COLOR: Record<string, string> = {
  Draft: "gray",
  "Under Review": "yellow",
  Approved: "blue",
  Released: "mask",
  NRND: "orange",
  Obsolete: "dark",
  Prohibited: "red",
  Superseded: "gray",
  Discarded: "gray",
  Proposed: "yellow",
  Disqualified: "red",
  Available: "mask",
  "Pending Inspection": "yellow",
  Quarantined: "red",
};
