import {
  Alert, Anchor, Button, Checkbox, Code, FileInput, Group, Modal, Paper, SegmentedControl, Select, SimpleGrid, Stack,
  Table, Tabs, Text, TextInput, Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconDownload, IconQrcode, IconUpload } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { SignDialog } from "../components/SignDialog";
import { Empty, ErrorBox, Ident, LinkRow, Loading, PageHeader, StatusBadge } from "../components/ui";
import { api, fmtDate, fmtDay, fmtQty, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { COMMENT_REQUIRED, REV_MEANINGS, allowedMeanings } from "../lib/signing";

const FIELDS: [string, string][] = [
  ["description", "Description"], ["category", "Category"], ["subcategory", "Subcategory"],
  ["component_type", "Component type"], ["value", "Value"], ["package", "Package"],
  ["rohs_status", "RoHS"], ["reach_status", "REACH"], ["notes", "Notes"], ["change_reason", "Reason for change"],
];
const RAIL = ["Draft", "Under Review", "Approved", "Released"];

function Lifecycle({ status }: { status: string }) {
  const idx = RAIL.indexOf(status);
  const off = idx < 0;
  return (
    <div className="lifecycle" aria-label={`Lifecycle: ${status}`}>
      {RAIL.map((s, i) => (
        <div key={s} className="lifecycle-step" data-done={!off && i < idx} data-current={!off && i === idx}>{s}</div>
      ))}
      {off && <div className="lifecycle-step" data-bad={["Prohibited", "Obsolete"].includes(status)} data-current={!["Prohibited", "Obsolete"].includes(status)}>{status}</div>}
    </div>
  );
}

export default function PartDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const { can } = useAuth();
  const nav = useNavigate();
  const { data: item, error, isLoading } = useQuery({ queryKey: ["item", id], queryFn: () => api(`/api/items/${id}`) });
  const [revId, setRevId] = useState<string | null>(null);
  const [signing, setSigning] = useState(false);
  const [newRev, setNewRev] = useState(false);
  const [actionErr, setActionErr] = useState<unknown>(null);
  const [adminEditing, setAdminEditing] = useState(false);

  useEffect(() => {
    if (!item) return;
    if (revId && item.revisions.some((r: any) => r.id === revId)) return;
    const open = item.revisions.find((r: any) => ["Draft", "Under Review", "Approved"].includes(r.status));
    setRevId(open?.id ?? item.current_released_revision_id ?? item.revisions[0]?.id);
  }, [item, revId]);

  const rev = useMemo(() => item?.revisions.find((r: any) => r.id === revId), [item, revId]);
  const refresh = (d?: any) => { if (d) qc.setQueryData(["item", id], d); qc.invalidateQueries({ queryKey: ["item", id] }); qc.invalidateQueries({ queryKey: ["audit-entity"] }); };
  const act = async (fn: () => Promise<any>, msg: string) => {
    setActionErr(null);
    try { refresh(await fn()); notifications.show({ message: msg, color: "mask" }); } catch (x) { setActionErr(x); }
  };

  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!rev) return <Loading />;
  const base = `/api/items/${id}/revisions/${rev.id}`;
  const meanings = allowedMeanings(REV_MEANINGS[rev.status] ?? [], can);
  const hasOpen = item.revisions.some((r: any) => ["Draft", "Under Review", "Approved"].includes(r.status));

  return (
    <>
      <PageHeader
        title={<Group gap="sm"><Ident size="lg">{item.part_number}</Ident><StatusBadge status={rev.status} /></Group>}
        sub={`${rev.description} · ${item.item_class} · ${item.uom}`}
        actions={<>
          <Button variant="default" leftSection={<IconQrcode size={16} />} component="a" href={`/api/qr/item/${item.id}.svg`} target="_blank">QR</Button>
          {meanings.length > 0 && ["Released", "NRND", "Prohibited"].includes(rev.status) &&
            <Button variant="default" onClick={() => setSigning(true)}>Change lifecycle…</Button>}
          {can("item:write") && !hasOpen && item.current_released_revision_id &&
            <Button variant="default" onClick={() => setNewRev(true)}>New revision</Button>}
          {can("admin:override") && <Button variant="default" onClick={() => setAdminEditing(true)}>Superuser edit</Button>}
          {can("admin:override") && <Button color="red" variant="outline" onClick={async () => {
            const reason = window.prompt(`PERMANENTLY DELETE ${item.part_number}?\n\nThis cannot be undone. Enter the reason:`);
            if (!reason || reason.trim().length < 3) return;
            if (!window.confirm(`Final confirmation: permanently delete ${item.part_number}?`)) return;
            try { await api(`/api/items/${item.id}`, { method: "DELETE", body: { reason } }); notifications.show({ message: `${item.part_number} permanently deleted`, color: "red" }); nav("/parts"); }
            catch (x) { setActionErr(x); }
          }}>Delete permanently</Button>}
        </>} />

      <Group mb="md" gap="lg" align="center">
        <SegmentedControl value={rev.id} onChange={setRevId}
          data={item.revisions.slice().reverse().map((r: any) => ({ value: r.id, label: `Rev ${r.revision_label}${r.is_current_released ? " (current)" : ""}` }))} />
        <Lifecycle status={rev.status} />
      </Group>

      <ErrorBox error={actionErr} />
      {rev.status === "Draft" && (
        <Alert variant="light" color="gray" mb="md">
          <Group justify="space-between">
            <Text size="sm">This revision is a draft. Edit it, attach files, then submit it for review.</Text>
            {can("item:write") && <Group gap="xs">
              <Button size="xs" variant="default" color="red" onClick={() => {
                const reason = window.prompt("Reason for discarding this draft:");
                if (reason && reason.trim().length >= 3) act(() => api(`${base}/discard`, { body: { reason } }), "Draft discarded");
              }}>Discard draft</Button>
              <Button size="xs" onClick={() => act(() => api(`${base}/submit`, { method: "POST" }), "Submitted for review")}>Submit for review</Button>
            </Group>}
          </Group>
        </Alert>
      )}
      {meanings.length > 0 && !["Released", "NRND", "Prohibited"].includes(rev.status) && (
        <Alert variant="light" color={rev.status === "Released" ? "gray" : "yellow"} mb="md">
          <Group justify="space-between">
            <Text size="sm">
              {rev.status === "Under Review" && "Awaiting Engineering and Quality approval. Both are required before release."}
              {rev.status === "Approved" && "Approved. Release it for production to make it the current revision."}
            </Text>
            <Button size="xs" onClick={() => setSigning(true)}>Sign…</Button>
          </Group>
        </Alert>
      )}

      <Tabs defaultValue="details" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="details">Details</Tabs.Tab>
          <Tabs.Tab value="files">Files ({rev.attachments.length})</Tabs.Tab>
          <Tabs.Tab value="approvals">Approvals ({rev.signatures.length})</Tabs.Tab>
          <Tabs.Tab value="sources">Manufacturer sources ({item.aml.length})</Tabs.Tab>
          <Tabs.Tab value="stock">Stock</Tabs.Tab>
          <Tabs.Tab value="history">History</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="details">
          {rev.status === "Draft" && can("item:write")
            ? <DraftEditor key={rev.id + rev.row_version} rev={rev} base={base} onSaved={refresh} />
            : <Paper withBorder p="md" radius="sm">
                <dl className="kv">
                  {FIELDS.map(([k, l]) => (<Fragment key={k}><dt>{l}</dt><dd>{rev[k] || <Text span c="dimmed">—</Text>}</dd></Fragment>))}
                  <dt>Content hash</dt><dd>{rev.content_hash ? <Code>{rev.content_hash}</Code> : <Text span c="dimmed">computed on submission</Text>}</dd>
                </dl>
              </Paper>}
          <Paper withBorder p="md" radius="sm" mt="md">
            <dl className="kv">
              <dt>Created</dt><dd>{fmtDate(rev.created_at)} by {rev.created_by}</dd>
              <dt>Last modified</dt><dd>{fmtDate(rev.modified_at)} by {rev.modified_by}</dd>
              {rev.released_at && (<><dt>Released</dt><dd>{fmtDate(rev.released_at)}</dd></>)}
              <dt>Minimum stock</dt><dd className="ident">{fmtQty(item.min_stock)} {item.uom}</dd>
            </dl>
          </Paper>
        </Tabs.Panel>
        <Tabs.Panel value="files"><Files rev={rev} base={base} editable={rev.status === "Draft" && can("files:upload")} onChanged={refresh} /></Tabs.Panel>
        <Tabs.Panel value="approvals"><Approvals rev={rev} /></Tabs.Panel>
        <Tabs.Panel value="sources"><Sources item={item} onChanged={refresh} /></Tabs.Panel>
        <Tabs.Panel value="stock"><PartStock itemId={item.id} stock={item.stock} uom={item.uom} /></Tabs.Panel>
        <Tabs.Panel value="history"><History entities={[["item", item.id], ...item.revisions.map((r: any) => ["item_revision", r.id] as [string, string])]} /></Tabs.Panel>
      </Tabs>

      <SignDialog opened={signing} onClose={() => setSigning(false)} title={`Sign ${item.part_number} rev ${rev.revision_label}`}
        recordLabel={`${item.part_number} rev ${rev.revision_label}`} contentHash={rev.content_hash} meanings={meanings}
        commentRequired={COMMENT_REQUIRED}
        onSubmit={async (meaning, password, comment) => {
          const d = await api(`${base}/sign`, { body: { meaning, password, comment, content_hash: rev.content_hash } });
          refresh(d); notifications.show({ message: `Signed “${meaning}”`, color: "mask" });
        }} />
      <NewRevision opened={newRev} onClose={() => setNewRev(false)} itemId={item.id} onDone={(d) => { refresh(d); setRevId(null); }} />
      <Modal opened={adminEditing} onClose={() => setAdminEditing(false)} title={`Superuser edit — ${item.part_number} rev ${rev.revision_label}`} size="lg">
        <AdminEditor rev={rev} base={base} onSaved={(d) => { refresh(d); setAdminEditing(false); }} />
      </Modal>
    </>
  );
}

