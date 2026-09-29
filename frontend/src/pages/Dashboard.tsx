import { Anchor, Grid, Paper, SimpleGrid, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Empty, ErrorBox, Ident, Loading, PageHeader, StatusBadge } from "../components/ui";
import { api, fmtDate, fmtQty } from "../lib/api";
import { useAuth } from "../lib/auth";

function Stat({ label, value, to, warn }: { label: string; value: number; to?: string; warn?: boolean }) {
  const body = (
    <Paper withBorder p="md" radius="sm" style={warn && value > 0 ? { borderColor: "#B42318", borderLeftWidth: 4 } : undefined}>
      <Text size="sm" c="dimmed">{label}</Text>
      <Text fz={28} fw={600} className="ident" c={warn && value > 0 ? "var(--plm-danger)" : undefined}>{value}</Text>
    </Paper>
  );
  return to ? <Anchor component={Link} to={to} underline="never" c="inherit">{body}</Anchor> : body;
}

export default function Dashboard() {
  const { me } = useAuth();
  const { data, error, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: () => api("/api/dashboard") });
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const d = data!;
  return (
    <>
      <PageHeader title="Dashboard" sub={`Signed in as ${me?.full_name}`} />
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }} mb="lg">
        <Stat label="Released parts" value={d.parts_active} to="/parts?status=Released" />
        <Stat label="Awaiting approval" value={d.pending_approvals} to="/parts?status=Under Review" />
        <Stat label="Lots awaiting inspection" value={d.lots_pending_inspection} to="/lots?status=Pending Inspection" warn />
        <Stat label="Lots in quarantine" value={d.lots_quarantined} to="/lots?status=Quarantined" warn />
        <Stat label="Below minimum stock" value={d.below_min_stock} to="/parts" warn />
      </SimpleGrid>
      <Grid>
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Paper withBorder p="md" radius="sm">
            <Title order={4} mb="sm">Recent stock movements</Title>
            {d.recent_transactions.length === 0 ? <Empty>No movements yet. Receive stock to get started.</Empty> : (
              <Table.ScrollContainer minWidth={520}>
                <Table>
                  <Table.Thead><Table.Tr><Table.Th>When</Table.Th><Table.Th>Type</Table.Th><Table.Th>Lot</Table.Th><Table.Th>Part</Table.Th><Table.Th ta="right">Qty</Table.Th><Table.Th>By</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {d.recent_transactions.map((t: any) => (
                      <Table.Tr key={t.id}>
                        <Table.Td>{fmtDate(t.occurred_at)}</Table.Td><Table.Td>{t.txn_type}</Table.Td>
                        <Table.Td><Anchor component={Link} to={`/lots/${t.lot_id}`}><Ident>{t.lot_no}</Ident></Anchor></Table.Td>
                        <Table.Td><Ident>{t.part_number}</Ident></Table.Td>
                        <Table.Td ta="right" className="ident">{t.d_on_hand > 0 ? "+" : ""}{fmtQty(t.d_on_hand) || (t.d_reserved ? `res ${fmtQty(t.d_reserved)}` : "—")}</Table.Td>
                        <Table.Td>{t.by}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Paper withBorder p="md" radius="sm">
            <Title order={4} mb="sm">Recently changed parts</Title>
            {d.recent_changes.length === 0 ? <Empty>No parts yet.</Empty> : (
              <Table>
                <Table.Tbody>
                  {d.recent_changes.map((r: any) => (
                    <Table.Tr key={`${r.item_id}-${r.revision}`}>
                      <Table.Td><Anchor component={Link} to={`/parts/${r.item_id}`}><Ident>{r.part_number}</Ident></Anchor> <Text span c="dimmed" size="sm">rev {r.revision}</Text></Table.Td>
                      <Table.Td><Text size="sm" lineClamp={1}>{r.description}</Text></Table.Td>
                      <Table.Td><StatusBadge status={r.status} /></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Paper>
        </Grid.Col>
      </Grid>
    </>
  );
}
