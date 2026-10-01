import { Button, Group, Modal, NumberInput, Pagination, Paper, Select, SimpleGrid, Stack, Table, Text, TextInput, Textarea } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconPlus } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, Ident, LinkRow, Loading, PageHeader, StatusBadge } from "../components/ui";
import { api, fmtQty, qs } from "../lib/api";
import { useAuth } from "../lib/auth";

const PAGE = 50;
const STATUSES = ["Draft", "Under Review", "Approved", "Released", "NRND", "Obsolete", "Prohibited"];

export default function Parts() {
  const { can } = useAuth();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [dq] = useDebouncedValue(q, 250);
  const status = sp.get("status");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const { data, error, isLoading } = useQuery({
    queryKey: ["items", dq, status, page],
    queryFn: () => api(`/api/items${qs({ q: dq, status, limit: PAGE, offset: (page - 1) * PAGE })}`),
  });
  return (
    <>
      <PageHeader title="Parts" sub="Internal part numbers with their controlled revisions"
        actions={can("item:write") && <Button leftSection={<IconPlus size={16} />} onClick={() => setCreating(true)}>New part</Button>} />
      <Group mb="sm">
        <TextInput placeholder="Filter by part number, description, value or MPN" value={q} onChange={(e) => { setQ(e.currentTarget.value); setPage(1); }} w={380} />
        <Select placeholder="Any latest status" data={STATUSES} value={status} clearable w={200}
          onChange={(v) => { setPage(1); setSp(v ? { status: v } : {}); }} />
      </Group>
      <ErrorBox error={error} />
      {isLoading ? <Loading /> : !data?.items.length ? <Empty>No parts match. {can("item:write") && "Create one with New part."}</Empty> : (
        <Paper withBorder radius="sm">
          <Table.ScrollContainer minWidth={900}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Part number</Table.Th><Table.Th>MPN</Table.Th><Table.Th>Description</Table.Th><Table.Th>Value</Table.Th><Table.Th>Package</Table.Th>
                  <Table.Th>Released</Table.Th><Table.Th>Latest</Table.Th><Table.Th ta="right">Available</Table.Th><Table.Th ta="right">On hand</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((i: any) => (
                  <LinkRow key={i.id} to={`/parts/${i.id}`}>
                    <Table.Td><Ident>{i.part_number}</Ident></Table.Td>
                    <Table.Td>{i.mpns?.length ? i.mpns.map((mpn: string) => <div key={mpn}><Ident>{mpn}</Ident></div>) : <Text size="sm" c="dimmed">—</Text>}</Table.Td>
                    <Table.Td><Text size="sm" lineClamp={1}>{i.description}</Text></Table.Td>
                    <Table.Td>{i.value}</Table.Td><Table.Td>{i.package}</Table.Td>
                    <Table.Td>{i.released_revision ? <Group gap={6} wrap="nowrap"><Text size="sm">{i.released_revision}</Text><StatusBadge status={i.released_status} /></Group> : <Text size="sm" c="dimmed">none</Text>}</Table.Td>
                    <Table.Td><Group gap={6} wrap="nowrap"><Text size="sm">{i.latest_revision}</Text>{i.latest_revision !== i.released_revision && <StatusBadge status={i.latest_status} />}</Group></Table.Td>
                    <Table.Td ta="right" className="ident" c={i.min_stock > 0 && i.available < i.min_stock ? "var(--plm-danger)" : undefined}>{fmtQty(i.available)}</Table.Td>
                    <Table.Td ta="right" className="ident">{fmtQty(i.on_hand)}</Table.Td>
                  </LinkRow>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
      {data && data.total > PAGE && <Pagination mt="sm" total={Math.ceil(data.total / PAGE)} value={page} onChange={setPage} />}
      <NewPart opened={creating} onClose={() => setCreating(false)} />
    </>
  );
}

function NewPart({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const meta = useQuery({ queryKey: ["item-meta"], queryFn: () => api("/api/items/meta"), enabled: opened });
  const [f, setF] = useState<Record<string, any>>({ item_class: "component", uom: "pcs", min_stock: 0 });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e?.currentTarget ? e.currentTarget.value : e });
  return (
    <Modal opened={opened} onClose={onClose} title="New part" size="lg">
      <Stack>
        <Text size="sm" c="dimmed">A part number is assigned automatically. The part starts as revision A in Draft.</Text>
        <SimpleGrid cols={2}>
          <Select label="Class" data={meta.data?.item_classes ?? []} value={f.item_class} onChange={set("item_class")} allowDeselect={false} />
          <Select label="Unit of measure" data={meta.data?.uoms ?? []} value={f.uom} onChange={set("uom")} allowDeselect={false} />
        </SimpleGrid>
        <TextInput label="Description" required value={f.description ?? ""} onChange={set("description")} placeholder="e.g. RES 10k 0603 1% 0.1W" />
        <SimpleGrid cols={2}>
          <TextInput label="Category" value={f.category ?? ""} onChange={set("category")} />
          <TextInput label="Subcategory" value={f.subcategory ?? ""} onChange={set("subcategory")} />
          <TextInput label="Component type" value={f.component_type ?? ""} onChange={set("component_type")} />
          <TextInput label="Value" value={f.value ?? ""} onChange={set("value")} />
          <TextInput label="Package" value={f.package ?? ""} onChange={set("package")} />
          <NumberInput label="Minimum stock" min={0} value={f.min_stock} onChange={set("min_stock")} />
        </SimpleGrid>
        <Textarea label="Notes" value={f.notes ?? ""} onChange={set("notes")} autosize minRows={2} />
        <ErrorBox error={err} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button loading={busy} disabled={!f.description?.trim()} onClick={async () => {
            setBusy(true); setErr(null);
            try { const r = await api("/api/items", { body: f }); onClose(); nav(`/parts/${r.id}`); } catch (x) { setErr(x); } finally { setBusy(false); }
          }}>Create part</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