function AdminEditor({ rev, base, onSaved }: { rev: any; base: string; onSaved: (d: any) => void }) {
  const [f, setF] = useState<Record<string, any>>(Object.fromEntries(FIELDS.map(([k]) => [k, rev[k] ?? ""])));
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return <Stack>
    <Alert color="red" variant="light">This bypasses normal revision immutability. The correction is permanent; the audit ledger records the before/after values and reason.</Alert>
    <TextInput label="Description" required value={f.description} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} />
    <SimpleGrid cols={{ base: 1, sm: 3 }}>{FIELDS.filter(([k]) => !["description","notes","change_reason"].includes(k)).map(([k,l]) => <TextInput key={k} label={l} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.currentTarget.value })} />)}</SimpleGrid>
    <Textarea label="Notes" value={f.notes} autosize minRows={2} onChange={(e) => setF({ ...f, notes: e.currentTarget.value })} />
    <Textarea label="Reason for superuser correction" required value={reason} autosize minRows={2} onChange={(e) => setReason(e.currentTarget.value)} />
    <ErrorBox error={err} />
    <Group justify="flex-end"><Button color="red" disabled={reason.trim().length < 3} loading={busy} onClick={async () => {
      setBusy(true); setErr(null); const body: Record<string, any> = { row_version: rev.row_version, reason };
      FIELDS.forEach(([k]) => { if ((f[k] ?? "") !== (rev[k] ?? "")) body[k] = f[k] === "" ? null : f[k]; });
      try { onSaved(await api(`${base}/admin-override`, { method: "PATCH", body })); notifications.show({ message: "Superuser correction saved", color: "mask" }); } catch (x) { setErr(x); } finally { setBusy(false); }
    }}>Apply permanent correction</Button></Group>
  </Stack>;
}

