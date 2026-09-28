import { Alert, Button, Group, NumberInput, Pagination, Paper, Select, SimpleGrid, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorBox, Loading, PageHeader } from "../components/ui";
import { api, qs } from "../lib/api";
import { LedgerTable } from "./Lots";

export function Receive() {
  const nav = useNavigate();
  const [search, setSearch] = useState("");
  const [dq] = useDebouncedValue(search, 250);
  const [itemId, setItemId] = useState<string | null>(null);
  const [f, setF] = useState<Record<string, any>>({});
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const items = useQuery({ queryKey: ["items-receivable", dq], queryFn: () => api(`/api/items${qs({ q: dq, limit: 30 })}`) });
  const item = useQuery({ queryKey: ["item", itemId], queryFn: () => api(`/api/items/${itemId}`), enabled: !!itemId });
  const locs = useQuery({ queryKey: ["locations"], queryFn: () => api("/api/locations") });
  const receivable = (items.data?.items ?? []).filter((i: any) => ["Released", "NRND"].includes(i.released_status));
  const approvedAml = (item.data?.aml ?? []).filter((a: any) => a.status === "Approved");
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e?.currentTarget ? e.currentTarget.value : e });
  return (
    <>
      <PageHeader title="Receive stock" sub="Creates a new lot in Pending Inspection. It cannot be used until inspection is signed." />
      <Paper withBorder p="md" radius="sm" maw={900}>
        <Stack>
          <Select label="Part" required searchable placeholder="Type a part number or description" nothingFoundMessage="No released parts match"
            searchValue={search} onSearchChange={setSearch} value={itemId} onChange={(v) => { setItemId(v); setF({ ...f, manufacturer_part_id: null }); }}
            data={receivable.map((i: any) => ({ value: i.id, label: `${i.part_number}  ${i.description}` }))} />
          {item.data && (approvedAml.length ? (
            <Select label="Manufacturer part received" required data={approvedAml.map((a: any) => ({ value: a.manufacturer_part_id, label: `${a.manufacturer} ${a.mpn}` }))}
              value={f.manufacturer_part_id ?? null} onChange={set("manufacturer_part_id")} />
          ) : <Alert variant="light" color="yellow">This part has no approved manufacturer source. Stock can be received without one, but an approved source is recommended.</Alert>)}
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberInput label={`Quantity${item.data ? ` (${item.data.uom})` : ""}`} required min={0} value={f.qty ?? ""} onChange={set("qty")} />
            <Select label="Put away to" required searchable value={f.location_id ?? null} onChange={set("location_id")}
              data={(locs.data ?? []).filter((l: any) => l.is_active).map((l: any) => ({ value: l.id, label: `${l.code} ${l.name}` }))} />
            <TextInput label="Supplier" value={f.supplier_name ?? ""} onChange={set("supplier_name")} />
            <TextInput label="Supplier part number" value={f.supplier_part_number ?? ""} onChange={set("supplier_part_number")} />
            <TextInput label="Purchase order reference" value={f.purchase_order_ref ?? ""} onChange={set("purchase_order_ref")} />
            <TextInput label="Supplier lot" value={f.supplier_lot ?? ""} onChange={set("supplier_lot")} />
            <TextInput label="Manufacturer lot" value={f.manufacturer_lot ?? ""} onChange={set("manufacturer_lot")} />
            <TextInput label="Date code" value={f.date_code ?? ""} onChange={set("date_code")} />
            <TextInput label="Expiry date" type="date" value={f.expiry_date ?? ""} onChange={set("expiry_date")} />
          </SimpleGrid>
          <Textarea label="Notes" value={f.notes ?? ""} onChange={set("notes")} autosize minRows={2} />
          <ErrorBox error={err} />
          <Group justify="flex-end">
            <Button loading={busy} disabled={!itemId || !f.qty || !f.location_id} onClick={async () => {
              setBusy(true); setErr(null);
              const body = Object.fromEntries(Object.entries({ ...f, item_id: itemId }).filter(([, v]) => v !== "" && v !== null && v !== undefined));
              try { const lot = await api("/api/lots", { body }); notifications.show({ message: `Received as ${lot.lot_no}`, color: "mask" }); nav(`/lots/${lot.id}`); }
              catch (x) { setErr(x); } finally { setBusy(false); }
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
