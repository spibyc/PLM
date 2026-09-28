import {
  Alert, Anchor, Button, Code, FileInput, Group, Menu, Modal, NumberInput, Pagination, Paper, Select, SimpleGrid, Stack,
  Table, Tabs, Text, TextInput, Textarea,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconChevronDown, IconDownload, IconPrinter } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { SignDialog } from "../components/SignDialog";
import { Empty, ErrorBox, Ident, LinkRow, Loading, PageHeader, StatusBadge } from "../components/ui";
import { api, fmtDate, fmtDay, fmtQty, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { COMMENT_REQUIRED, allowedMeanings } from "../lib/signing";
import { History } from "./PartDetail";

const PAGE = 50;

export default function Lots() {
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState("");
  const [dq] = useDebouncedValue(q, 250);
  const [page, setPage] = useState(1);
  const status = sp.get("status");
  const [includeEmpty, setIncludeEmpty] = useState(false);
  const { data, error, isLoading } = useQuery({
    queryKey: ["lots", dq, status, includeEmpty, page],
    queryFn: () => api(`/api/lots${qs({ q: dq, status, include_empty: includeEmpty, limit: PAGE, offset: (page - 1) * PAGE })}`),
  });
  return (
    <>
      <PageHeader title="Lots" sub="Every received lot, where it is, and whether it can be used" />
      <Group mb="sm">
        <TextInput placeholder="Lot, part number, MPN, supplier lot, date code" value={q} onChange={(e) => { setQ(e.currentTarget.value); setPage(1); }} w={380} />
        <Select placeholder="Any status" data={["Pending Inspection", "Available", "Quarantined"]} value={status} clearable w={200}
          onChange={(v) => { setPage(1); setSp(v ? { status: v } : {}); }} />
        <Select w={200} value={includeEmpty ? "all" : "stock"} onChange={(v) => setIncludeEmpty(v === "all")} allowDeselect={false}
          data={[{ value: "stock", label: "With stock on hand" }, { value: "all", label: "Including consumed" }]} />
      </Group>
      <ErrorBox error={error} />
      {isLoading ? <Loading /> : !data?.items.length ? <Empty>No lots match.</Empty> : (
        <Paper withBorder radius="sm">
          <Table.ScrollContainer minWidth={1000}>
            <Table striped>
              <Table.Thead><Table.Tr><Table.Th>Lot</Table.Th><Table.Th>Part</Table.Th><Table.Th>Rev</Table.Th><Table.Th>Status</Table.Th><Table.Th>Manufacturer / MPN</Table.Th><Table.Th>Date code</Table.Th><Table.Th ta="right">On hand</Table.Th><Table.Th ta="right">Reserved</Table.Th><Table.Th>Expiry</Table.Th><Table.Th>Received</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {data.items.map((l: any) => (
                  <LinkRow key={l.id} to={`/lots/${l.id}`}>
                    <Table.Td><Ident>{l.lot_no}</Ident></Table.Td>
                    <Table.Td><Ident>{l.part_number}</Ident><Text size="xs" c="dimmed" lineClamp={1}>{l.description}</Text></Table.Td>
                    <Table.Td>{l.revision}</Table.Td><Table.Td><StatusBadge status={l.status} /></Table.Td>
                    <Table.Td>{l.manufacturer} <Ident>{l.mpn}</Ident></Table.Td><Table.Td>{l.date_code}</Table.Td>
                    <Table.Td ta="right" className="ident">{fmtQty(l.qty_on_hand)} {l.uom}</Table.Td>
                    <Table.Td ta="right" className="ident">{l.qty_reserved ? fmtQty(l.qty_reserved) : ""}</Table.Td>
                    <Table.Td>{fmtDay(l.expiry_date)}</Table.Td><Table.Td>{fmtDay(l.received_at)}</Table.Td>
                  </LinkRow>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
      {data && data.total > PAGE && <Pagination mt="sm" total={Math.ceil(data.total / PAGE)} value={page} onChange={setPage} />}
    </>
  );
}

type Op = "issue" | "return" | "reserve" | "release-reservation" | "transfer" | "adjust" | "scrap" | "quarantine";
const OP_TITLES: Record<Op, string> = {
  issue: "Issue to production", return: "Return to stock", reserve: "Reserve", "release-reservation": "Release reservation",
  transfer: "Move to another location", adjust: "Post adjustment", scrap: "Scrap", quarantine: "Quarantine lot",
};

export function LotDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const nav = useNavigate();
  const { can } = useAuth();
  const { data: lot, error, isLoading } = useQuery({ queryKey: ["lot", id], queryFn: () => api(`/api/lots/${id}`) });
  const [op, setOp] = useState<Op | null>(null);
  const [sign, setSign] = useState<"inspect" | "release" | null>(null);
  const refresh = (d?: any) => { if (d) qc.setQueryData(["lot", id], d); qc.invalidateQueries({ queryKey: ["lot", id] }); qc.invalidateQueries({ queryKey: ["audit-entity"] }); };
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const inspectMeanings = allowedMeanings(["Material Released", "Material Rejected"], can);
  const releaseMeanings = allowedMeanings(["Material Released"], can);
  return (
    <>
      <PageHeader title={<Group gap="sm"><Ident size="lg">{lot.lot_no}</Ident><StatusBadge status={lot.status} /></Group>}
        sub={<><Anchor component={Link} to={`/parts/${lot.item_id}`}><span className="ident">{lot.part_number}</span></Anchor> rev {lot.revision} · {lot.description}</>}
        actions={<>
          <Button variant="default" leftSection={<IconPrinter size={16} />} onClick={() => nav(`/labels?lots=${lot.id}`)}>Label</Button>
          {lot.status === "Pending Inspection" && inspectMeanings.length > 0 && <Button onClick={() => setSign("inspect")}>Record inspection…</Button>}
          {lot.status === "Quarantined" && releaseMeanings.length > 0 && <Button onClick={() => setSign("release")}>Release from quarantine…</Button>}
          <Menu position="bottom-end">
            <Menu.Target><Button variant="default" rightSection={<IconChevronDown size={14} />}>Stock action</Button></Menu.Target>
            <Menu.Dropdown>
              {can("inventory:transact") && (["issue", "return", "reserve", "release-reservation", "transfer"] as Op[]).map((o) =>
                <Menu.Item key={o} onClick={() => setOp(o)}>{OP_TITLES[o]}</Menu.Item>)}
              {can("inventory:adjust") && <><Menu.Divider /><Menu.Item onClick={() => setOp("adjust")}>{OP_TITLES.adjust}</Menu.Item><Menu.Item onClick={() => setOp("scrap")}>{OP_TITLES.scrap}</Menu.Item></>}
              {can("inventory:quarantine") && lot.status !== "Quarantined" && <><Menu.Divider /><Menu.Item color="red" onClick={() => setOp("quarantine")}>{OP_TITLES.quarantine}</Menu.Item></>}
              {!can("inventory:transact") && !can("inventory:adjust") && !can("inventory:quarantine") && <Menu.Item disabled>No stock permissions</Menu.Item>}
            </Menu.Dropdown>
          </Menu>
        </>} />
      {lot.usability_problems.length > 0 && (
        <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} mb="md" title="Not usable for production">
          {lot.usability_problems.join(". ")}.
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, lg: 2 }} mb="md">
        <Paper withBorder p="md" radius="sm">
          <dl className="kv">
            <dt>Manufacturer</dt><dd>{lot.manufacturer ?? "—"} {lot.mpn && <Ident>{lot.mpn}</Ident>}</dd>
            <dt>Supplier</dt><dd>{lot.supplier_name ?? "—"} {lot.supplier_part_number && `(${lot.supplier_part_number})`}</dd>
            <dt>PO reference</dt><dd>{lot.purchase_order_ref ?? "—"}</dd>
            <dt>Supplier lot</dt><dd>{lot.supplier_lot ?? "—"}</dd>
            <dt>Manufacturer lot</dt><dd>{lot.manufacturer_lot ?? "—"}</dd>
            <dt>Date code</dt><dd>{lot.date_code ?? "—"}</dd>
            <dt>Expiry</dt><dd>{fmtDay(lot.expiry_date) || "—"}</dd>
            <dt>Received</dt><dd>{fmtDate(lot.received_at)} by {lot.received_by} · <span className="ident">{fmtQty(lot.qty_received)}</span> {lot.uom}</dd>
          </dl>
        </Paper>
        <Paper withBorder p="md" radius="sm">
          <Group justify="space-between" mb="xs"><Text fw={600}>Where it is</Text><Text className="ident">{fmtQty(lot.qty_on_hand)} {lot.uom} on hand</Text></Group>
          {!lot.balances.length ? <Empty>Fully consumed.</Empty> : (
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Location</Table.Th><Table.Th ta="right">On hand</Table.Th><Table.Th ta="right">Reserved</Table.Th><Table.Th ta="right">Free</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {lot.balances.map((b: any) => (
                  <LinkRow key={b.location_id} to={`/locations/${b.location_id}`}>
                    <Table.Td><Ident>{b.location_code}</Ident>{b.is_quarantine && <Text span c="red.8" size="xs" fw={600}> quarantine</Text>}</Table.Td>
                    <Table.Td ta="right" className="ident">{fmtQty(b.qty_on_hand)}</Table.Td>
                    <Table.Td ta="right" className="ident">{fmtQty(b.qty_reserved)}</Table.Td>
                    <Table.Td ta="right" className="ident">{fmtQty(b.qty_available)}</Table.Td>
                  </LinkRow>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Paper>
      </SimpleGrid>
      <Tabs defaultValue="ledger" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="ledger">Ledger ({lot.transactions.length})</Tabs.Tab>
          <Tabs.Tab value="records">Certificates & records ({lot.attachments.length})</Tabs.Tab>
          <Tabs.Tab value="signatures">Signatures ({lot.signatures.length})</Tabs.Tab>
          <Tabs.Tab value="history">History</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="ledger"><LedgerTable rows={lot.transactions} /></Tabs.Panel>
        <Tabs.Panel value="records"><LotFiles lot={lot} onChanged={refresh} /></Tabs.Panel>
        <Tabs.Panel value="signatures">
          {!lot.signatures.length ? <Empty>No signatures.</Empty> : (
            <Paper withBorder radius="sm"><Table><Table.Tbody>
              {lot.signatures.map((s: any) => <Table.Tr key={s.id}><Table.Td fw={500}>{s.meaning}</Table.Td><Table.Td>{s.signer_name}</Table.Td><Table.Td>{fmtDate(s.signed_at)}</Table.Td><Table.Td>{s.comment}</Table.Td></Table.Tr>)}
            </Table.Tbody></Table></Paper>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="history"><History entities={[["inventory_lot", lot.id]]} /></Tabs.Panel>
      </Tabs>
      <OpDialog op={op} lot={lot} onClose={() => setOp(null)} onDone={refresh} />
      <SignDialog opened={sign !== null} onClose={() => setSign(null)}
        title={sign === "inspect" ? "Incoming inspection" : "Release from quarantine"} recordLabel={`${lot.lot_no} (${lot.part_number})`}
        meanings={sign === "inspect" ? inspectMeanings : releaseMeanings} commentRequired={[...COMMENT_REQUIRED, ...(sign === "release" ? ["Material Released"] : [])]}
        onSubmit={async (meaning, password, comment) => {
          const d = sign === "inspect"
            ? await api(`/api/lots/${lot.id}/inspect`, { body: { accept: meaning === "Material Released", password, comment } })
            : await api(`/api/lots/${lot.id}/release-quarantine`, { body: { password, comment } });
          refresh(d); notifications.show({ message: `Signed “${meaning}”`, color: "mask" });
        }} />
    </>
  );
}

export function LedgerTable({ rows, showLot }: { rows: any[]; showLot?: boolean }) {
  if (!rows.length) return <Empty>No transactions.</Empty>;
  return (
    <Paper withBorder radius="sm">
      <Table.ScrollContainer minWidth={1000}>
        <Table striped>
          <Table.Thead><Table.Tr><Table.Th>#</Table.Th><Table.Th>When</Table.Th><Table.Th>Type</Table.Th>{showLot && <><Table.Th>Lot</Table.Th><Table.Th>Part</Table.Th></>}<Table.Th>Location</Table.Th>
            <Table.Th ta="right">Δ on hand</Table.Th><Table.Th ta="right">After</Table.Th><Table.Th ta="right">Δ reserved</Table.Th><Table.Th>Reference / reason</Table.Th><Table.Th>By</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {rows.map((t) => (
              <Table.Tr key={t.id}>
                <Table.Td className="ident">{t.id}</Table.Td><Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(t.occurred_at)}</Table.Td><Table.Td>{t.txn_type}</Table.Td>
                {showLot && <><Table.Td><Anchor component={Link} to={`/lots/${t.lot_id}`}><Ident>{t.lot_no}</Ident></Anchor></Table.Td><Table.Td><Ident>{t.part_number}</Ident></Table.Td></>}
                <Table.Td>{t.location ? <Ident>{t.location}</Ident> : <Text span c="dimmed">status</Text>}</Table.Td>
                <Table.Td ta="right" className="ident" c={t.d_on_hand < 0 ? "red.8" : undefined}>{t.d_on_hand ? (t.d_on_hand > 0 ? "+" : "") + fmtQty(t.d_on_hand) : ""}</Table.Td>
                <Table.Td ta="right" className="ident">{fmtQty(t.on_hand_after)}</Table.Td>
                <Table.Td ta="right" className="ident">{t.d_reserved ? (t.d_reserved > 0 ? "+" : "") + fmtQty(t.d_reserved) : ""}</Table.Td>
                <Table.Td><Text size="sm">{[t.reference, t.reason, t.comment].filter(Boolean).join(" · ")}{t.corrects_txn_id && ` · corrects #${t.corrects_txn_id}`}</Text></Table.Td>
                <Table.Td>{t.by}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}

function OpDialog({ op, lot, onClose, onDone }: { op: Op | null; lot: any; onClose: () => void; onDone: (d: any) => void }) {
  const locs = useQuery({ queryKey: ["locations"], queryFn: () => api("/api/locations"), enabled: !!op });
  const [f, setF] = useState<Record<string, any>>({});
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const here = lot.balances.map((b: any) => ({ value: b.location_id, label: `${b.location_code} (${fmtQty(b.qty_available)} free, ${fmtQty(b.qty_on_hand)} on hand)` }));
  const all = (locs.data ?? []).filter((l: any) => l.is_active).map((l: any) => ({ value: l.id, label: `${l.code} ${l.name}${l.is_quarantine ? " (quarantine)" : ""}` }));
  const close = () => { setF({}); setErr(null); onClose(); };
  if (!op) return null;
  const needsLoc = op !== "quarantine";
  const locData = op === "return" || op === "adjust" ? all : here;
  const submit = async () => {
    setBusy(true); setErr(null);
    const body: Record<string, any> = { ...f };
    if (op === "transfer") { body.from_location_id = f.location_id; delete body.location_id; }
    if (op === "adjust") { body.delta = f.qty; delete body.qty; if (!f.corrects_txn_id) delete body.corrects_txn_id; }
    try { onDone(await api(`/api/lots/${lot.id}/${op}`, { body })); notifications.show({ message: `${OP_TITLES[op]}: done`, color: "mask" }); close(); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  };
  const refReq = ["issue", "reserve", "release-reservation", "return"].includes(op);
  const reasonReq = ["adjust", "scrap", "quarantine"].includes(op);
  return (
    <Modal opened onClose={close} title={`${OP_TITLES[op]}: ${lot.lot_no}`}>
      <Stack>
        {needsLoc && <Select label={op === "transfer" ? "From location" : "Location"} data={locData} value={f.location_id ?? null} onChange={(v) => setF({ ...f, location_id: v })} searchable required />}
        {op === "transfer" && <Select label="To location" data={all.filter((l: any) => l.value !== f.location_id)} value={f.to_location_id ?? null} onChange={(v) => setF({ ...f, to_location_id: v })} searchable required />}
        {needsLoc && <NumberInput label={op === "adjust" ? `Change in quantity (${lot.uom}; negative to reduce)` : `Quantity (${lot.uom})`} value={f.qty ?? ""}
          onChange={(v) => setF({ ...f, qty: v })} allowNegative={op === "adjust"} required />}
        {refReq && <TextInput label="Reference" description="Build, work order or other reference" value={f.reference ?? ""} onChange={(e) => setF({ ...f, reference: e.currentTarget.value })} required />}
        {reasonReq && <TextInput label={op === "quarantine" ? "Reason (e.g. NCR number)" : "Reason"} value={f.reason ?? ""} onChange={(e) => setF({ ...f, reason: e.currentTarget.value })} required />}
        {op === "adjust" && <NumberInput label="Corrects transaction # (optional)" value={f.corrects_txn_id ?? ""} onChange={(v) => setF({ ...f, corrects_txn_id: v || null })} allowDecimal={false} />}
        <Textarea label="Comment" value={f.comment ?? ""} onChange={(e) => setF({ ...f, comment: e.currentTarget.value })} autosize minRows={2} />
        <ErrorBox error={err} />
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>Cancel</Button>
          <Button onClick={submit} loading={busy} color={op === "quarantine" || op === "scrap" ? "red" : undefined}>{OP_TITLES[op]}</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function LotFiles({ lot, onChanged }: { lot: any; onChanged: (d: any) => void }) {
  const { can } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<string | null>("certificate_of_conformance");
  const [err, setErr] = useState<unknown>(null);
  return (
    <Stack>
      {can("files:upload") && (
        <Paper withBorder p="md" radius="sm">
          <Group align="flex-end">
            <FileInput label="File" value={file} onChange={setFile} w={320} placeholder="CoC, inspection record, photo" />
            <Select label="Kind" value={kind} onChange={setKind} w={260} allowDeselect={false}
              data={["certificate_of_conformance", "inspection_record", "certificate", "compliance_declaration", "other"]} />
            <Button disabled={!file} onClick={async () => {
              const fd = new FormData(); fd.append("file", file!); fd.append("doc_kind", kind!);
              try { onChanged(await api(`/api/lots/${lot.id}/attachments`, { form: fd })); setFile(null); setErr(null); } catch (x) { setErr(x); }
            }}>Upload</Button>
          </Group>
          <ErrorBox error={err} />
        </Paper>
      )}
      {!lot.attachments.length ? <Empty>No records attached.</Empty> : (
        <Paper withBorder radius="sm"><Table><Table.Tbody>
          {lot.attachments.map((a: any) => (
            <Table.Tr key={a.id}><Table.Td>{a.filename}</Table.Td><Table.Td>{a.doc_kind}</Table.Td><Table.Td><Code>{a.sha256.slice(0, 16)}…</Code></Table.Td>
              <Table.Td>{fmtDate(a.uploaded_at)}</Table.Td><Table.Td><Anchor href={`/api/files/${a.id}/download`} aria-label="Download"><IconDownload size={16} /></Anchor></Table.Td></Table.Tr>
          ))}
        </Table.Tbody></Table></Paper>
      )}
    </Stack>
  );
}