function DraftEditor({ rev, base, onSaved }: { rev: any; base: string; onSaved: (d: any) => void }) {
  const [f, setF] = useState<Record<string, any>>(Object.fromEntries(FIELDS.map(([k]) => [k, rev[k] ?? ""])));
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const dirty = FIELDS.some(([k]) => (f[k] ?? "") !== (rev[k] ?? ""));
  return (
    <Paper withBorder p="md" radius="sm">
      <Stack>
        <TextInput label="Description" required value={f.description} onChange={(e) => setF({ ...f, description: e.currentTarget.value })} />
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          {FIELDS.filter(([k]) => !["description", "notes", "change_reason"].includes(k)).map(([k, l]) => (
            <TextInput key={k} label={l} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.currentTarget.value })} />
          ))}
        </SimpleGrid>
        <Textarea label="Notes" value={f.notes} autosize minRows={2} onChange={(e) => setF({ ...f, notes: e.currentTarget.value })} />
        {rev.revision_label !== "A" && <Textarea label="Reason for change (required)" value={f.change_reason} autosize minRows={2}
          onChange={(e) => setF({ ...f, change_reason: e.currentTarget.value })} />}
        <ErrorBox error={err} />
        <Group justify="flex-end">
          <Button disabled={!dirty} loading={busy} onClick={async () => {
            setBusy(true); setErr(null);
            const body: Record<string, any> = { row_version: rev.row_version };
            FIELDS.forEach(([k]) => { if ((f[k] ?? "") !== (rev[k] ?? "")) body[k] = f[k] === "" ? null : f[k]; });
            try { onSaved(await api(base, { method: "PATCH", body })); notifications.show({ message: "Draft saved", color: "mask" }); }
            catch (x) { setErr(x); } finally { setBusy(false); }
          }}>Save draft</Button>
        </Group>
      </Stack>
    </Paper>
  );
}

