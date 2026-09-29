import { Anchor, Alert, Button, Group, NumberInput, Pagination, Paper, Select, SimpleGrid, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorBox, Loading, PageHeader } from "../components/ui";
import { api, fmtQty, partOptionLabel, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { LedgerTable } from "./Lots";

export function Receive() {
  const nav = useNavigate();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [poSelection, setPoSelection] = useState<{ lineId: string; context: string } | null>(null);
  const [search, setSearch] = useState("");
  const [selectedPart, setSelectedPart] = useState<any>(null);
  const selectedPartLabel = selectedPart ? partOptionLabel(selectedPart) : "";
  const [dq] = useDebouncedValue(search === selectedPartLabel ? "" : search, 250);
  const [itemId, setItemId] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [f, setF] = useState<Record<string, any>>({});
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const items = useQuery({ queryKey: ["items-receivable", dq], queryFn: () => api(`/api/items${qs({ q: dq, limit: 30 })}`) });
  const item = useQuery({ queryKey: ["item", itemId], queryFn: () => api(`/api/items/${itemId}`), enabled: !!itemId });
  const locs = useQuery({ queryKey: ["locations"], queryFn: () => api("/api/locations") });
  const receivable = (items.data?.items ?? []).filter((i: any) => ["Released", "NRND"].includes(i.released_status));
  const partOptions = receivable.filter((i: any) => i.id !== itemId).map((i: any) => ({ value: i.id, label: partOptionLabel(i) }));
  if (itemId && selectedPart) partOptions.unshift({ value: itemId, label: selectedPartLabel });
  const approvedAml = (item.data?.aml ?? []).filter((a: any) => a.status === "Approved");
  const sources: { id: string; distributor: string; source_part_number: string | null; preferred: boolean }[] =
    approvedAml.find((a: any) => a.manufacturer_part_id === f.manufacturer_part_id)?.sources ?? [];
  const preferredSources = sources.filter((source) => source.preferred);
  const defaultSource = sources.length === 1 ? sources[0] : preferredSources.length === 1 ? preferredSources[0] : null;
  const selectedSource = sourceId ? sources.find((source) => source.id === sourceId) : defaultSource;
  const supplierName = selectedSource?.distributor ?? f.supplier_name ?? "";
  const supplierPartNumber = selectedSource?.source_part_number ?? f.supplier_part_number ?? "";
  const context = JSON.stringify([itemId, f.manufacturer_part_id, supplierName, supplierPartNumber]);
  const pos = useQuery({ queryKey: ["pos"], queryFn: () => api<any[]>("/api/purchase-orders"),
    enabled: can("po:read") && !!itemId && !!supplierName.trim() });
  const normalize = (value: string) => value.trim().replace(/\s+/g, " ").toLowerCase();
  const matchingLines = (pos.data ?? []).filter(po => supplierName.trim() &&
    [po.supplier, po.supplier_code].some(name => name && normalize(name) === normalize(supplierName)))
    .flatMap(po => po.lines.filter((line: any) => line.item_id === itemId &&
      (!line.manufacturer_part_id || line.manufacturer_part_id === f.manufacturer_part_id))
      .map((line: any) => ({ po, line, remaining: Number(line.qty_ordered) - Number(line.qty_received) })));
  const selectedPO = poSelection?.context === context
    ? matchingLines.find(entry => entry.line.id === poSelection.lineId) : undefined;
  const hasPOSelection = poSelection?.context === context;
  const receivablePO = selectedPO && ["Approved", "Ordered", "Partially Received"].includes(selectedPO.po.status) && selectedPO.remaining > 0;
  const changeManufacturer = (manufacturer_part_id: string | null) => {
    setSourceId(null);
    setPoSelection(null);
    setF((current) => ({ ...current, manufacturer_part_id, supplier_name: "", supplier_part_number: "", qty: "" }));
  };
  const set = (k: string) => (e: any) => {
    const value = e?.currentTarget ? e.currentTarget.value : e;
    if (k === "supplier_name" || k === "supplier_part_number") {
      setPoSelection(null);
      setF(current => ({ ...current, [k]: value, qty: "" }));
    } else setF(current => ({ ...current, [k]: value }));
  };
  return (
    <>
      <PageHeader title="Receive stock" sub="Creates a new lot in Pending Inspection. It cannot be used until inspection is signed." />
      <Paper withBorder p="md" radius="sm" maw={900}>
        <Stack>
          <Select label="Part" required searchable placeholder="Internal PN, MPN or description" nothingFoundMessage="No released parts match"
            searchValue={search} onSearchChange={setSearch} value={itemId} onChange={(v) => {
              if (v === itemId) return;
              setSelectedPart(receivable.find((i: any) => i.id === v) ?? null);
              setItemId(v); changeManufacturer(null);
            }}
            data={partOptions} />
          {item.data && (approvedAml.length ? (
            <Select label="Manufacturer part received" required data={approvedAml.map((a: any) => ({ value: a.manufacturer_part_id, label: `${a.manufacturer} ${a.mpn}` }))}
              value={f.manufacturer_part_id ?? null} onChange={changeManufacturer} />
          ) : <Alert variant="light" color="yellow">This part has no approved manufacturer source. Stock can be received without one, but an approved source is recommended.</Alert>)}
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberInput label={`Quantity${item.data ? ` (${item.data.uom})` : ""}`} required min={0} max={selectedPO?.remaining} description={selectedPO ? `${fmtQty(selectedPO.remaining)} outstanding; reduce for a partial delivery.` : undefined} value={f.qty ?? ""} onChange={set("qty")} />
            <Select label="Storage location" required searchable value={f.location_id ?? null} onChange={set("location_id")}
              data={(locs.data ?? []).filter((l: any) => l.is_active).map((l: any) => ({ value: l.id, label: `${l.code} ${l.name}` }))} />
            {sources.length > 0 ? <Select label="Supplier" required searchable allowDeselect={false}
              description="Purchasing sources saved on the selected manufacturer part."
              placeholder="Select a purchasing source" value={selectedSource?.id ?? null} onChange={value => {
                setSourceId(value); setPoSelection(null); setF(current => ({ ...current, qty: "" }));
              }}
              data={sources.map((source) => ({ value: source.id,
                label: `${source.distributor}${source.source_part_number ? ` · ${source.source_part_number}` : ""}${source.preferred ? " (preferred)" : ""}` }))} />
              : <TextInput label="Supplier" value={f.supplier_name ?? ""} onChange={set("supplier_name")}
                description={f.manufacturer_part_id ? "No purchasing sources saved for this manufacturer part. Enter the supplier manually." : undefined} />}
            <TextInput label="Supplier part number" readOnly={sources.length > 0 || !!selectedPO}
              value={selectedPO ? selectedPO.line.supplier_part_number ?? "" : supplierPartNumber}
              description={sources.length > 0 ? "Filled from the selected purchasing source." : undefined}
              onChange={set("supplier_part_number")} />
            <Select label="Purchase order reference" searchable clearable
              placeholder="Select a matching PO line (optional)" value={selectedPO?.line.id ?? null}
              disabled={!can("po:read") || !can("po:receive") || !itemId || !supplierName.trim() || pos.isLoading}
              description={!can("po:receive") ? "PO receipt permission is required to receive against an order."
                : "Matches this part and the supplier's registered name or code. Fully received lines are disabled."}
              nothingFoundMessage="No matching purchase orders for this part and supplier"
              data={matchingLines.map(({ po, line, remaining }) => ({ value: line.id,
                label: `${po.po_number} · line ${line.line_no} · ${line.supplier_part_number || "no supplier part number"} · ${remaining > 0 ? `${fmtQty(remaining)} outstanding` : "Fully received"} · ${po.status}`,
                disabled: !["Approved", "Ordered", "Partially Received"].includes(po.status) || remaining <= 0 }))}
              onChange={lineId => {
                const entry = matchingLines.find(entry => entry.line.id === lineId);
                setPoSelection(entry ? { lineId: entry.line.id, context } : null);
                setF(current => ({ ...current, qty: entry?.remaining ?? "" }));
                setErr(null);
              }} />
            <TextInput label="Supplier lot" value={f.supplier_lot ?? ""} onChange={set("supplier_lot")} />
            <TextInput label="Manufacturer lot" value={f.manufacturer_lot ?? ""} onChange={set("manufacturer_lot")} />
            <TextInput label="Date code" value={f.date_code ?? ""} onChange={set("date_code")} />
            <TextInput label="Expiry date" type="date" value={f.expiry_date ?? ""} onChange={set("expiry_date")} />
          </SimpleGrid>
          {selectedPO && <Text size="sm">Receiving against <Anchor component={Link} to={`/purchase-orders/${selectedPO.po.id}`}>{selectedPO.po.po_number}</Anchor>,
            line {selectedPO.line.line_no}. This updates the order's received quantity and creates a linked goods receipt.</Text>}
          {!selectedPO && <Text size="sm" c="dimmed">No PO selected: this receipt will not update a purchase order.</Text>}
          <Textarea label="Notes" value={f.notes ?? ""} onChange={set("notes")} autosize minRows={2} />
          <ErrorBox error={item.error ?? items.error ?? locs.error ?? pos.error ?? err} />
          <Group justify="flex-end">
            <Button loading={busy} disabled={!itemId || !item.data || !!item.error || !f.qty || !f.location_id ||
              (approvedAml.length > 0 && !approvedAml.some((a: any) => a.manufacturer_part_id === f.manufacturer_part_id)) ||
              (sources.length > 0 && !selectedSource) ||
              (hasPOSelection && (!receivablePO || !can("po:receive") || Number(f.qty) > selectedPO.remaining))} onClick={async () => {
              setBusy(true); setErr(null);
              const body = Object.fromEntries(Object.entries({ ...f, item_id: itemId,
                ...(selectedSource ? { supplier_name: selectedSource.distributor, supplier_part_number: selectedSource.source_part_number } : {}),
              }).filter(([, v]) => v !== "" && v !== null && v !== undefined));
              try {
                let lotId: string;
                if (hasPOSelection) {
                  if (!selectedPO || !receivablePO) throw new Error("This PO line is no longer receivable. Refresh and select an outstanding line.");
                  const receipt = await api(`/api/purchase-orders/${selectedPO.po.id}/receive`, { body: {
                    location_id: f.location_id, notes: f.notes || null,
                    lines: [{ po_line_id: selectedPO.line.id, qty: f.qty,
                      expected_qty_received: selectedPO.line.qty_received, manufacturer_part_id: f.manufacturer_part_id || null,
                      supplier_lot: f.supplier_lot || null, manufacturer_lot: f.manufacturer_lot || null,
                      date_code: f.date_code || null, expiry_date: f.expiry_date || null, notes: f.notes || null }],
                  } });
                  lotId = receipt.lot_ids[0];
                  notifications.show({ message: `Received against ${selectedPO.po.po_number} (${receipt.receipt_no})`, color: "mask" });
                } else {
                  const lot = await api("/api/lots", { body }); lotId = lot.id;
                  notifications.show({ message: `Received as ${lot.lot_no}`, color: "mask" });
                }
                await qc.invalidateQueries();
                nav(`/lots/${lotId}`);
              } catch (x) {
                setErr(x);
                if (hasPOSelection) { setPoSelection(null); setF(current => ({ ...current, qty: "" })); }
                // Refresh outstanding quantities after a stale or duplicate receipt attempt.
                await qc.invalidateQueries({ queryKey: ["pos"] });
              } finally { setBusy(false); }
            }}>Receive</Button>
          </Group>
        </Stack>
      </Paper>
      {!receivable.length && !items.isLoading && <Text size="sm" c="dimmed" mt="sm">Only parts with a released revision can be received.</Text>}
    </>
  );
}

const TYPES = ["RECEIPT", "ISSUE", "RETURN", "RESERVE", "RESERVE_RELEASE", "TRANSFER_OUT", "TRANSFER_IN", "ADJUST", "SCRAP",
  "QUARANTINE", "QUARANTINE_RELEASE", "INSPECTION_ACCEPT", "INSPECTION_REJECT"];

export function Transactions() {
  const [type, setType] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const { data, error, isLoading } = useQuery({
    queryKey: ["txns", type, page], queryFn: () => api(`/api/transactions${qs({ txn_type: type, limit: 100, offset: (page - 1) * 100 })}`),
  });
  return (
    <>
      <PageHeader title="Transactions" sub="The inventory ledger. Entries are never edited; corrections are new entries." />
      <Select mb="sm" w={240} placeholder="All transaction types" data={TYPES} value={type} onChange={(v) => { setType(v); setPage(1); }} clearable />
      <ErrorBox error={error} />
      {isLoading ? <Loading /> : <LedgerTable rows={data?.items ?? []} showLot />}
      {data && data.total > 100 && <Pagination mt="sm" total={Math.ceil(data.total / 100)} value={page} onChange={setPage} />}
    </>
  );
}
