import { Select, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ErrorBox } from "./ui";

type Source = { id: string; distributor: string; source_part_number: string | null; preferred: boolean; manufacturer_part_id: string; manufacturer: string; mpn: string };
const preferred = (sources: Source[]) => sources.length === 1 ? sources[0] : sources.filter(s => s.preferred).length === 1 ? sources.find(s => s.preferred) : undefined;

/** Copies the selected purchasing SKU into the order; saved PO values remain snapshots. */
export function PurchasingSourceFields({ itemId, manufacturerPartId, supplierPartNumber, suffix = "", disabled = false, onChange }: {
  itemId: string | null; manufacturerPartId: string | null; supplierPartNumber: string;
  suffix?: string; disabled?: boolean;
  onChange: (manufacturerPartId: string | null, supplierPartNumber: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const item = useQuery({ queryKey: ["item", itemId], queryFn: () => api(`/api/items/${itemId}`), enabled: !!itemId });
  const aml = (item.data?.aml ?? []).filter((a: any) => a.status === "Approved");
  const allSources: Source[] = aml.flatMap((a: any) => (a.sources ?? []).map((s: any) => ({ ...s,
    manufacturer_part_id: a.manufacturer_part_id, manufacturer: a.manufacturer, mpn: a.mpn })));
  const sources = manufacturerPartId ? allSources.filter(s => s.manufacturer_part_id === manufacturerPartId) : allSources;
  const matches = sources.filter(s => s.manufacturer_part_id === manufacturerPartId && (s.source_part_number ?? "") === supplierPartNumber);
  const selected = matches.find(s => s.id === selectedId) ?? matches[0];
  const automatic = preferred(sources);
  useEffect(() => {
    if (!disabled && !manufacturerPartId && !supplierPartNumber && automatic && automatic.source_part_number) {
      onChange(automatic.manufacturer_part_id, automatic.source_part_number);
    }
  }, [disabled, manufacturerPartId, supplierPartNumber, automatic?.id, automatic?.source_part_number, automatic?.manufacturer_part_id]);
  const manufacturerOptions = aml.map((a: any) => ({ value: a.manufacturer_part_id, label: `${a.manufacturer} ${a.mpn}` }));
  if (manufacturerPartId && !manufacturerOptions.some((a: any) => a.value === manufacturerPartId)) {
    const saved = (item.data?.aml ?? []).find((a: any) => a.manufacturer_part_id === manufacturerPartId);
    manufacturerOptions.push({ value: manufacturerPartId, label: saved ? `${saved.manufacturer} ${saved.mpn} (${saved.status})` : "Saved manufacturer part" });
  }
  return <>
    <Select label={`Manufacturer part${suffix}`} clearable disabled={disabled || !itemId || item.isLoading} value={manufacturerPartId}
      data={manufacturerOptions} onChange={value => {
        const source = preferred(allSources.filter(s => s.manufacturer_part_id === value));
        setSelectedId(source?.id ?? null);
        onChange(value, source?.source_part_number ?? "");
      }} />
    {sources.length > 0 && <Select label={`Purchasing source${suffix}`} searchable allowDeselect={false}
      description="Choose the source used for this order. Its Source part number fills the supplier part number."
      disabled={disabled} placeholder="Select a purchasing source" value={selected?.id ?? null}
      data={sources.map(s => ({ value: s.id, label: `${s.distributor} · ${s.source_part_number || "No source part number"} · ${s.manufacturer} ${s.mpn}${s.preferred ? " (preferred)" : ""}` }))}
      onChange={id => { const source = sources.find(s => s.id === id); if (source) { setSelectedId(source.id); onChange(source.manufacturer_part_id, source.source_part_number ?? ""); } }} />}
    <TextInput label={`Supplier part number${suffix}`} maxLength={100} value={supplierPartNumber} disabled={disabled || item.isLoading}
      readOnly={sources.length > 0}
      description={sources.length ? "From the selected purchasing source's Source part number." : "No saved purchasing sources for this selection; enter manually if needed."}
      onChange={e => onChange(manufacturerPartId, e.currentTarget.value)} />
    <ErrorBox error={item.error} />
  </>;
}
