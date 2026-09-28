import { Anchor, Button, Checkbox, Group, Modal, Paper, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconPlus, IconPrinter } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Empty, ErrorBox, Ident, LinkRow, Loading, PageHeader, StatusBadge } from "../components/ui";
import { api, fmtDate, fmtDay, fmtQty } from "../lib/api";
import { useAuth } from "../lib/auth";

const KINDS = ["site", "room", "cabinet", "drawer", "bin", "compartment"];

export default function Locations() {
  const { can } = useAuth();
  const [creating, setCreating] = useState<string | null | undefined>(undefined);
  const { data, error, isLoading } = useQuery({ queryKey: ["locations"], queryFn: () => api("/api/locations") });
  const tree = useMemo(() => {
    const kids: Record<string, any[]> = {};
    (data ?? []).forEach((l: any) => { (kids[l.parent_id ?? "root"] ||= []).push(l); });
    const out: { loc: any; depth: number }[] = [];
    const walk = (pid: string, depth: number) => (kids[pid] ?? []).forEach((l) => { out.push({ loc: l, depth }); walk(l.id, depth + 1); });
    walk("root", 0);
    return out;
  }, [data]);
  return (
    <>
      <PageHeader title="Locations" sub="Where stock is kept. Every location has a printable QR label."
        actions={can("location:write") && <Button leftSection={<IconPlus size={16} />} onClick={() => setCreating(null)}>New site</Button>} />
      <ErrorBox error={error} />
      {isLoading ? <Loading /> : !tree.length ? <Empty>No locations yet. Start by creating a site.</Empty> : (
        <Paper withBorder radius="sm">
          <Table.ScrollContainer minWidth={700}>
            <Table highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>Code</Table.Th><Table.Th>Name</Table.Th><Table.Th>Kind</Table.Th><Table.Th ta="right">Qty held</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {tree.map(({ loc, depth }) => (
                  <LinkRow key={loc.id} to={`/locations/${loc.id}`}>
                    <Table.Td style={{ paddingLeft: 12 + depth * 20 }}><Ident>{loc.code}</Ident></Table.Td>
                    <Table.Td>{loc.name}{loc.is_quarantine && <Text span c="red.8" size="xs" fw={600}> quarantine</Text>}{!loc.is_active && <Text span c="dimmed" size="xs"> inactive</Text>}</Table.Td>
                    <Table.Td>{loc.kind}</Table.Td>
                    <Table.Td ta="right" className="ident">{loc.qty_on_hand ? fmtQty(loc.qty_on_hand) : ""}</Table.Td>
                    <Table.Td onClick={(e) => e.stopPropagation()}>
                      {can("location:write") && loc.kind !== "compartment" && loc.is_active &&
                        <Button size="compact-xs" variant="subtle" onClick={() => setCreating(loc.id)}>Add inside</Button>}
                    </Table.Td>
                  </LinkRow>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
      <NewLocation parentId={creating} all={data ?? []} onClose={() => setCreating(undefined)} />
    </>
  );
}

function NewLocation({ parentId, all, onClose }: { parentId: string | null | undefined; all: any[]; onClose: () => void }) {
  const qc = useQueryClient();
  const parent = all.find((l) => l.id === parentId);
  const kinds = parent ? KINDS.slice(KINDS.indexOf(parent.kind) + 1) : ["site"];
  const [f, setF] = useState<Record<string, any>>({});
  const [err, setErr] = useState<unknown>(null);
  const kind = f.kind ?? kinds[0];
  return (
    <Modal opened={parentId !== undefined} onClose={() => { setF({}); setErr(null); onClose(); }} title={parent ? `New location inside ${parent.code}` : "New site"}>
      <Stack>
        <Select label="Kind" data={kinds} value={kind} onChange={(v) => setF({ ...f, kind: v })} allowDeselect={false} />
        <TextInput label="Code segment" description={`Letters and digits. Full code: ${parent ? parent.code + "-" : ""}${(f.segment ?? "").toUpperCase() || "…"}`}
          value={f.segment ?? ""} onChange={(e) => setF({ ...f, segment: e.currentTarget.value.toUpperCase() })} maxLength={16} required />
        <TextInput label="Name" value={f.name ?? ""} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} required />
        <Checkbox label="Quarantine location (stock here can never be issued to production)" checked={!!f.is_quarantine || !!parent?.is_quarantine}
          disabled={!!parent?.is_quarantine} onChange={(e) => setF({ ...f, is_quarantine: e.currentTarget.checked })} />
        <ErrorBox error={err} />
        <Button disabled={!f.segment || !f.name} onClick={async () => {
          try {
            await api("/api/locations", { body: { parent_id: parentId ?? null, kind, segment: f.segment, name: f.name, is_quarantine: !!f.is_quarantine } });
            qc.invalidateQueries({ queryKey: ["locations"] }); setF({}); onClose();
            notifications.show({ message: "Location created", color: "mask" });
          } catch (x) { setErr(x); }
        }}>Create location</Button>
      </Stack>
    </Modal>
  );
}

export function LocationDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: loc, error, isLoading } = useQuery({ queryKey: ["location", id], queryFn: () => api(`/api/locations/${id}`) });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  return (
    <>
      <Text size="sm" mb={4}>
        <Anchor component={Link} to="/locations">Locations</Anchor>
        {loc.ancestors.map((a: any) => <span key={a.id}> / <Anchor component={Link} to={`/locations/${a.id}`}>{a.code}</Anchor></span>)}
      </Text>
      <PageHeader title={<Ident size="lg">{loc.code}</Ident>} sub={`${loc.path} · ${loc.kind}${loc.is_quarantine ? " · quarantine" : ""}${loc.is_active ? "" : " · inactive"}`}
        actions={<Button variant="default" leftSection={<IconPrinter size={16} />} onClick={() => nav(`/labels?locations=${loc.id}${loc.children.map((c: any) => "," + c.id).join("")}`)}>Print labels</Button>} />
      <Group align="flex-start" gap="lg" wrap="wrap">
        <Paper withBorder p="sm" radius="sm"><img src={`/api/qr/location/${loc.id}.svg`} width={140} height={140} alt={`QR code for ${loc.code}`} /></Paper>
        <Stack style={{ flex: 1, minWidth: 320 }}>
          <Paper withBorder radius="sm" p="md">
            <Text fw={600} mb="xs">Stock here</Text>
            {!loc.stock.length ? <Empty>Nothing stored here.</Empty> : (
              <Table.ScrollContainer minWidth={640}><Table>
                <Table.Thead><Table.Tr><Table.Th>Lot</Table.Th><Table.Th>Part</Table.Th><Table.Th>Status</Table.Th><Table.Th ta="right">On hand</Table.Th><Table.Th ta="right">Reserved</Table.Th><Table.Th>Expiry</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {loc.stock.map((s: any) => (
                    <LinkRow key={s.lot_id} to={`/lots/${s.lot_id}`}>
                      <Table.Td><Ident>{s.lot_no}</Ident></Table.Td>
                      <Table.Td><Ident>{s.part_number}</Ident> <Text span size="sm" c="dimmed">{s.description}</Text></Table.Td>
                      <Table.Td><StatusBadge status={s.lot_status} /></Table.Td>
                      <Table.Td ta="right" className="ident">{fmtQty(s.qty_on_hand)} {s.uom}</Table.Td>
                      <Table.Td ta="right" className="ident">{s.qty_reserved ? fmtQty(s.qty_reserved) : ""}</Table.Td>
                      <Table.Td>{fmtDay(s.expiry_date)}</Table.Td>
                    </LinkRow>
                  ))}
                </Table.Tbody>
              </Table></Table.ScrollContainer>
            )}
          </Paper>
          {loc.children.length > 0 && (
            <Paper withBorder radius="sm" p="md">
              <Text fw={600} mb="xs">Inside this {loc.kind}</Text>
              <Group gap="xs">{loc.children.map((c: any) => <Button key={c.id} size="xs" variant="default" component={Link} to={`/locations/${c.id}`}><span className="ident">{c.code}</span>&nbsp;{c.name}</Button>)}</Group>
            </Paper>
          )}
          <Paper withBorder radius="sm" p="md">
            <Text fw={600} mb="xs">Recent movements</Text>
            {!loc.recent_movements.length ? <Empty>No movements.</Empty> : (
              <Table.ScrollContainer minWidth={560}><Table>
                <Table.Tbody>
                  {loc.recent_movements.map((m: any) => (
                    <Table.Tr key={m.id}><Table.Td>{fmtDate(m.occurred_at)}</Table.Td><Table.Td>{m.txn_type}</Table.Td><Table.Td><Ident>{m.lot_no}</Ident></Table.Td>
                      <Table.Td ta="right" className="ident">{m.d_on_hand > 0 ? "+" : ""}{fmtQty(m.d_on_hand)}</Table.Td><Table.Td>{m.by}</Table.Td></Table.Tr>
                  ))}
                </Table.Tbody>
              </Table></Table.ScrollContainer>
            )}
          </Paper>
        </Stack>
      </Group>
    </>
  );
}

/** Printable label sheet (62 x 29 mm labels). Query: ?locations=id,id or ?lots=id,id */
export function Labels() {
  const params = new URLSearchParams(window.location.search);
  const locIds = (params.get("locations") ?? "").split(",").filter(Boolean);
  const lotIds = (params.get("lots") ?? "").split(",").filter(Boolean);
  const { data, isLoading, error } = useQuery({
    queryKey: ["labels", locIds, lotIds],
    queryFn: async () => [
      ...(await Promise.all(locIds.map((i) => api(`/api/locations/${i}`)))).map((l: any) => ({ key: l.id, qr: `/api/qr/location/${l.id}.svg`, code: l.code, line1: l.name, line2: l.path })),
      ...(await Promise.all(lotIds.map((i) => api(`/api/lots/${i}`)))).map((l: any) => ({ key: l.id, qr: `/api/qr/lot/${l.id}.svg`, code: l.lot_no, line1: `${l.part_number} rev ${l.revision}`, line2: `${l.description} · rcvd ${fmtDay(l.received_at)}${l.expiry_date ? " · exp " + fmtDay(l.expiry_date) : ""}` })),
    ],
  });
  if (isLoading) return <Loading />;
  return (
    <>
      <div className="no-print">
        <PageHeader title="Labels" sub="62 × 29 mm labels. Use your browser's print dialog; set margins to none and scale to 100%."
          actions={<Button leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>Print</Button>} />
        <ErrorBox error={error} />
      </div>
      <div className="label-sheet">
        {data?.map((l) => (
          <div className="label" key={l.key}>
            <img src={l.qr} alt="" />
            <div style={{ minWidth: 0 }}>
              <div className="ident">{l.code}</div>
              <small>{l.line1}</small>
              <small>{l.line2}</small>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
