import { Button, Group, Modal, NumberInput, Paper, Select, SimpleGrid, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PurchasingSourceFields } from "../components/PurchasingSourceFields";
import { ErrorBox } from "../components/ui";
import { api, partOptionLabel, qs } from "../lib/api";

type Line = { key: string; id?: string; item_id: string; part_number?: string; description?: string | null; mpns?: string[]; mpn?: string | null; manufacturer_part_id: string | null;
  supplier_part_number: string; qty_ordered: number | string; unit_cost: number | string };

export default function PurchaseOrderEditor({ po, onClose, onSaved }: { po?: any; onClose: () => void; onSaved: (po: any) => void }) {
  const [supplierId, setSupplierId] = useState<string | null>(po?.supplier_id ?? null);
  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: () => api<any[]>("/api/suppliers") });
  const supplierOptions = (suppliers.data ?? []).filter(s => s.status === "Approved" || s.id === supplierId)
    .map(s => ({ value: s.id, label: `${s.code} — ${s.name} (${s.status})` }));
  if (supplierId && !supplierOptions.some(s => s.value === supplierId)) supplierOptions.push({ value: supplierId, label: po?.supplier || supplierId });
  const [revision] = useState(po?.revision);
  const [lines, setLines] = useState<Line[]>(() => po ? po.lines.map((l: any) => ({ ...l, key: l.id, supplier_part_number: l.supplier_part_number ?? "" })) : [{ key: crypto.randomUUID(), item_id: "", manufacturer_part_id: null, supplier_part_number: "", qty_ordered: 1, unit_cost: 0 }]);
  const [currency, setCurrency] = useState(po?.currency ?? "GBP");
  const [date, setDate] = useState(po?.expected_date ?? "");
  const [notes, setNotes] = useState(po?.notes ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const valid = !!supplierId && lines.length > 0 && lines.every(l => l.item_id && Number(l.qty_ordered) > 0 && l.unit_cost !== "" && Number(l.unit_cost) >= 0)
    && /^[A-Z]{3}$/.test(currency) && (!po || reason.trim().length >= 3);
  return <Modal opened onClose={() => { if (!busy) onClose(); }} title={po ? `Edit ${po.po_number}` : "New purchase order"} size="xl"
    closeOnClickOutside={false} closeOnEscape={!busy} withCloseButton={!busy}>
    <Stack>
      <Text size="sm" c="dimmed">Draft order changes are audited. This order becomes read-only when approved.</Text>
      <Select label="Supplier" required searchable value={supplierId} data={supplierOptions} disabled={busy} onChange={setSupplierId} />
      <ErrorBox error={suppliers.error} />
      <SimpleGrid cols={2}>
        <TextInput label="Currency" required maxLength={3} value={currency} disabled={busy} onChange={e => setCurrency(e.currentTarget.value.toUpperCase())} />
        <TextInput label="Expected date" type="date" value={date} disabled={busy} onChange={e => setDate(e.currentTarget.value)} />
      </SimpleGrid>
      {lines.map((line, index) => <LineEditor key={line.key} line={line} index={index} busy={busy}
        onChange={next => setLines(current => current.map(l => l.key === line.key ? next : l))}
        onRemove={() => setLines(current => current.filter(l => l.key !== line.key))} />)}
      <Button variant="light" disabled={busy} onClick={() => setLines(current => [...current, { key: crypto.randomUUID(),
        item_id: "", manufacturer_part_id: null, supplier_part_number: "", qty_ordered: 1, unit_cost: 0 }])}>Add line</Button>
      <Textarea label="Notes" value={notes} disabled={busy} onChange={e => setNotes(e.currentTarget.value)} />
      {po && <Textarea label="Reason for change" required value={reason} disabled={busy} onChange={e => setReason(e.currentTarget.value)} />}
      <ErrorBox error={error} />
      <Group justify="flex-end"><Button variant="default" disabled={busy} onClick={onClose}>Cancel</Button>
        <Button loading={busy} disabled={!valid} onClick={async () => {
          setBusy(true); setError(null);
          try {
            const updated = await api(po ? `/api/purchase-orders/${po.id}` : "/api/purchase-orders", { method: po ? "PUT" : "POST", body: {
              revision, supplier_id: supplierId, currency, expected_date: date || null, notes: notes || null, reason: reason.trim(),
              lines: lines.map(l => ({ id: l.id, item_id: l.item_id, manufacturer_part_id: l.manufacturer_part_id,
                supplier_part_number: l.supplier_part_number || null, qty_ordered: l.qty_ordered, unit_cost: l.unit_cost })),
            } });
            onSaved(updated);
          } catch (e) { setError(e); } finally { setBusy(false); }
        }}>{po ? "Save changes" : "Create PO"}</Button></Group>
    </Stack>
  </Modal>;
}

function LineEditor({ line, index, busy, onChange, onRemove }: {
  line: Line; index: number; busy: boolean; onChange: (line: Line) => void; onRemove: () => void;
}) {
  // Search results may omit the selected part. Keep its label independent of those
  // results so Mantine does not repeatedly replace the input and trigger another search.
  const selectedLabel = line.item_id ? partOptionLabel(line) : "";
  const [search, setSearch] = useState(selectedLabel);
  const [q] = useDebouncedValue(search === selectedLabel ? "" : search, 250);
  const items = useQuery({ queryKey: ["po-edit-items", q], queryFn: () => api(`/api/items${qs({ q, limit: 30 })}`) });
  const options = (items.data?.items ?? []).filter((i: any) => i.id !== line.item_id)
    .map((i: any) => ({ value: i.id, label: partOptionLabel(i) }));
  if (line.item_id) options.unshift({ value: line.item_id, label: selectedLabel });
  return <Paper withBorder p="sm"><Stack gap="xs">
    <Group justify="space-between"><Text fw={600}>Line {index + 1}</Text><Button color="red" variant="subtle" size="xs" disabled={busy} onClick={onRemove}>Remove line {index + 1}</Button></Group>
    <Select label={`Part for line ${index + 1}`} required searchable data={options} value={line.item_id || null}
      searchValue={search} onSearchChange={setSearch} disabled={busy}
      onChange={value => {
        if (value === line.item_id) return;
        const selected = (items.data?.items ?? []).find((i: any) => i.id === value);
        onChange({ ...line, item_id: value || "", part_number: selected?.part_number, description: selected?.description, mpns: selected?.mpns, mpn: null,
          manufacturer_part_id: null, supplier_part_number: "" });
      }} />
    <PurchasingSourceFields itemId={line.item_id || null} manufacturerPartId={line.manufacturer_part_id}
      supplierPartNumber={line.supplier_part_number} suffix={` for line ${index + 1}`} disabled={busy}
      onChange={(manufacturer_part_id, supplier_part_number) => onChange({ ...line, manufacturer_part_id, supplier_part_number })} />
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <NumberInput label={`Quantity for line ${index + 1}`} required min={0} value={line.qty_ordered} disabled={busy} onChange={v => onChange({ ...line, qty_ordered: v })} />
      <NumberInput label={`Unit cost for line ${index + 1}`} required min={0} decimalScale={6} value={line.unit_cost} disabled={busy} onChange={v => onChange({ ...line, unit_cost: v })} />
    </SimpleGrid>
    <ErrorBox error={items.error} />
  </Stack></Paper>;
}
