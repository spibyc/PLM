import { Alert, Anchor, Button, Paper, PasswordInput, Stack, Table, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, Ident, Loading, PageHeader } from "../components/ui";
import { api, qs } from "../lib/api";

export function Search() {
  const [sp] = useSearchParams();
  const q = sp.get("q") ?? "";
  const { data, error, isLoading } = useQuery({ queryKey: ["search", q], queryFn: () => api(`/api/search${qs({ q })}`), enabled: q.length >= 2 });
  return (
    <>
      <PageHeader title="Search" sub={`Results for “${q}”`} />
      <ErrorBox error={error} />
      {isLoading ? <Loading /> : !data?.length ? <Empty>Nothing matches “{q}”. Try a part number, MPN, lot number or location code.</Empty> : (
        <Paper withBorder radius="sm">
          <Table>
            <Table.Tbody>
              {data.map((r: any) => (
                <Table.Tr key={r.type + r.id}>
                  <Table.Td w={100}><Text size="sm" c="dimmed">{r.type}</Text></Table.Td>
                  <Table.Td><Anchor component={Link} to={r.url}><Ident>{r.title}</Ident></Anchor></Table.Td>
                  <Table.Td>{r.subtitle}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
    </>
  );
}

/** Target of QR labels: /scan/location/:code and /scan/lot/:lot_no resolve to the record page. */
export function Scan() {
  const { kind, key } = useParams();
  const nav = useNavigate();
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    const path = kind === "location" ? `/api/locations/by-code/${encodeURIComponent(key!)}` : `/api/lots/by-number/${encodeURIComponent(key!)}`;
    api(path).then((r) => nav(kind === "location" ? `/locations/${r.id}` : `/lots/${r.id}`, { replace: true })).catch(setErr);
  }, [kind, key, nav]);
  return err ? <ErrorBox error={err} /> : <Loading />;
}

export function About() {
  const { data, error } = useQuery({ queryKey: ["version"], queryFn: () => api("/api/version") });
  return (
    <>
      <PageHeader title="About this system" />
      <ErrorBox error={error} />
      {data && (
        <Paper withBorder p="md" radius="sm" maw={720}>
          <dl className="kv">
            <dt>Application</dt><dd>{data.application} {data.version}</dd>
            <dt>Commit</dt><dd className="ident">{data.commit}</dd>
            <dt>Build time</dt><dd>{data.build_time}</dd>
            <dt>Database schema</dt><dd className="ident">{data.schema_revision} (expected {data.expected_schema_revision})</dd>
            <dt>Environment</dt><dd>{data.environment}</dd>
          </dl>
          <Alert mt="md" variant="light" color="gray">
            <Text size="sm">
              PLM supports processes used under ISO 13485. Using it does not make an organisation compliant or certified;
              the organisation must validate the software for its intended use and maintain its own procedures.
            </Text>
          </Alert>
        </Paper>
      )}
    </>
  );
}

export function Account() {
  const [cur, setCur] = useState("");
  const [n1, setN1] = useState("");
  const [n2, setN2] = useState("");
  const [err, setErr] = useState<unknown>(null);
  return (
    <>
      <PageHeader title="Change password" />
      <Paper withBorder p="md" radius="sm" maw={420}>
        <form onSubmit={async (e) => {
          e.preventDefault(); setErr(null);
          if (n1 !== n2) { setErr(new Error("New passwords do not match")); return; }
          try {
            await api("/api/auth/change-password", { body: { current_password: cur, new_password: n1 } });
            notifications.show({ message: "Password changed. Other sessions were signed out.", color: "mask" });
            setCur(""); setN1(""); setN2("");
          } catch (x) { setErr(x); }
        }}>
          <Stack>
            <PasswordInput label="Current password" value={cur} onChange={(e) => setCur(e.currentTarget.value)} required autoComplete="current-password" />
            <PasswordInput label="New password" description="At least 12 characters, mixed case, with a digit" value={n1} onChange={(e) => setN1(e.currentTarget.value)} required autoComplete="new-password" />
            <PasswordInput label="Repeat new password" value={n2} onChange={(e) => setN2(e.currentTarget.value)} required autoComplete="new-password" />
            <ErrorBox error={err} />
            <Button type="submit">Change password</Button>
          </Stack>
        </form>
      </Paper>
    </>
  );
}

export function NotFound() {
  return <Empty>This page does not exist. <Anchor component={Link} to="/">Go to the dashboard</Anchor>.</Empty>;
}
