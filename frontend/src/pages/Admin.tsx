import { Alert, Button, Code, Group, Modal, MultiSelect, Pagination, Paper, PasswordInput, Select, SimpleGrid, Stack, Table, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconDownload } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Empty, ErrorBox, Loading, PageHeader } from "../components/ui";
import { api, fmtDate, qs } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ChangeView } from "./PartDetail";

const ENTITY_TYPES = ["item", "item_revision", "aml_entry", "manufacturer", "manufacturer_part", "inventory_lot", "location",
  "user", "role", "session", "file_store", "audit_event"];

export function Audit() {
  const { can } = useAuth();
  const [f, setF] = useState<Record<string, any>>({});
  const [page, setPage] = useState(1);
  const [verify, setVerify] = useState<any>(null);
  const [files, setFiles] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const params = { entity_type: f.entity_type, actor_name: f.actor_name, action: f.action, date_from: f.date_from, date_to: f.date_to };
  const { data, error, isLoading } = useQuery({
    queryKey: ["audit", params, page], queryFn: () => api(`/api/audit${qs({ ...params, limit: 100, offset: (page - 1) * 100 })}`),
  });
  const set = (k: string) => (e: any) => { setPage(1); setF({ ...f, [k]: e?.currentTarget ? e.currentTarget.value : e }); };
  return (
    <>
      <PageHeader title="Audit trail" sub="Every change, signature, login and export. Entries cannot be edited or deleted."
        actions={<>
          <Button variant="default" onClick={async () => { setErr(null); try { setVerify(await api("/api/audit/verify")); } catch (x) { setErr(x); } }}>Verify audit chain</Button>
          {can("files:verify") && <Button variant="default" onClick={async () => { setErr(null); try { setFiles(await api("/api/files/verify", { method: "POST" })); } catch (x) { setErr(x); } }}>Verify stored files</Button>}
          <Button leftSection={<IconDownload size={16} />} component="a" href={`/api/audit/export.csv${qs(params)}`}>Export CSV</Button>
        </>} />
      <ErrorBox error={err || error} />
      {verify && <Alert mb="sm" color={verify.ok ? "mask" : "red"} variant="light" withCloseButton onClose={() => setVerify(null)}>
        {verify.ok ? `Audit chain intact: ${verify.events_checked} events verified. Head ` : `Audit chain BROKEN at event ${verify.first_bad_event_id} after ${verify.events_checked} valid events. `}
        <Code>{verify.head?.slice(0, 16)}</Code></Alert>}
      {files && <Alert mb="sm" color={files.findings.length ? "red" : "mask"} variant="light" withCloseButton onClose={() => setFiles(null)}>
        {files.files_ok} files verified OK. {files.findings.length ? `${files.findings.length} problem(s): ${files.findings.map((x: any) => `${x.result} ${x.sha256.slice(0, 12)}`).join(", ")}` : "No problems found."}
      </Alert>}
      <Paper withBorder p="sm" radius="sm" mb="sm">
        <SimpleGrid cols={{ base: 2, md: 5 }}>
          <Select label="Record type" data={ENTITY_TYPES} value={f.entity_type ?? null} onChange={set("entity_type")} clearable />
          <TextInput label="User" value={f.actor_name ?? ""} onChange={set("actor_name")} />
          <TextInput label="Action" placeholder="e.g. sign, modify" value={f.action ?? ""} onChange={set("action")} />
          <TextInput label="From" type="date" value={f.date_from ?? ""} onChange={set("date_from")} />
          <TextInput label="To" type="date" value={f.date_to ?? ""} onChange={set("date_to")} />
        </SimpleGrid>
      </Paper>
      {isLoading ? <Loading /> : !data?.items.length ? <Empty>No events match these filters.</Empty> : (
        <Paper withBorder radius="sm">
          <Table.ScrollContainer minWidth={1000}>
            <Table striped>
              <Table.Thead><Table.Tr><Table.Th>#</Table.Th><Table.Th>When (local)</Table.Th><Table.Th>User</Table.Th><Table.Th>Action</Table.Th><Table.Th>Record</Table.Th><Table.Th>Change</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {data.items.map((e: any) => (
                  <Table.Tr key={e.id}>
                    <Table.Td className="ident">{e.id}</Table.Td><Table.Td style={{ whiteSpace: "nowrap" }}>{fmtDate(e.occurred_at)}</Table.Td>
                    <Table.Td>{e.actor}</Table.Td><Table.Td>{e.action}</Table.Td>
                    <Table.Td><Text size="sm">{e.entity_type}</Text><Text size="xs" c="dimmed">{e.entity_label}</Text></Table.Td>
                    <Table.Td><ChangeView before={e.before} after={e.after} reason={e.reason} /></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}
      {data && data.total > 100 && <Pagination mt="sm" total={Math.ceil(data.total / 100)} value={page} onChange={setPage} />}
    </>
  );
}

export function Users() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api("/api/users") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api("/api/users/roles") });
  const [edit, setEdit] = useState<any>(null);
  const [creating, setCreating] = useState(false);
  const roleData = (roles.data ?? []).map((r: any) => ({ value: r.code, label: r.name }));
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  return (
    <>
      <PageHeader title="Users & roles" sub="Administrators manage accounts but cannot sign approvals or change their own roles."
        actions={<Button onClick={() => setCreating(true)}>New user</Button>} />
      <ErrorBox error={users.error} />
      {users.isLoading ? <Loading /> : (
        <Paper withBorder radius="sm" mb="lg">
          <Table>
            <Table.Thead><Table.Tr><Table.Th>Username</Table.Th><Table.Th>Name</Table.Th><Table.Th>Roles</Table.Th><Table.Th>Status</Table.Th><Table.Th /></Table.Tr></Table.Thead>
            <Table.Tbody>
              {users.data.map((u: any) => (
                <Table.Tr key={u.id}>
                  <Table.Td className="ident">{u.username}</Table.Td><Table.Td>{u.full_name}</Table.Td><Table.Td>{u.roles.join(", ")}</Table.Td>
                  <Table.Td>{!u.is_active ? "Inactive" : u.locked ? "Locked" : "Active"}</Table.Td>
                  <Table.Td>{u.id !== me?.id && <Button size="compact-xs" variant="default" onClick={() => setEdit(u)}>Manage</Button>}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
      <Text fw={600} mb="xs">Role permissions</Text>
      <Paper withBorder radius="sm">
        <Table>
          <Table.Tbody>
            {(roles.data ?? []).map((r: any) => (
              <Table.Tr key={r.code}><Table.Td w={140} fw={500}>{r.name}</Table.Td><Table.Td><Text size="xs">{r.permissions.join(", ")}</Text></Table.Td></Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>
      <ManageUser user={edit} roleData={roleData} onClose={() => setEdit(null)} onChanged={refresh} />
      <CreateUser opened={creating} roleData={roleData} onClose={() => setCreating(false)} onChanged={refresh} />
    </>
  );
}

function CreateUser({ opened, roleData, onClose, onChanged }: { opened: boolean; roleData: any[]; onClose: () => void; onChanged: () => void }) {
  const [f, setF] = useState<Record<string, any>>({ roles: [] });
  const [err, setErr] = useState<unknown>(null);
  return (
    <Modal opened={opened} onClose={onClose} title="New user">
      <Stack>
        <TextInput label="Username" value={f.username ?? ""} onChange={(e) => setF({ ...f, username: e.currentTarget.value })} required />
        <TextInput label="Full name" value={f.full_name ?? ""} onChange={(e) => setF({ ...f, full_name: e.currentTarget.value })} required />
        <TextInput label="Email" value={f.email ?? ""} onChange={(e) => setF({ ...f, email: e.currentTarget.value })} />
        <PasswordInput label="Initial password" description="At least 12 characters, mixed case, with a digit" value={f.password ?? ""} onChange={(e) => setF({ ...f, password: e.currentTarget.value })} required />
        <MultiSelect label="Roles" data={roleData} value={f.roles} onChange={(v) => setF({ ...f, roles: v })} />
        <ErrorBox error={err} />
        <Button onClick={async () => {
          try { await api("/api/users", { body: { ...f, email: f.email || null } }); onChanged(); setF({ roles: [] }); setErr(null); onClose(); notifications.show({ message: "User created", color: "mask" }); }
          catch (x) { setErr(x); }
        }}>Create user</Button>
      </Stack>
    </Modal>
  );
}

function ManageUser({ user, roleData, onClose, onChanged }: { user: any; roleData: any[]; onClose: () => void; onChanged: () => void }) {
  const [roles, setRoles] = useState<string[] | null>(null);
  const [reason, setReason] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<unknown>(null);
  if (!user) return null;
  const run = async (fn: () => Promise<any>, msg: string) => {
    setErr(null);
    try { await fn(); onChanged(); notifications.show({ message: msg, color: "mask" }); close(); } catch (x) { setErr(x); }
  };
  const close = () => { setRoles(null); setReason(""); setPw(""); setErr(null); onClose(); };
  return (
    <Modal opened onClose={close} title={`Manage ${user.username}`}>
      <Stack>
        <MultiSelect label="Roles" data={roleData} value={roles ?? user.roles} onChange={setRoles} />
        <Button variant="default" disabled={!roles} onClick={() => run(() => api(`/api/users/${user.id}/roles`, { method: "PUT", body: { roles } }), "Roles updated")}>Save roles</Button>
        <TextInput label="Reason (for activation change or password reset)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
        <Group grow>
          <Button variant="default" color={user.is_active ? "red" : undefined} disabled={reason.trim().length < 3}
            onClick={() => run(() => api(`/api/users/${user.id}/active`, { method: "PUT", body: { is_active: !user.is_active, reason } }), user.is_active ? "User deactivated" : "User activated")}>
            {user.is_active ? "Deactivate" : "Activate"}
          </Button>
        </Group>
        <PasswordInput label="New password" value={pw} onChange={(e) => setPw(e.currentTarget.value)} />
        <Button variant="default" disabled={!pw || reason.trim().length < 3}
          onClick={() => run(() => api(`/api/users/${user.id}/reset-password`, { body: { password: pw, reason } }), "Password reset; the user's sessions were signed out")}>Reset password</Button>
        <ErrorBox error={err} />
      </Stack>
    </Modal>
  );
}
