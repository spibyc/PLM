import { Anchor, Badge, Button, Group, Paper, Stack, Table, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import PurchaseOrderEditor from "./PurchaseOrderEditor";
import { SignDialog } from "../components/SignDialog";
import { Empty, ErrorBox, Ident, Loading, PageHeader } from "../components/ui";
import { api, fmtDate, fmtDay, fmtQty } from "../lib/api";
import { useAuth } from "../lib/auth";

type POLine = {
  id: string; line_no: number; item_id: string; part_number: string; description: string | null;
  uom: string; manufacturer: string | null; mpn: string | null; supplier_part_number: string | null;
  qty_ordered: number | string; qty_received: number | string; qty_outstanding: number | string;
  unit_cost: number | string; line_total: number | string;
};
type PO = {
  id: string; po_number: string; supplier: string; supplier_code: string; status: string; currency: string;
  revision: number; expected_date: string | null; notes: string | null; created_at: string;
  created_by: string | null; approved_at: string | null; total: number | string; lines: POLine[];
  signatures: { id: string; meaning: string; signer_name: string; signed_at: string; comment: string | null }[];
  receipts: { receipt_id: string; receipt_no: string; received_at: string; po_line_id: string;
    lot_id: string; lot_no: string; qty: number | string }[];
};
const quantity = (n: number | string) => fmtQty(Number(n));

export default function PurchaseOrderDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [signing, setSigning] = useState(false);
  const { data: po, error, isLoading } = useQuery({ queryKey: ["po", id],
    queryFn: () => api<PO>(`/api/purchase-orders/${id}`) });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!po) return <Empty>Purchase order not found.</Empty>;
  const money = (n: number | string) => `${po.currency} ${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`;
  return <Stack>
    <Anchor component={Link} to="/purchase-orders">Back to purchase orders</Anchor>
    <PageHeader title={<Ident size="lg">{po.po_number}</Ident>} sub={`${po.supplier_code} · ${po.supplier}`}
      actions={<Group><Badge color={po.status === "Draft" ? "gray" : po.status === "Partially Received" ? "yellow" : "green"}>{po.status}</Badge>
        {po.status === "Draft" && can("po:write") && <Button variant="default" onClick={() => setEditing(true)}>Edit PO</Button>}
        {po.status === "Draft" && can("sign:po_approved") && <Button onClick={() => setSigning(true)}>Approve PO</Button>}</Group>} />
    <Paper withBorder p="md">
      <dl className="kv">
        <dt>Revision</dt><dd>{po.revision}</dd>
        <dt>Expected date</dt><dd>{fmtDay(po.expected_date) || "—"}</dd>
        <dt>Created</dt><dd>{fmtDate(po.created_at)}{po.created_by ? ` by ${po.created_by}` : ""}</dd>
        <dt>Approved</dt><dd>{fmtDate(po.approved_at) || "Not approved"}</dd>
        <dt>Order total</dt><dd>{money(po.total)}</dd>
      </dl>
      {po.notes && <><Text fw={600}>Notes</Text><Text style={{ whiteSpace: "pre-wrap" }}>{po.notes}</Text></>}
    </Paper>
    <Paper withBorder p="md">
      <Text fw={600} mb="sm">Order lines</Text>
      <Table.ScrollContainer minWidth={1000}><Table striped>
        <Table.Thead><Table.Tr>{["Line", "Part", "Manufacturer / MPN", "Supplier part number", "Ordered", "Received", "Outstanding", "Receipt status", "Unit cost", "Line total"].map(h => <Table.Th key={h}>{h}</Table.Th>)}</Table.Tr></Table.Thead>
        <Table.Tbody>{po.lines.map(line => <Table.Tr key={line.id}>
          <Table.Td>{line.line_no}</Table.Td>
          <Table.Td>{can("item:read") ? <Anchor component={Link} to={`/parts/${line.item_id}`}><Ident>{line.part_number}</Ident></Anchor> : <Ident>{line.part_number}</Ident>}
            <Text size="xs" c="dimmed">{line.description || ""}</Text></Table.Td>
          <Table.Td>{[line.manufacturer, line.mpn].filter(Boolean).join(" · ") || "—"}</Table.Td>
          <Table.Td>{line.supplier_part_number || "—"}</Table.Td>
          <Table.Td>{quantity(line.qty_ordered)} {line.uom}</Table.Td>
          <Table.Td>{quantity(line.qty_received)}</Table.Td>
          <Table.Td>{quantity(line.qty_outstanding)}</Table.Td>
          <Table.Td><Badge color={Number(line.qty_outstanding) <= 0 ? "green" : Number(line.qty_received) > 0 ? "yellow" : "gray"}>
            {Number(line.qty_outstanding) <= 0 ? "Fully received" : Number(line.qty_received) > 0 ? "Partially received" : "Awaiting receipt"}
          </Badge></Table.Td>
          <Table.Td>{money(line.unit_cost)}</Table.Td><Table.Td>{money(line.line_total)}</Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table></Table.ScrollContainer>
    </Paper>
    <Paper withBorder p="md">
      <Text fw={600} mb="sm">Goods receipts</Text>
      {!po.receipts.length ? <Empty>No stock received against this order.</Empty> : <Table.ScrollContainer minWidth={600}><Table>
        <Table.Thead><Table.Tr><Table.Th>Receipt</Table.Th><Table.Th>Date</Table.Th><Table.Th>Order line</Table.Th><Table.Th>Lot</Table.Th><Table.Th>Quantity</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{po.receipts.map(r => <Table.Tr key={r.lot_id}>
          <Table.Td><Ident>{r.receipt_no}</Ident></Table.Td><Table.Td>{fmtDate(r.received_at)}</Table.Td>
          <Table.Td>{po.lines.find(l => l.id === r.po_line_id)?.line_no ?? "—"}</Table.Td>
          <Table.Td>{can("inventory:read") ? <Anchor component={Link} to={`/lots/${r.lot_id}`}><Ident>{r.lot_no}</Ident></Anchor> : <Ident>{r.lot_no}</Ident>}</Table.Td>
          <Table.Td>{quantity(r.qty)}</Table.Td>
        </Table.Tr>)}</Table.Tbody>
      </Table></Table.ScrollContainer>}
    </Paper>
    <Paper withBorder p="md">
      <Text fw={600} mb="sm">Approval signatures</Text>
      {!po.signatures.length ? <Empty>No signatures.</Empty> : <Table.ScrollContainer minWidth={600}><Table>
        <Table.Thead><Table.Tr><Table.Th>Meaning</Table.Th><Table.Th>Signed by</Table.Th><Table.Th>Date</Table.Th><Table.Th>Comment</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>{po.signatures.map(s => <Table.Tr key={s.id}><Table.Td>{s.meaning}</Table.Td><Table.Td>{s.signer_name}</Table.Td><Table.Td>{fmtDate(s.signed_at)}</Table.Td><Table.Td>{s.comment || "—"}</Table.Td></Table.Tr>)}</Table.Tbody>
      </Table></Table.ScrollContainer>}
    </Paper>
    {editing && <PurchaseOrderEditor key={po.id} po={po} onClose={() => setEditing(false)} onSaved={updated => {
      qc.setQueryData(["po", id], updated);
      qc.invalidateQueries({ queryKey: ["pos"] });
      setEditing(false);
      notifications.show({ message: "Draft purchase order updated", color: "green" });
    }} />}
    <SignDialog opened={signing} onClose={() => setSigning(false)} title="Approve purchase order"
      recordLabel={po.po_number} meanings={["Purchase Order Approved"]} onSubmit={async (_meaning, password, comment) => {
        const updated = await api<PO>(`/api/purchase-orders/${po.id}/approve`, { body: { password, comment, revision: po.revision } });
        qc.setQueryData(["po", id], updated);
        await qc.invalidateQueries({ queryKey: ["pos"] });
        notifications.show({ message: "Purchase order approved", color: "green" });
      }} />
  </Stack>;
}