function Files({ rev, base, editable, onChanged }: { rev: any; base: string; editable: boolean; onChanged: (d: any) => void }) {
  const meta = useQuery({ queryKey: ["item-meta"], queryFn: () => api("/api/items/meta") });
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<string | null>("datasheet");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Stack>
      {editable ? (
        <Paper withBorder p="md" radius="sm">
          <Group align="flex-end">
            <FileInput label="File" value={file} onChange={setFile} placeholder="Choose a file" w={320}
              accept={(meta.data?.allowed_extensions ?? []).join(",")} />
            <Select label="Kind" data={meta.data?.doc_kinds ?? []} value={kind} onChange={setKind} w={220} allowDeselect={false} />
            <Button leftSection={<IconUpload size={16} />} disabled={!file || !kind} loading={busy} onClick={async () => {
              const fd = new FormData(); fd.append("file", file!); fd.append("doc_kind", kind!);
              setBusy(true); setErr(null);
              try { onChanged(await api(`${base}/attachments`, { form: fd })); setFile(null); } catch (x) { setErr(x); } finally { setBusy(false); }
            }}>Upload</Button>
          </Group>
          <ErrorBox error={err} />
        </Paper>
      ) : <Text size="sm" c="dimmed">Files are frozen with this revision. To change them, create a new revision.</Text>}
      {rev.attachments.length === 0 ? <Empty>No files attached.</Empty> : (
        <Paper withBorder radius="sm">
          <Table.ScrollContainer minWidth={700}>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>File</Table.Th><Table.Th>Kind</Table.Th><Table.Th>SHA-256</Table.Th><Table.Th ta="right">Size</Table.Th><Table.Th>Uploaded</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {rev.attachments.map((a: any) => (
                  <Table.Tr key={a.id}>
                    <Table.Td>{a.filename}</Table.Td><Table.Td>{a.doc_kind}</Table.Td>
                    <Table.Td><Code title={a.sha256}>{a.sha256.slice(0, 16)}…</Code></Table.Td>
                    <Table.Td ta="right">{(a.size_bytes / 1024).toFixed(1)} KB</Table.Td>
                    <Table.Td>{fmtDate(a.uploaded_at)} · {a.uploaded_by}</Table.Td>
                    <Table.Td><Anchor href={`/api/files/${a.id}/download`} aria-label={`Download ${a.filename}`}><IconDownload size={16} /></Anchor></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
    </Stack>
  );
}

function Approvals({ rev }: { rev: any }) {
  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }}>
      <Paper withBorder p="md" radius="sm">
        <Text fw={600} mb="xs">Electronic signatures</Text>
        {rev.signatures.length === 0 ? <Empty>No signatures yet.</Empty> : (
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Meaning</Table.Th><Table.Th>Signer</Table.Th><Table.Th>When</Table.Th><Table.Th>Cycle</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {rev.signatures.map((s: any) => (
                <Table.Tr key={s.id}>
                  <Table.Td><Text size="sm" fw={500}>{s.meaning}</Text>{s.comment && <Text size="xs" c="dimmed">{s.comment}</Text>}</Table.Td>
                  <Table.Td>{s.signer_name}</Table.Td><Table.Td>{fmtDate(s.signed_at)}</Table.Td><Table.Td>{s.review_cycle}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
      <Paper withBorder p="md" radius="sm">
        <Text fw={600} mb="xs">Status changes</Text>
        {rev.transitions.length === 0 ? <Empty>No status changes yet.</Empty> : (
          <Table>
            <Table.Tbody>
              {rev.transitions.map((t: any, i: number) => (
                <Table.Tr key={i}>
                  <Table.Td>{fmtDate(t.at)}</Table.Td><Table.Td>{t.from ?? "—"} → <b>{t.to}</b></Table.Td><Table.Td>{t.by}</Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{t.reason}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
    </SimpleGrid>
  );
}

function Sources({ item, onChanged }: { item: any; onChanged: (d: any) => void }) {
  const { can } = useAuth();
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState<Record<string, any>>({ preferred: false });
  const [err, setErr] = useState<unknown>(null);
  const [sign, setSign] = useState<any>(null);
  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">Manufacturer parts approved as form-fit-function sources. Stock can only be received against an approved source.</Text>
        {can("aml:write") && <Button size="xs" variant="default" onClick={() => setAdding(true)}>Propose source</Button>}
      </Group>
      {item.aml.length === 0 ? <Empty>No manufacturer sources yet.</Empty> : (
        <Paper withBorder radius="sm">
          <Table.ScrollContainer minWidth={700}>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Manufacturer</Table.Th><Table.Th>MPN</Table.Th><Table.Th>Purchasing sources</Table.Th><Table.Th>Lifecycle</Table.Th><Table.Th>Status</Table.Th><Table.Th>Approved</Table.Th><Table.Th /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {item.aml.map((a: any) => (
                  <Table.Tr key={a.id}>
                    <Table.Td>{a.manufacturer}{a.preferred && <Text span size="xs" c="mask.8" fw={600}> preferred</Text>}</Table.Td>
                    <Table.Td><Ident>{a.mpn}</Ident>{a.datasheet_url && <> · <Anchor href={a.datasheet_url} target="_blank" rel="noreferrer" size="sm">datasheet</Anchor></>}</Table.Td>
                    <Table.Td>{a.sources?.length ? a.sources.map((src: any) => <div key={src.id}>{src.distributor}{src.source_part_number && <> · <Ident>{src.source_part_number}</Ident></>}{src.source_url && <> · <Anchor href={src.source_url} target="_blank" rel="noreferrer" size="sm">link</Anchor></>}</div>) : "—"}</Table.Td>
                    <Table.Td>{a.lifecycle}</Table.Td><Table.Td><StatusBadge status={a.status} /></Table.Td>
                    <Table.Td>{a.approved_by ? `${a.approved_by}, ${fmtDay(a.approved_at)}` : ""}</Table.Td>
                    <Table.Td>{allowedMeanings(a.status === "Proposed" ? ["AML Approved", "AML Disqualified"] : a.status === "Approved" ? ["AML Disqualified"] : [], can).length > 0 &&
                      <Button size="xs" variant="default" onClick={() => setSign(a)}>Sign…</Button>}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
      <Modal opened={adding} onClose={() => setAdding(false)} title="Propose manufacturer source">
        <Stack>
          <TextInput label="Manufacturer" required value={f.manufacturer ?? ""} onChange={(e) => setF({ ...f, manufacturer: e.currentTarget.value })} />
          <TextInput label="Manufacturer part number" required value={f.mpn ?? ""} onChange={(e) => setF({ ...f, mpn: e.currentTarget.value })} />
          <TextInput label="Datasheet URL" value={f.datasheet_url ?? ""} onChange={(e) => setF({ ...f, datasheet_url: e.currentTarget.value })} />
          <Text fw={600} size="sm" mt="xs">Purchasing source</Text>
          <TextInput label="Distributor / source" placeholder="e.g. Mouser, Farnell, DigiKey" value={f.distributor ?? ""} onChange={(e) => setF({ ...f, distributor: e.currentTarget.value })} />
          <TextInput label="Source part number" value={f.source_part_number ?? ""} onChange={(e) => setF({ ...f, source_part_number: e.currentTarget.value })} />
          <TextInput label="Source URL" value={f.source_url ?? ""} onChange={(e) => setF({ ...f, source_url: e.currentTarget.value })} />
          <Checkbox label="Preferred manufacturer source" checked={f.preferred} onChange={(e) => setF({ ...f, preferred: e.currentTarget.checked })} />
          <Textarea label="Notes" value={f.notes ?? ""} onChange={(e) => setF({ ...f, notes: e.currentTarget.value })} />
          <ErrorBox error={err} />
          <Button onClick={async () => {
            setErr(null);
            try { onChanged(await api(`/api/items/${item.id}/aml`, { body: { ...f, datasheet_url: f.datasheet_url || null } })); setAdding(false); setF({ preferred: false }); }
            catch (x) { setErr(x); }
          }}>Propose</Button>
        </Stack>
      </Modal>
      <SignDialog opened={!!sign} onClose={() => setSign(null)} title="Sign manufacturer source"
        recordLabel={sign ? `${item.part_number} ← ${sign.manufacturer} ${sign.mpn}` : ""}
        meanings={sign ? allowedMeanings(sign.status === "Proposed" ? ["AML Approved", "AML Disqualified"] : ["AML Disqualified"], can) : []}
        commentRequired={COMMENT_REQUIRED}
        onSubmit={async (meaning, password, comment) => onChanged(await api(`/api/items/${item.id}/aml/${sign.id}/sign`, { body: { meaning, password, comment } }))} />
    </Stack>
  );
}

function PartStock({ itemId, stock, uom }: { itemId: string; stock: any; uom: string }) {
  const { data } = useQuery({ queryKey: ["lots", "item", itemId], queryFn: () => api(`/api/lots${qs({ item_id: itemId, limit: 200 })}`) });
  return (
    <Stack>
      <Text size="sm">On hand <b className="ident">{fmtQty(stock.on_hand)}</b> {uom} · reserved <b className="ident">{fmtQty(stock.reserved)}</b> · available for production <b className="ident">{fmtQty(stock.available)}</b></Text>
      {!data?.items.length ? <Empty>No stock of this part.</Empty> : (
        <Paper withBorder radius="sm">
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Lot</Table.Th><Table.Th>Status</Table.Th><Table.Th>Rev</Table.Th><Table.Th>MPN</Table.Th><Table.Th ta="right">On hand</Table.Th><Table.Th>Expiry</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {data.items.map((l: any) => (
                <LinkRow key={l.id} to={`/lots/${l.id}`}>
                  <Table.Td><Ident>{l.lot_no}</Ident></Table.Td><Table.Td><StatusBadge status={l.status} /></Table.Td>
                  <Table.Td>{l.revision}</Table.Td><Table.Td>{l.mpn}</Table.Td>
                  <Table.Td ta="right" className="ident">{fmtQty(l.qty_on_hand)}</Table.Td><Table.Td>{fmtDay(l.expiry_date)}</Table.Td>
                </LinkRow>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
    </Stack>
  );
}

export function History({ entities }: { entities: [string, string][] }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["audit-entity", entities],
    queryFn: async () => (await Promise.all(entities.map(([t, i]) => api(`/api/audit/entity/${t}/${i}`)))).flat()
      .sort((a: any, b: any) => b.id - a.id),
  });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!data?.length) return <Empty>No history.</Empty>;
  return (
    <Paper withBorder radius="sm">
      <Table.ScrollContainer minWidth={800}>
        <Table>
          <Table.Thead><Table.Tr><Table.Th>When</Table.Th><Table.Th>Who</Table.Th><Table.Th>Action</Table.Th><Table.Th>Record</Table.Th><Table.Th>Change</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {data.map((e: any) => (
              <Table.Tr key={e.id}>
                <Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(e.occurred_at)}</Table.Td><Table.Td>{e.actor}</Table.Td>
                <Table.Td>{e.action}</Table.Td><Table.Td>{e.entity_label}</Table.Td>
                <Table.Td><ChangeView before={e.before} after={e.after} reason={e.reason} /></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  );
}

export function ChangeView({ before, after, reason }: { before: any; after: any; reason?: string }) {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  return (
    <Stack gap={2}>
      {keys.map((k) => (
        <Text size="xs" key={k}>
          <b>{k}</b>: {before && k in before ? <Text span c="red.8" td="line-through">{String(before[k] ?? "∅")}</Text> : null}{" "}
          {after && k in after ? <Text span c="mask.8">{typeof after[k] === "object" ? JSON.stringify(after[k]) : String(after[k] ?? "∅")}</Text> : null}
        </Text>
      ))}
      {reason && <Text size="xs" c="dimmed">Reason: {reason}</Text>}
    </Stack>
  );
}

function NewRevision({ opened, onClose, itemId, onDone }: { opened: boolean; onClose: () => void; itemId: string; onDone: (d: any) => void }) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);
  return (
    <Modal opened={opened} onClose={onClose} title="Create new revision">
      <Stack>
        <Text size="sm">The current released revision stays in use until the new revision is approved and released. Content and files are copied into a new Draft.</Text>
        <Textarea label="Reason for change" required value={reason} onChange={(e) => setReason(e.currentTarget.value)} placeholder="e.g. Second source added per ECO-0042" />
        <ErrorBox error={err} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button disabled={reason.trim().length < 3} onClick={async () => {
            try { onDone(await api(`/api/items/${itemId}/revisions`, { body: { change_reason: reason } })); onClose(); setReason(""); } catch (x) { setErr(x); }
          }}>Create draft revision</Button>
        </Group>
      </Stack>
    </Modal>
  );
}

